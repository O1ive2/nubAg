"""
Brain 模块 - 推理决策核心
====================================
基于 LangChain create_agent 构建的 LLM 推理大脑，负责规划、决策、生成回复。
"""
from .brain import Brain

__all__ = ["Brain"]