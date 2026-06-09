"""
NubAgent 主入口
====================================
编排五大模块：
- harvest : 信息采集
- memory  : 短期 + 长期记忆
- brain   : LLM 推理决策
- sandbox : 安全执行环境
- hands   : 工具/动作执行
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

from main.brain import Brain
from main.hands import default_toolset
from main.harvest import Harvester
from main.memory import LongTermMemory, ShortTermMemory

load_dotenv()


class NubAgent:
    """五大模块组合而成的 Agent。"""

    def __init__(
        self,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        # 感知
        self.harvester = Harvester()
        # 记忆
        self.short_memory = ShortTermMemory()
        self.long_memory = LongTermMemory()
        # 双手（工具集）
        self.tools = default_toolset()
        # 大脑（接入自定义网关，全部走环境变量，无硬编码）
        self.brain = Brain(
            model=model or os.getenv("ANTHROPIC_MODEL", "Claude-Sonnet-4.6"),
            tools=self.tools,
            system_prompt=system_prompt,
            checkpointer=self.short_memory.checkpointer,
            base_url=base_url or os.getenv("ANTHROPIC_BASE_URL"),
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
        )

    # ---------- 对话----------
    def chat(self, user_input: str, thread_id: str = "default") -> str:
        """一次完整的感知 → 思考 → 行动循环。"""
        # 1) harvest：把用户输入结构化（这里只做最小封装）
        _ = self.harvester.from_user(user_input)
        # 2) brain：思考 + 通过 hands 调工具 + 走 sandbox 执行
        config = self.short_memory.make_config(thread_id)
        return self.brain.think(user_input, config=config)


# ====== 交互式 REPL ======
def _repl(thread_id: str = "demo-session") -> None:
    """启动一个持续对话循环，输入 exit/quit/q 退出，Ctrl+C 中断当前回答。"""
    agent = NubAgent()
    print("=" * 60)
    print("🤖 NubAgent 已启动")
    print(f"   model    : {agent.brain.model}")
    print(f"   base_url : {agent.brain.base_url}")
    print(f"   thread   : {thread_id}")
    print("   提示：输入 exit / quit / q 退出；Ctrl+C 中断当前回答；")
    print("        Ctrl+D（或在空输入按回车两次）也可退出。")
    print("=" * 60)

    while True:
        # 1) 读取用户输入
        try:
            user_input = input("\n👤 用户：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n� 再见")
            break

        # 2) 空输入跳过；命令退出
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q", ":q"}:
            print("👋 再见")
            break

        # 3) 调用 Agent，单次异常不退出循环
        try:
            reply = agent.chat(user_input, thread_id=thread_id)
            print(f"🤖 Agent：{reply}")
        except KeyboardInterrupt:
            print("\n⏹  已中断本次回答，可继续提问")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Agent 调用失败：{e}")


if __name__ == "__main__":
    _repl()