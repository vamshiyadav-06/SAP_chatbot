import re
from typing import Dict, Any, List, Optional

# Whole words only: substrings misroute "issued", "prefix", "unfixed" to troubleshooting.
TROUBLESHOOTING_PATTERN = re.compile(
    r"\b(?:errors?|fail(?:s|ed|ing|ures?)?|dumps?|troubleshoot\w*|issues?|stuck|exceptions?|cannot|can't"
    r"|fix(?:es)?|not\s+working)\b",
    re.I,
)

class AnswerPlanner:
    """
    Question-Aware Answer Planning Service for SAP BRIM Knowledge Assistant.
    
    Identifies the technical inquiry type and dictates evidence-grounded structural guidelines:
    1. Conceptual questions (definition, purpose, role in BRIM, relationships, examples, limitations)
    2. Configuration questions (prerequisites, verified SPRO path, documented steps, validation)
    3. T-code and table lookups (exact identifier, usage, key fields, prerequisites)
    4. Troubleshooting questions (symptom, root causes, diagnostic checks, resolution, validation)
    5. Integration & process-flow questions (components, sequence, exchanged objects e.g. BITs/CITs, failure points)
    6. Comparison questions (direct answer, comparison table, differences/similarities, implications)
    7. Scenario-based technical questions (practical solution, architectural impact)
    8. Follow-up questions (resolved conversational reference, focused direct answer)
    9. Version-specific questions (ECC vs S/4HANA release differences)
    10. Insufficient evidence (explicit boundary, verified vs missing)
    """

    @staticmethod
    def plan_answer(query: str, is_follow_up: bool = False) -> Dict[str, Any]:
        q_lower = query.lower()

        # 1. Complex Production Incident / Multi-Discrepancy Scenario Analysis
        is_upgrade_or_release = any(term in q_lower for term in [
            "upgrade", "support package", "sp upgrade", "release change", "old vs new",
            "old versus new", "migration difference", "release comparison", "ecc to s/4"
        ])
        is_reconciliation = any(term in q_lower for term in [
            "reconcil", "discrepancy", "variance", "mismatch", "billing difference",
            "invoice difference", "differ in invoice", "invoice amount", "reconciliation matrix"
        ])
        is_billing_or_invoice = any(term in q_lower for term in [
            "invoice", "invoicing", "billing", "billable item", "rating", "charge",
            "fi-ca", "fica", "subledger", "tax", "rounding"
        ])
        is_solution_design = bool(re.search(
            r"\bhow\s+would\s+you\s+design\s+(?:and\s+implement\s+)?(?:an\s+)?end-to-end\s+sap\s+brim\s+solution\b",
            query, re.I
        ))
        is_production_incident = (
            any(term in q_lower for term in [
                "production incident", "month-end", "month end", "production failure",
                "production issue", "posting discrepancies", "duplicate financial",
                "duplicated financial", "recover missing", "prevent duplicate",
                "investigate the discrepancies", "reconciliation and duplicate"
            ])
            or (
                ("missing" in q_lower or "discrepanc" in q_lower or "duplicate" in q_lower)
                and ("recover" in q_lower or "investigat" in q_lower or "safely" in q_lower)
                and ("convergent" in q_lower or "fi-ca" in q_lower or "brim" in q_lower or "charging" in q_lower)
            )
        ) and not is_upgrade_or_release and not is_solution_design

        if is_production_incident:
            return {
                "question_type": "production_incident",
                "title": "Senior SAP BRIM Production Incident Resolution & Scenario Analysis",
                "instructions": (
                    "MANDATORY SENIOR ARCHITECT STRUCTURE (SAP BRIM Production Incident & Scenario Resolution):\n"
                    "Structure your response using the following comprehensive 10-section framework:\n\n"
                    "### 1. Executive Summary\n"
                    "- Explain the problem, the core architectural assessment, and the recommended approach.\n"
                    "- State clearly what is known from evidence and what remains uncertain.\n\n"
                    "### 2. Problem Analysis\n"
                    "- Break the scenario into individual symptoms (e.g. missing billable items, posting discrepancies, duplicate records).\n"
                    "- Identify all affected SAP BRIM components (e.g. CC, CI, FI-CA).\n"
                    "- Explain the relationships between the symptoms without assuming an unverified common cause.\n\n"
                    "### 3. Evidence and Findings\n"
                    "- Present relevant technical information retrieved from the knowledge base and official documentation.\n"
                    "- Reference source documents, page numbers, or sections where available.\n"
                    "- Distinguish documented facts, observed evidence, and hypotheses.\n\n"
                    "### 4. Root-Cause Analysis\n"
                    "- Explain plausible root causes for each identified symptom category.\n"
                    "- Describe the evidence needed to confirm or eliminate each cause.\n"
                    "- Never present an unverified hypothesis as a confirmed root cause.\n\n"
                    "### 5. Step-by-Step Investigation\n"
                    "- Explain the investigation sequence in priority order.\n"
                    "- Identify relevant transaction codes, logs, status monitors, reconciliation checks, and interfaces where supported by documentation.\n"
                    "- Explain the specific purpose and diagnostic value of each step.\n\n"
                    "### 6. Corrective and Recovery Actions\n"
                    "- Describe the appropriate corrective actions for each confirmed failure category.\n"
                    "- Explain prerequisites, dependencies, operational risks, and validation requirements.\n"
                    "- Avoid recommending potentially destructive actions without sufficient evidence.\n\n"
                    "### 7. Duplicate Prevention and Financial Integrity\n"
                    "- Explain how to verify processing status before initiating any reprocessing or retry.\n"
                    "- Include reconciliation and duplicate-prevention checks when relevant.\n"
                    "- Distinguish missing transactions, delayed processing, failed processing, and duplicate transactions.\n\n"
                    "### 8. Validation and Reconciliation\n"
                    "- Explain how to confirm that the issue is fully resolved across all components.\n"
                    "- Include relevant counts, monetary totals, status checks, and financial reconciliation between CC, CI, and FI-CA.\n\n"
                    "### 9. Risks and Limitations\n"
                    "- Identify unresolved questions, operational risks, and system assumptions.\n"
                    "- Clearly state when the available documentation does not establish a specific procedure or parameter.\n\n"
                    "### 10. Final Recommendations\n"
                    "- Summarize the immediate next steps in prioritized order.\n"
                    "- Provide useful, targeted follow-up questions to clarify any remaining implementation details.\n"
                    "CRITICAL: Ground all technical statements strictly in retrieved evidence. Never fabricate SAP transaction codes, tables, or procedures."
                )
            }

        # 2. Senior SAP BRIM Upgrade, Invoice Reconciliation & Billing Discrepancy Analysis
        if (is_reconciliation and is_billing_or_invoice) or (is_upgrade_or_release and (is_billing_or_invoice or is_reconciliation)):
            return {
                "question_type": "upgrade_invoice_reconciliation",
                "title": "Senior SAP BRIM Upgrade & Invoice Reconciliation Diagnostic Analysis",
                "instructions": (
                    "MANDATORY SENIOR ARCHITECT STRUCTURE (SAP BRIM Upgrade & Invoice Reconciliation):\n"
                    "You must structure your response with the following exact primary sections:\n\n"
                    "### 1. Executive Summary\n"
                    "- State the core finding, suspected stage of divergence, and high-level architectural assessment.\n\n"
                    "### 2. Symptom Classification\n"
                    "- Establish the exact symptom: identify whether the discrepancy originates in:\n"
                    "  [a] Usage Volume / Mediation Ingestion (CDR loss, unconsumed CITs)\n"
                    "  [b] Rating (SAP CC charge plans, pricing logic tree, allowance exhaustion, BART rate tables)\n"
                    "  [c] Billable Items (CI BIT generation, BIT class mapping, status 0 Raw vs status 2 Billable in DFKKBIXBIT*)\n"
                    "  [d] Invoicing Aggregation (CI billing doc aggregation, grouping variants, invoicing locks)\n"
                    "  [e] Tax Calculation (external tax interface vs FI-CA internal tax procedure)\n"
                    "  [f] Rounding & Currency Differences (unit price precision, rounding rules per currency)\n"
                    "  [g] FI-CA Subledger Posting (reconciliation key, GL account assignment, clearing variants, DFKKKO/DFKKOP)\n\n"
                    "### 3. Stage-by-Stage Reconciliation Matrix\n"
                    "- Construct a Markdown reconciliation matrix comparing record counts and monetary totals across documented processing stages:\n"
                    "  | Processing Stage | Source Component | Input Records | Output Records | Input Total Amount | Output Total Amount | Variance / Check |\n"
                    "  | Consumption Items (CIT) | Convergent Mediation | ... | ... | ... | ... | ... |\n"
                    "  | Rating / Charged Items | Convergent Charging (CC) | ... | ... | ... | ... | ... |\n"
                    "  | Billable Items (Raw BITs) | Convergent Invoicing (CI) | ... | ... | ... | ... | ... |\n"
                    "  | Billable Items (Billable) | Convergent Invoicing (CI) | ... | ... | ... | ... | ... |\n"
                    "  | Billing Documents | Convergent Invoicing (CI) | ... | ... | ... | ... | ... |\n"
                    "  | Invoicing Documents | Convergent Invoicing (CI) | ... | ... | ... | ... | ... |\n"
                    "  | FI-CA Open Items | FI-CA Subledger | ... | ... | ... | ... | ... |\n\n"
                    "### 4. Release and Configuration Comparison\n"
                    "- Recommend controlled old-versus-new release testing with identical inputs and equivalent master data, configuration, effective dates, currencies, tax conditions, and processing parameters.\n"
                    "- Compare individual business records using stable identifiers (e.g. BIT numbers, CIT IDs, Invoicing Document numbers, Contract Account VKONT), NOT ONLY aggregate totals. Detect missing records, duplicates, changed quantities, changed prices, rounding differences, and offsetting discrepancies.\n"
                    "- Investigate SAP release changes, Support Packages, relevant SAP Notes/corrections, transports, configuration drift, master-data differences, and custom enhancements/BAdIs.\n\n"
                    "### 5. Root-Cause Decision Tree\n"
                    "- Provide diagnostic decision logic branching across SOM, CC, CI, FI-CA, Tax, and Rounding.\n"
                    "- Data Model Safeguard: Do NOT assume VBRK/VBRP (classical SD billing) or any /BIC/* (BW object) is the correct source for CI or FI-CA processes. Verify the document flow and relevant BRIM data models (DFKKBIXBIT*, DFKKBILLDOC*, DFKKINVDOC*, DFKKKO/DFKKOP) first.\n\n"
                    "### 6. Safe Validation and Remediation\n"
                    "- Recommend replaying production inputs ONLY in a controlled test environment with duplicate-processing and financial-side-effect safeguards (e.g. reconciliation key isolation, dummy payment execution, suppressed correspondence).\n"
                    "- Documented remediation actions: BIT reversal/adjustment, invoicing document reversal, correction billing runs, and reprocessing.\n\n"
                    "### 7. Evidence-Based Conclusion\n"
                    "- Explicitly categorize all findings into:\n"
                    "  * [Verified SAP-Standard Functionality]\n"
                    "  * [Customer-Specific Configuration or Custom Implementation]\n"
                    "  * [General Testing Recommendations]\n"
                    "  * [Hypotheses That Still Require Verification]\n"
                    "- Cite precise source documents, page numbers, sections, or retrieved passages supporting each technical claim. If evidence is unavailable for a specific sub-process, explicitly state the limitation.\n"
                    "CRITICAL: Never invent or assume SAP table names, transaction codes, item categories, APIs, report names, or configuration paths."
                )
            }

        # 2. Blocks, locks and restrictions (BP, customer, supplier, org-level, FI-CA)
        from backend.app.services.restriction_scope_classifier import restriction_scope_classifier
        scope = restriction_scope_classifier.classify(query)
        if scope.is_restriction_query:
            return {
                "question_type": "restriction_block",
                "title": "Block / Restriction Diagnosis",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Block or Restriction):\n"
                    "1. Direct answer: state whether the evidence identifies ONE block type or several possible ones.\n"
                    "2. Block-type scope: for each block type the evidence covers, give the business object, role and "
                    "organizational level it applies to, and what the cited passage establishes (cite [E#]).\n"
                    "3. Where it can be viewed: only locations documented in a cited passage, per block type.\n"
                    "4. How it is removed or changed: only procedures a cited passage documents for that exact block type. "
                    "If none is documented, say the removal procedure is not established by the evidence. Never suggest "
                    "direct table edits.\n"
                    "5. Unresolved points and one targeted clarification question when the block type or release is unknown.\n"
                    "Omit any section the evidence cannot support; do not fill it with generic SAP knowledge."
                ),
            }

        # 3. Comparison questions
        if any(term in q_lower for term in ["difference between", "compare", "versus", " vs ", "diff between", "comparison"]):
            return {
                "question_type": "comparison",
                "title": "Comparison Analysis",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Comparison):\n"
                    "1. Direct Summary Answer stating the primary distinction.\n"
                    "2. Markdown Comparison Table contrasting key dimensions (Scope, Core Objects, Integration, Processing Mode).\n"
                    "3. Detailed Differences & Similarities based strictly on retrieved documentation.\n"
                    "4. Practical Architectural Implications in SAP BRIM.\n"
                    "5. Citing supporting documents."
                )
            }

        # 2. Configuration questions
        if any(term in q_lower for term in ["how to configure", "configuration steps", "customizing", "spro", "maintain table", "setup guide", "configure"]):
            return {
                "question_type": "configuration",
                "title": "Configuration Guide",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Configuration):\n"
                    "1. Objective: What component or process is being configured.\n"
                    "2. Prerequisites and master data dependencies.\n"
                    "3. Exact SPRO / IMG Configuration Path (ONLY if verified in evidence; never invent paths).\n"
                    "4. Step-by-Step Documented Configuration Sequence.\n"
                    "5. Expected System Behavior & Validation Checks."
                )
            }

        # 3. T-Code & Table Lookup questions
        if (
            re.search(r"\b(tcode|t-code|transaction|table|se16|se11|sm30)\b", q_lower)
            or re.search(r"\b(/[a-z0-9_]{2,}/[a-z0-9_]+|[a-z]{1,2}[0-9]{2}[a-z0-9]?)\b", q_lower)
            or re.search(r"\b(dfkk[a-z0-9_]+|fkk[a-z0-9_]+|erdk|erch)\b", q_lower)
        ):
            return {
                "question_type": "tcode_table",
                "title": "Technical Identifier Lookup",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Technical Identifier / T-Code / Table Lookup):\n"
                    "1. Identifier Name & Documented Purpose.\n"
                    "2. Functional Context within SAP BRIM (e.g. CI Billable Item processing, FI-CA clearing, SOM order).\n"
                    "3. Documented Key Fields, Selection Parameters, or Menu Access.\n"
                    "4. Execution Prerequisites and Related Transactions.\n"
                    "CRITICAL: Do NOT invent transaction codes or table names not present in the evidence."
                )
            }

        # 4. Troubleshooting questions
        if TROUBLESHOOTING_PATTERN.search(q_lower):
            return {
                "question_type": "troubleshooting",
                "title": "Troubleshooting & Diagnostics",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Troubleshooting):\n"
                    "1. Identified Symptom & Error Context.\n"
                    "2. Verified Root Causes documented in the source evidence.\n"
                    "3. Diagnostic & Investigation Procedures (relevant logs, monitors, or status tables).\n"
                    "4. Evidence-Supported Resolution Steps.\n"
                    "5. Verification Checks to confirm the issue is resolved."
                )
            }

        # 5. Integration and Process-Flow questions
        if any(term in q_lower for term in ["process flow", "end to end", "integration", "how does it interact", "flow from", "billing cycle", "order to cash"]):
            return {
                "question_type": "integration",
                "title": "Process Flow & Integration",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Integration & End-to-End Flow):\n"
                    "1. Involved SAP BRIM Architecture Components (e.g. SOM, CC, CI, FI-CA).\n"
                    "2. End-to-End Processing Sequence (ordered numbered steps).\n"
                    "3. Information & Objects Exchanged (e.g. Provider Order -> Subscription Contract -> CIT -> BIT -> Invoicing Document -> FI-CA Open Item).\n"
                    "4. Component Handshakes and Dependencies.\n"
                    "5. Documented Failure Points & Reconciliation Considerations."
                )
            }

        # 6. Version-specific questions
        if any(term in q_lower for term in ["s/4hana", "s4hana", "ecc", "release", "version", "upgrade", "clean core"]):
            return {
                "question_type": "version_specific",
                "title": "Release & Version Specifics",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Version & Release Specifics):\n"
                    "1. Release Context (S/4HANA vs ECC / Classical BRIM).\n"
                    "2. Documented Functional or Architectural Differences.\n"
                    "3. Migration or Modernization Considerations supported by the evidence.\n"
                    "4. Explicitly state if certain features are restricted to specific releases."
                )
            }

        # 7. Follow-up conversational question
        if is_follow_up:
            return {
                "question_type": "followup",
                "title": "Conversational Follow-up",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Follow-up Response):\n"
                    "1. Direct, concise answer addressing the specific follow-up inquiry immediately.\n"
                    "2. Seamlessly link to the established conversation context without repeating lengthy introductions.\n"
                    "3. Preserve exact technical identifiers discussed in prior turns.\n"
                    "4. Cite supporting passages."
                )
            }

        # 8. Conceptual / Overview question (Default)
        return {
            "question_type": "conceptual",
            "title": "Conceptual Architecture & Overview",
            "instructions": (
                "STRUCTURE REQUIREMENT (Conceptual Architecture):\n"
                "1. Direct Definition & Purpose.\n"
                "2. Functional Mechanism: How the component operates.\n"
                "3. Place in the SAP BRIM Landscape and relationships with adjacent components.\n"
                "4. Practical Example or Business Use Case (where supported by evidence).\n"
                "5. Important Constraints, Best Practices, and Documented Considerations."
            )
        }


answer_planner = AnswerPlanner()
