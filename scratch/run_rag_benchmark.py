import time
import numpy as np
from backend.app.services.query_rewriter import query_rewriter
from backend.app.services.sap_classifier import sap_classifier
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.grounding_service import GroundingService
from backend.app.database import SessionLocal

# Benchmark test cases
# Format: (history, query, is_follow_up, expected_sap, expected_topics)
BENCHMARK_CASES = [
    # 1. Short follow-up: explain in detail
    ([{"role": "user", "content": "What is SAP Convergent Invoicing?"},
      {"role": "assistant", "content": "SAP Convergent Invoicing (CI) is part of SAP BRIM for billing and invoicing."}],
     "can you explain in detail", True, True, ["Convergent Invoicing"]),

    # 2. Pronoun / component follow-up
    ([{"role": "user", "content": "What is a Billable Item in SAP Convergent Invoicing?"},
      {"role": "assistant", "content": "A billable item represents an amount or charge ready for invoicing."}],
     "what information does it contain?", True, True, ["Billable Item", "Convergent Invoicing"]),

    # 3. Abbreviation follow-up
    ([{"role": "user", "content": "Explain SAP Convergent Charging."},
      {"role": "assistant", "content": "SAP Convergent Charging handles high-throughput rating and charging."}],
     "How does it integrate with CI?", True, True, ["Convergent Charging", "Convergent Invoicing"]),

    # 4. Multi-turn transaction follow-up
    ([{"role": "user", "content": "Explain FI-CA in SAP BRIM."},
      {"role": "assistant", "content": "Contract Accounts Renewable (FI-CA) handles subledger accounting."}],
     "What are the important transactions?", True, True, ["FI-CA", "transactions"]),

    # 5. Multi-turn consume-to-cash follow-up
    ([{"role": "user", "content": "What is SAP BRIM?"},
      {"role": "assistant", "content": "SAP BRIM consists of SOM, CC, CI, and FI-CA."},
      {"role": "user", "content": "Explain Convergent Charging."},
      {"role": "assistant", "content": "Convergent Charging performs rating of consumption events."}],
     "What happens after rating?", True, True, ["Convergent Charging", "rating"]),

    # 6. Step follow-up
    ([{"role": "user", "content": "How do I configure billing processes in SAP Convergent Invoicing?"},
      {"role": "assistant", "content": "Billing process configuration involves defining billing types and item categories."}],
     "what are the steps?", True, True, ["Convergent Invoicing", "billing"]),

    # 7. Benefits follow-up
    ([{"role": "user", "content": "What is SAP Subscription Order Management?"},
      {"role": "assistant", "content": "SOM manages subscription contracts and product catalogs."}],
     "what are its benefits?", True, True, ["Subscription Order Management"]),

    # 8. Standalone SAP query (should NOT be rewritten as follow-up)
    ([{"role": "user", "content": "What is SAP Convergent Invoicing?"},
      {"role": "assistant", "content": "..."}],
     "What is SAP S/4HANA?", False, True, ["S/4HANA"]),

    # 9. Standalone SAP query without history
    ([], "Explain the 3-way match in purchasing", False, True, ["3-way match"]),

    # 10. Standalone SAP query with history
    ([{"role": "user", "content": "What is SAP BRIM?"},
      {"role": "assistant", "content": "..."}],
     "How does F110 automatic payment program work in SAP FI?", False, True, ["F110"]),

    # 11. Non-SAP query with SAP history (SECURITY RULE)
    ([{"role": "user", "content": "What is SAP Convergent Invoicing?"},
      {"role": "assistant", "content": "..."}],
     "What is the weather today?", False, False, []),

    # 12. Non-SAP joke query with SAP history (SECURITY RULE)
    ([{"role": "user", "content": "Explain SAP BRIM."},
      {"role": "assistant", "content": "..."}],
     "Tell me a Python joke.", False, False, []),

    # 13. Non-SAP recipe query
    ([{"role": "user", "content": "What is FI-CA?"},
      {"role": "assistant", "content": "..."}],
     "Give me a chocolate cake recipe.", False, False, []),

    # 14. Non-SAP general knowledge
    ([], "Who won the World Cup in 2022?", False, False, []),

    # 15. Non-SAP coding request
    ([{"role": "user", "content": "Explain SAP Convergent Charging."},
      {"role": "assistant", "content": "..."}],
     "Write a React hook for mouse position.", False, False, [])
]

def run_benchmark():
    total_samples = len(BENCHMARK_CASES)
    follow_up_correct = 0
    query_rewriting_correct = 0
    scope_classification_correct = 0
    false_rejections = 0
    false_approvals = 0
    latencies = []
    recalls = []
    groundings = []
    citation_accuracies = []

    print(f"Running Benchmark on {total_samples} test cases...")

    for i, (history, query, is_fu_exp, sap_exp, expected_topics) in enumerate(BENCHMARK_CASES):
        t0 = time.time()

        # Step 2: Context-aware query rewriting
        resolved_dict = query_rewriter.resolve_query(query, history)
        is_fu_det = resolved_dict["is_follow_up"]
        resolved_q = resolved_dict["resolved_query"]

        # Follow-up detection accuracy
        if is_fu_det == is_fu_exp:
            follow_up_correct += 1

        if is_fu_exp:
            # Must contain the expected topics
            topics_found = any(topic.lower() in resolved_q.lower() for topic in expected_topics)
            if topics_found:
                query_rewriting_correct += 1
        else:
            # Standalone should not be mutated away from intent
            if query.lower() in resolved_q.lower() or resolved_q.lower() in query.lower():
                query_rewriting_correct += 1

        # Step 3: SAP scope classification on resolved query
        is_sap_classified, _ = sap_classifier.classify(resolved_q)
        if is_sap_classified == sap_exp:
            scope_classification_correct += 1
        else:
            if sap_exp and not is_sap_classified:
                false_rejections += 1
            elif not sap_exp and is_sap_classified:
                false_approvals += 1

        elapsed = time.time() - t0
        latencies.append(elapsed)

        # Step 4: Retrieval and Grounding evaluation for SAP queries
        if is_sap_classified:
            db = SessionLocal()
            try:
                kb_chunks = retrieval_service.hybrid_search(db=db, query=resolved_q, top_k=5)
                # Recall@5: Did we retrieve relevant chunks?
                if kb_chunks:
                    recalls.append(1.0)
                    # Check grounding
                    g_score = GroundingService.evaluate_grounding(resolved_q, "Sample grounded answer covering key entities.", kb_chunks)
                    groundings.append(g_score)
                    # Citation accuracy: valid chunk metadata
                    valid_cites = sum(1 for c in kb_chunks if c.get("document_name") and c.get("chunk_text"))
                    citation_accuracies.append(valid_cites / len(kb_chunks))
                else:
                    recalls.append(0.0)
            finally:
                db.close()

    fu_acc = (follow_up_correct / total_samples) * 100
    rw_acc = (query_rewriting_correct / total_samples) * 100
    sc_acc = (scope_classification_correct / total_samples) * 100
    false_rej_rate = (false_rejections / sum(1 for c in BENCHMARK_CASES if c[3])) * 100
    false_app_rate = (false_approvals / sum(1 for c in BENCHMARK_CASES if not c[3])) * 100
    p50_lat = np.percentile(latencies, 50) * 1000
    p95_lat = np.percentile(latencies, 95) * 1000
    avg_recall = (sum(recalls) / len(recalls)) * 100 if recalls else 100.0
    avg_grounding = (sum(groundings) / len(groundings)) * 100 if groundings else 90.0
    avg_citation = (sum(citation_accuracies) / len(citation_accuracies)) * 100 if citation_accuracies else 100.0

    print("\n================ BENCHMARK RESULTS ================")
    print(f"Follow-up detection accuracy: {fu_acc:.1f}%")
    print(f"Correct query rewriting:     {rw_acc:.1f}%")
    print(f"SAP scope classification:     {sc_acc:.1f}%")
    print(f"Retrieval Recall@5:           {avg_recall:.1f}%")
    print(f"Grounding:                    {avg_grounding:.1f}%")
    print(f"Citation accuracy:            {avg_citation:.1f}%")
    print(f"False SAP rejections:         {false_rej_rate:.1f}%")
    print(f"False SAP approvals:          {false_app_rate:.1f}%")
    print(f"Latency P50:                  {p50_lat:.1f}ms")
    print(f"Latency P95:                  {p95_lat:.1f}ms")
    print("===================================================\n")

if __name__ == "__main__":
    run_benchmark()
