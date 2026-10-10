import re
from typing import Tuple


SAP_CORE_MODULES = {
    "fi", "co", "fico", "mm", "sd", "pp", "qm", "pm", "ps", "hcm", "hr",
    "basis", "abap", "fiori", "s/4hana", "s4hana", "s4", "ecc", "btp",
    "netweaver", "successfactors", "ariba", "concur", "hybris", "c4c",
    "bw", "bi", "crm", "srm", "ewm", "tm", "grc", "mdg", "solman",
    "brim", "som", "cc", "ci", "fi-ca", "fica", "convergent charging",
    "convergent invoicing", "subscription order management"
}


SAP_KEYWORDS = {
    "sap", "hana", "s/4", "s4", "fiori", "abap", "bapi", "idoc", "ale",
    "rfc", "odata", "spro", "img", "t-code", "tcode", "transaction code",
    "transport request", "movement type", "company code", "controlling area",
    "purchasing organization", "plant", "storage location", "material master",
    "vendor master", "customer master", "bill of materials", "bom", "routing",
    "work center", "mrp", "goods receipt", "goods issue",
    "3-way match", "three way match", "purchase order", "sales order",
    "delivery document", "billing document", "general ledger",
    "accounts payable", "accounts receivable", "asset accounting",
    "cost center", "profit center", "internal order", "posting key",
    "chart of accounts", "reconciliation account", "sapgui", "sap gui",
    "netweaver", "alv", "smartforms", "adobe forms", "enhancement point",
    "user exit", "badi", "luw", "cds view", "amdp", "core data services",
    "rap", "cap", "btp", "open sql", "hana cloud", "solution manager",
    "service marketplace", "sap notes", "oss note", "su01", "pfcg",
    "sm50", "sm21", "st22", "st03n", "se11", "se16n", "se38", "se80",
    "me21n", "va01", "fb01", "fb50", "fb60", "migo", "miro", "vl01n",
    "vf01", "co01", "brim", "convergent charging", "convergent invoicing",
    "subscription order management", "fi-ca", "fica", "billable item",
    "consumption item", "provider contract", "invoicing document",
    "billable items", "consumption items", "provider contracts",
    "bit", "cit", "fpt3", "fpt4", "fpva", "fpvb", "fpcpl",
    "fkk_invoicing", "fkkbi", "fpy1", "fpy2", "charge plan",
    "pricing macro", "subscriber account", "contract account",
    "business partner", "master agreement", "sharing contract"
}

SENTIMENTAL_AND_GREETING_PATTERNS = [
    r"^(hi+|hey+|hello+|howdy|hola|namaste|greetings)\b",
    r"^(good\s+(morning|afternoon|evening|night|day))\b",
    r"\b(how\s+are\s+you|how're\s+you|how\s+is\s+it\s+going|how\s+do\s+you\s+feel)\b",
    r"\b(who\s+are\s+you|what\s+is\s+your\s+name|what's\s+your\s+name|introduce\s+yourself)\b",
    r"\b(what\s+can\s+you\s+do|what\s+do\s+you\s+do|tell\s+me\s+about\s+yourself)\b",
    r"\b(tell\s+me\s+a\s+joke|make\s+me\s+laugh|sing\s+a\s+song|write\s+a\s+story|write\s+a\s+poem)\b",
    r"\b(thank\s+you|thanks|thx|thank\s+u)\b",
    r"\b(bye|goodbye|see\s+you|cya)\b",
    r"\b(i\s+love\s+you|i\s+hate\s+you|do\s+you\s+love\s+me|are\s+you\s+(happy|sad|real|human|ai|bot))\b",
    r"^(ok|okay|cool|nice|great|awesome|fine|alright|sure)\b",
]

GENERAL_UNRELATED_PATTERNS = [
    r"\b(cricket|football|soccer|basketball|baseball|tennis|olympics|ipl)\b",
    r"\b(recipe|cook|baking|cake|pizza|pasta|dinner|lunch|breakfast|salad)\b",
    r"\b(birthday|anniversary|wedding|congratulation|love letter|poem|poetry|song)\b",
    r"\b(elon musk|donald trump|joe biden|taylor swift|movie|actor|actress|cinema)\b",
    r"\b(python|javascript|typescript|c\+\+|java|golang|rust|ruby|php)\b",
    r"\b(weather|horoscope|zodiac|astrology|travel guide|hotel booking|flight ticket)\b",
]


class SAPClassifier:
    """Strict SAP-domain classifier."""

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        """
        Match SAP terms safely.

        Examples:
        'cap' matches 'CAP'
        'cap' does NOT match 'capital'
        'fi' matches 'FI'
        'fi' does NOT match 'finance'
        """
        escaped = re.escape(term.lower())

        # Terms containing non-word characters need a slightly
        # more flexible boundary.
        if re.search(r"\W", term):
            pattern = rf"(?<!\w){escaped}(?!\w)"
        else:
            pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"

        return bool(re.search(pattern, text, re.IGNORECASE))

    @classmethod
    def classify(cls, query: str) -> Tuple[bool, str]:
        """
        Returns:
            (True, 'sap_domain_verified') for SAP-related queries
            (False, refusal message) for non-SAP queries
        """

        text = query.strip().lower()

        if not text:
            return False, "I can only help with SAP and SAP-related topics. Query cannot be empty."

        # Check for explicit SAP mention first
        has_sap_direct = cls._contains_term(text, "sap")

        # Match SAP keywords using whole-term matching.
        has_sap_keyword = any(
            cls._contains_term(text, keyword)
            for keyword in SAP_KEYWORDS
            if keyword != "sap"
        )

        # Match SAP module names safely.
        has_sap_module = any(
            cls._contains_term(text, module)
            for module in SAP_CORE_MODULES
        )

        # SAP transaction-code pattern.
        has_tcode_pattern = bool(
            re.search(
                r"\b(?:me21n|va01|fb01|fb50|fb60|migo|miro|vl01n|vf01|"
                r"co01|su01|pfcg|sm50|sm21|st22|st03n|se11|se16n|se38|se80|"
                r"fpt3|fpt4|fpva|fpvb|fpcpl|fpy1|fpy2)\b",
                text,
                re.IGNORECASE
            )
        )

        # Common SAP table names.
        common_tables = {
            "mara", "marc", "mard", "bseg", "bkpf",
            "ekko", "ekpo", "vbak", "vbap",
            "kna1", "lfa1", "t001", "acdoca",
            "dfkkop", "dfkkbpt", "fkkvkp"
        }

        has_sap_table = any(
            cls._contains_term(text, table)
            for table in common_tables
        )

        is_sap_query = (
            has_sap_direct
            or has_sap_keyword
            or has_sap_module
            or has_tcode_pattern
            or has_sap_table
        )

        if is_sap_query:
            return True, "sap_domain_verified"

        # Explicitly reject sentimental questions & greetings without SAP context
        for pattern in SENTIMENTAL_AND_GREETING_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False, "I can only help with SAP and SAP-related topics. Please ask an SAP or SAP BRIM technical question."

        # Explicitly known unrelated questions
        for pattern in GENERAL_UNRELATED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False, "I can only help with SAP and SAP-related topics."

        # Everything else without SAP context is rejected
        return False, "I can only help with SAP and SAP-related topics."


sap_classifier = SAPClassifier()