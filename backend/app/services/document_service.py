import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
import pymupdf


class DocumentService:
    # Curated metadata lookup for known SAP publications
    SAP_DOC_METADATA = {
        "pdfdownload.pdf": {
            "title": "SAP S/4HANA Subscription Order Management (SOM) Guide",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM"
        },
        "SAP CC.pdf": {
            "title": "SAP Convergent Charging (CC) Implementation Guide",
            "module": "CC / BRIM",
            "product": "SAP Convergent Charging"
        },
        "SAP CI1.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 1)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing"
        },
        "SAP CI2.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 2)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing"
        },
        "SAP CI3.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 3)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing"
        },
        "SAP CI4.pdf": {
            "title": "SAP Cloud Integration & Convergent Invoicing Guide (Part 4)",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing"
        },
        "SAP FI-CA.pdf": {
            "title": "SAP Contract Accounts Receivable and Payable (FI-CA) Guide",
            "module": "FI-CA / BRIM",
            "product": "SAP FI-CA"
        },
        "2020_S4H_BRIM_SOM_Device_as_a_Service.pdf": {
            "title": "SAP S/4HANA BRIM SOM: Device as a Service (DaaS) Architecture",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM"
        },
        "Authorizations-in-S4-HANA-and-Fiori.pdf": {
            "title": "Authorizations and Security Architecture in SAP S/4HANA and Fiori",
            "module": "Security / Basis / Fiori",
            "product": "SAP S/4HANA"
        },
        "Billing_and_Revenue_Innovation_Management.pdf": {
            "title": "SAP Billing and Revenue Innovation Management (BRIM) Solution Overview",
            "module": "BRIM Architecture",
            "product": "SAP BRIM"
        },
        "BR234_EN_SOM 2.pdf": {
            "title": "BR234: SAP S/4HANA Subscription Order Management (SOM) Course Handbook",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM"
        },
        "BRIM Q Bank.pdf": {
            "title": "SAP BRIM Certification and Technical Interview Question Bank",
            "module": "BRIM Architecture",
            "product": "SAP BRIM"
        },
        "BRIM_AC240_EN_Col16.pdf": {
            "title": "AC240: SAP BRIM Solution Overview & End-to-End Integration Handbook",
            "module": "BRIM Core",
            "product": "SAP BRIM"
        },
        "Budget billing.pdf": {
            "title": "SAP FI-CA & BRIM Budget Billing Plan Configuration Guide",
            "module": "FI-CA / BRIM",
            "product": "SAP FI-CA"
        },
        "E_Book_ABAP_RESTful_Programming_Model_2020_Rel_NW_wwwERPExamsCom.pdf": {
            "title": "ABAP RESTful Application Programming Model (RAP) Reference Guide",
            "module": "ABAP RAP / Development",
            "product": "SAP S/4HANA & BTP"
        },
        "RAR Contract Reversal Process.pdf": {
            "title": "SAP Revenue Accounting and Reporting (RAR) Contract Reversal Process",
            "module": "RAR / Revenue Accounting",
            "product": "SAP S/4HANA RAR"
        },
        "SAP BRIM Press Book 2nd Edition - Expertsoft.pdf": {
            "title": "SAP Press: SAP Billing and Revenue Innovation Management (2nd Edition)",
            "module": "BRIM End-to-End",
            "product": "SAP BRIM"
        },
        "SAP Revenue Recognition (RAR) Processing Flow, Exemptions, Reversals & System Integration.pdf": {
            "title": "SAP RAR Revenue Recognition Processing Flow, Exemptions, & System Integration",
            "module": "RAR / Revenue Accounting",
            "product": "SAP S/4HANA RAR"
        },
        "SAP-PRESS-Catalog-Shop.pdf": {
            "title": "SAP Press Technical & Architecture Publication Catalog",
            "module": "SAP Reference",
            "product": "SAP Ecosystem"
        },
        "SIMPL_OP1709.pdf": {
            "title": "Simplification List for SAP S/4HANA Enterprise Management",
            "module": "S/4HANA Transition",
            "product": "SAP S/4HANA"
        },
        "mg.pdf": {
            "title": "SAP BRIM Master Guide: Solution Landscapes & Implementation Strategy",
            "module": "BRIM Architecture",
            "product": "SAP BRIM"
        },
        "SAP_BRIM_CC_Convergent_Charging_Advanced_Architecture.pdf": {
            "title": "SAP Convergent Charging (CC) Advanced Architecture & Implementation Guide",
            "module": "CC / BRIM",
            "product": "SAP Convergent Charging"
        },
        "SAP_BRIM_FICA_Contract_Accounts_Master_Handbook.pdf": {
            "title": "SAP Contract Accounts Receivable and Payable (FI-CA) Master Configuration & Architecture Guide",
            "module": "FI-CA / BRIM",
            "product": "SAP FI-CA"
        },
        "SAP_BRIM_Convergent_Invoicing_CIT_BIT_Master_Architecture.pdf": {
            "title": "SAP Convergent Invoicing (CI) Consumption & Billable Item Management Master Guide",
            "module": "CI / BRIM",
            "product": "SAP Convergent Invoicing"
        },
        "SAP_BRIM_SOM_Subscription_Order_Management_Master_Guide.pdf": {
            "title": "SAP Subscription Order Management (SOM) Master Configuration & Order Distribution Guide",
            "module": "SOM / BRIM",
            "product": "SAP S/4HANA BRIM"
        },
        "SAP_BRIM_End_to_End_Integration_and_SPRO_Cookbook.pdf": {
            "title": "SAP BRIM End-to-End Integration, SPRO Customizing Cookbook & War-Room Guide",
            "module": "BRIM End-to-End",
            "product": "SAP BRIM"
        }
    }

    @staticmethod
    def get_document_info(filename: str, sample_text: str = "") -> Dict[str, str]:
        """
        Dynamically derives title, module, and product from lookup or content heuristics.
        """
        if filename in DocumentService.SAP_DOC_METADATA:
            return DocumentService.SAP_DOC_METADATA[filename]

        lower_fn = filename.lower()
        lower_txt = sample_text[:1000].lower() if sample_text else ""
        combined = f"{lower_fn} {lower_txt}"

        module = "General SAP"
        product = "SAP ERP"

        if "som" in combined or "subscription" in combined:
            module = "SOM / BRIM"
            product = "SAP S/4HANA BRIM"
        elif "fi-ca" in combined or "fica" in combined or "contract accounts" in combined:
            module = "FI-CA / BRIM"
            product = "SAP FI-CA"
        elif "convergent charging" in combined or " cc " in combined:
            module = "CC / BRIM"
            product = "SAP Convergent Charging"
        elif "convergent invoicing" in combined or " ci " in combined:
            module = "CI / BRIM"
            product = "SAP Convergent Invoicing"
        elif "rar" in combined or "revenue accounting" in combined:
            module = "RAR / Revenue Accounting"
            product = "SAP S/4HANA RAR"
        elif "brim" in combined or "billing and revenue" in combined:
            module = "BRIM Architecture"
            product = "SAP BRIM"
        elif "fiori" in combined or "authorization" in combined or "security" in combined:
            module = "Security / Fiori"
            product = "SAP S/4HANA"
        elif "abap" in combined or "rap" in combined:
            module = "ABAP RAP"
            product = "SAP S/4HANA & BTP"
        elif "s/4" in combined or "s4hana" in combined:
            module = "S/4HANA Core"
            product = "SAP S/4HANA"

        clean_title = re.sub(r"[\-_]+", " ", Path(filename).stem).strip()
        clean_title = re.sub(r"\s+", " ", clean_title).title()

        return {
            "title": clean_title,
            "module": module,
            "product": product
        }

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Computes SHA-256 hash for strict idempotency."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        # Filter private-use unicode glyphs and replacement chars
        text = re.sub(r"[\ue000-\uf8ff\ufffd]", " ", text)
        # Remove repetitive SAP Help Portal headers & footers without dropping technical content
        text = re.sub(r"Warning\s+This document has been generated from SAP Help Portal[^\n]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"Original content:\s*https?://help\.sap\.com[^\n]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"Generated on:\s*\d{4}-\d{2}-\d{2}[^\n]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"(?i)\bPage\s+\d+(\s+of\s+\d+)?\b", "", text)
        text = re.sub(r"(?i)SAP S/4HANA\s*\|\s*\d{4}[^\n]*", "", text)
        # Normalize newlines and excess whitespace
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def extract_pdf_pages(file_path: Path) -> List[Dict[str, Any]]:
        """
        Extracts text and section structure from each page using PyMuPDF.
        Tracks active chapter and section hierarchy across pages.
        """
        pages_data = []
        doc = pymupdf.open(str(file_path))
        active_section = "Overview"
        active_subsection = ""

        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_number = page_idx + 1
                raw_text = page.get_text("text") or ""
                cleaned_text = DocumentService.clean_text(raw_text)

                headings = []
                lines = [l.strip() for l in cleaned_text.split("\n") if l.strip()]
                for line in lines:
                    # Match numbered sections (e.g. "1.1 Flexible Billing", "Chapter 2", "Section 3.4")
                    # or uppercase short topic titles
                    if (
                        re.match(r"^(?:(?:Section|Chapter)\s+\d+(?:\.\d+)*|\d+(?:\.\d+)+\s+[A-Z0-9].*|\d+\s+[A-Z][A-Za-z0-9\s\-_/:]{3,50})$", line)
                        and len(line) < 70
                    ):
                        headings.append(line)
                    elif len(line) < 45 and line.isupper() and not line.startswith("PAGE"):
                        headings.append(line.title())

                if headings:
                    active_section = headings[0]
                    if len(headings) > 1:
                        active_subsection = headings[1]
                    else:
                        active_subsection = ""

                pages_data.append({
                    "page_number": page_number,
                    "text": cleaned_text,
                    "headings": headings,
                    "active_section": active_section,
                    "active_subsection": active_subsection
                })
        finally:
            doc.close()

        return pages_data

    @staticmethod
    def extract_text_file(file_path: Path) -> List[Dict[str, Any]]:
        """
        Extracts markdown or text files, segmenting by header boundaries (# or ##)
        as pseudo-pages to preserve structure.
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()

        cleaned = DocumentService.clean_text(raw_text)
        if not cleaned:
            return []

        # Split on markdown H1/H2 boundaries (# or ##)
        sections = re.split(r"\n(?=#{1,2}\s+)", cleaned)
        pages_data = []

        for idx, sec in enumerate(sections, start=1):
            sec_clean = sec.strip()
            if not sec_clean:
                continue

            # Detect heading
            first_line = sec_clean.split("\n")[0].strip("# ").strip()
            heading = first_line if first_line and len(first_line) < 80 else f"Section {idx}"

            pages_data.append({
                "page_number": idx,
                "text": sec_clean,
                "headings": [heading],
                "active_section": heading,
                "active_subsection": ""
            })

        return pages_data

    @staticmethod
    def extract_document_pages(file_path: Path) -> List[Dict[str, Any]]:
        """Universal document extractor supporting PDF, Markdown, and text formats."""
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return DocumentService.extract_pdf_pages(file_path)
        elif suffix in [".txt", ".md", ".markdown"]:
            return DocumentService.extract_text_file(file_path)
        else:
            # Fallback for plain text readable formats
            try:
                return DocumentService.extract_text_file(file_path)
            except Exception:
                return []

    @staticmethod
    def _detect_chunk_type(text: str) -> str:
        """Determines the semantic archetype of the chunk."""
        if re.search(r"(?:Step\s+\d+|\bProcedure\b|\bPrerequisites\b|\bHow\s+to\b|\n\s*\d+\.\s+[A-Z])", text, re.IGNORECASE):
            return "procedure"
        if re.search(r"(?:\|.*\|.*\||\bTable\s+\d+|\bField\s+Name\b.*\bDescription\b)", text, re.IGNORECASE):
            return "table"
        if re.search(r"(?:\bOverview\b|\bIntroduction\b|\bArchitecture\b|\bSummary\b)", text, re.IGNORECASE):
            return "overview"
        return "concept"

    @staticmethod
    def chunk_page_text(
        text: str,
        page_number: int,
        document_name: str,
        active_section: str,
        active_subsection: str = "",
        target_chunk_size: int = 1200,
        chunk_overlap: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Structure-aware hierarchical chunker designed for SAP enterprise documentation:
        - Targets 1,000-1,400 chars.
        - Preserves procedure integrity (Title, Prerequisites, Steps 1..N, Result).
        - Preserves tables and structured data.
        - Splits on logical paragraph/procedure breaks rather than cutting sentences.
        """
        if not text or len(text.strip()) < 30:
            return []

        cleaned = text.strip()
        doc_info = DocumentService.get_document_info(document_name, sample_text=cleaned)

        # Detect structural features
        chunk_type = DocumentService._detect_chunk_type(cleaned)
        has_procedure = (chunk_type == "procedure")
        has_table = (chunk_type == "table")

        # If page text is within standard chunk size range, keep as a single unified chunk
        if len(cleaned) <= target_chunk_size + 350:
            return [{
                "chunk_index": 0,
                "page_number": page_number,
                "document_name": document_name,
                "section": active_section,
                "subsection": active_subsection,
                "chunk_text": cleaned,
                "chunk_type": chunk_type,
                "metadata": {
                    "document_title": doc_info["title"],
                    "filename": document_name,
                    "page_number": page_number,
                    "section": active_section,
                    "subsection": active_subsection,
                    "chunk_type": chunk_type,
                    "product": doc_info["product"],
                    "module": doc_info["module"],
                    "source": "knowledge_base",
                    "char_length": len(cleaned),
                    "has_procedure": has_procedure,
                    "has_table": has_table
                }
            }]

        chunks = []
        start = 0
        text_length = len(cleaned)
        chunk_idx = 0

        while start < text_length:
            end = min(start + target_chunk_size, text_length)

            # If not at the end of the text, seek a clean logical boundary
            if end < text_length:
                # 1. Paragraph boundary
                p_break = cleaned.rfind("\n\n", start + 300, end)
                if p_break != -1:
                    end = p_break
                else:
                    # 2. Numbered step boundary (e.g. "\n1. ", "\n2. ", "\nStep ")
                    step_match = None
                    for m in re.finditer(r"\n(?:\d+\.|\-|\*|Step\s+\d+:?)\s+", cleaned[start + 300 : end]):
                        step_match = start + 300 + m.start()
                    if step_match:
                        end = step_match
                    else:
                        # 3. Sentence boundary (". ", ".\n")
                        sent_break = max(
                            cleaned.rfind(". ", start + 300, end),
                            cleaned.rfind(".\n", start + 300, end)
                        )
                        if sent_break != -1:
                            end = sent_break + 1
                        else:
                            # 4. Line break
                            line_break = cleaned.rfind("\n", start + 300, end)
                            if line_break != -1:
                                end = line_break

            chunk_content = cleaned[start:end].strip()
            if len(chunk_content) >= 60:
                seg_type = DocumentService._detect_chunk_type(chunk_content)
                chunks.append({
                    "chunk_index": chunk_idx,
                    "page_number": page_number,
                    "document_name": document_name,
                    "section": active_section,
                    "subsection": active_subsection,
                    "chunk_text": chunk_content,
                    "chunk_type": seg_type,
                    "metadata": {
                        "document_title": doc_info["title"],
                        "filename": document_name,
                        "page_number": page_number,
                        "section": active_section,
                        "subsection": active_subsection,
                        "chunk_type": seg_type,
                        "product": doc_info["product"],
                        "module": doc_info["module"],
                        "source": "knowledge_base",
                        "char_length": len(chunk_content),
                        "has_procedure": (seg_type == "procedure"),
                        "has_table": (seg_type == "table")
                    }
                })
                chunk_idx += 1

            if end >= text_length:
                break
            start = max(end - chunk_overlap, start + 100)

        return chunks


document_service = DocumentService()
