import re
from typing import Dict, Any, Optional, List

# Curated reference registry of verified SAP BRIM & S/4HANA technical entities
SAP_TECHNICAL_ENTITIES: Dict[str, Dict[str, Any]] = {
    # SAP Convergent Invoicing (CI) T-Codes & Tables
    "/1fe/": {
        "name": "/1FE/ (Class Prefix)",
        "type": "tcode_prefix",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Standard generated transaction code and table prefix for Billable Item (BIT) Classes in SAP Convergent Invoicing.",
        "verified_objects": ["/1FE/BIT_CREATE", "/1FE/BIT_MONITOR", "/1FE/BIT_DISPLAY"]
    },
    "fpc1": {
        "name": "FPC1",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Create Invoicing Order / Individual Invoicing Run in Convergent Invoicing.",
        "standard_use": "Executes billing and invoicing for selected contract accounts or business partners."
    },
    "fpc2": {
        "name": "FPC2",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Mass Invoicing Run in Convergent Invoicing.",
        "standard_use": "Executes mass batch processing of billable items into invoicing documents."
    },
    "fpc0": {
        "name": "FPC0",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Display Invoicing Document in Convergent Invoicing.",
        "standard_use": "Inspects invoicing document headers, items, and linked billing documents."
    },
    "dfkkbict": {
        "name": "DFKKBICT",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Items: Control Data and Item Status Table.",
        "key_fields": ["MANDT", "BITCAT", "BITSTATUS", "SRCTYPE"]
    },
    "dfkkbict_it": {
        "name": "DFKKBICT_IT",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Item Main Items (IT) Table.",
        "key_fields": ["MANDT", "BITNUMBER", "BITSTATUS", "VKONT", "GPART"]
    },
    "dfkkbict_py": {
        "name": "DFKKBICT_PY",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Item Payment Data (PY) Table.",
        "key_fields": ["MANDT", "BITNUMBER", "PY_AMOUNT", "WAERS"]
    },
    "dfkkbict_tx": {
        "name": "DFKKBICT_TX",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Item Tax Data (TX) Table.",
        "key_fields": ["MANDT", "BITNUMBER", "TAX_AMOUNT", "TAX_DATE"]
    },

    # SAP FI-CA (Contract Accounts Receivable and Payable)
    "fpcopara": {
        "name": "FPCOPARA",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Correspondence Run in FI-CA.",
        "standard_use": "Mass output processing for invoices, account statements, and dunning letters."
    },
    "fpe1": {
        "name": "FPE1",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Post Document in FI-CA.",
        "standard_use": "Manual posting of financial documents into contract accounts."
    },
    "fpe2": {
        "name": "FPE2",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Change Document in FI-CA.",
        "standard_use": "Modifies open item line item attributes (e.g. payment terms, dunning locks)."
    },
    "fpe3": {
        "name": "FPE3",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Display Document in FI-CA.",
        "standard_use": "Inspects document header (DFKKKO) and line items (DFKKOP)."
    },
    "fp05": {
        "name": "FP05",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Payment Lot Processing in FI-CA.",
        "standard_use": "Processes incoming customer bank payments and clearing of open items."
    },
    "fpva": {
        "name": "FPVA",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Dunning Proposal Run in FI-CA.",
        "standard_use": "Evaluates overdue open items and proposes dunning levels."
    },
    "fpvb": {
        "name": "FPVB",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Dunning Activity Run in FI-CA.",
        "standard_use": "Executes dunning actions, generates dunning fees, interest, and letters."
    },
    "dfkkko": {
        "name": "DFKKKO",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Document Header Table.",
        "key_fields": ["MANDT", "OPBEL", "FIKEY", "BLDAT", "BUDAT"]
    },
    "dfkkop": {
        "name": "DFKKOP",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Contract Account Document: Line Item Table (Open Items).",
        "key_fields": ["MANDT", "OPBEL", "OPUPK", "OPUPW", "OPUPZ", "VKONT", "GPART", "BETRW"]
    },
    "dfkkopk": {
        "name": "DFKKOPK",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Document: General Ledger Items.",
        "key_fields": ["MANDT", "OPBEL", "OPUPK", "HKONT", "BETRW"]
    },

    # Master Data Entities
    "but000": {
        "name": "BUT000",
        "type": "table",
        "component": "SAP Master Data (BP)",
        "description": "Business Partner General Data Table (Central Header).",
        "key_fields": ["CLIENT", "PARTNER", "TYPE", "NAME_FIRST", "NAME_LAST"]
    },
    "fkkvkp": {
        "name": "FKKVKP",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "Contract Account Header and Partner-Specific Data.",
        "key_fields": ["MANDT", "VKONT", "GPART"]
    },

    # Core ERP Transactions
    "me21n": {
        "name": "ME21N",
        "type": "tcode",
        "component": "SAP MM",
        "description": "Create Purchase Order.",
        "standard_use": "Purchasing transaction for procurement orders in SAP ERP / S/4HANA."
    },
    "migo": {
        "name": "MIGO",
        "type": "tcode",
        "component": "SAP MM",
        "description": "Goods Movement (Goods Receipt / Issue).",
        "standard_use": "Processes inventory movements and posts warehouse receipts."
    },
    "miro": {
        "name": "MIRO",
        "type": "tcode",
        "component": "SAP MM / FI",
        "description": "Enter Incoming Invoice (Logistics Invoice Verification).",
        "standard_use": "Performs 3-Way Match validation against Purchase Order and Goods Receipt."
    },
    "sm30": {
        "name": "SM30",
        "type": "tcode",
        "component": "SAP Basis / Customizing",
        "description": "Call View Maintenance.",
        "standard_use": "Maintains configuration tables and views defined in ABAP Dictionary."
    },
    "se16": {
        "name": "SE16",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "Data Browser.",
        "standard_use": "Displays database table contents and records."
    },
    "se16n": {
        "name": "SE16N",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "General Table Display.",
        "standard_use": "Interactive browser for ABAP database tables."
    },
    "spro": {
        "name": "SPRO",
        "type": "tcode",
        "component": "SAP Customizing",
        "description": "Customizing - Edit Project / SAP Reference IMG.",
        "standard_use": "Central entry transaction for all SAP configuration and IMG paths."
    }
}


class SAPEntityService:
    """Provides entity lookups for documented SAP T-codes, tables, and BRIM components."""

    @staticmethod
    def lookup_entity(identifier: str) -> Optional[Dict[str, Any]]:
        clean_id = identifier.lower().strip()
        # Direct match
        if clean_id in SAP_TECHNICAL_ENTITIES:
            return SAP_TECHNICAL_ENTITIES[clean_id]
        # Prefix match (e.g. for /1FE/ classes)
        for key, entry in SAP_TECHNICAL_ENTITIES.items():
            if clean_id.startswith(key):
                return entry
        return None

    @staticmethod
    def is_known_sap_identifier(identifier: str) -> bool:
        clean_id = identifier.lower().strip()
        if clean_id in SAP_TECHNICAL_ENTITIES:
            return True
        for key in SAP_TECHNICAL_ENTITIES:
            if clean_id.startswith(key):
                return True
        return False


sap_entity_service = SAPEntityService()
