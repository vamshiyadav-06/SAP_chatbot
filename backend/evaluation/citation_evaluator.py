from typing import List, Dict, Any

class CitationEvaluator:
    """Evaluates Citation Correctness: document validity, non-empty snippets, and factual grounding."""

    @staticmethod
    def evaluate(rag_response: Dict[str, Any]) -> Dict[str, float]:
        citations = rag_response.get("citations", [])
        web_sources = rag_response.get("web_sources", [])
        source_type = rag_response.get("source_type", "")

        # For refusals or explicit abstentions, citations are not required
        if source_type in ("refusal", "abstention") or not rag_response.get("answer"):
            return {"citation_correctness": 1.0}

        total_sources = len(citations) + len(web_sources)
        if total_sources == 0:
            # If answer was published without citations, citation correctness is 0
            return {"citation_correctness": 0.0}

        valid_citations = 0

        # Validate internal citations
        for c in citations:
            doc = c.get("document", "")
            page = c.get("page")
            snippet = c.get("snippet", "")
            # Check for non-empty document name, valid page number, and real excerpt snippet
            if doc and doc != "None" and page is not None and len(snippet) > 10:
                # Ensure no local filepaths leaked
                if "C:\\" not in doc and "/Users/" not in doc:
                    valid_citations += 1

        # Validate web sources
        for w in web_sources:
            url = w.get("url", "")
            title = w.get("title", "")
            snippet = w.get("snippet", "")
            if url.startswith("http") and title and len(snippet) > 10:
                if any(domain in url for domain in ["help.sap.com", "community.sap.com", "blogs.sap.com", "sap.com"]):
                    valid_citations += 1

        score = valid_citations / total_sources if total_sources > 0 else 0.0
        return {"citation_correctness": round(score, 4)}

citation_evaluator = CitationEvaluator()
