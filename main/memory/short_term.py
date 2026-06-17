"""
短期记忆：基于 SQLite 的持久化 checkpointer，按 thread_id 维护对话上下文。
进程重启后对话历史不丢失。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver


class ShortTermMemory:
    """持久化短期记忆（SQLite）。"""

    def __init__(self, db_path: str | Path = ".agent_memory/checkpoint.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = __import__("sqlite3").connect(str(self._db_path), check_same_thread=False)
        self._saver = SqliteSaver(self._conn)
        self._saver.setup()

    @property
    def checkpointer(self) -> SqliteSaver:
        """返回 LangGraph checkpointer，供 create_react_agent 注入。"""
        return self._saver

    def make_config(self, thread_id: str) -> dict[str, Any]:
        """生成 invoke 所需的 config。"""
        return {"configurable": {"thread_id": thread_id}}

    def close(self) -> None:
        """关闭数据库连接。"""
        self._conn.close()
