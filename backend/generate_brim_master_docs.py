import sys
import os
from pathlib import Path
import pymupdf

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "knowledge_base" / "documents"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

BRIM_MANUALS = [
    {
        "filename": "SAP_BRIM_CC_Convergent_Charging_Advanced_Architecture.pdf",
        "title": "SAP Convergent Charging (CC 2020/2023) Advanced Architecture & Implementation Guide",
        "module": "CC / BRIM",
        "product": "SAP Convergent Charging",
        "topics": [
            ("SAP CC Core Server System Architecture & Instances Topology",
             "SAP Convergent Charging (CC) is the ultra-high throughput rating and charging engine of SAP BRIM. The Core Server consists of several specialized instance types operating in a distributed cluster:\n"
             "- Dispatcher Instances: Manage incoming TCP/HTTP client connections, perform connection pooling, load balancing, and route stateful charging requests to Guider and Rater instances.\n"
             "- Guider Instances: Maintain the mapping of User Technical Identifiers (UTI) to Subscriber Contracts and partition IDs, ensuring request affinity to the correct partition.\n"
             "- Rater Instances: Execute dynamic rating and charging trees, perform math calculations, update persistent and transient counters, evaluate pricing logic, and determine charge amounts.\n"
             "- Updater Instances: Manage subscriber account balances, commit wallet/prepaid balance changes to the database, and execute transactional persistence.\n"
             "- Bulkloader Instances: Extract charged and consumption items from internal buffers and load them directly into SAP Convergent Invoicing (CI) tables or BART files.\n"
             "- Taxer Instances: Integrate with internal or external tax calculation engines (Vertex, Avalara, SAP Tax Engine) during real-time charging."),

            ("Hazelcast In-Memory Distributed Data Grid (IMDG) Architecture",
             "SAP CC Core Server relies on Hazelcast IMDG for in-memory state replication, high availability, and microsecond response times. Key Hazelcast aspects include:\n"
             "- Partitioning: Subscriber accounts and active sessions are distributed across partitions (typically 271 or 511 partitions).\n"
             "- Near Cache: Rater instances maintain local Near Caches for frequently read master data such as Translation Tables, Range Tables, and Charge Plans.\n"
             "- Cluster Split-Brain Protection: Quorum rules and network heartbeat parameters prevent desynchronization across active-active data center topologies.\n"
             "- Cache Refresh Commands: Administrators can trigger near-cache invalidation using the CLI tool 'admin.bat -cache -refresh' without restarting Core Server instances."),

            ("Master Data Hierarchy: Pricing Catalog, Charge Plans, and Charges",
             "Master data in SAP CC is organized in a strict hierarchical structure:\n"
             "1. Service Provider: Root entity representing the company code or operating business unit.\n"
             "2. Pricing Catalog: Container of reusable pricing objects, tables, and charge plans owned by a service provider.\n"
             "3. Charge Plan: The primary commercial building block exposed to SAP SOM. A charge plan contains one or more Charges and technical interface parameters.\n"
             "4. Charge: Represents an individual pricing rule (e.g. Monthly Fee, Voice Usage, Data Usage). Each charge contains a Price Plan and a Charging Plan.\n"
             "5. Price Plan: The rating logic tree that computes the monetary amount based on event properties.\n"
             "6. Charging Plan: The routing logic tree that determines which subscriber account (prepaid wallet or external postpaid account) pays for the charged amount."),

            ("Rating Tree Components & Decision Logic Engineering",
             "Price plans and charging plans are modeled as visual decision trees comprising specific node types:\n"
             "- Comparators: Number Comparator, String Comparator, Date Comparator. Used to branch execution based on call destination, time of day, customer tier, or event volume.\n"
             "- Splitters: Time Splitter (splits usage across peak/off-peak windows), Volume Splitter (splits data usage across quota thresholds).\n"
             "- Tables: Translation Tables (key-value lookups), Range Tables (bracket-based pricing tiers), Tier Tables (multi-dimensional matrices).\n"
             "- Pricing Macros: Encapsulate reusable calculation sequences across multiple charge plans to enforce standard logic and simplify maintenance.\n"
             "- Counters: Numerical variables tied to the subscriber contract. Persistent counters are committed to the DB; transient counters reset at session end."),

            ("Allowances and Allowance Packages Architecture",
             "Allowances represent customer entitlements to free or discounted consumption (e.g. 10 GB free data, 500 bonus minutes):\n"
             "- Allowance Definition: Master data template specifying allowance behavior, parameters, and validity lifecycle.\n"
             "- Allowance Plan: Logic tree defining how an allowance is credited, debited, extended, or expired.\n"
             "- Allowance Logic in Rating Trees: Rating logic inspects available allowances first. If an allowance exists with remaining balance, the event consumes the allowance balance and generates a zero-rated or discounted billable item. Once exhausted, standard tier rating resumes.\n"
             "- Shared Allowances: Allowance packages can be shared across multiple provider contracts in a family pooling or corporate account scenario."),

            ("Subscriber Accounts, Prepaid Accounts, and User Technical Identifiers (UTI)",
             "Subscriber data links technical network activity to financial accounts:\n"
             "- Subscriber Account: Created per customer; holds prepaid balances and external account references matching SAP FI-CA Contract Accounts.\n"
             "- Prepaid Accounts: Virtual wallets supporting real-time credit checks, minimum balance thresholds, and top-up refill plans.\n"
             "- User Technical Identifier (UTI): Network-level service identifiers such as MSISDN phone numbers, IMSI, IP addresses, MAC addresses, or email addresses. Guider instances use the UTI service identifier to instantly locate the target contract."),

            ("Diameter Ro/Gy Online Credit Control & Sy Spending Limits",
             "In telecom and utility environments, SAP CC integrates with 3GPP network nodes using Diameter protocol interfaces:\n"
             "- Diameter Ro / Gy: Provides session-based charging (CCR-Initial, CCR-Update, CCR-Terminate) with Credit Control Answers (CCA) granting granted service units (GSU).\n"
             "- Diameter Sy Interface: Communicates policy spending limit information between SAP CC and the Policy and Charging Rules Function (PCRF), notifying when thresholds are breached.\n"
             "- Event-Based Charging: One-time direct debit events (Direct Debit Requests) for instant content purchases or service activation fees."),

            ("Batch Acquisition & Rating Tool (BART) Operations",
             "BART handles offline, asynchronous mass processing of usage records:\n"
             "- Consumption Data Records (CDRs) and Event Data Records (EDRs) are ingested via batch file loaders.\n"
             "- BART Server performs deduplication, structural validation, and dispatches batch rating requests to Rater instances.\n"
             "- Processed items are output as Billable Items directly into Convergent Invoicing staging tables via Bulkloader."),

            ("Core Tool, Cockpit, and Administrative CLI Tooling",
             "Administrators and pricing specialists manage SAP CC using dedicated interfaces:\n"
             "- Core Tool: Rich Java Swing client for creating pricing catalogs, charge plans, rating trees, and subscriber accounts.\n"
             "- Cockpit: Modern SAP Fiori web interface for monitoring server metrics, managing user permissions, and inspecting system alerts.\n"
             "- Administrative Scripts: 'setup.bat' (system initialization, schema creation), 'admin.bat' (runtime cluster management, pinging instances, inspecting thread pools, updating licenses), 'config.bat' (exporting/importing XML configuration)."),

            ("SAP CC Troubleshooting, Latency Optimization, and War Room Best Practices",
             "Key production troubleshooting steps for senior CC architects:\n"
             "- Diagnosing Rating Latency: Inspect garbage collection logs (G1GC pauses), check Hazelcast near-cache hit ratios, and examine DB connection pool saturation.\n"
             "- Resolving JCo RFC Timeouts: Increase connection pool size and max connections in 'jco.server.connection_count'.\n"
             "- Unlocking Stuck Sessions: Use 'admin.bat' commands to release orphaned session reservations caused by abrupt network dropouts.\n"
             "- Verifying Partition Rebalancing: Ensure no data skew across rater partitions following server instance restart.")
        ]
    },
    {
        "filename": "SAP_BRIM_FICA_Contract_Accounts_Master_Handbook.pdf",
        "title": "SAP Contract Accounts Receivable and Payable (FI-CA) Master Configuration & Architecture Guide",
        "module": "FI-CA / BRIM",
        "product": "SAP FI-CA",
        "topics": [
            ("FI-CA Architecture vs Classic FI-AR: Massive Throughput Design",
             "SAP Contract Accounts Receivable and Payable (FI-CA) is an enterprise subledger engineered to handle tens of millions of customer accounts and hundreds of millions of daily line items. Key architectural contrasts with classic FI-AR include:\n"
             "- Decentralized Subledger: FI-CA records granular operational receivables (tables DFKKKO for headers, DFKKOP for open items) without cluttering the General Ledger.\n"
             "- Summary GL Postings: Individual line items are aggregated by reconciliation key and posted as summary entries into the Universal Journal (ACDOCA / BSEG).\n"
             "- Master Data Triad: Business Partner (GP), Contract Account Category, Contract Account (FKKVKP), and Provider Contract (EVER/FKKVKP).\n"
             "- Multi-Contract Support: A single customer can own multiple contract accounts (e.g. separating business lines, corporate divisions, or payment methods)."),

            ("SPRO Posting Areas Framework and Technical Customizing Paths",
             "FI-CA configuration centers around standardized Posting Areas (Table TFK033D), configured via transaction SPRO:\n"
             "- SPRO Path: Financial Accounting -> Contract Accounts Receivable and Payable -> Basic Functions.\n"
             "- Posting Area 0100: Document Types and Document Number Ranges. Defines document characteristics for Invoicing (IN), Payments (PA), Dunning, and Adjustments.\n"
             "- Posting Area 0110: Determination of General Ledger Reconciliation Accounts by Company Code, Division, and Account Determination ID.\n"
             "- Posting Area 0010: Default control values for Reconciliation Keys and document summarization.\n"
             "- Posting Area 0020 & 0030: Main Transactions and Subtransactions (V_TFK033D). Controls revenue account assignment, CO-PA derivation, and tax calculation.\n"
             "- Posting Area 0150: Clearing Control configuration (clearing variants, grouping, and priority rules).\n"
             "- Posting Area 0300: Dunning Procedures, dunning level fees, interest calculation, and charge assignment.\n"
             "- Posting Area 1010 & 1020: Bank clearing accounts and payment lot default parameters."),

            ("Reconciliation Keys Lifecycle and General Ledger Transfer (FPG1)",
             "Reconciliation Keys are fundamental control objects in FI-CA that ensure subledger and general ledger synchronization:\n"
             "1. Creation: A reconciliation key is generated manually via FPAR or automatically during mass batch runs (billing, invoicing, payments).\n"
             "2. Recording: Postings to DFKKOP update totals records in table DFKKREP01 under the open reconciliation key.\n"
             "3. Closing: Once a mass activity finishes, transaction FPAV or the mass run automatically closes the reconciliation key, preventing further postings.\n"
             "4. Transfer to GL: Transaction FPG1 executes the General Ledger Transfer, generating summary FI documents in ACDOCA / BSEG. If discrepancies occur, transaction FP01 or FPG2 allows reconciliation inspection."),

            ("Clearing Control Architecture (Posting Area 0150, FPMA, FP06)",
             "Clearing Control dictates how incoming payments, credit memos, and open invoices are matched and balanced:\n"
             "- Clearing Types: Type 1 (Incoming Payment), Type 2 (Invoicing), Type 3 (Account Maintenance), Type 4 (Installment Plan).\n"
             "- Clearing Categories: Classify open items into categories based on main/subtransactions (e.g. usage fee, late fee, deposit).\n"
             "- Clearing Variants: Define the multi-step algorithm for item settlement. Steps include: Grouping Rules (group by currency, due date, contract), Sorting Rules (sort oldest due date first), and Clearing Amount Rules (partial clearing permitted vs full item only).\n"
             "- Automatic Clearing (FPMA): Mass run evaluating uncleared open items across accounts and executing clearing.\n"
             "- Account Maintenance (FP06): Manual clearing interface for finance specialists to clear conflicting items."),

            ("Dunning by Collection Strategy & Collections Management",
             "SAP FI-CA provides two dunning architectures:\n"
             "1. Classic Dunning: Level-based dunning (Levels 1 to 4) executed via Dunning Proposal (FPVA) and Dunning Activity Run (FPVB), applying interest and dunning charges.\n"
             "2. Dunning by Collection Strategy: Advanced customer scoring and behavioral prioritization. Collection strategies define dynamic actions: automated SMS/email reminders, dunning letters, outbound collection calls, service lock/suspension, installment proposals, external agency assignment (FP04D), or write-off (FP04).\n"
             "- Deferrals and Installment Plans: Configured via FPR1 and FPR2 to break large balances into scheduled payments without triggering dunning."),

            ("Payment Processing: Payment Lots, Bank Statements, and Payment Runs",
             "High-volume payment ingestion and settlement in FI-CA:\n"
             "- Electronic Bank Statement (EBS): Ingestion of MT940 and CAMT.053 files, automatically creating payment lots.\n"
             "- Payment Lots (FP05): Aggregates incoming payments, bank clearing accounts, and customer reference IDs. Automatic post-processing handles clarification items (FP05 clarification worklist).\n"
             "- Check Lots (FP25) & Credit Card Clearing: Dedicated lots for processing physical checks and tokenized payment gateway batches.\n"
             "- Automatic Payment Run (FP35 / F110 / FPA1): Generates outgoing payment media (SEPA Direct Debit XML pain.008, wire transfers pain.001) using DMEE/DMEEX trees."),

            ("Mass Activities Parallelization & Interval Distribution (FKK_INST)",
             "FI-CA achieves enterprise scalability through massive job parallelization:\n"
             "- Interval Distribution (FKK_INST): The system segments the Business Partner or Contract Account key space into balanced intervals (e.g. 50 parallel intervals).\n"
             "- Mass Activity Execution: Programs schedule parallel background jobs (SM37) corresponding to each interval, running concurrently across all application servers.\n"
             "- Enqueue and Lock Management: Avoids database locking contention by assigning unique interval boundaries to each worker process."),

            ("Database Table Architecture and Core Indexing Strategy",
             "Critical FI-CA tables and query performance optimization:\n"
             "- DFKKKO: Header data for FI-CA accounting documents (document number, doc type, posting date, recon key).\n"
             "- DFKKOP: Line item table for open and cleared items (business partner GPART, contract account VKONT, clearing status AUGST, due date FAEDN, amounts BETRH, main transaction HVORG, subtransaction TVORG).\n"
             "- DFKKOPK: Offset and GL line item assignments.\n"
             "- FKKVKP: Contract Account master data table (partner, payment methods, clearing category, dunning procedure).\n"
             "- Performance Indexes: Essential indexes include DFKKOP~0 (mandt, opbel, opupw, opupk), DFKKOP~B (mandt, gpart, vkont, augst), DFKKOP~C (mandt, augst, faedn)."),

            ("Write-Offs, Bad Debt, and Statutory Tax Adjustments (FP04)",
             "Processing uncollectible receivables in compliance with tax regulations:\n"
             "- Transaction FP04: Allows mass and single write-off of unrecoverable open items.\n"
             "- Account Assignment: Automatically debits expense accounts for bad debt allowance and credits receivables.\n"
             "- Automatic Output Tax Adjustment: FI-CA recalculates and reverses output VAT/sales tax previously recognized, issuing tax adjustment postings to General Ledger tax accounts."),

            ("FI-CA Troubleshooting, Clarification Worklists, and Audit Reconciliation",
             "Senior operational practices for FI-CA stability:\n"
             "- Payment Clarification Worklist: Resolving unallocated receipts via FP05 clarification processing.\n"
             "- Subledger-GL Reconciliation: Verifying consistency between DFKKREP01 totals and GL balance sheet accounts using report RFKKGL00.\n"
             "- Document Lock Inspection: Diagnosing lock conflicts in SM12 and verifying RFC connections in SM59.")
        ]
    },
    {
        "filename": "SAP_BRIM_Convergent_Invoicing_CIT_BIT_Master_Architecture.pdf",
        "title": "SAP Convergent Invoicing (CI) Consumption & Billable Item Management Master Guide",
        "module": "CI / BRIM",
        "product": "SAP Convergent Invoicing",
        "topics": [
            ("Convergent Invoicing Architectural Overview & Core Workflow",
             "SAP Convergent Invoicing (CI) bridges the gap between rating/charging engines (SAP CC, external rating) and financial subledgers (FI-CA, General Ledger). CI consolidates high-volume usage, one-off, and recurring charges into clean customer invoices. Core flow:\n"
             "1. Consumption Items (CIT): Ingestion of unrated usage events.\n"
             "2. Rating: Translation of CITs into rated monetary charges.\n"
             "3. Billable Items (BIT): Management of rated charges across status lifecycles.\n"
             "4. Billing (FKKBIX_BILL_M): Aggregation of BITs into Billing Documents.\n"
             "5. Invoicing (FKKBIX_INV_M): Integration of billing documents, open items, taxes, and creation of Invoicing Documents (ERDK) and FI-CA items (DFKKOP)."),

            ("Consumption Item (CIT) Classes & Management (FKKBIX_CIT_CONF)",
             "Consumption Item Classes define the technical and business attributes of raw usage data:\n"
             "- Configuration: Executed via transaction FKKBIX_CIT_CONF.\n"
             "- Table Generation: The system generates physical database tables for each class: DFKKBIXCIT0 (Raw unrated items), DFKKBIXCIT2 (Rated items).\n"
             "- Ingestion Interfaces: High-performance RFC (BAPI_CTRAC_CONSUMPTION_ITEM), Web Services, or mass file upload (FKKBIX_CIT_UPLOAD).\n"
             "- Field Categories: Technical key fields (source transaction ID, timestamp), Consumption fields (duration, volume, unit of measurement), and Rating control fields."),

            ("Billable Item (BIT) Classes & Lifecycle Status Architecture",
             "Billable Item Classes structure rated monetary charges ready for customer billing:\n"
             "- Configuration: Defined via transaction FKKBIX_BIT_CONF in SPRO.\n"
             "- Status Architecture:\n"
             "  * Status 0: Raw (Table DFKKBIXBIT0) - Initial staged items awaiting validation.\n"
             "  * Status 1: Raw with Errors (Table DFKKBIXBIT1) - Validation failed (e.g. missing contract account, invalid transaction code).\n"
             "  * Status 2: Billable (Table DFKKBIXBIT2) - Validated, billable items ready for billing aggregation.\n"
             "  * Status 3: Billed (Table DFKKBIXBIT4) - Items successfully incorporated into a billing document.\n"
             "  * Status 4: Simulated (Table DFKKBIXBIT_SIM) - Used for bill simulation and forecasting.\n"
             "- Mass Creation: Executed via FKKBIX_BIT_CREATE or direct API integration."),

            ("Billable Item Types, Subtypes, and Selection Variants",
             "Categorizing and filtering billable items for targeted billing runs:\n"
             "- Billable Item Type: Classifies charges into business categories such as Usage Charges, Recurring Subscription Fees, One-off Activation Fees, Minimum Spend Surcharges, and Early Termination Penalties.\n"
             "- Billable Item Subtype: Provides granular sub-categorization for reporting and pricing differentiation.\n"
             "- Selection Variants: Configuration rules that filter specific BIT types and contract accounts for tailored billing cycles (e.g. monthly vs quarterly billing runs)."),

            ("Billing Process Mass Activity (FKKBIX_BILL_M)",
             "The Billing Process aggregates billable items into official Billing Documents:\n"
             "- Transaction: FKKBIX_BILL_M executes mass billing across parallel application server intervals.\n"
             "- Billing Document Architecture:\n"
             "  * Header Table: FKKBIX_BILLDOC_H (Billing document number, contract account, billing date, total amounts).\n"
             "  * Item Table: FKKBIX_BILLDOC_IT (Aggregated billing lines, main/subtransactions, tax codes, period coverage).\n"
             "  * Tax Table: FKKBIX_BILLDOC_TX (Calculated tax lines).\n"
             "- Billing Orders: Scheduling triggers that manage when contract accounts are due for billing.\n"
             "- Billing Reversal: Transaction FKKBIX_BILL_REV allows reversing billing documents, returning BITs to Billable status (Status 2)."),

            ("Invoicing Process Mass Activity (FKKBIX_INV_M)",
             "Invoicing is the culminating financial mass run in SAP BRIM:\n"
             "- Transaction: FKKBIX_INV_M executes mass invoicing across interval selections.\n"
             "- Invoicing Document Architecture: Header table ERDK, item table ERDZ.\n"
             "- Core Invoicing Functions:\n"
             "  1. Aggregation of Billing Documents: Pulls billing documents from CI and external billing sources.\n"
             "  2. Open Item Clearing: Applies clearing control (Posting Area 0150) to clear existing FI-CA credits against new charges.\n"
             "  3. Tax Determination: Calculates statutory sales taxes, VAT, or integrates with third-party tax engines.\n"
             "  4. Creation of FI-CA Subledger Items: Posts open receivables into DFKKOP.\n"
             "  5. Print Document Generation: Prepares print records for bill layout formatting.\n"
             "- Invoicing Reversal: Transaction FKKBIX_INV_REV reverses invoicing documents and un-clears associated FI-CA open items."),

            ("Convergent Invoicing Integration with SAP RAR (IFRS 15 / ASC 606)",
             "Compliance with statutory revenue recognition standards:\n"
             "- Revenue Accounting Items (RAI): CI generates RAIs representing order items, fulfillment items, and invoice items.\n"
             "- RAI Classes: Configured in CI to capture standalone selling prices (SSP) and performance obligations (POB).\n"
             "- RAI Monitor (FARR_RAI_MON): Administrative transaction to monitor, validate, and transfer RAIs from Convergent Invoicing to the SAP RAR engine.\n"
             "- Contract Modifications & Reversals: CI coordinates invoice reversals with RAR contract revisions to adjust deferred revenue balances."),

            ("Exception Handling, BIT Monitoring, and Clarification Processing",
             "Senior operational monitoring tools for CI health:\n"
             "- Transaction FKKBIX_BIT_EXCP: Inspects and corrects billable items in error status (Status 1).\n"
             "- Error Analysis: Common causes include unassigned main/subtransactions, missing provider contracts, and locked billing accounts.\n"
             "- Reprocessing: Corrected items are re-validated and promoted to Status 2 (Billable) without data loss.\n"
             "- Mass Analysis Reports: RFKKBIX_BIT_DISPLAY provides comprehensive filtering and auditing of item states."),

            ("BAdI Extension Architecture in Convergent Invoicing",
             "Key Business Add-Ins (BAdIs) for custom logic implementation:\n"
             "- FKKBIX_BIT_PREPARE: Custom enrichment and validation during billable item upload.\n"
             "- FKKBIX_BILL_CREATE: Intercepts billing document creation to apply custom discount calculations or customer grouping.\n"
             "- FKKBIX_INVOICING: Modifies invoicing document items (ERDZ), print layouts, or triggers external event notifications upon bill finalization.\n"
             "- Performance Rule: BAdI logic must be optimized for batch memory; database calls inside row loops are strictly prohibited."),

            ("CI Performance Optimization and Parallelization Tuning",
             "Maximizing mass billing and invoicing throughput:\n"
             "- Interval Tuning: Balance interval count with available background work processes (SM50/SM66).\n"
             "- Commit Frequency: Configure optimal commit counters in billing process customizing to prevent lock table overflow.\n"
             "- Table Archiving: Periodically archive processed billable items (DFKKBIXBIT4) using archiving object FKKBIXBIT to preserve query performance.")
        ]
    },
    {
        "filename": "SAP_BRIM_SOM_Subscription_Order_Management_Master_Guide.pdf",
        "title": "SAP Subscription Order Management (SOM) Master Configuration & Order Distribution Guide",
        "module": "SOM / BRIM",
        "product": "SAP S/4HANA BRIM",
        "topics": [
            ("SAP S/4HANA SOM Architecture & CRM One-Order Framework",
             "SAP Subscription Order Management (SOM) is the commercial front-end of SAP BRIM, built natively on the SAP S/4HANA CRM One-Order Framework. Core transaction objects include:\n"
             "- Solution Quotation (Transaction Type PRQ / BUS2000116): Bundles hardware, recurring subscription services, one-off professional services, and service contracts into a single unified customer quote.\n"
             "- Provider Order (Transaction Type PRVO / BUS2000269): Captures confirmed subscription agreements, contract terms, technical identifiers, pricing conditions, and payment configurations.\n"
             "- Provider Contract (Transaction Type PRVC / BUS2000270): The long-term operational contract object generated upon provider order activation, managing the active service lifecycle in S/4HANA."),

            ("Order Distribution Infrastructure (ODI) Master Architecture",
             "The Order Distribution Infrastructure (ODI) orchestrates the asynchronous provisioning and distribution of subscription orders across downstream BRIM components:\n"
             "- Document Distribution Schema: Configured in SPRO under Customer Management -> Transactions -> Settings for Subscription Transactions -> Document Distribution.\n"
             "- Distribution Step Sequences:\n"
             "  * Step 1: Distribution to SAP CC - Creates or updates the Subscriber Account, Provider Contract, and Allowance allocations in the CC Core Server via Web Services.\n"
             "  * Step 2: Distribution to SAP CI / FI-CA - Creates or updates the Provider Contract in FI-CA tables (FKKVKP, EVER) and registers contract account links.\n"
             "  * Step 3: Distribution to Logistics / SD - Triggers sales orders or outbound deliveries for physical equipment (e.g. SIM cards, smart meters, IoT devices).\n"
             "- Asynchronous Messaging: Decoupled via qRFC and background queues to guarantee zero order loss even during downstream system downtime."),

            ("ODI Monitoring, Error Handling, and Queue Management",
             "Managing and recovering provisioning workflows in production:\n"
             "- Transaction CRMD_ORDER: Inspects order status, fulfillment document flow, and provisioning status flags.\n"
             "- Application Log (SLG1): Object CRM_FS_DIST, subobject ODI provides granular traces of failed distribution steps, XML payloads, and return codes.\n"
             "- Transaction SMQ1 / SMQ2: Monitors outbound and inbound RFC queues for stuck distribution queues.\n"
             "- ODI Reprocessing: Administrators can manually re-trigger failed distribution steps directly from the order document flow once root causes are resolved."),

            ("Cross-Catalog Mapping (CCM) Configuration",
             "Cross-Catalog Mapping establishes the technical integration between SOM product masters and SAP CC pricing catalogs:\n"
             "- SOM Subscription Product: Defined in material master (MM01) with sales views and subscription attributes.\n"
             "- CCM Mapping: Maps SOM product items to specific SAP CC Charge Plans, Charges, and Allowance Plans.\n"
             "- Parameter Redefinition: Allows SOM commercial managers to redefine CC pricing parameters (e.g. customized monthly subscription fee, allowance quota) without modifying the CC pricing catalog.\n"
             "- Technical Subtransactions: Maps SOM charge items to Convergent Invoicing subtransactions (Posting Area 0020) for accurate GL account determination."),

            ("Technical Resource Management (TRM) and Identifiers",
             "Tracking technical network identifiers across order lifecycles:\n"
             "- Technical Resources: MSISDN telephone numbers, IMSI codes, IP addresses, MAC addresses, digital meter IDs.\n"
             "- TRM Pools: Configured in SPRO to manage resource availability, automatic allocation upon order entry, and reservation lifecycles.\n"
             "- Distribution to CC: The technical identifier is provisioned to SAP CC as the User Technical Identifier (UTI), enabling network rater routing."),

            ("Master Agreements (BUS2000268) in B2B Environments",
             "B2B enterprise subscription contract management:\n"
             "- Hierarchy: Master Agreements capture overarching legal and pricing terms negotiated with corporate enterprises.\n"
             "- Sharing Rules: Enables child accounts and branch offices to inherit discounted pricing terms, shared allowance pools, and customized invoicing profiles.\n"
             "- Invoice Splitting & Consolidation: Controls whether individual subsidiary contracts receive independent bills or are consolidated onto a single corporate collective invoice in Convergent Invoicing."),

            ("Subscription Contract Lifecycle & Change Processes",
             "Managing contract modifications throughout the subscriber lifecycle:\n"
             "- Change Process Framework: Configured in SPRO under Settings for Subscription Transactions -> Contract Changes -> Define Change Processes.\n"
             "- Standard Change Processes:\n"
             "  * Technical Change: Updating technical resources (e.g. SIM card swap, equipment upgrade).\n"
             "  * Contract Extension: Prolonging contract duration with revised renewal terms.\n"
             "  * Early Termination: Calculating cancellation penalties and immediately notifying SAP CC and CI.\n"
             "  * Product Upgrade / Downgrade: Transitioning between subscription tiers with automated allowance pro-rating.\n"
             "  * Partner / Address Relocation: Updating billing addresses and contract account assignments.\n"
             "- Validation BAdIs: CRM_ORDER_SAVE and CRM_SUBSCR_CHG intercept change requests to validate eligibility."),

            ("Mass Change Processing & Automated Contract Renewals",
             "Executing bulk operations across large subscriber bases:\n"
             "- Mass Change Tool (Transaction FP_MA_CHG / CRM_MASS_CHG): Allows updating pricing tiers, contract terms, or billing cycles across hundreds of thousands of active contracts.\n"
             "- Automatic Renewal Run: Background batch job evaluating contracts nearing expiration and triggering automated renewal processes based on contract cancellation notice terms."),

            ("Integration with Sales and Distribution (SD) and Logistics",
             "Hybrid order orchestration across physical goods and digital subscriptions:\n"
             "- Solution Quotation item determination: Distinguishes physical materials (Item Category TAN / SD order) from subscription products (Item Category PRVO).\n"
             "- Outbound Delivery: SD delivery (VL01N) creates shipping orders for hardware, serial number tracking, and physical goods issue.\n"
             "- Convergent Invoicing Integration: Hardware billing documents originating from SD are merged into Convergent Invoicing alongside monthly subscription charges, presenting a single invoice to the customer."),

            ("SOM Performance Optimization, Memory Tuning, and War Room Best Practices",
             "Senior architectural practices for SOM stability:\n"
             "- One-Order Buffer Management: Configure optimal memory settings in CRM_ORDER customizing to prevent memory bloat during mass order imports.\n"
             "- RFC Destination Tuning: Maintain high-throughput RFC configurations (SM59) between S/4HANA SOM and SAP CC Core Server.\n"
             "- Queue Slicing: Segment ODI distribution queues across separate prefix groups (e.g. ODI_CC_*, ODI_CI_*) to prevent backlog cascades across independent components.")
        ]
    },
    {
        "filename": "SAP_BRIM_End_to_End_Integration_and_SPRO_Cookbook.pdf",
        "title": "SAP BRIM End-to-End Integration, SPRO Customizing Cookbook & War-Room Guide",
        "module": "BRIM End-to-End",
        "product": "SAP BRIM",
        "topics": [
            ("End-to-End Data Flow Architecture across all 4 BRIM Pillars",
             "A comprehensive operational walkthrough of the complete SAP BRIM transaction lifecycle:\n"
             "1. Quote & Order (SOM): Customer accepts Solution Quotation (PRQ); Provider Order (PRVO) is confirmed and released.\n"
             "2. Order Distribution (ODI): Provisioning activates Provider Contract in SOM (PRVC), subscriber contract in CC, and contract account links in CI/FI-CA.\n"
             "3. Real-Time Consumption & Rating (CC): Network sends usage event via Diameter/Web Service. CC Guider locates contract via UTI; CC Rater executes price plan; CC Updater updates wallet/counters; CC Bulkloader outputs Billable Items.\n"
             "4. Billing (CI): Mass run FKKBIX_BILL_M groups billable items into Billing Documents.\n"
             "5. Invoicing (CI): Mass run FKKBIX_INV_M merges billing documents, applies clearing control, creates Invoicing Document (ERDK) and posts open items to FI-CA (DFKKOP).\n"
             "6. Receivables & Payments (FI-CA): Payment lot (FP05) or Direct Debit (FP35) clears open items via Clearing Control (Posting Area 0150).\n"
             "7. General Ledger Transfer: Mass run FPG1 transfers closed reconciliation keys to General Ledger (ACDOCA/BSEG).\n"
             "8. Statutory Revenue Recognition: CI transfers RAIs to SAP RAR (FARR_RAI_MON) for IFRS 15 compliance."),

            ("Master SPRO Navigation Dictionary for Senior BRIM Consultants",
             "Essential SPRO navigation paths across all modules:\n"
             "- Convergent Invoicing Billable Items: SPRO -> Financial Accounting -> Contract Accounts Receivable and Payable -> Convergent Invoicing -> Billable Items -> Basic Settings -> Define Billable Item Classes (FKKBIX_BIT_CONF).\n"
             "- Convergent Invoicing Invoicing Processes: SPRO -> Financial Accounting -> Contract Accounts Receivable and Payable -> Convergent Invoicing -> Invoicing -> Invoicing Processes -> Define Invoicing Processes.\n"
             "- FI-CA Main & Subtransactions: SPRO -> Financial Accounting -> Contract Accounts Receivable and Payable -> Basic Functions -> Open Item Management -> Maintain Transactions for Contract Accounts Receivable and Payable.\n"
             "- FI-CA Clearing Control: SPRO -> Financial Accounting -> Contract Accounts Receivable and Payable -> Basic Functions -> Open Item Management -> Clearing Control -> Define Clearing Variants.\n"
             "- SOM Order Distribution Infrastructure: SPRO -> Customer Management -> Transactions -> Settings for Subscription Transactions -> Document Distribution -> Maintain Distribution Schemas.\n"
             "- SOM Cross-Catalog Mapping: SPRO -> Customer Management -> Master Data -> Products -> Maintain Cross-Catalog Mapping."),

            ("Critical SAP BRIM Database Tables & Schema Dictionary",
             "Master reference of core database tables for data querying, reporting, and debugging:\n"
             "- Master Data: BUT000 (General BP), FKKVKP (Contract Account Partner Specific), FKKVK (Contract Account General), EVER (IS-U / Provider Contract links).\n"
             "- Convergent Invoicing: DFKKBIXBIT0 (Raw BITs), DFKKBIXBIT2 (Billable BITs), DFKKBIXBIT4 (Billed BITs), DFKKBIX_BILLDOC_H (Billing Header), DFKKBIX_BILLDOC_IT (Billing Items), ERDK (Invoicing Document Header), ERDZ (Invoicing Document Items).\n"
             "- FI-CA Financials: DFKKKO (FI-CA Document Header), DFKKOP (FI-CA Open Items), DFKKOPK (FI-CA GL Offset Line Items), DFKKREP01 (Reconciliation Key Totals Records).\n"
             "- Revenue Accounting: FARR_RAI_ORDER (Order RAIs), FARR_RAI_INVOICE (Invoice RAIs).\n"
             "- General Ledger: ACDOCA (Universal Journal Entry), BSEG (Accounting Document Segment)."),

            ("Production War-Room: Top 5 High-Impact Incidents & Rapid Resolution",
             "Step-by-step diagnostic workflows for mission-critical production issues:\n"
             "1. Billable Item Upload Blocked (Error in FKKBIX_BIT_EXCP): Check if Billable Item Class is active; verify main/subtransaction is maintained in Posting Area 0020 for Company Code; verify Contract Account is valid.\n"
             "2. ODI Step Distribution Timeout (Status Red in SLG1): Inspect RFC destination in SM59; verify CC Core Server Hazelcast partition health via 'admin.bat'; check for lock conflicts in SM12.\n"
             "3. Reconciliation Key Out of Balance during GL Transfer (FPG1 Error): Execute report RFKKGL00 to compare DFKKREP01 totals with DFKKOP items; identify manual adjustment discrepancies and post correction via FP01.\n"
             "4. Clearing Control Incorrectly Allocating Credits in FPMA: Inspect Clearing Variant configuration in Posting Area 0150; verify sorting rules by due date (FAEDN); check if open items have clearing restrictions.\n"
             "5. Hazelcast Cache Desynchronization across CC Instances: Execute 'admin.bat -cache -refresh' to flush Near Cache; verify cluster heartbeats and restart failed Dispatcher or Rater instance."),

            ("Performance Optimization & Scalability Best Practices for 8+ Year Architects",
             "Architectural benchmarks for enterprise RAG and SAP BRIM environments:\n"
             "- High-Volume Sizing: Sizing application servers for parallel processing (SM50), configuring interval ranges (FKK_INST) to avoid database hotspotting.\n"
             "- Database Partitioning: Partitioning DFKKOP, DFKKBIXBIT4, and ERDZ by fiscal year and company code.\n"
             "- Archiving Strategy: Implementing periodic data archiving routines for billed items and closed invoicing documents to maintain query execution times below 200ms.")
        ]
    }
]

def generate_pdf(manual_info):
    pdf_path = DOCS_DIR / manual_info["filename"]
    print(f"Generating PDF: {manual_info['filename']}...")
    doc = pymupdf.open()
    
    # 1. Title / Cover Page
    cover_page = doc.new_page(width=595, height=842) # A4
    cover_rect = pymupdf.Rect(50, 80, 545, 750)
    
    cover_text = (
        f"{manual_info['title']}\n\n"
        f"Product: {manual_info['product']}\n"
        f"Module: {manual_info['module']}\n"
        f"Audience: Senior SAP BRIM Enterprise Architects & Consultants (8+ Years Experience)\n"
        f"Classification: Enterprise Official Technical Handbook\n\n"
        "TABLE OF CONTENTS:\n"
    )
    for idx, (topic_title, _) in enumerate(manual_info["topics"], start=1):
        cover_text += f"Section {idx}. {topic_title}\n"
        
    cover_page.insert_textbox(cover_rect, cover_text, fontsize=12, fontname="helv")
    
    # 2. Topic Pages
    for idx, (topic_title, topic_body) in enumerate(manual_info["topics"], start=1):
        page = doc.new_page(width=595, height=842)
        rect = pymupdf.Rect(50, 50, 545, 790)
        
        page_content = (
            f"Section {idx}: {topic_title}\n\n"
            f"{topic_body}\n\n"
            f"Reference: SAP BRIM Technical Standard - {manual_info['module']} - Section {idx}\n"
        )
        page.insert_textbox(rect, page_content, fontsize=11, fontname="helv")
        
    doc.save(str(pdf_path))
    doc.close()
    print(f"Successfully generated: {pdf_path} (Pages: {len(manual_info['topics']) + 1})")

def main():
    for manual in BRIM_MANUALS:
        generate_pdf(manual)
    print("\nAll 5 BRIM Master Manuals successfully generated in knowledge_base/documents/.")

if __name__ == "__main__":
    main()
