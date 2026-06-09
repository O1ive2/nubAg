"""
推理大脑：封装 LangChain create_agent，把模型/工具/记忆/系统提示词组合成可执行 agent。
支持自定义 Anthropic 兼容网关（如 JDCloud AI Gateway）。
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Optional

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

DEFAULT_SYSTEM_PROMPT = (
    "你是一个具备 harvest/memory/brain/sandbox/hands 五大模块的智能 Agent。"
    "请按需调用工具完成用户任务，回答简洁、准确，并主动利用记忆。"
)


class Brain:
    """LLM 推理大脑。"""

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
    ) -> None:
        self.model = model
        self.tools = list(tools or [])
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.checkpointer = checkpointer

        # 优先使用显式参数；否则回退到环境变量
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
        return create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=self.system_prompt,
            checkpointer=self.checkpointer,
        )

    # ---------- 推理 ----------
    def think(self, user_input: str, config: Optional[dict] = None) -> str:
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config or {},
        )
        return result["messages"][-1].content

    def stream(self, user_input: str, config: Optional[dict] = None):
        return self._agent.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config or {},
        )