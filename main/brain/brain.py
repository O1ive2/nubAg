"""
推理大脑：封装 LangGraph create_react_agent，支持 interrupt 权限审批 + 上下文压缩。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from ..memory.compactor import Compactor, make_pre_model_hook
from ..permission import PermissionManager

DEFAULT_SYSTEM_PROMPT = (
    "你是一个具备 harvest/memory/brain/sandbox/hands 五大模块的智能 Agent。"
    "回答简洁、准确。\n"
    "关于记忆：\n"
    "- 你拥有 remember 和 recall 工具管理长期记忆。\n"
    "- 当用户透露个人信息（姓名、职业、偏好等）或对话中出现值得记住的重要事实时，"
    "主动调用 remember 存入长期记忆，无需用户明确要求。\n"
    "- 回答与用户相关的问题前，先调用 recall 查看是否有相关记忆。"
)


@dataclass
class ThinkResult:
    """think() 的返回值：可能是最终回复，也可能是等待审批的中断。"""

    reply: str | None = None
    pending_approval: dict | None = None  # {"tool": ..., "args": ...}

    @property
    def is_interrupt(self) -> bool:
        return self.pending_approval is not None


class Brain:
    """LLM 推理大脑，内置权限审批。"""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        tools: Optional[Iterable[Any]] = None,
        system_prompt: Optional[str] = None,
        checkpointer: Any = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        permission: Optional[PermissionManager] = None,
        compactor: Optional[Compactor] = None,
    ) -> None:
        self.model = model
        self.tools = list(tools or [])
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.checkpointer = checkpointer
        self.permission = permission or PermissionManager()
        self.compactor = compactor

        self.base_url = base_url or os.getenv("ANTHROPIC_BASE_URL")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.llm = self._build_llm()
        self._agent = self._build_agent()

    # ---------- 构建 ----------
    def _build_llm(self) -> ChatAnthropic:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key
        return ChatAnthropic(**kwargs)

    def _build_agent(self) -> Any:
        if self.compactor and not self.compactor.llm:
            self.compactor.llm = self.llm

        kwargs: dict[str, Any] = {
            "model": self.llm,
            "tools": self.tools,
            "prompt": self.system_prompt,
            "checkpointer": self.checkpointer,
        }
        if self.compactor:
            kwargs["pre_model_hook"] = make_pre_model_hook(self.compactor)
        return create_react_agent(**kwargs)

    # ---------- 推理 ----------
    def _check_pending_interrupt(self, config: dict) -> ThinkResult | None:
        """检查是否有未处理的 interrupt，有则返回它。"""
        try:
            state = self._agent.get_state(config)
        except Exception:  # noqa: BLE001
            return None
        if state and state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    return ThinkResult(pending_approval=task.interrupts[0].value)
        return None

    def think(self, user_input: str, config: Optional[dict] = None) -> ThinkResult:
        """执行一次推理，可能返回最终回复或中断等待审批。"""
        config = config or {}

        # 先处理上次残留的 interrupt
        pending = self._check_pending_interrupt(config)
        if pending:
            return pending

        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )

        # 检查是否有 interrupt
        interrupts = result.get("__interrupt__")
        if interrupts:
            return ThinkResult(
                pending_approval=interrupts[0].value
                if hasattr(interrupts[0], "value")
                else interrupts[0]
            )

        return ThinkResult(reply=result["messages"][-1].content)

    def resume(self, approved: bool, config: dict) -> ThinkResult:
        """审批后恢复执行。approved=True 继续执行，approved=False 拒绝。"""
        result = self._agent.invoke(
            Command(resume=approved),
            config=config,
        )

        interrupts = result.get("__interrupt__")
        if interrupts:
            return ThinkResult(
                pending_approval=interrupts[0].value
                if hasattr(interrupts[0], "value")
                else interrupts[0]
            )

        return ThinkResult(reply=result["messages"][-1].content)

    def stream(self, user_input: str, config: Optional[dict] = None):
        return self._agent.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config or {},
        )
