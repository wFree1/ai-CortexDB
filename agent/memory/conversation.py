# agent/memory/conversation.py
from typing import Dict, List, Any, Optional
from agent.memory.base import BaseMemory, MemoryItem


class ConversationMemory(BaseMemory):
    """
    会话记忆 (Conversation Memory)
    保存多轮对话历史，以 session_id 为分区。
    """

    def __init__(self, max_history_per_session: int = 20):
        self.max_history = max_history_per_session
        self._sessions: Dict[str, List[Dict[str, str]]] = {}

    def add_message(self, session_id: str, role: str, content: str) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append({"role": role, "content": content})
        if len(self._sessions[session_id]) > self.max_history:
            self._sessions[session_id] = self._sessions[session_id][-self.max_history:]

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        return list(self._sessions.get(session_id, []))

    def get(self, key: str) -> Optional[List[Dict[str, str]]]:
        return self._sessions.get(key)

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        if isinstance(value, list):
            self._sessions[key] = value

    def clear_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]

    def clear(self) -> None:
        self._sessions.clear()
