# agent/memory/manager.py
from typing import Dict, Any, List, Optional
from agent.memory.working import WorkingMemory
from agent.memory.conversation import ConversationMemory
from agent.memory.schema import SchemaMemory
from agent.memory.semantic import SemanticMemory
from agent.memory.episodic import EpisodicMemory, Episode
from agent.memory.preference import PreferenceMemory


class MemoryManager:
    """
    六层统一记忆管理中枢 (Memory Architecture Manager)
    协同调度 Working, Conversation, Schema, Semantic, Episodic, Preference 六层记忆
    """

    def __init__(self):
        self.working = WorkingMemory()
        self.conversation = ConversationMemory()
        self.schema = SchemaMemory()
        self.semantic = SemanticMemory()
        self.episodic = EpisodicMemory()
        self.preference = PreferenceMemory()

    def retrieve_context(self, user_query: str, session_id: str) -> Dict[str, Any]:
        """
        根据用户当前输入与 session_id 精准召回多层上下文
        """
        # 1. 召回会话历史
        recent_msgs = self.conversation.get_messages(session_id)

        # 2. 召回相似历史执行经验 (Episodic)
        similar_episodes = self.episodic.find_similar(user_query, limit=2)
        episodes_context = [
            {"query": ep.query, "sql": ep.sql, "success": ep.success}
            for ep in similar_episodes
        ]

        # 3. 召回语义关联与同义词
        synonyms = self.semantic.get_synonyms()
        join_paths = self.semantic.get_join_paths()

        # 4. 召回用户偏好
        prefs = self.preference.get_all()

        return {
            "session_history": recent_msgs,
            "similar_episodes": episodes_context,
            "semantic_synonyms": synonyms,
            "semantic_joins": join_paths,
            "preferences": prefs
        }

    def record_success_experience(self, query: str, sql: str, error: Optional[str] = None, correction: Optional[str] = None):
        """记录正向/自愈经验"""
        self.episodic.record(
            query=query,
            sql=sql,
            error=error,
            correction=correction,
            success=True
        )

    def reset_working_memory(self):
        self.working.clear()
