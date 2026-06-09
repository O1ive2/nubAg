"""
信息采集器：统一封装多源数据获取能力。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HarvestResult:
    """采集结果统一结构。"""

    source: str                       # 来源类型: user / file / web / api
    content: str                      # 原始文本内容
    metadata: dict[str, Any] = field(default_factory=dict)


class Harvester:
    """信息采集器。

    后续可扩展：网页爬取、PDF 解析、向量检索、MCP 数据拉取等。
    """

    def __init__(self, workspace: str | Path = "."):
        self.workspace = Path(workspace)

    # ---------- 用户输入 ----------
    def from_user(self, text: str) -> HarvestResult:
        return HarvestResult(source="user", content=text)

    # ---------- 本地文件 ----------
    def from_file(self, path: str | Path) -> HarvestResult:
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        content = p.read_text(encoding="utf-8")
        return HarvestResult(
            source="file",
            content=content,
            metadata={"path": str(p), "size": p.stat().st_size},
        )

    # ---------- 网络资源 ----------
    def from_web(self, url: str) -> HarvestResult:
        """占位实现 - 接入 requests / httpx / playwright 时替换。"""
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            return HarvestResult(source="web", content=content, metadata={"url": url})
        except Exception as e:  # noqa: BLE001
            return HarvestResult(
                source="web", content="", metadata={"url": url, "error": str(e)}
            )

    # ---------- 通用 API ----------
    def from_api(self, name: str, payload: dict[str, Any]) -> HarvestResult:
        """占位实现 - 适配各类业务 API。"""
        return HarvestResult(
            source="api",
            content="",
            metadata={"api": name, "payload": payload, "status": "not_implemented"},
        )

    # ---------- 批量 ----------
    def harvest_many(self, tasks: list[dict[str, Any]]) -> list[HarvestResult]:
        results: list[HarvestResult] = []
        for t in tasks:
            kind = t.get("type")
            handler = getattr(self, f"from_{kind}", None)
            if callable(handler):
                results.append(handler(**{k: v for k, v in t.items() if k != "type"}))
        return results