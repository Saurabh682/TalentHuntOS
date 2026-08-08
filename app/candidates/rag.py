"""LlamaIndex RAG pipeline for natural language Q&A over Candidate profiles."""

import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.candidates.service import list_candidates, get_candidate
from app.ai.engine import ai_engine

logger = logging.getLogger("talenthunt.candidates.rag")


class CandidateRAGPipeline:
    """LlamaIndex candidate retrieval-augmented generation pipeline."""

    def _build_candidate_document_content(self, cand: Any) -> str:
        """Serialize a Candidate object into a structured document text for LlamaIndex."""
        profile_summary = cand.profile.summary if cand.profile and cand.profile.summary else ""
        resume_text = cand.profile.resume_text if cand.profile and cand.profile.resume_text else ""
        ai_eval = cand.profile.ai_evaluation if cand.profile and cand.profile.ai_evaluation else ""

        skills = []
        if cand.profile and cand.profile.skills_json:
            try:
                skills = json.loads(cand.profile.skills_json)
            except Exception:
                skills = []

        experiences_text = []
        for exp in cand.experiences:
            exp_str = f"- {exp.title} at {exp.company} ({exp.start_date or ''} - {exp.end_date or 'Present'}): {exp.description or ''}"
            experiences_text.append(exp_str)

        educations_text = []
        for edu in cand.educations:
            edu_str = f"- {edu.degree or 'Degree'} in {edu.field_of_study or 'Field'} from {edu.institution} ({edu.start_year or ''} - {edu.end_year or ''})"
            educations_text.append(edu_str)

        notes_text = [f"- [{n.created_at.strftime('%Y-%m-%d')}] {n.author}: {n.content}" for n in cand.notes]

        doc_parts = [
            f"=== CANDIDATE PROFILE #{cand.id} ===",
            f"Full Name: {cand.full_name}",
            f"Current Role: {cand.current_title or 'N/A'} at {cand.current_company or 'N/A'}",
            f"Location: {cand.location or 'N/A'}",
            f"Experience: {cand.experience_years or 0} years",
            f"Email: {cand.email or 'N/A'}",
            f"Status: {cand.status}",
            f"Skills: {', '.join(skills)}" if skills else "",
            f"Headline: {cand.profile.headline if cand.profile else ''}",
            f"Summary: {profile_summary}",
            f"AI Evaluation: {ai_eval}",
            "\nWork Experience:\n" + "\n".join(experiences_text) if experiences_text else "",
            "\nEducation:\n" + "\n".join(educations_text) if educations_text else "",
            "\nRecruiter Notes:\n" + "\n".join(notes_text) if notes_text else "",
            "\nResume Content:\n" + resume_text if resume_text else "",
        ]

        return "\n".join([p for p in doc_parts if p.strip()])

    def query_candidate_database(self, query: str, db: Session) -> Dict[str, Any]:
        """Perform RAG Q&A across all candidates in the CRM database using LlamaIndex."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.candidates.models import Candidate

        stmt = select(Candidate).options(
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations),
            selectinload(Candidate.notes),
            selectinload(Candidate.profile)
        ).limit(200)
        candidates = db.scalars(stmt).unique().all()
        if not candidates:
            return {
                "query": query,
                "answer": "No candidates found in the database to answer your query.",
                "sources": [],
            }

        documents = []
        doc_map = {}

        try:
            from llama_index.core import Document, VectorStoreIndex, Settings

            for cand in candidates:
                text_content = self._build_candidate_document_content(cand)
                doc = Document(
                    text=text_content,
                    doc_id=str(cand.id),
                    metadata={
                        "candidate_id": cand.id,
                        "full_name": cand.full_name,
                        "current_title": cand.current_title or "",
                    },
                )
                documents.append(doc)
                doc_map[cand.id] = cand

            # Build in-memory LlamaIndex VectorStoreIndex
            index = VectorStoreIndex.from_documents(documents)
            retriever = index.as_retriever(similarity_top_k=5)
            nodes = retriever.retrieve(query)

            context_texts = []
            source_candidates = []
            for node in nodes:
                cand_id = node.metadata.get("candidate_id")
                score = round(float(node.score or 0.0) * 100, 1) if hasattr(node, "score") else 85.0
                cand_obj = doc_map.get(cand_id)
                if cand_obj:
                    source_candidates.append({
                        "id": cand_obj.id,
                        "full_name": cand_obj.full_name,
                        "current_title": cand_obj.current_title,
                        "relevance_score": score,
                    })
                context_texts.append(f"Source Document (Candidate #{cand_id}):\n{node.text}")

            context_str = "\n\n---\n\n".join(context_texts)

            prompt = (
                f"You are an expert AI recruiter assistant for TalentHunt OS.\n"
                f"Based on the following candidate database profiles:\n\n"
                f"{context_str}\n\n"
                f"Please answer the user's question accurately and concisely:\n"
                f"Question: {query}\n\n"
                f"Answer with specific candidate names, experience details, and clear justification."
            )

            answer = ai_engine.generate_response(prompt=prompt)

            return {
                "query": query,
                "answer": answer,
                "sources": source_candidates,
            }

        except Exception as e:
            logger.warning(f"LlamaIndex execution fallback due to: {e}. Falling back to AI engine direct retrieval.")
            # Fallback answer synthesis using AI engine
            context_summary = []
            for cand in candidates[:10]:
                context_summary.append(f"Candidate #{cand.id}: {cand.full_name} ({cand.current_title}), Skills/Summary: {cand.profile.summary if cand.profile else ''}")

            prompt = (
                f"You are an AI recruiter assistant.\n"
                f"Candidate list:\n" + "\n".join(context_summary) + "\n\n"
                f"Question: {query}\n"
                f"Provide a helpful answer."
            )
            answer = ai_engine.generate_response(prompt=prompt)
            return {
                "query": query,
                "answer": answer,
                "sources": [{"id": c.id, "full_name": c.full_name, "current_title": c.current_title} for c in candidates[:5]],
            }

    def ask_candidate_question(self, candidate_id: int, question: str, db: Session) -> Dict[str, Any]:
        """Perform targeted Q&A on a specific candidate's 360-degree profile."""
        cand = get_candidate(db, candidate_id)
        if not cand:
            return {
                "query": question,
                "answer": f"Candidate ID {candidate_id} not found.",
                "candidate_id": candidate_id,
            }

        doc_text = self._build_candidate_document_content(cand)

        prompt = (
            f"You are evaluating candidate {cand.full_name} ({cand.current_title or 'Professional'}).\n"
            f"Candidate Record:\n{doc_text}\n\n"
            f"User Question: {question}\n\n"
            f"Provide a detailed, objective analysis addressing the question directly."
        )

        answer = ai_engine.generate_response(prompt=prompt)

        return {
            "query": question,
            "answer": answer,
            "candidate_id": cand.id,
            "candidate_name": cand.full_name,
        }


# Global RAG pipeline instance
candidate_rag = CandidateRAGPipeline()
