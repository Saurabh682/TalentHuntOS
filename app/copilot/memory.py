"""ChromaDB pipeline for long-term Copilot conversation memory (RAG)."""

import logging
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.config.settings import settings, DATA_DIR

logger = logging.getLogger("talenthunt.copilot.memory")


class ConversationMemoryIndex:
    """Vector similarity engine for persistent conversation history using ChromaDB."""

    def __init__(self) -> None:
        self.chroma_dir = DATA_DIR / "chroma_db"
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = "copilot_memory"
        self._client = None
        self._collection = None
        self._embedder = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
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
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB for memory: {e}")

        try:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception as e:
            logger.warning(f"FastEmbed init warning for memory: {e}")

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        self._ensure_initialized()
        if not self._embedder or not text.strip():
            return None
        try:
            embeddings = list(self._embedder.embed([text]))
            if embeddings and len(embeddings) > 0:
                return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"Memory embedding error: {e}")
        return None

    def index_interaction(self, session_id: str, user_text: str, ai_text: str) -> bool:
        """Store a user-AI interaction turn in the vector database."""
        self._ensure_initialized()
        if not self._collection or not user_text.strip():
            return False

        doc_text = f"User: {user_text}\nCopilot: {ai_text}"
        doc_id = f"mem_{uuid.uuid4().hex[:12]}"
        metadata = {
            "session_id": session_id,
            "type": "interaction"
        }

        embedding = self._generate_embedding(doc_text)
        if not embedding:
            return False

        try:
            self._collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[doc_text],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upsert memory: {e}")
            return False

    def search_history(self, session_id: str, query: str, top_k: int = 3) -> str:
        """Retrieve relevant past interactions to serve as RAG context."""
        self._ensure_initialized()
        if not self._collection or not query.strip():
            return ""

        query_embedding = self._generate_embedding(query)
        if not query_embedding:
            return ""

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"session_id": session_id},
                include=["documents", "distances"],
            )

            context_blocks = []
            if results and results.get("ids") and len(results["ids"][0]) > 0:
                documents = results["documents"][0]
                distances = results["distances"][0]
                
                for i, doc in enumerate(documents):
                    # Only include if sufficiently relevant (cosine distance < 0.6)
                    if distances[i] < 0.6:
                        context_blocks.append(f"--- Past Interaction ---\n{doc}")
            
            return "\n\n".join(context_blocks)
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return ""

# Global memory singleton
memory_index = ConversationMemoryIndex()
