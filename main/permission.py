"""
权限控制：定义工具的执行权限级别与审批管理。

权限级别：
- auto   : 自动执行，无需审批
- confirm: 需要用户确认才执行
- deny    : 禁止执行
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class PermissionLevel(str, Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    DENY = "deny"


# 默认权限配置：工具名 → 权限级别
DEFAULT_PERMISSIONS: dict[str, PermissionLevel] = {
    "add": PermissionLevel.AUTO,
    "recall": PermissionLevel.AUTO,
    "fetch_url": PermissionLevel.CONFIRM,
    "read_local_file": PermissionLevel.CONFIRM,
    "remember": PermissionLevel.CONFIRM,
    "run_python": PermissionLevel.CONFIRM,
    "run_shell": PermissionLevel.DENY,
}


class PermissionManager:
    """管理工具权限配置。"""

    def __init__(self, config: dict[str, PermissionLevel] | None = None) -> None:
        self._config: dict[str, PermissionLevel] = dict(config or DEFAULT_PERMISSIONS)

    def get_level(self, tool_name: str) -> PermissionLevel:
        """获取工具权限级别，未配置的默认 confirm。"""
        return self._config.get(tool_name, PermissionLevel.CONFIRM)

    def set_level(self, tool_name: str, level: PermissionLevel) -> None:
        self._config[tool_name] = level

    def allow(self, tool_name: str) -> bool:
        """工具是否允许执行（非 deny）。"""
        return self.get_level(tool_name) != PermissionLevel.DENY

    def needs_confirm(self, tool_name: str) -> bool:
        """工具是否需要审批。"""
        return self.get_level(tool_name) == PermissionLevel.CONFIRM
