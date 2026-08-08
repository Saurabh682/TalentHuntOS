"""ChromaDB and FastEmbed pipeline for candidate vector similarity search."""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.config.settings import settings, DATA_DIR

logger = logging.getLogger("talenthunt.candidates.search")


class CandidateVectorIndex:
    """Vector similarity search engine for candidates using ChromaDB and FastEmbed."""

    def __init__(self) -> None:
        self.chroma_dir = DATA_DIR / "chroma_db"
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = "candidates"
        self._client = None
        self._collection = None
        self._embedder = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initializer for ChromaDB client and FastEmbed model."""
        if self._initialized:
            return

        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._client = chromadb.PersistentClient(
                path=str(self.chroma_dir),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB candidate collection initialized at {self.chroma_dir}")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB persistent client: {e}")

        try:
            from fastembed import TextEmbedding
            # Lightweight BAAI/bge-small-en-v1.5 model for rapid local vector embeddings
            self._embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            logger.info("FastEmbed BAAI/bge-small-en-v1.5 model loaded successfully.")
        except Exception as e:
            logger.warning(f"FastEmbed initialization warning: {e}. Will fallback to basic text processing if needed.")

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate float vector embedding for given text string using FastEmbed."""
        self._ensure_initialized()
        if not self._embedder or not text.strip():
            return None

        try:
            embeddings = list(self._embedder.embed([text]))
            if embeddings and len(embeddings) > 0:
                return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
        return None

    def _build_doc_text(
        self,
        full_name: str,
        title: str,
        skills: List[str],
        summary: str,
        resume_text: str,
        location: str,
    ) -> str:
        """Construct rich semantic text block for vector indexing."""
        parts = [
            f"Candidate: {full_name}",
            f"Title: {title}" if title else "",
            f"Location: {location}" if location else "",
            f"Skills: {', '.join(skills)}" if skills else "",
            f"Summary: {summary}" if summary else "",
            f"Resume Excerpt: {resume_text[:1000]}" if resume_text else "",
        ]
        return "\n".join([p for p in parts if p])

    def index_candidate(
        self,
        candidate_id: int,
        full_name: str,
        title: str = "",
        skills: Optional[List[str]] = None,
        summary: str = "",
        resume_text: str = "",
        location: str = "",
    ) -> bool:
        """Index or update candidate profile vectors in ChromaDB."""
        self._ensure_initialized()
        if not self._collection:
            return False

        skills_list = skills or []
        doc_text = self._build_doc_text(
            full_name=full_name,
            title=title,
            skills=skills_list,
            summary=summary,
            resume_text=resume_text,
            location=location,
        )

        doc_id = str(candidate_id)
        metadata = {
            "candidate_id": candidate_id,
            "full_name": full_name,
            "title": title or "",
            "location": location or "",
            "skills": ", ".join(skills_list),
        }

        embedding = self._generate_embedding(doc_text)

        try:
            if not embedding:
                return False
                
            self._collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[doc_text],
                metadatas=[metadata],
            )
            logger.info(f"Indexed candidate {candidate_id} ({full_name}) into ChromaDB.")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert candidate {candidate_id} into ChromaDB: {e}")
            return False

    def search_candidates(
        self, query: str, top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Perform semantic vector similarity search for candidates given a search prompt."""
        self._ensure_initialized()
        if not self._collection or not query.strip():
            return []

        query_embedding = self._generate_embedding(query)

        try:
            if query_embedding:
                results = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
            else:
                return []

            hits = []
            if results and results.get("ids") and len(results["ids"][0]) > 0:
                ids = results["ids"][0]
                metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
                distances = results["distances"][0] if results.get("distances") else [0.5] * len(ids)
                documents = results["documents"][0] if results.get("documents") else [""] * len(ids)

                for i, doc_id in enumerate(ids):
                    distance = distances[i]
                    # Convert cosine distance to 0-100 similarity percentage score
                    similarity_score = max(0.0, min(100.0, round((1.0 - (distance / 2.0)) * 100, 1)))

                    hits.append({
                        "candidate_id": int(doc_id) if doc_id.isdigit() else doc_id,
                        "metadata": metadatas[i],
                        "document": documents[i],
                        "distance": distance,
                        "similarity_score": similarity_score,
                    })

            return hits
        except Exception as e:
            logger.error(f"Vector search failed for query '{query}': {e}")
            return []

    def delete_candidate(self, candidate_id: int) -> bool:
        """Remove candidate vector from ChromaDB."""
        self._ensure_initialized()
        if not self._collection:
            return False

        try:
            self._collection.delete(ids=[str(candidate_id)])
            logger.info(f"Deleted vector index for candidate {candidate_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete candidate vector {candidate_id}: {e}")
            return False


# Global vector search engine singleton
candidate_search_index = CandidateVectorIndex()
