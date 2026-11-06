"""Questions about Clyptus itself ("What is Clyptus?", "Who built you?") get a fixed, owner-written answer.

The SAP-scope classifier refuses everything that is not SAP, which also refused questions about the
company behind the product. The answer below is the "About Clyptus" text of the landing page; it is
returned as-is (no model call), so it cannot invent facts. Keep it in step with that page.
"""
import re

COMPANY_ANSWER = (
    "**Clyptus Technologies** builds domain-specialised AI for complex ERP landscapes. "
    "**Clyptus.AI** is its AI knowledge assistant for SAP, with a dedicated focus on **SAP BRIM**: "
    "Subscription Order Management, Convergent Charging, Convergent Invoicing, FI-CA and Convergent Mediation.\n\n"
    "It connects scattered SAP BRIM documentation to grounded, practical answers for solution architects, "
    "billing consultants and support teams. Answers are built from retrieved evidence first and checked "
    "against it, so the assistant says so when the evidence does not support an answer instead of guessing.\n\n"
    "For other company details such as contact, pricing or partnerships, please contact the Clyptus team. "
    "I'm happy to help with any SAP or SAP BRIM question."
)

_NAME = re.compile(r"\bc?clyptus(?:\.?ai|\s+(?:technologies|tech|soft|company|team))?\b", re.IGNORECASE)
_INTENT = re.compile(
    r"\b(what|who|which|about|tell|describe|explain|introduce|company|firm|organi[sz]ation|business|"
    r"founder|founded|team|owner|owns|built|build|builds|made|makes|created|creates|develop\w*|"
    r"products?|services?|offer\w*|mission|vision|do(?:es)?|is|are)\b",
    re.IGNORECASE,
)
_ABOUT_ME = re.compile(
    r"\bwho\s+(?:made|built|created|developed|owns|trained|designed)\s+(?:you|this)\b"
    r"|\bwhich\s+company\s+(?:made|built|created|developed|owns)\s+(?:you|this)\b"
    r"|\bwho(?:'s| is)\s+(?:behind|your\s+(?:creator|developer|maker|owner))\b",
    re.IGNORECASE,
)


def is_company_question(text: str) -> bool:
    """True when the user asks about Clyptus / Clyptus.AI or who built this assistant."""
    query = (text or "").strip()
    if not query or len(query) > 300:
        return False
    if _ABOUT_ME.search(query):
        return True
    return bool(_NAME.search(query) and _INTENT.search(query))
