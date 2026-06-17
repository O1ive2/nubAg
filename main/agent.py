"""
NubAgent 主入口
====================================
编排六大模块：
- harvest   : 信息采集
- memory    : 短期上下文 + 长期记忆
- brain     : LLM 推理决策
- sandbox   : 安全执行环境
- hands     : 工具/动作执行
- permission: 权限控制

上下文 vs 记忆：
- 上下文：当前对话可见，对话结束即消失（短期记忆 + MEMORY.md 索引）
- 记忆：跨对话持久化，只有 LLM 判断值得记住时才通过 remember 工具主动创建
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

from main.brain import Brain
from main.hands import default_toolset
from main.harvest import Harvester
from main.memory import LongTermMemory, ShortTermMemory
from main.memory.compactor import Compactor
from main.permission import PermissionManager

load_dotenv()


class NubAgent:
    """六大模块组合而成的 Agent。"""

    def __init__(
        self,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        permission: Optional[PermissionManager] = None,
    ) -> None:
        # 感知
        self.harvester = Harvester()
        # 记忆
        self.short_memory = ShortTermMemory()
        self.long_memory = LongTermMemory()
        # 权限
        self.permission = permission or PermissionManager()
        # 双手（工具集 + 权限）
        self.tools = default_toolset(permission=self.permission)
        # 大脑
        self.brain = Brain(
            model=model or os.getenv("ANTHROPIC_MODEL", "Claude-Sonnet-4.6"),
            tools=self.tools,
            system_prompt=system_prompt,
            checkpointer=self.short_memory.checkpointer,
            base_url=base_url or os.getenv("ANTHROPIC_BASE_URL"),
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            permission=self.permission,
            compactor=Compactor(),
        )

    # ---------- 上下文注入 ----------
    def _build_context(self, user_input: str) -> str:
        """构建输入上下文：MEMORY.md 索引 + 用户输入。"""
        index = self.long_memory.load_index()
        if not index.strip():
            return user_input
        return f"<memory_index>\n{index}</memory_index>\n{user_input}"

    # ---------- 对话 ----------
    def chat(self, user_input: str, thread_id: str = "default") -> str:
        """一次完整的感知 → 思考 → 审批 → 行动循环。"""
        _ = self.harvester.from_user(user_input)
        config = self.short_memory.make_config(thread_id)
        enriched = self._build_context(user_input)

        result = self.brain.think(enriched, config=config)

        if not result.is_interrupt:
            return result.reply or ""

        while result.is_interrupt:
            raise InterruptedError("NEED_APPROVAL") from None

        return result.reply or ""

    def chat_with_approval(
        self, user_input: str, thread_id: str = "default"
    ) -> str:
        """带交互式审批的对话（REPL 使用）。"""
        _ = self.harvester.from_user(user_input)
        config = self.short_memory.make_config(thread_id)
        enriched = self._build_context(user_input)

        result = self.brain.think(enriched, config=config)

        while result.is_interrupt:
            info = result.pending_approval or {}
            tool_name = info.get("tool", "未知工具")
            tool_args = info.get("args", {})

            print(f"\n🔑 Agent 请求执行工具: {tool_name}")
            print(f"   参数: {tool_args}")

            answer = input("   允许执行？[y/n]: ").strip().lower()
            approved = answer in {"y", "yes", "是"}

            result = self.brain.resume(approved, config=config)

            if not approved and not result.is_interrupt:
                return result.reply or "用户拒绝了工具调用。"

        return result.reply or ""


# ====== 交互式 REPL ======
def _repl(thread_id: str = "demo-session") -> None:
    """启动一个持续对话循环，输入 exit/quit/q 退出，Ctrl+C 中断当前回答。"""
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import InMemoryHistory

    agent = NubAgent()
    history = InMemoryHistory()
    print("=" * 60)
    print("🤖 NubAgent 已启动")
    print(f"   model    : {agent.brain.model}")
    print(f"   base_url : {agent.brain.base_url}")
    print(f"   thread   : {thread_id}")
    print("   提示：输入 exit / quit / q 退出；Ctrl+C 中断当前回答；")
    print("        上/下方向键浏览历史；Ctrl+D 退出。")
    print("=" * 60)

    while True:
        try:
            user_input = pt_prompt("\n👤 用户：", history=history).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q", ":q"}:
            print("👋 再见")
            break

        try:
            reply = agent.chat_with_approval(user_input, thread_id=thread_id)
            print(f"🤖 Agent：{reply}")
        except KeyboardInterrupt:
            print("\n⏹  已中断本次回答，可继续提问")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Agent 调用失败：{e}")

    agent.short_memory.close()


if __name__ == "__main__":
    _repl()
