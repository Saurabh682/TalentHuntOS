import uuid
from unittest.mock import patch

from app.candidates.rag import CandidateRAGPipeline
from app.candidates.service import create_candidate, delete_candidate
from app.infrastructure.db import SessionFactory, init_db


def test_hybrid_rag_ranks_field_evidence_and_requests_citations():
    init_db()
    suffix = uuid.uuid4().hex[:8]
    with patch("app.candidates.search.candidate_search_index.index_candidate", return_value=True):
        with SessionFactory() as db:
            engineer = create_candidate(
                db,
                full_name=f"Evidence Engineer {suffix}",
                email=f"evidence-engineer-{suffix}@example.com",
                current_title="Search Platform Engineer",
                location="Bengaluru, India",
                skills=["Python", "FastAPI", "ChromaDB", "Vector Search"],
                resume_text="Built production semantic retrieval and reranking pipelines using Python.",
            )
            marketer = create_candidate(
                db,
                full_name=f"Evidence Marketer {suffix}",
                email=f"evidence-marketer-{suffix}@example.com",
                current_title="Growth Marketing Manager",
                skills=["Campaign Strategy", "SEO"],
                resume_text="Led brand and demand generation programs.",
            )
            assert engineer is not None and marketer is not None

            captured_prompt = {}

            def fake_generate(*, prompt, **kwargs):
                captured_prompt["value"] = prompt
                return f"{engineer.full_name} has direct vector retrieval evidence [Candidate #{engineer.id} · Skills]."

            pipeline = CandidateRAGPipeline()
            with (
                patch.object(pipeline, "_semantic_scores", return_value={}),
                patch("app.candidates.rag.ai_engine.generate_response", side_effect=fake_generate),
            ):
                result = pipeline.query_candidate_database(
                    "Who has Python vector search and reranking experience?", db
                )

            assert result["sources"][0]["id"] == engineer.id
            assert result["retrieval"]["mode"] == "hybrid_keyword_vector"
            evidence_types = {item["source_type"] for item in result["sources"][0]["evidence"]}
            assert "skills" in evidence_types or "resume" in evidence_types
            assert "Every candidate-specific claim" in captured_prompt["value"]
            assert f"Candidate #{engineer.id}" in captured_prompt["value"]

            assert delete_candidate(db, engineer.id)
            assert delete_candidate(db, marketer.id)
