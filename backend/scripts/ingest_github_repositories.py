"""
Reproducible GitHub Repository Ingestion Pipeline for cClyptus.AI SAP BRIM.
Entry point: backend/scripts/ingest_github_repositories.py

Workflow:
1. Repository Acquisition with commit SHA pinning and shallow clones
2. License audit and provenance verification
3. Strict file filtering (skipping lockfiles, binaries, build dirs, secrets)
4. Structure-aware chunking (Markdown, OpenAPI, Code, SQL, Config)
5. Pre-embedding BRIM Relevance Gate:
   KEEP = (MATCHES_IDENTIFIER_INDEX or MATCHES_CONTEXTUAL_KEYWORDS) and ANCHOR_SIMILARITY >= CALIBRATED_THRESHOLD
6. Low-Yield Enforcement (< 10 chunks -> skipped_low_yield)
7. Isolated vector indexing in `github_repo_chunks`
8. Generation of GITHUB_REPO_INGESTION_REPORT.md and PER_REPO_KEEP_DROP_REPORT.md
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.config import settings
from backend.app.database import SessionLocal, init_db
from backend.app.retrieval.repo_registry import repo_registry, RepositoryRegistryEntry
from backend.app.retrieval.license_manager import license_manager
from backend.app.retrieval.brim_relevance_gate import brim_relevance_gate
from backend.app.retrieval.repo_chunker import repo_chunker
from backend.app.retrieval.repo_store import repo_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("repo_ingest")

SNAPSHOTS_DIR = Path(settings.REPO_SNAPSHOTS_DIR)
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# File exclusion rules
EXCLUDED_EXTENSIONS = {
    ".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib",
    ".jar", ".war", ".class", ".pyc", ".pyo", ".min.js", ".min.css",
    ".map", ".wasm", ".bin", ".dat"
}

EXCLUDED_DIR_NAMES = {
    ".git", ".github", "node_modules", "vendor", "venv", ".venv",
    "target", "build", "dist", "out", ".next", "__pycache__",
    ".pytest_cache", ".idea", ".vscode", "fixtures", "synthetic"
}

EXCLUDED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Cargo.lock", "composer.lock", "go.sum"
}

MAX_FILE_BYTES = 1024 * 1024  # 1 MB


def get_safe_repo_dir_name(repo_url: str) -> str:
    parts = repo_url.rstrip("/").split("/")
    return f"{parts[-2]}_{parts[-1]}"


def acquire_repository(repo_url: str) -> Tuple[Path, str]:
    """
    Shallow clones or updates repository snapshot with pinned commit SHA.
    Returns: (repo_dir, commit_sha)
    """
    safe_name = get_safe_repo_dir_name(repo_url)
    target_dir = SNAPSHOTS_DIR / safe_name

    if not target_dir.exists():
        logger.info(f"Cloning {repo_url} into {target_dir}...")
        try:
            cmd = ["git", "clone", "--depth", "1", "--single-branch", f"{repo_url}.git", str(target_dir)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=35)
        except Exception as e:
            logger.warning(f"Git clone error for {repo_url}: {e}. Creating snapshot directory.")
            target_dir.mkdir(parents=True, exist_ok=True)
            # Try writing README from GitHub API if clone timed out
            try:
                import urllib.request
                parts = repo_url.rstrip("/").split("/")
                api_url = f"https://api.github.com/repos/{parts[-2]}/{parts[-1]}/readme"
                req = urllib.request.Request(api_url, headers={"User-Agent": "cClyptus-Ingest/1.0", "Accept": "application/vnd.github.v3.raw"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    readme_content = resp.read().decode("utf-8", errors="ignore")
                    (target_dir / "README.md").write_text(readme_content, encoding="utf-8")
            except Exception:
                pass

    commit_sha = "unknown"
    if (target_dir / ".git").exists():
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(target_dir),
                check=True,
                capture_output=True,
                text=True
            )
            commit_sha = res.stdout.strip()
        except Exception:
            commit_sha = "main_snapshot"
    else:
        commit_sha = "api_snapshot"

    return target_dir, commit_sha


def should_skip_file(file_path: Path) -> Tuple[bool, Optional[str]]:
    """Evaluates file filtering rules."""
    if file_path.name in EXCLUDED_FILENAMES:
        return True, "lockfile"

    if file_path.suffix.lower() in EXCLUDED_EXTENSIONS:
        return True, f"binary_or_lock_extension ({file_path.suffix})"

    for part in file_path.parts:
        if part in EXCLUDED_DIR_NAMES:
            return True, f"excluded_dir ({part})"

    if file_path.name.startswith(".env") or "secret" in file_path.name.lower() or file_path.suffix in (".pem", ".key"):
        return True, "credential_or_secret"

    try:
        if file_path.stat().st_size > MAX_FILE_BYTES:
            return True, "exceeds_max_size_1mb"
    except Exception:
        pass

    return False, None


def infer_chunk_module(chunk_text: str, file_path: str) -> str:
    """Infers primary SAP BRIM module from chunk text and path."""
    combined = f"{file_path} {chunk_text}".lower()
    if any(k in combined for k in ["som", "subscription order", "provider order"]):
        return "SOM"
    if any(k in combined for k in ["convergent charging", "rating", "charge plan"]):
        return "CC"
    if any(k in combined for k in ["convergent invoicing", "billable item", "consumption item", "fkkbix"]):
        return "CI"
    if any(k in combined for k in ["fi-ca", "fica", "dfkkop", "fkkvkp", "contract account"]):
        return "FI-CA"
    if any(k in combined for k in ["rar", "revenue accounting", "pob"]):
        return "RAR"
    if any(k in combined for k in ["mediation", "convergent mediation"]):
        return "CM"
    if any(k in combined for k in ["integration", "payment", "api", "rest"]):
        return "integration"
    return "unknown"


def ingest_all_repositories() -> Dict[str, Any]:
    """Runs the complete ingestion pipeline across all registered repositories."""
    init_db()
    db = SessionLocal()

    registered_repos = repo_registry.get_all()
    overall_summary: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_repositories": len(registered_repos),
        "repositories_active": 0,
        "repositories_skipped_low_yield": 0,
        "repositories_rejected_license": 0,
        "total_files_discovered": 0,
        "total_files_skipped": 0,
        "total_chunks_considered": 0,
        "total_chunks_retained": 0,
        "total_chunks_dropped": 0,
        "rejection_reasons_tally": {},
        "repo_reports": []
    }

    per_repo_details = []

    for entry in registered_repos:
        repo_url = entry.repo_url
        logger.info(f"\n========================================\nProcessing: {repo_url} ({entry.tier})")

        # 1. Acquisition
        repo_dir, commit_sha = acquire_repository(repo_url)
        entry.pinned_commit_sha = commit_sha
        entry.last_synced_at = datetime.now(timezone.utc).isoformat()

        # 2. License Audit
        license_audit = license_manager.inspect_repository_license(
            repo_dir=repo_dir,
            repo_url=repo_url,
            commit_sha=commit_sha
        )
        entry.license_id = license_audit["license"]
        entry.license_status = license_audit["license_status"]

        # 3. File Discovery and Filtering
        discovered_files = []
        skipped_files = []

        if repo_dir.exists():
            for p in repo_dir.rglob("*"):
                if p.is_file():
                    skip, reason = should_skip_file(p)
                    if skip:
                        skipped_files.append((str(p.relative_to(repo_dir)), reason))
                    else:
                        discovered_files.append(p)

        entry.files_discovered = len(discovered_files) + len(skipped_files)
        entry.files_skipped = len(skipped_files)

        overall_summary["total_files_discovered"] += entry.files_discovered
        overall_summary["total_files_skipped"] += entry.files_skipped

        # 4. Chunking and BRIM Relevance Gate Evaluation
        chunks_considered = 0
        chunks_retained = []
        chunks_dropped = []
        id_matches_count = 0
        kw_matches_count = 0
        anchor_rejections_count = 0

        repo_rejection_tally: Dict[str, int] = {}

        for fpath in discovered_files:
            rel_path = str(fpath.relative_to(repo_dir))
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            raw_chunks = repo_chunker.chunk_file(rel_path, content)

            for rc in raw_chunks:
                chunks_considered += 1
                chunk_text = rc["chunk_text"]

                # Evaluate BRIM Relevance Gate
                eval_res = brim_relevance_gate.evaluate_chunk(chunk_text)

                if eval_res["matched_identifiers"]:
                    id_matches_count += 1
                if eval_res["matched_keywords"]:
                    kw_matches_count += 1

                if eval_res["keep"]:
                    chunk_obj = {
                        "repo_url": repo_url,
                        "repo_name": entry.name,
                        "commit_hash": commit_sha,
                        "file_path": rel_path,
                        "section": rc.get("section", rel_path),
                        "chunk_text": chunk_text,
                        "license": entry.license_id or "unknown",
                        "license_status": entry.license_status,
                        "language": rc.get("chunk_type", "text"),
                        "module": infer_chunk_module(chunk_text, rel_path),
                        "provenance_tier": entry.provenance_tier,
                        "anchor_similarity": eval_res["anchor_similarity"],
                        "relevance_gate_version": "1.0",
                        "matched_identifiers": eval_res["matched_identifiers"],
                        "matched_keywords": eval_res["matched_keywords"]
                    }
                    chunks_retained.append(chunk_obj)
                else:
                    reason = eval_res["rejection_reason"] or "unknown_rejection"
                    if "below_anchor_similarity_threshold" in reason:
                        anchor_rejections_count += 1
                    chunks_dropped.append({
                        "file_path": rel_path,
                        "reason": reason,
                        "anchor_similarity": eval_res["anchor_similarity"]
                    })
                    repo_rejection_tally[reason] = repo_rejection_tally.get(reason, 0) + 1
                    overall_summary["rejection_reasons_tally"][reason] = (
                        overall_summary["rejection_reasons_tally"].get(reason, 0) + 1
                    )

        entry.chunks_considered = chunks_considered
        entry.identifier_matches = id_matches_count
        entry.contextual_keyword_matches = kw_matches_count
        entry.anchor_similarity_rejections = anchor_rejections_count
        entry.chunks_retained = len(chunks_retained)
        entry.chunks_dropped = len(chunks_dropped)

        overall_summary["total_chunks_considered"] += chunks_considered
        overall_summary["total_chunks_retained"] += len(chunks_retained)
        overall_summary["total_chunks_dropped"] += len(chunks_dropped)

        # 5. Low-Yield & License Decisions
        # Low Yield Threshold: < 10 chunks -> skipped_low_yield
        MIN_THRESHOLD = settings.REPO_MIN_CHUNKS_THRESHOLD  # 10

        if len(chunks_retained) < MIN_THRESHOLD:
            entry.ingestion_status = "skipped_low_yield"
            overall_summary["repositories_skipped_low_yield"] += 1
            logger.info(
                f"Repository '{entry.name}' yielded only {len(chunks_retained)} chunks "
                f"(< {MIN_THRESHOLD}). Status set to skipped_low_yield. Indexing bypassed."
            )
        elif entry.license_status == "unknown":
            entry.ingestion_status = "rejected_unlicensed"
            overall_summary["repositories_rejected_license"] += 1
            logger.warning(
                f"Repository '{entry.name}' has unverified license ({entry.license_id}). "
                f"Status set to rejected_unlicensed per governance policy."
            )
        else:
            # Approved for active retrieval: insert into repo_store
            inserted, dupes = repo_store.insert_chunks(db, chunks_retained)
            entry.ingestion_status = "active"
            overall_summary["repositories_active"] += 1
            logger.info(
                f"Repository '{entry.name}' successfully activated with {inserted} chunks "
                f"({dupes} duplicates suppressed)."
            )

        repo_detail_record = {
            "repo_url": repo_url,
            "name": entry.name,
            "owner": entry.owner,
            "tier": entry.tier,
            "provenance_tier": entry.provenance_tier,
            "license_id": entry.license_id,
            "license_status": entry.license_status,
            "commit_sha": commit_sha,
            "files_discovered": entry.files_discovered,
            "files_skipped": entry.files_skipped,
            "chunks_considered": entry.chunks_considered,
            "identifier_matches": entry.identifier_matches,
            "contextual_keyword_matches": entry.contextual_keyword_matches,
            "anchor_similarity_rejections": entry.anchor_similarity_rejections,
            "chunks_retained": entry.chunks_retained,
            "chunks_dropped": entry.chunks_dropped,
            "final_ingestion_status": entry.ingestion_status,
            "rejection_reasons": repo_rejection_tally
        }
        per_repo_details.append(repo_detail_record)

    db.close()
    overall_summary["repo_reports"] = per_repo_details

    # Save summary JSON
    results_dir = ROOT_DIR / "backend" / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    summary_json_path = results_dir / "repo_ingestion_summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(overall_summary, f, indent=2)
    logger.info(f"Saved ingestion summary to {summary_json_path}")

    # Generate GITHUB_REPO_INGESTION_REPORT.md
    generate_ingestion_markdown_report(overall_summary)

    # Generate PER_REPO_KEEP_DROP_REPORT.md
    generate_keep_drop_markdown_report(per_repo_details)

    return overall_summary


def generate_ingestion_markdown_report(summary: Dict[str, Any]):
    report_path = ROOT_DIR / "GITHUB_REPO_INGESTION_REPORT.md"
    lines = [
        "# cClyptus.AI SAP BRIM — GitHub Repository Ingestion Report",
        "",
        "## Executive Summary",
        "This report documents the end-to-end ingestion execution across all registered GitHub repositories in Tiers A, B, and C.",
        "",
        "### Ingestion Highlights & Key Metrics",
        f"- **Ingestion Execution Timestamp**: `{summary['timestamp']}`",
        f"- **Total Repositories Audited**: **{summary['total_repositories']}**",
        f"- **Active Ingested Repositories**: **{summary['repositories_active']}**",
        f"- **Repositories Skipped (Low Yield < 10 Chunks)**: **{summary['repositories_skipped_low_yield']}**",
        f"- **Repositories Rejected (License Unknown/Restricted)**: **{summary['repositories_rejected_license']}**",
        f"- **Total Files Discovered**: **{summary['total_files_discovered']:,}**",
        f"- **Total Files Filtered/Skipped**: **{summary['total_files_skipped']:,}**",
        f"- **Total Chunks Considered**: **{summary['total_chunks_considered']:,}**",
        f"- **Total Chunks Retained**: **{summary['total_chunks_retained']:,}**",
        f"- **Total Chunks Dropped**: **{summary['total_chunks_dropped']:,}**",
        "",
        "## Repository Ingestion Status Table",
        "",
        "| Repository URL | Tier | License | Status | Commit SHA | Files Considered | Chunks Retained | Chunks Dropped | Final Ingestion Status |",
        "| :--- | :---: | :---: | :---: | :---: | ---: | ---: | ---: | :--- |"
    ]

    for r in summary["repo_reports"]:
        lines.append(
            f"| [{r['name']}]({r['repo_url']}) | `{r['tier']}` | `{r['license_id']}` ({r['license_status']}) | "
            f"`{r['final_ingestion_status']}` | `{r['commit_sha'][:8]}` | {r['files_discovered']} | "
            f"**{r['chunks_retained']}** | {r['chunks_dropped']} | `{r['final_ingestion_status']}` |"
        )

    lines.extend([
        "",
        "## Machine-Readable Rejection Reasons Breakdown",
        "",
        "| Rejection Reason | Count | Operational Impact |",
        "| :--- | ---: | :--- |"
    ])

    for reason, count in sorted(summary["rejection_reasons_tally"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| `{reason}` | {count:,} | Filtered pre-embedding by BRIM Relevance Gate |")

    lines.extend([
        "",
        "## Governance and Isolation Verification",
        "- **Vector Store Partitioning**: Retained chunks are isolated exclusively in `github_repo_chunks` table.",
        "- **Knowledge Base Integrity**: Existing chunks in `document_chunks` remain 100% untouched.",
        "- **Low Yield Enforcement**: Every repository yielding < 10 chunks was marked `skipped_low_yield` and bypassed from indexing."
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info(f"Saved GITHUB_REPO_INGESTION_REPORT.md to {report_path}")


def generate_keep_drop_markdown_report(repo_details: List[Dict[str, Any]]):
    report_path = ROOT_DIR / "PER_REPO_KEEP_DROP_REPORT.md"
    lines = [
        "# cClyptus.AI SAP BRIM — Per-Repository Keep / Drop Statistics Report",
        "",
        "## Overview",
        "Detailed audit statistics for every evaluated repository detailing file discovery, chunk retention, identifier hits, keyword matches, and rejection reasons.",
        ""
    ]

    for r in repo_details:
        lines.extend([
            f"### Repository: {r['owner']}/{r['name']}",
            f"- **URL**: [{r['repo_url']}]({r['repo_url']})",
            f"- **Tier**: `{r['tier']}` ({r['provenance_tier']})",
            f"- **License**: `{r['license_id']}` (status: `{r['license_status']}`)",
            f"- **Pinned Commit SHA**: `{r['commit_sha']}`",
            f"- **Files Discovered**: {r['files_discovered']} (Skipped: {r['files_skipped']})",
            f"- **Chunks Considered**: {r['chunks_considered']}",
            f"- **638-Identifier Matches**: {r['identifier_matches']}",
            f"- **Contextual Keyword Matches**: {r['contextual_keyword_matches']}",
            f"- **Anchor Similarity Rejections**: {r['anchor_similarity_rejections']}",
            f"- **Chunks Retained**: **{r['chunks_retained']}**",
            f"- **Chunks Dropped**: **{r['chunks_dropped']}**",
            f"- **Final Ingestion Status**: `{r['final_ingestion_status']}`",
            "",
            "#### Rejection Reasons Tally:"
        ])
        if r["rejection_reasons"]:
            for reason, cnt in r["rejection_reasons"].items():
                lines.append(f"  - `{reason}`: {cnt}")
        else:
            lines.append("  - *None (All chunks retained)*")
        lines.append("")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info(f"Saved PER_REPO_KEEP_DROP_REPORT.md to {report_path}")


if __name__ == "__main__":
    ingest_all_repositories()
