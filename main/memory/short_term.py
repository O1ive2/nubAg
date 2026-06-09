"""
短期记忆：基于 LangGraph 的 MemorySaver，按 thread_id 维护对话上下文。
"""
from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver


class ShortTermMemory:
    """单会话短期记忆封装。"""

    def __init__(self) -> None:
        self._saver = MemorySaver()

    @property
    def checkpointer(self) -> MemorySaver:
        """返回 LangGraph checkpointer，供 create_agent 注入。"""
        return self._saver

    def make_config(self, thread_id: str) -> dict[str, Any]:
        """生成 invoke 所需的 config。"""
        return {"configurable": {"thread_id": thread_id}}

    def snapshot(self, thread_id: str) -> Any:
        """读取某个会话的最新状态。"""
        config = self.make_config(thread_id)
        try:
            return self._saver.get(config)
        except Exception:  # noqa: BLE001
            return None

    def clear(self, thread_id: str) -> None:
        """清空某个会话（重新创建 saver 是最简单的兜底）。"""
        # MemorySaver 没有删除单 thread 的 API，这里仅作占位。
        _ = thread_id