"""
上下文压缩：当对话消息超出阈值时，用 LLM 将旧消息压缩为摘要，
防止超出模型上下文窗口。

策略：
1. 保留最近 N 条消息不动
2. 超出部分用 LLM 生成摘要，替换为一条 SystemMessage
3. 如果 LLM 不可用，回退到简单截断
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, trim_messages


SUMMARY_PROMPT = (
    "请将以下对话历史压缩为一段简洁的摘要，保留关键事实、决策和结论，"
    "省略寒暄和重复内容。用中文输出。"
)

# 默认配置
DEFAULT_MAX_MESSAGES = 40  # 超过此条数触发压缩
DEFAULT_KEEP_RECENT = 10   # 始终保留最近 N 条


class Compactor:
    """上下文压缩器。"""

    def __init__(
        self,
        llm: object | None = None,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        keep_recent: int = DEFAULT_KEEP_RECENT,
    ) -> None:
        self.llm = llm
        self.max_messages = max_messages
        self.keep_recent = keep_recent
        self._summary: str = ""  # 累积摘要

    def compact(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """压缩消息列表：超阈值时摘要旧消息，始终保留最近 N 条。"""
        if len(messages) <= self.max_messages:
            return messages

        # 分割：旧消息 + 最近消息
        split = len(messages) - self.keep_recent
        old_msgs = messages[:split]
        recent_msgs = messages[split:]

        # 尝试用 LLM 摘要
        summary = self._summarize(old_msgs)

        # 构建压缩后的消息列表
        result: list[BaseMessage] = []
        if summary:
            result.append(SystemMessage(content=f"[对话摘要]\n{summary}"))
        result.extend(recent_msgs)
        return result

    def _summarize(self, messages: list[BaseMessage]) -> str:
        """用 LLM 摘要旧消息，失败则回退截断。"""
        if not self.llm:
            return self._fallback(messages)

        # 将旧消息拼接为文本
        conversation = self._messages_to_text(messages)
        if not conversation.strip():
            return ""

        # 如果有累积摘要，一并纳入
        context = conversation
        if self._summary:
            context = f"[之前的摘要]\n{self._summary}\n\n[新增对话]\n{conversation}"

        try:
            response = self.llm.invoke([
                SystemMessage(content=SUMMARY_PROMPT),
                HumanMessage(content=context),
            ])
            self._summary = response.content
            return self._summary
        except Exception:  # noqa: BLE001
            return self._fallback(messages)

    def _fallback(self, messages: list[BaseMessage]) -> str:
        """LLM 不可用时，简单提取关键信息。"""
        lines: list[str] = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                lines.append(f"用户: {msg.content[:100]}")
            elif isinstance(msg, AIMessage):
                lines.append(f"助手: {msg.content[:100]}")
        return "\n".join(lines[:20])  # 最多保留 20 条摘要行

    @staticmethod
    def _messages_to_text(messages: list[BaseMessage]) -> str:
        """将消息列表转为纯文本。"""
        parts: list[str] = []
        for msg in messages:
            role = "用户" if isinstance(msg, HumanMessage) else "助手"
            if isinstance(msg, SystemMessage):
                continue  # 跳过系统消息
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            parts.append(f"{role}: {content}")
        return "\n".join(parts)


def make_pre_model_hook(compactor: Compactor):
    """创建 pre_model_hook 供 create_react_agent 使用。

    返回 llm_input_messages：只影响发给 LLM 的内容，不修改 state 中的完整历史。
    """
    def hook(state: dict) -> dict:
        messages = state.get("messages", [])
        compacted = compactor.compact(messages)
        return {"llm_input_messages": compacted}
    return hook
