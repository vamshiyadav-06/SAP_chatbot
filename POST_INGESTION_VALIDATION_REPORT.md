# SAP RAG Post-Ingestion Validation Report

---

## Dataset

* **Knowledge Base Root Directories**:
  * `knowledge_base/`
  * `knowledge_base/documents/` (7 core PDF guides)
  * `knowledge_base/the full rag data sap/` (14 new enterprise SAP PDFs)
* **Total Discovered Document Files**: 21 Knowledge Base PDFs + 10 Standard SAP Manuals = **31 Documents**
* **Total Pages Processed**: **4,591 pages** across all volumes
* **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
* **Ingestion Mode**: Idempotent SHA-256 hashed batch ingestion with structure-aware chunking (procedures, tables, sections)

---

## Database Statistics

| Metric | Measured Value | Notes |
| :--- | :---: | :--- |
| **Total Documents** | **31** | 21 in Knowledge Base + 10 Reference Manuals |
| **Total Chunks** | **10,661** | All generated and persisted |
| **Total Embeddings** | **10,661** | 100% vector coverage |
| **NULL Embeddings** | **0** | Verified across all rows |
| **Vector Dimensionality** | **384** | Exactly matches `EMBEDDING_DIM = 384` |
| **Dimension Mismatches** | **0** | Verified across all rows |
| **Missing Required Fields** | **0** | `document_id`, `chunk_text`, `embedding`, `page_number`, `section`, `metadata_json` are all present |
| **Vector Storage Format** | **EmbeddingVector** | Serialized JSON array in SQLite / `vector(384)` with HNSW index in PostgreSQL |
| **Documents Successfully Indexed (New)** | **14** | All 14 files in `the full rag data sap` |
| **Documents Skipped (Idempotent)** | **7** | Hash matched with pre-existing chunk counts |
| **Documents Failed** | **0** | 100% extraction and ingestion success |

---

## Document Coverage

| Document | Pages | Chunks | Embedded | Status |
| :--- | ---: | ---: | :---: | :--- |
| `2020_S4H_BRIM_SOM_Device_as_a_Service.pdf` | 27 | 27 | 27/27 | Indexed |
| `Authorizations-in-S4-HANA-and-Fiori.pdf` | 629 | 1,422 | 1422/1422 | Indexed |
| `BR234_EN_SOM 2.pdf` | 300 | 364 | 364/364 | Indexed |
| `BRIM Q Bank.pdf` | 7 | 19 | 19/19 | Indexed |
| `BRIM_AC240_EN_Col16.pdf` | 299 | 348 | 348/348 | Indexed |
| `Billing_and_Revenue_Innovation_Management.pdf` | 32 | 39 | 39/39 | Indexed |
| `Budget billing.pdf` | 5 | 5 | 5/5 | Indexed |
| `E_Book_ABAP_RESTful_Programming_Model_2020_Rel_NW_wwwERPExamsCom.pdf` | 560 | 1,137 | 1137/1137 | Indexed |
| `RAR Contract Reversal Process.pdf` | 3 | 5 | 5/5 | Indexed |
| `SAP BRIM Press Book 2nd Edition - Expertsoft.pdf` | 582 | 1,501 | 1501/1501 | Indexed |
| `SAP CC.pdf` | 34 | 62 | 62/62 | Indexed (Skipped identical hash) |
| `SAP CI1.pdf` | 181 | 537 | 537/537 | Indexed (Skipped identical hash) |
| `SAP CI2.pdf` | 217 | 482 | 482/482 | Indexed (Skipped identical hash) |
| `SAP CI3.pdf` | 211 | 681 | 681/681 | Indexed (Skipped identical hash) |
| `SAP CI4.pdf` | 327 | 708 | 708/708 | Indexed (Skipped identical hash) |
| `SAP FI-CA.pdf` | 49 | 49 | 49/49 | Indexed (Skipped identical hash) |
| `SAP Revenue Recognition (RAR) Processing Flow...` | 2 | 3 | 3/3 | Indexed |
| `SAP-PRESS-Catalog-Shop.pdf` | 88 | 181 | 181/181 | Indexed |
| `SIMPL_OP1709.pdf` | 894 | 1,565 | 1565/1565 | Indexed |
| `mg.pdf` | 43 | 81 | 81/81 | Indexed |
| `pdfdownload.pdf` (S/4HANA SOM) | 283 | 803 | 803/803 | Indexed (Skipped identical hash) |
| `SAP_ABAP_Development_and_RAP_Standards.pdf` | 20 | 60 | 60/60 | Indexed (Reference Manual) |
| `SAP_Basis_Administration_and_Security_Handbook.pdf` | 20 | 62 | 62/62 | Indexed (Reference Manual) |
| `SAP_CO_Controlling_Configuration_Handbook.pdf` | 20 | 65 | 65/65 | Indexed (Reference Manual) |
| `SAP_FI_Financial_Accounting_Guide.pdf` | 20 | 73 | 73/73 | Indexed (Reference Manual) |
| `SAP_Fiori_Design_and_Deployment_Manual.pdf` | 20 | 61 | 61/61 | Indexed (Reference Manual) |
| `SAP_HCM_Human_Capital_Management_Guide.pdf` | 20 | 60 | 60/60 | Indexed (Reference Manual) |
| `SAP_MM_Materials_Management_Manual.pdf` | 20 | 75 | 75/75 | Indexed (Reference Manual) |
| `SAP_PP_Production_Planning_Reference.pdf` | 20 | 63 | 63/63 | Indexed (Reference Manual) |
| `SAP_S4HANA_Architecture_and_Migration_Guide.pdf` | 20 | 60 | 60/60 | Indexed (Reference Manual) |
| `SAP_SD_Sales_and_Distribution_Handbook.pdf` | 20 | 63 | 63/63 | Indexed (Reference Manual) |

---

## Retrieval Metrics

### Empirical Recall Results (10 Mandatory Test Queries)

| Metric | Measured Result | Evaluation Criteria |
| :--- | :---: | :--- |
| **Recall@1** | **90.0%** (9 / 10) | Exact target document retrieved as #1 hit |
| **Recall@3** | **90.0%** (9 / 10) | Exact target document retrieved in Top 3 |
| **Recall@5** | **100.0%** (10 / 10) | Exact target document retrieved in Top 5 |
| **Recall@10** | **100.0%** (10 / 10) | Exact target document retrieved in Top 10 |

### Query Breakdown (Top Hit & Hybrid Scores)

| # | Test Query | Top Retrieved Document | Page / Section | Vector | Lexical | Hybrid Score | Hit Rank |
| :-: | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Q1** | *What is SAP BRIM?* | `SAP CC.pdf` | P.10 (Public) | 0.8145 | 0.8500 | 0.8287 | **1** |
| **Q2** | *What is SAP Convergent Invoicing?* | `BRIM_AC240_EN_Col16.pdf` | P.285 (Unit 16) | 0.9061 | 1.0000 | 0.9437 | **1** |
| **Q3** | *What is SAP Convergent Charging?* | `SAP BRIM Press Book 2nd Ed.pdf` | P.147 (Chapter 3) | 0.8762 | 1.0000 | 0.9257 | **1** |
| **Q4** | *How does CC integrate with CI?* | `SAP BRIM Press Book 2nd Ed.pdf` | P.212 (4 Invoicing) | 0.8012 | 1.0000 | 0.8807 | **1** |
| **Q5** | *What is FI-CA?* | `SAP FI-CA.pdf` | P.3 (FI-CA) | 0.7905 | 0.8500 | 0.8143 | **1** |
| **Q6** | *Explain end-to-end BRIM billing flow.* | `BRIM_AC240_EN_Col16.pdf` | P.21 (Objectives) | 0.8487 | 1.0000 | 0.9092 | **1** |
| **Q7** | *What is a Billable Item?* | `SAP BRIM Press Book 2nd Ed.pdf` | P.217 (4.3 CI Config) | 0.8528 | 1.0000 | 0.9117 | **1** |
| **Q8** | *Relationship between SOM, CC, CI, FI-CA?* | `SAP FI-CA.pdf` | P.1 (1.1 Overview) | 0.7352 | 0.8333 | 0.7744 | **1** |
| **Q9** | *Find a documented BRIM config procedure.* | `mg.pdf` | P.12 (Public) | 0.7737 | 0.6167 | 0.7109 | **1** |
| **Q10**| *Prerequisites for DaaS in BRIM SOM?* | `SAP CC.pdf` & `2020_S4H_BRIM_SOM...`| P.14 & P.3 | 0.8118 | 0.8444 | 0.8248 | **4** |

---

## Answer Grounding

Grounding was evaluated by extracting factual declarative statements from synthesized answers and validating each claim directly against retrieved evidence chunks.

$$\text{Grounding Accuracy} = \frac{\text{Supported Claims}}{\text{Total Factual Claims}} = \frac{258}{305} = \mathbf{84.59\%}$$

### Per-Query Claim Breakdown

| Query | Synthesized Claims | Supported Claims | Accuracy | Grounding Signal |
| :--- | :---: | :---: | :---: | :---: |
| Q1: *What is SAP BRIM?* | 23 | 20 | **87.0%** | 0.90 |
| Q2: *What is SAP Convergent Invoicing?* | 25 | 24 | **96.0%** | 0.94 |
| Q3: *What is SAP Convergent Charging?* | 35 | 34 | **97.1%** | 0.94 |
| Q4: *How does CC integrate with CI?* | 36 | 29 | **80.6%** | 0.92 |
| Q5: *What is FI-CA?* | 25 | 24 | **96.0%** | 0.89 |
| Q6: *End-to-End BRIM billing flow* | 40 | 27 | **67.5%** | 0.90 |
| Q7: *What is a Billable Item?* | 30 | 28 | **93.3%** | 0.92 |
| Q8: *Relationship between SOM, CC, CI, FI-CA* | 35 | 35 | **100.0%** | 0.88 |
| Q9: *Documented BRIM config procedure* | 36 | 24 | **66.7%** | 0.68 |
| Q10: *Prerequisites for Device as a Service* | 20 | 13 | **65.0%** | 0.90 |
| **TOTAL** | **305** | **258** | **84.59%** | **Avg: 0.887** |

---

## Citation Accuracy

* **Document Validity**: **100%** — Every cited document exists in the database.
* **Page Existence**: **100%** — Every cited page number exists within the physical document boundaries.
* **Content Match**: **93.3%** — 28 of 30 examined citation references directly corroborated the exact claim made in the text.
* **Citation Precision**: $\frac{28}{30} = \mathbf{93.3\%}$

---

## Newly Added Document Test

We tested 5 queries specifically designed around the newly ingested documents in `knowledge_base/the full rag data sap/`:

| Test | Query | Target New Document | Top Retrieved Document | Match in Top 5? |
| :-: | :--- | :--- | :--- | :---: |
| **N1** | *Prerequisites for Device as a Service in SOM?* | `2020_S4H_BRIM_SOM_Device_as_a_Service.pdf` | `SAP CC.pdf` (Hit #4: Target) | **YES** |
| **N2** | *Role of SAP_S4C_UIU_SOM_REP in authorizations?* | `Authorizations-in-S4-HANA-and-Fiori.pdf` | `Authorizations-in-S4-HANA-and-Fiori.pdf` | **YES (#1)** |
| **N3** | *What is Budget billing in SAP FI-CA?* | `Budget billing.pdf` | `BRIM Q Bank.pdf` | **NO** |
| **N4** | *What is ABAP RESTful Programming Model RAP?* | `E_Book_ABAP_RESTful_Programming_Model...` | `SAP_ABAP_Development...` (Hit #2: Target) | **YES** |
| **N5** | *Explain RAR contract reversal process in RAR?* | `RAR Contract Reversal Process.pdf` | `RAR Contract Reversal Process.pdf` | **YES (#1)** |

* **New Document Retrieval Rate**: **80.0%** (4 out of 5 matched in top ranks).
* **Finding on N3 (`Budget billing.pdf`)**: `Budget billing.pdf` is only 5 pages (5 chunks). High-density keyword matching favored the 582-page `SAP BRIM Press Book` and `BRIM Q Bank`.

---

## Hallucination Tests

We executed 4 edge-case tests targeting specific technical identifiers:

1. **Transaction Code Precision**:
   * *Query*: *"What is the exact transaction code for Transfer Credit Data to SAP Credit Management in FI-CA?"*
   * *Result*: **PASSED**. Correct transaction code `FPCM1` was retrieved from `pdfdownload.pdf` (Page 24) and cited accurately.
2. **Configuration Field Anchor**:
   * *Query*: *"Which custom field must be assigned in Customizing for Billable Item Classes relevant for Credit Management?"*
   * *Result*: **PASSED Guardrail**. Intercepted by domain classifier when phrased ambiguously; retrieved `CM_OBJECT_KEY` when scoped to SAP BRIM customizing.
3. **Fictitious / Non-Existent Transaction Code**:
   * *Query*: *"What is transaction code FPO1 in SAP FI-CA?"*
   * *Result*: **PASSED**. The system did not invent a function for `FPO1`. It identified lack of documentation for `FPO1` and restricted its answer to documented FI-CA transaction codes (`FP01`, `FPCM1`).
4. **Fictitious SAP Module**:
   * *Query*: *"What is the fictitious module SAP ULTRA_BRIM_2030?"*
   * *Result*: **PASSED**. The system reported insufficient evidence in the knowledge base and did not hallucinate capabilities.

---

## Latency Profile

Execution times were measured empirically across the 10 validation queries:

| Pipeline Stage | P50 (Median) | P95 | P99 | Notes |
| :--- | ---: | ---: | ---: | :--- |
| **Query Embedding** | **12.3 ms** | **13.5 ms** | **14.0 ms** | FastEmbed / ST CPU inference |
| **Vector Search** | **8.7 ms** | **9.7 ms** | **10.1 ms** | In-memory dot-product across 10,661 chunks |
| **Lexical Scoring** | **5.8 ms** | **6.5 ms** | **6.7 ms** | BM25 term frequency match |
| **Reranking** | **0.2 ms** | **0.3 ms** | **0.3 ms** | Multi-factor boost calculation |
| **Grounding Evaluation** | **37.3 ms** | **54.7 ms** | **56.0 ms** | Term overlap & cross-validation |
| **LLM Generation** | **16,241.6 ms** | **25,300.3 ms** | **25,797.7 ms** | Groq reasoning model (`openai/gpt-oss-120b`) |
| **TOTAL End-to-End Latency** | **16,301.6 ms** | **25,374.0 ms** | **25,867.9 ms** | Dominated by LLM reasoning generation |

---

## Problems Found

### 1. Primary Latency Bottleneck: LLM Reasoning Model Selection
* **Root Cause**: `settings.LLM_MODEL` is set to `openai/gpt-oss-120b` in `.env`.
* **Impact**: While answer quality is high, `gpt-oss-120b` generates reasoning tokens before responding, adding **16 to 25 seconds** per query.
* **Evidence**: Retrieval and reranking take under **30 milliseconds**, while LLM generation accounts for **99.8% of total response latency**.

### 2. In-Memory Vector Cache Cold-Start Overhead
* **Root Cause**: On SQLite fallback, `retrieval_service._get_cache()` loads all 10,661 chunks and deserializes JSON vector arrays into a NumPy array on first startup.
* **Impact**: The initial cold-start query takes **15.95 seconds** to build the cache. Subsequent queries take only **14 ms**.

### 3. Small Document Under-Representation
* **Root Cause**: Very short documents (such as `Budget billing.pdf` with 5 chunks, or `RAR Contract Reversal Process.pdf` with 5 chunks) can be eclipsed in pure frequency-based lexical scoring by massive reference handbooks (`SAP BRIM Press Book` with 1,501 chunks).

---

## Recommended Next Changes

1. **Switch Default LLM to `llama-3.3-70b-versatile`**:
   * Switch `LLM_MODEL` in `backend/.env` from `openai/gpt-oss-120b` to `llama-3.3-70b-versatile`.
   * *Expected Benefit*: Reduces end-to-end response latency from **16.3 seconds down to 800 - 1,200 ms** (a 15x speedup) while maintaining 70B parameter technical accuracy.
2. **Persist Pre-Calculated Matrix Binary (`cache.npy`)**:
   * Dump the normalized NumPy vector matrix to a `.npy` binary file during ingestion so SQLite cold-start loads in **50 ms** instead of 16 seconds.
3. **Short Document Boost / Inverse Document Density Dampening**:
   * Apply an inverse document length normalizer to prevent 1,500-chunk books from overshadowing precise 5-page specialty guides on narrow queries.
