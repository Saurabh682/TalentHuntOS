import os
import json
import time
import threading
from typing import Dict, List, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

STORE_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "conversations_store.json")

class ConversationManager:
    """In-memory and disk-persistent conversation context manager."""

    def __init__(self) -> None:
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._max_sessions = 100
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load conversation histories from disk on startup."""
        try:
            abs_path = os.path.abspath(STORE_FILE_PATH)
            if os.path.exists(abs_path):
                with open(abs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._store = data
        except Exception as e:
            import logging
            logging.getLogger("talenthunt.copilot.conversation").error(f"Failed to load conversation store from disk: {e}")

    def _save_to_disk(self) -> None:
        """Save conversation histories to disk."""
        try:
            abs_path = os.path.abspath(STORE_FILE_PATH)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger("talenthunt.copilot.conversation").error(f"Failed to save conversation store to disk: {e}")

    def get_messages(self, session_id: str = "default") -> List[Dict[str, Any]]:
        """Retrieve raw message list for a given session."""
        with self._lock:
            return self._store.get(session_id, [])[:]

    def get_langchain_messages(self, session_id: str = "default") -> List[BaseMessage]:
        """Convert stored session history to LangChain BaseMessage objects."""
        raw_msgs = self.get_messages(session_id)
        lc_msgs: List[BaseMessage] = []
        for msg in raw_msgs:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                lc_msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_msgs.append(AIMessage(content=content))
            elif role == "system":
                lc_msgs.append(SystemMessage(content=content))
        return lc_msgs

    def add_user_message(self, content: str, session_id: str = "default") -> Dict[str, Any]:
        """Record user message in context memory and save to disk."""
        with self._lock:
            if session_id not in self._store:
                if len(self._store) >= self._max_sessions:
                    self._store.pop(next(iter(self._store)))
                self._store[session_id] = []
            entry = {
                "role": "user",
                "content": content,
                "timestamp": time.strftime("%H:%M")
            }
            self._store[session_id].append(entry)
            self._save_to_disk()
            return entry

    def add_assistant_message(self, content: str, session_id: str = "default") -> Dict[str, Any]:
        """Record AI assistant response in context memory, save to disk, and RAG index."""
        with self._lock:
            if session_id not in self._store:
                if len(self._store) >= self._max_sessions:
                    self._store.pop(next(iter(self._store)))
                self._store[session_id] = []
            
            # Find the last user message to pair with this assistant response
            last_user_msg = ""
            for msg in reversed(self._store[session_id]):
                if msg["role"] == "user":
                    last_user_msg = msg["content"]
                    break

            entry = {
                "role": "assistant",
                "content": content,
                "timestamp": time.strftime("%H:%M")
            }
            self._store[session_id].append(entry)
            self._save_to_disk()

        # Fire and forget RAG indexing
        if last_user_msg:
            try:
                from app.copilot.memory import memory_index
                threading.Thread(
                    target=memory_index.index_interaction,
                    args=(session_id, last_user_msg, content),
                    daemon=True
                ).start()
            except Exception as e:
                import logging
                logging.getLogger("talenthunt.copilot.conversation").error(f"RAG indexing error: {e}")

        return entry

    def update_last_assistant_message(self, content: str, session_id: str = "default") -> None:
        """Update the latest assistant message during streaming and save to disk."""
        with self._lock:
            msgs = self._store.get(session_id, [])
            if msgs and msgs[-1]["role"] == "assistant":
                msgs[-1]["content"] = content
            else:
                if session_id not in self._store:
                    if len(self._store) >= self._max_sessions:
                        self._store.pop(next(iter(self._store)))
                    self._store[session_id] = []
                self._store[session_id].append({
                    "role": "assistant",
                    "content": content,
                    "timestamp": time.strftime("%H:%M")
                })
            self._save_to_disk()

    def clear_session(self, session_id: str = "default") -> None:
        """Clear context memory for a given session and update disk storage."""
        with self._lock:
            self._store[session_id] = []
            self._save_to_disk()

conversation_manager = ConversationManager()
