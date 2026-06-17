"""
工具集合：把 harvest / memory / sandbox 等模块能力封装为 LangChain @tool，
支持 interrupt 权限审批。
"""
from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.tools import tool
from langgraph.types import interrupt

from ..harvest import Harvester
from ..memory import LongTermMemory
from ..permission import PermissionLevel, PermissionManager
from ..sandbox import Sandbox

# 模块级单例
_harvester = Harvester()
_long_memory = LongTermMemory()
_sandbox = Sandbox(timeout=10, allow_shell=False)

# 权限管理器（由 default_toolset 注入）
_permission: PermissionManager | None = None


class PermissionDenied(Exception):
    """用户拒绝工具调用，返回字符串让 LangGraph 正常生成 ToolMessage。"""
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"用户拒绝执行 {tool_name}")


def _confirm(tool_name: str, args: dict) -> None:
    """若工具需审批，调用 interrupt 暂停图执行。"""
    if _permission is None:
        return
    if _permission.get_level(tool_name) == PermissionLevel.DENY:
        raise PermissionDenied(tool_name)
    if _permission.needs_confirm(tool_name):
        approved = interrupt({"tool": tool_name, "args": args})
        if not approved:
            raise PermissionDenied(tool_name)


# ====== Harvest 工具 ======
@tool
def fetch_url(url: str) -> str:
    """抓取一个网页 URL 的原始内容（截断 2000 字）。

    Args:
        url: 完整的 http(s) URL
    """
    _confirm("fetch_url", {"url": url})
    res = _harvester.from_web(url)
    if res.metadata.get("error"):
        return f"抓取失败: {res.metadata['error']}"
    return res.content[:2000]


@tool
def read_local_file(path: str) -> str:
    """读取本地文件内容。

    Args:
        path: 文件路径（相对或绝对均可）
    """
    _confirm("read_local_file", {"path": path})
    try:
        return _harvester.from_file(path).content
    except Exception as e:  # noqa: BLE001
        return f"读取失败: {e}"


# ====== Memory 工具 ======
@tool
def remember(content: str, tags: Optional[List[str]] = None) -> str:
    """把信息写入长期记忆。

    Args:
        content: 要记住的内容
        tags: 可选标签列表
    """
    _confirm("remember", {"content": content, "tags": tags})
    item_id = _long_memory.remember(content, tags=tags)
    return f"已记住，id={item_id}"


@tool
def recall(keyword: Optional[str] = None, limit: int = 5) -> List[dict]:
    """从长期记忆中召回信息。

    Args:
        keyword: 关键字（可空）
        limit:   返回条数
    """
    _confirm("recall", {"keyword": keyword, "limit": limit})
    return _long_memory.recall(keyword=keyword, limit=limit)


# ====== Sandbox 工具 ======
@tool
def run_python(code: str) -> str:
    """在沙箱中执行一段 Python 代码并返回 stdout /错误。

    Args:
        code: Python 代码片段
    """
    _confirm("run_python", {"code": code})
    result = _sandbox.run_python(code)
    if result.ok:
        return result.stdout or "<no output>"
    return f"执行失败: {result.stderr}"


# ====== 数学 / 基础工具 ======
@tool
def add(a: float, b: float) -> float:
    """两数相加。"""
    return a + b


def default_toolset(
    permission: PermissionManager | None = None,
) -> List[Any]:
    """返回 Agent 默认装载的工具集。"""
    global _permission
    _permission = permission
    return [fetch_url, read_local_file, remember, recall, run_python, add]
