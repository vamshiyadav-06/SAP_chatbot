import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.sap_classifier import sap_classifier

client = TestClient(app)

def test_sap_classifier_acceptance():
    accepted_queries = [
        "What is SAP MM?",
        "Explain the 3-way match in purchasing",
        "How do I create a purchase order with ME21N?",
        "What is the difference between table MARA and MARC?",
        "Explain Universal Journal table ACDOCA in S/4HANA",
        "How does F110 automatic payment program work in SAP FI?",
        "Describe SAP Fiori launchpad architecture",
        "What is the purpose of SAP Basis transaction SM50?",
        "What are Infotypes in SAP HCM?",
        "Explain CDS views and RAP in modern ABAP"
    ]
    for q in accepted_queries:
        is_sap, msg = sap_classifier.classify(q)
        assert is_sap is True, f"Query '{q}' should be accepted as SAP-related"

def test_sap_classifier_refusal():
    rejected_queries = [
        "What is Python?",
        "Write me a birthday message for my sister.",
        "What is cricket?",
        "Who is Elon Musk?",
        "Give me a chocolate cake recipe.",
        "How is the weather today?",
        "Tell me a joke about cats."
    ]
    for q in rejected_queries:
        is_sap, msg = sap_classifier.classify(q)
        assert is_sap is False, f"Query '{q}' should be rejected"
        assert "I can only assist with SAP and SAP-related topics." in msg

def test_rag_endpoint_refusal():
    # Register/login user
    client.post("/api/auth/register", json={"email": "tester_rag@sap.com", "name": "RAG Tester", "password": "Password123!"})
    login_resp = client.post("/api/auth/login", json={"email": "tester_rag@sap.com", "password": "Password123!"}).json()
    token = login_resp["access_token"]

    resp = client.post(
        "/api/rag/query",
        json={"query": "Write me a birthday poem."},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "refusal"
    assert data["grounding_score"] == 0.0
    assert "I can only assist with SAP and SAP-related topics." in data["answer"]
    # Regular users never receive citations (the key is stripped), and a refusal has none anyway.
    assert not data.get("citations")
