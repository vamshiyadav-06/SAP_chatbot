"""
Restriction/block scope classification for SAP master-data and BRIM questions.

"Block" means different things at different organizational levels. A Business
Partner question can concern a general BP status, a customer or supplier master
block, a company-code, sales-area or purchasing-organization restriction, an FI-CA
contract-account lock, a posting or dunning restriction, or a billing/invoicing
error. These are not interchangeable, so the assistant must establish the precise
block type before recommending a transaction or maintenance procedure.

This module only classifies the *question*. It makes no claim about SAP behavior;
retrieval expansions are search strings, and clarification text asks the user for
the facts needed to choose the correct evidence.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RestrictionCategory:
    key: str
    label: str
    signals: re.Pattern
    retrieval_query: str
    evidence_needed: str


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


CATEGORIES: List[RestrictionCategory] = [
    RestrictionCategory(
        "bp_general_status", "General Business Partner status (central BP-level block)",
        _rx(r"\b(central\s+block|bp[-\s]level|business\s+partner\s+(?:status|lock)|but000|bp\s+status)\b"),
        "business partner central block status business partner lock",
        "Is the block shown on the Business Partner itself, independent of any role or organizational level?",
    ),
    RestrictionCategory(
        "customer_master_block", "Customer master block (customer role)",
        _rx(r"\b(customer|debtor|sold-to|kna1|knb1|knvv|fd0\d|xd0\d|vd0\d)\b"),
        "blocked customer master data customer block",
        "Is the partner affected in its customer role?",
    ),
    RestrictionCategory(
        "supplier_master_block", "Supplier master block (supplier role)",
        _rx(r"\b(supplier|vendor|creditor|lfa1|lfb1|lfm1|xk0\d|fk0\d|mk0\d)\b"),
        "blocked supplier master data supplier vendor block",
        "Is the partner affected in its supplier role?",
    ),
    RestrictionCategory(
        "company_code_restriction", "Company-code-specific restriction",
        _rx(r"\b(company\s+code|bukrs|knb1|lfb1)\b"),
        "company code blocked customer supplier master data",
        "In which company code does the restriction apply?",
    ),
    RestrictionCategory(
        "sales_area_restriction", "Sales-area restriction",
        _rx(r"\b(sales\s+area|sales\s+org(?:anization|anisation)?|distribution\s+channel|division|knvv|order\s+block|"
            r"delivery\s+block)\b"),
        "sales area order block delivery block billing block customer",
        "In which sales area (sales organization, distribution channel, division) does the restriction appear?",
    ),
    RestrictionCategory(
        "purchasing_org_restriction", "Purchasing-organization restriction",
        _rx(r"\b(purchasing\s+org(?:anization|anisation)?|purchasing\s+block|ekorg|lfm1)\b"),
        "purchasing organization purchasing block supplier",
        "In which purchasing organization does the restriction appear?",
    ),
    RestrictionCategory(
        "fica_contract_account_restriction", "FI-CA contract-account restriction or lock",
        _rx(r"\b(contract\s+account|fi-?ca|vkont|fkkvkp|processing\s+lock|clearing\s+lock|fklock\d?|brim|"
            r"convergent|contract\s+partner)\b"),
        "contract account lock central posting block FI-CA processing locks",
        "Which contract account, lock category/process and lock reason are involved, and is the lock set at account or item level?",
    ),
    RestrictionCategory(
        "posting_restriction", "Posting restriction",
        _rx(r"\b(posting\s+(?:block|lock|restriction)|blocked\s+for\s+posting|central\s+posting)\b"),
        "central posting block contract account postings prevented",
        "Are postings rejected, and what exact message is shown?",
    ),
    RestrictionCategory(
        "dunning_restriction", "Dunning restriction",
        _rx(r"\b(dunning\s+(?:block|lock|restriction)|dunning)\b"),
        "dunning lock contract account item level dunning block",
        "Is dunning suppressed for the whole account or only for individual items?",
    ),
    RestrictionCategory(
        "billing_invoicing_error", "Billing or invoicing error / block",
        _rx(r"\b(billing\s+(?:block|lock|error)|invoic(?:e|ing)\s+(?:lock|block|error)|billable\s+item|"
            r"invoicing\s+run|billing\s+run)\b"),
        "invoicing lock billing block billable items error",
        "Which billing or invoicing document or run is affected, and with what status and error message?",
    ),
    RestrictionCategory(
        "data_protection_block", "Data-protection (end-of-purpose) blocking",
        _rx(r"\b(end\s+of\s+purpose|data\s+protection|data\s+privacy|gdpr|ilm|information\s+lifecycle|"
            r"business\s+purpose\s+completed)\b"),
        "blocked customer supplier master data end of purpose data protection",
        "Does the block result from data-protection (end-of-purpose) processing?",
    ),
]
CATEGORY_BY_KEY: Dict[str, RestrictionCategory] = {c.key: c for c in CATEGORIES}

_BLOCK_TERMS = _rx(
    r"\b(block(?:ed|s|ing)?|unblock\w*|lock(?:ed|s)?|unlock\w*|restriction\w*|restricted|deletion\s+flag|"
    r"posting\s+block|dunning\s+block|payment\s+block|billing\s+block|invoicing\s+lock)\b"
)
_MASTER_DATA_CONTEXT = _rx(
    r"\b(business\s+partner|bp|customer|supplier|vendor|contract\s+account|debtor|creditor|partner|fi-?ca|"
    r"master\s+data|company\s+code|sales\s+area|purchasing|dunning|posting|billing|invoic\w*)\b"
)
_RELEASE = _rx(r"\b(s/?4\s?hana|ecc|business\s+suite|(?:1[5-9]|20)\d{2}|on-premise|cloud\s+edition)\b")

# Categories that remain plausible when the user only says "Business Partner". Order sets the
# retrieval-expansion priority (only the first RESTRICTION_SCOPE_MAX_EXPANSIONS are retrieved);
# FI-CA contract-account locks come early because this is a BRIM assistant.
_BP_DEFAULT_CANDIDATES = [
    "bp_general_status",
    "fica_contract_account_restriction",
    "customer_master_block",
    "supplier_master_block",
    "company_code_restriction",
    "sales_area_restriction",
    "purchasing_org_restriction",
    "posting_restriction",
    "dunning_restriction",
    "data_protection_block",
]


@dataclass
class RestrictionScope:
    is_restriction_query: bool = False
    explicit_categories: List[str] = field(default_factory=list)
    candidate_categories: List[str] = field(default_factory=list)
    ambiguous: bool = False
    release_specified: bool = False
    clarification_question: Optional[str] = None
    evidence_needed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    def labels(self, keys: Optional[List[str]] = None) -> List[str]:
        return [CATEGORY_BY_KEY[k].label for k in (keys if keys is not None else self.candidate_categories)]

    def retrieval_queries(self, limit: int = 5) -> List[Dict[str, str]]:
        return [{"category": k, "query": CATEGORY_BY_KEY[k].retrieval_query} for k in self.candidate_categories[:limit]]

    def prompt_guidance(self) -> str:
        """Instructions for the answer generator; empty when the query is not about restrictions."""
        if not self.is_restriction_query:
            return ""
        lines = [
            "RESTRICTION / BLOCK SCOPE (mandatory handling):",
            "- Block types are NOT interchangeable. Distinguish: " + "; ".join(c.label for c in CATEGORIES) + ".",
            "- Identify which block type each piece of evidence concerns (business object, role, organizational level, "
            "product/release) before naming any transaction, field, table or procedure.",
            "- Recommend a transaction or maintenance step only if a cited passage documents that exact operation for "
            "that exact block type. A transaction that exists, or that maintains related data, is not evidence that it "
            "removes this block.",
            "- Never infer a field's meaning from its name. Describe a field only within the scope the evidence states "
            "(table, organizational level, process).",
            "- Never present direct table edits (SE16N edit mode, SQL, debugging) as the way to remove a block.",
            "- Do not describe downstream effects of removing a block unless a cited passage states them.",
        ]
        if self.ambiguous:
            lines.append(
                "- The block type is NOT specified. Do not give a single definitive procedure. Briefly list the "
                "candidate block types the evidence covers, state what each cited passage establishes, and end with "
                "one targeted clarification that asks: " + " ".join(self.evidence_needed)
            )
        else:
            lines.append("- The user indicated: " + "; ".join(self.labels(self.explicit_categories)) + ".")
        if not self.release_specified:
            lines.append("- The SAP product/release is not specified; state the release each cited source applies to.")
        return "\n".join(lines)


class RestrictionScopeClassifier:
    """Detects restriction/block questions and which block types they may concern."""

    def classify(self, query: str) -> RestrictionScope:
        q = query or ""
        if not (_BLOCK_TERMS.search(q) and _MASTER_DATA_CONTEXT.search(q)):
            return RestrictionScope()

        explicit = [c.key for c in CATEGORIES if c.signals.search(q)]
        specific = [k for k in explicit if k != "bp_general_status"]
        ambiguous = not specific
        candidates = list(dict.fromkeys(explicit)) if specific else list(_BP_DEFAULT_CANDIDATES)

        release_specified = bool(_RELEASE.search(q))
        if ambiguous:
            evidence_needed = [
                "Which block indicator, status text or error message do you see, and on which screen?",
                "Which role or object is affected (customer, supplier, contract account, or the Business Partner itself)?",
                "At which organizational level does it apply (company code, sales area, purchasing organization, or contract account)?",
            ]
        else:
            evidence_needed = [CATEGORY_BY_KEY[k].evidence_needed for k in candidates]
        if not release_specified:
            evidence_needed.append("Which SAP product and release are you using (for example SAP S/4HANA on-premise and its version)?")

        clarification = None
        if ambiguous:
            clarification = (
                "To give the exact viewing and removal procedure, which restriction are you seeing: a general "
                "Business Partner block, a customer or supplier block, a company-code, sales-area or "
                "purchasing-organization restriction, or an FI-CA contract-account lock (for example posting or dunning)? "
                "Please also share the message or field where the block appears"
                + ("" if release_specified else " and your SAP product/release") + "."
            )

        return RestrictionScope(
            is_restriction_query=True,
            explicit_categories=explicit,
            candidate_categories=candidates,
            ambiguous=ambiguous,
            release_specified=release_specified,
            clarification_question=clarification,
            evidence_needed=evidence_needed,
        )


restriction_scope_classifier = RestrictionScopeClassifier()
