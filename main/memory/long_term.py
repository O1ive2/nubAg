"""
长期记忆：基于 Markdown 文件 + MEMORY.md 索引的持久化实现。

存储结构：
  .agent_memory/
  ├── MEMORY.md              # 索引文件（自动加载到上下文）
  ├── user_oliver.md         # 用户身份记忆
  ├── feedback_no-mock.md    # 反馈记忆
  └── ...

单条记忆文件格式：
  ---
  name: short-kebab-case-slug
  description: 一行摘要（决定是否相关）
  metadata:
    type: user | feedback | project | reference
    tags: [tag1, tag2]
    created: 2026-06-17T12:00:00
  ---

  正文内容...
  **Why:** ...
  **How to apply:** ...
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LongTermMemory:
    """跨会话持久化记忆（Markdown 文件 + 索引）。"""

    def __init__(self, store_dir: str | Path = ".agent_memory") -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.store_dir / "MEMORY.md"
        if not self.index_path.exists():
            self.index_path.write_text("", encoding="utf-8")

    # ---------- 索引 ----------
    def _load_index(self) -> list[str]:
        """读取索引行。"""
        if not self.index_path.exists():
            return []
        return [
            line.strip()
            for line in self.index_path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- ")
        ]

    def _append_index(self, name: str, description: str) -> None:
        """向索引追加一行。"""
        # 索引行控制在 150 字符内
        desc = description.replace("\n", " ")[:100]
        line = f"- [{name}]({name}.md) — {desc}\n"
        with open(self.index_path, "a", encoding="utf-8") as f:
            f.write(line)

    def _remove_index(self, name: str) -> None:
        """从索引移除一行。"""
        lines = self._load_index()
        pattern = f"({name}.md)"
        kept = [l for l in lines if pattern not in l]
        self.index_path.write_text("\n".join(kept) + "\n" if kept else "", encoding="utf-8")

    # ---------- 单条记忆读写 ----------
    def _read_memory(self, name: str) -> dict[str, Any] | None:
        """读取单条记忆文件，解析 frontmatter + body。"""
        path = self.store_dir / f"{name}.md"
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        return self._parse_frontmatter(text, name)

    def _write_memory(self, name: str, description: str, mem_type: str,
                      tags: list[str], body: str) -> None:
        """写入单条记忆文件。"""
        tags_str = ", ".join(f'"{t}"' for t in tags) if tags else "[]"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        content = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"metadata:\n"
            f"  type: {mem_type}\n"
            f"  tags: [{tags_str}]\n"
            f"  created: {now}\n"
            f"---\n\n"
            f"{body}\n"
        )
        (self.store_dir / f"{name}.md").write_text(content, encoding="utf-8")

    def _parse_frontmatter(self, text: str, name: str) -> dict[str, Any]:
        """简单解析 frontmatter，返回统一 dict。"""
        result: dict[str, Any] = {"id": name, "content": "", "tags": [], "type": "project"}

        # 提取 frontmatter 中的字段
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            result["content"] = text
            return result

        fm = fm_match.group(1)
        body = text[fm_match.end():].strip()

        # 解析简单键值
        for line in fm.splitlines():
            if line.startswith("description:"):
                result["description"] = line.split(":", 1)[1].strip()
            elif line.startswith("  type:"):
                result["type"] = line.split(":", 1)[1].strip()
            elif line.startswith("  tags:"):
                tag_str = line.split(":", 1)[1].strip()
                result["tags"] = [t.strip().strip('"\'') for t in tag_str.strip("[]").split(",") if t.strip()]
            elif line.startswith("  created:"):
                result["ts"] = line.split(":", 1)[1].strip()

        result["content"] = body or result.get("description", "")
        return result

    # ---------- 列出所有记忆 ----------
    def _list_memories(self) -> list[dict[str, Any]]:
        """读取所有记忆文件。"""
        items: list[dict[str, Any]] = []
        for path in sorted(self.store_dir.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            name = path.stem
            item = self._read_memory(name)
            if item:
                items.append(item)
        return items

    # ---------- 公共 API ----------
    def remember(self, content: str, tags: list[str] | None = None,
                 mem_type: str = "project", description: str = "") -> str:
        """写入一条记忆，返回 name。"""
        # 生成 name：从 description 或 content 提取 kebab-case
        name = self._make_name(description or content)
        desc = description or (content[:80] + "..." if len(content) > 80 else content)

        self._write_memory(name, desc, mem_type, tags or [], content)
        self._append_index(name, desc)
        return name

    def recall(self, keyword: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """召回记忆。keyword 在 description、content、tags 中搜索。"""
        items = self._list_memories()
        if keyword:
            kw = keyword.lower()
            items = [
                i for i in items
                if kw in i.get("content", "").lower()
                or kw in i.get("description", "").lower()
                or any(kw in t.lower() for t in i.get("tags", []))
            ]
        return items[:limit]

    def forget(self, name: str) -> bool:
        """删除一条记忆。"""
        path = self.store_dir / f"{name}.md"
        existed = path.exists()
        if existed:
            path.unlink()
            self._remove_index(name)
        return existed

    def load_index(self) -> str:
        """读取索引文件全文（供注入上下文）。"""
        if self.index_path.exists():
            return self.index_path.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _make_name(text: str) -> str:
        """从文本生成简短文件名：类型前缀 + 时间戳后缀。"""
        clean = re.sub(r"[^\w\s-]", "", text.lower())[:30]
        parts = clean.split()
        prefix = "_".join(parts[:3]) if parts else "mem"
        # 确保唯一性
        suffix = str(int(time.time()))[-6:]
        return f"{prefix}_{suffix}"
