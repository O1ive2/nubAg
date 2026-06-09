"""
长期记忆：基于本地 JSON 文件的简单持久化实现。
未来可替换为向量数据库（Chroma / FAISS / Pinecone）或 KV 存储。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class LongTermMemory:
    """跨会话持久化记忆。"""

    def __init__(self, store_path: str | Path = ".agent_memory/long_term.json"):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self.store_path.write_text("[]", encoding="utf-8")

    # ---------- 读写 ----------
    def _load(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _dump(self, items: list[dict[str, Any]]) -> None:
        self.store_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- API ----------
    def remember(self, content: str, tags: list[str] | None = None) -> str:
        items = self._load()
        item_id = uuid.uuid4().hex[:12]
        items.append(
            {
                "id": item_id,
                "content": content,
                "tags": tags or [],
                "ts": time.time(),
            }
        )
        self._dump(items)
        return item_id

    def recall(self, keyword: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        items = self._load()
        if keyword:
            items = [i for i in items if keyword.lower() in i["content"].lower()]
        items.sort(key=lambda x: x["ts"], reverse=True)
        return items[:limit]

    def forget(self, item_id: str) -> bool:
        items = self._load()
        new_items = [i for i in items if i["id"] != item_id]
        self._dump(new_items)
        return len(new_items) != len(items)