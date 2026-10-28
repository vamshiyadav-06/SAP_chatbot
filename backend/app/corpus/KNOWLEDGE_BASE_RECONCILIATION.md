# Knowledge-base reconciliation

Audit date: 2026-10-13

## Source inventory

- Canonical source directory: `knowledge_base/documents/`
- Source PDFs found: 30
- Legacy source directory removed after a move: `knowledge_base/the full rag data sap/`
- PDFs moved into the canonical directory: 14
- PDFs deleted: 0
- New external PDFs added: 0

## Index inventory

The local SQLite index contains 40 document records and 11,317 embedded chunks.
(Historical figure from the audit date. Since 2026-10-16 the index lives in PostgreSQL + pgvector;
the SQLite file was migrated without re-embedding and is no longer used by the application.)
Ten indexed document records have no corresponding local source PDF. They are retained as
historical index records and are surfaced as `orphaned` by `GET /api/rag-inspect/documents`;
they must be reviewed before rebuilding the index.

Missing local source files (not fabricated or downloaded):

- `SAP_ABAP_Development_and_RAP_Standards.pdf`
- `SAP_Basis_Administration_and_Security_Handbook.pdf`
- `SAP_CO_Controlling_Configuration_Handbook.pdf`
- `SAP_FI_Financial_Accounting_Guide.pdf`
- `SAP_Fiori_Design_and_Deployment_Manual.pdf`
- `SAP_HCM_Human_Capital_Management_Guide.pdf`
- `SAP_MM_Materials_Management_Manual.pdf`
- `SAP_PP_Production_Planning_Reference.pdf`
- `SAP_S4HANA_Architecture_and_Migration_Guide.pdf`
- `SAP_SD_Sales_and_Distribution_Handbook.pdf`

## Operating rule

Add only legally available, release-labelled SAP material to `knowledge_base/documents/`.
Before a full re-ingestion, export or back up the production index and review the ten orphaned
records: a rebuild without their source files will remove their historical chunks.
