"""Evidence-backed hybrid retrieval over the local candidate database."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.engine import ai_engine
from app.candidates.service import get_candidate
from app.config.settings import DATA_DIR

logger = logging.getLogger("talenthunt.candidates.rag")

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]{1,}", re.IGNORECASE)
_STOP_WORDS = {
    "about", "after", "also", "and", "are", "best", "candidate", "candidates",
    "does", "for", "from", "has", "have", "how", "into", "our", "that",
    "the", "their", "this", "what", "which", "who", "with", "years",
}
_SOURCE_WEIGHTS = {
    "skills": 1.35,
    "experience": 1.25,
    "recruiter_note": 1.15,
    "resume": 1.1,
    "snapshot": 1.05,
    "profile": 1.0,
    "education": 0.9,
}


def _tokens(text: str) -> list[str]:
    return [
        token.lower().strip(".-")
        for token in _TOKEN_RE.findall(text or "")
        if token.lower().strip(".-") not in _STOP_WORDS
    ]


def _snippet(text: str, query_tokens: set[str], limit: int = 420) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    lowered = clean.lower()
    starts = [lowered.find(token) for token in query_tokens if lowered.find(token) >= 0]
    center = min(starts) if starts else 0
    start = max(0, center - limit // 4)
    end = min(len(clean), start + limit)
    prefix = "..." if start else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end].strip()}{suffix}"


class CandidateRAGPipeline:
    """Hybrid candidate retrieval with field-level evidence and grounded synthesis."""

    def _build_candidate_document_content(self, cand: Any) -> str:
        """Serialize a candidate record for indexing and targeted analysis."""
        return "\n\n".join(chunk["text"] for chunk in self._candidate_evidence(cand))

    def _safe_snapshot_text(self, text_path: str | None) -> str:
        if not text_path:
            return ""
        try:
            path = Path(text_path)
            if not path.is_absolute():
                path = DATA_DIR / path
            resolved = path.resolve()
            if not resolved.is_relative_to(DATA_DIR.resolve()) or not resolved.is_file():
                return ""
            return resolved.read_text(encoding="utf-8", errors="replace")[:8_000]
        except OSError:
            return ""

    def _candidate_evidence(self, cand: Any) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []

        def add(source_type: str, label: str, text: str, **metadata: Any) -> None:
            clean = (text or "").strip()
            if clean:
                chunks.append({
                    "candidate_id": cand.id,
                    "source_type": source_type,
                    "label": label,
                    "text": clean,
                    **metadata,
                })

        profile = cand.profile
        profile_bits = [
            f"Name: {cand.full_name}",
            f"Current role: {cand.current_title or 'Unknown'} at {cand.current_company or 'Unknown'}",
            f"Location: {cand.location or 'Unknown'}",
            f"Experience: {cand.experience_years} years" if cand.experience_years is not None else "",
            f"Headline: {profile.headline}" if profile and profile.headline else "",
            f"Summary: {profile.summary}" if profile and profile.summary else "",
        ]
        add("profile", "Profile summary", "\n".join(bit for bit in profile_bits if bit))

        skills: list[str] = []
        if profile and profile.skills_json:
            try:
                parsed = json.loads(profile.skills_json)
                skills = [str(skill).strip() for skill in parsed if str(skill).strip()]
            except (TypeError, json.JSONDecodeError):
                skills = []
        if skills:
            add("skills", "Skills", ", ".join(skills))

        for index, exp in enumerate(cand.experiences or [], start=1):
            dates = f"{exp.start_date or 'Unknown'} to {exp.end_date or 'Present'}"
            text = f"{exp.title} at {exp.company}, {dates}. {exp.description or ''}".strip()
            add("experience", f"Experience {index}: {exp.title} at {exp.company}", text)

        for index, edu in enumerate(cand.educations or [], start=1):
            text = (
                f"{edu.degree or 'Degree'} in {edu.field_of_study or 'unspecified field'} "
                f"from {edu.institution}, {edu.start_year or 'unknown'} to {edu.end_year or 'unknown'}"
            )
            add("education", f"Education {index}: {edu.institution}", text)

        for note in cand.notes or []:
            date = note.created_at.strftime("%Y-%m-%d") if note.created_at else "undated"
            add(
                "recruiter_note",
                f"Recruiter note ({date}, {note.author})",
                note.content,
            )

        if profile and profile.resume_text:
            add("resume", "Resume", profile.resume_text[:12_000])
        if profile and profile.ai_evaluation:
            add("profile", "AI evaluation", profile.ai_evaluation)

        for snapshot in list(getattr(cand, "snapshots", []) or [])[:2]:
            snapshot_text = self._safe_snapshot_text(snapshot.text_path)
            if snapshot_text:
                add(
                    "snapshot",
                    f"Profile snapshot ({snapshot.created_at.date().isoformat() if snapshot.created_at else 'undated'})",
                    snapshot_text,
                    source_url=snapshot.source_url,
                    snapshot_id=snapshot.id,
                )
        return chunks

    def _keyword_score(self, query: str, text: str, source_type: str) -> float:
        query_terms = _tokens(query)
        if not query_terms:
            return 0.0
        frequencies = Counter(_tokens(text))
        matched = sum(min(2, frequencies[term]) for term in query_terms)
        coverage = sum(1 for term in set(query_terms) if frequencies[term]) / len(set(query_terms))
        phrase_boost = 0.35 if query.strip().lower() in text.lower() else 0.0
        tf_score = matched / max(1.0, len(query_terms) * 1.5)
        return min(1.0, (0.55 * coverage + 0.45 * tf_score + phrase_boost)) * _SOURCE_WEIGHTS.get(source_type, 1.0)

    def _semantic_scores(self, query: str, top_k: int = 30) -> dict[int, float]:
        try:
            from app.candidates.search import candidate_search_index

            hits = candidate_search_index.search_candidates(query, top_k=top_k)
            return {
                int(hit["candidate_id"]): max(0.0, min(1.0, float(hit.get("similarity_score", 0)) / 100.0))
                for hit in hits
                if str(hit.get("candidate_id", "")).isdigit()
            }
        except Exception as exc:
            logger.info("Semantic candidate retrieval unavailable: %s", exc)
            return {}

    def _retrieve(self, query: str, candidates: list[Any], top_k: int = 5) -> list[dict[str, Any]]:
        semantic_scores = self._semantic_scores(query)
        query_terms = set(_tokens(query))
        ranked: list[dict[str, Any]] = []

        for cand in candidates:
            evidence = []
            for chunk in self._candidate_evidence(cand):
                score = self._keyword_score(query, chunk["text"], chunk["source_type"])
                if score > 0:
                    evidence.append({
                        **{key: value for key, value in chunk.items() if key != "text"},
                        "snippet": _snippet(chunk["text"], query_terms),
                        "keyword_score": round(score, 4),
                    })
            evidence.sort(key=lambda item: item["keyword_score"], reverse=True)
            semantic = semantic_scores.get(cand.id, 0.0)
            keyword = evidence[0]["keyword_score"] if evidence else 0.0
            if not evidence and semantic <= 0:
                continue
            combined = (0.72 * keyword) + (0.28 * semantic)
            ranked.append({
                "candidate": cand,
                "score": combined,
                "keyword_score": keyword,
                "semantic_score": semantic,
                "evidence": evidence[:3] or [{
                    "candidate_id": cand.id,
                    "source_type": "profile",
                    "label": "Semantic profile match",
                    "snippet": _snippet(self._build_candidate_document_content(cand), query_terms),
                    "keyword_score": 0.0,
                }],
            })

        ranked.sort(key=lambda item: (item["score"], item["keyword_score"]), reverse=True)
        return ranked[:top_k]

    def _load_candidates(self, db: Session, limit: int = 500) -> list[Any]:
        from app.candidates.models import Candidate

        snapshots_rel = getattr(Candidate, "snapshots", None)
        options = [
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations),
            selectinload(Candidate.notes),
            selectinload(Candidate.profile),
        ]
        if snapshots_rel is not None:
            options.append(selectinload(snapshots_rel))
        stmt = select(Candidate).options(*options).where(Candidate.status != "Archived").limit(limit)
        return list(db.scalars(stmt).unique().all())

    def _source_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        cand = item["candidate"]
        return {
            "id": cand.id,
            "full_name": cand.full_name,
            "current_title": cand.current_title,
            "relevance_score": round(min(100.0, item["score"] * 100), 1),
            "candidate_url": f"/candidates/{cand.id}",
            "evidence": item["evidence"],
        }

    def query_candidate_database(self, query: str, db: Session) -> dict[str, Any]:
        candidates = self._load_candidates(db)
        if not candidates:
            return {
                "query": query,
                "answer": "No candidates found in the database to answer your query.",
                "sources": [],
                "retrieval": {"mode": "hybrid", "candidates_scanned": 0},
            }

        ranked = self._retrieve(query, candidates)
        if not ranked:
            return {
                "query": query,
                "answer": "I could not find evidence in the candidate database that supports this query.",
                "sources": [],
                "retrieval": {"mode": "hybrid", "candidates_scanned": len(candidates)},
            }

        context_blocks = []
        for item in ranked:
            cand = item["candidate"]
            evidence_lines = [
                f"- [{evidence['label']}] {evidence['snippet']}"
                for evidence in item["evidence"]
            ]
            context_blocks.append(
                f"Candidate #{cand.id}: {cand.full_name} ({cand.current_title or 'Role unknown'})\n"
                + "\n".join(evidence_lines)
            )
        prompt = (
            "You are the TalentHunt OS evidence analyst. Answer only from the supplied evidence. "
            "Do not infer missing skills, dates, employers, or experience. Every candidate-specific "
            "claim must end with a citation formatted exactly as [Candidate #ID · Evidence label]. "
            "If evidence is weak or contradictory, say so.\n\n"
            f"Recruiter question: {query}\n\nEvidence:\n"
            + "\n\n".join(context_blocks)
        )
        answer = ai_engine.generate_response(prompt=prompt)
        return {
            "query": query,
            "answer": answer,
            "sources": [self._source_payload(item) for item in ranked],
            "retrieval": {
                "mode": "hybrid_keyword_vector",
                "candidates_scanned": len(candidates),
                "candidates_retrieved": len(ranked),
            },
        }

    def ask_candidate_question(self, candidate_id: int, question: str, db: Session) -> dict[str, Any]:
        cand = get_candidate(db, candidate_id)
        if not cand:
            return {
                "query": question,
                "answer": f"Candidate ID {candidate_id} not found.",
                "candidate_id": candidate_id,
                "sources": [],
            }

        evidence = []
        query_terms = set(_tokens(question))
        for chunk in self._candidate_evidence(cand):
            score = self._keyword_score(question, chunk["text"], chunk["source_type"])
            evidence.append({
                **{key: value for key, value in chunk.items() if key != "text"},
                "snippet": _snippet(chunk["text"], query_terms),
                "keyword_score": round(score, 4),
            })
        evidence.sort(key=lambda item: item["keyword_score"], reverse=True)
        selected = evidence[:5]
        context = "\n".join(f"- [{item['label']}] {item['snippet']}" for item in selected)
        prompt = (
            f"Evaluate candidate {cand.full_name} only from the evidence below. Every factual claim "
            f"must cite [Candidate #{cand.id} · Evidence label]. State when the record does not answer "
            f"the question.\n\nQuestion: {question}\n\nEvidence:\n{context}"
        )
        answer = ai_engine.generate_response(prompt=prompt)
        return {
            "query": question,
            "answer": answer,
            "candidate_id": cand.id,
            "candidate_name": cand.full_name,
            "sources": [{
                "id": cand.id,
                "full_name": cand.full_name,
                "current_title": cand.current_title,
                "candidate_url": f"/candidates/{cand.id}",
                "evidence": selected,
            }],
        }


candidate_rag = CandidateRAGPipeline()
