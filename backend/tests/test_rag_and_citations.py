import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

@pytest.fixture
def auth_headers():
    client.post("/api/auth/register", json={"email": "rag_evaluator@sap.com", "name": "Evaluator", "password": "Password123!"})
    login_resp = client.post("/api/auth/login", json={"email": "rag_evaluator@sap.com", "password": "Password123!"}).json()
    return {"Authorization": f"Bearer {login_resp['access_token']}"}

def test_rag_knowledge_base_retrieval(auth_headers):
    # Query clearly present in SAP MM manual
    resp = client.post(
        "/api/rag/query",
        json={"query": "Explain the 3-Way Match verification process in SAP MM"},
        headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["source_type"] == "knowledge_base"
    assert data["grounding_score"] >= 0.60
    assert len(data["citations"]) > 0

    # Verify citation structure: safe metadata only
    first_citation = data["citations"][0]
    assert "document" in first_citation
    assert "page" in first_citation
    assert "section" in first_citation
    assert "snippet" in first_citation
    assert "SAP_MM" in first_citation["document"]
    # Verify no raw filepath leaks
    assert "C:\\" not in first_citation["document"]
    assert "/Users/" not in first_citation["document"]

def test_rag_web_fallback_for_external_topics(auth_headers):
    # Query for SAP Ariba cloud procurement (not in our 10 primary on-prem manuals)
    resp = client.post(
        "/api/rag/query",
        json={"query": "How does SAP Ariba integrate with S/4HANA for supplier sourcing?"},
        headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["source_type"] == "web"
    assert data["grounding_score"] > 0.0
    assert len(data["web_sources"]) > 0
    assert any("sap.com" in w["domain"] for w in data["web_sources"])
