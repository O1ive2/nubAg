"""
Hands 模块 - 动作执行层
====================================
所有 @tool 装饰的可调用工具集中在这里，作为 Agent 的"双手"对外部世界产生影响。
"""
from .tools import default_toolset

__all__ = ["default_toolset"]