import re
from typing import Dict, Any, List, Optional

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

        # 1. Comparison questions
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
        if any(term in q_lower for term in ["error", "fail", "failed", "dump", "troubleshoot", "issue", "stuck", "exception", "cannot", "fix"]):
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
