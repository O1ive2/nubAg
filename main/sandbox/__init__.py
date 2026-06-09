"""
Sandbox 模块 - 安全执行环境
====================================
为 Agent 提供受控的代码执行和命令运行能力，限制资源、隔离风险。
"""
from .sandbox import Sandbox, SandboxResult

__all__ = ["Sandbox", "SandboxResult"]