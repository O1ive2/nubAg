# NubAgent Harness 架构

NubAgent 的 harness 由六大模块组成，围绕 LLM 的 ReAct 循环编排感知、记忆、决策、执行和权限控制。

```
用户输入
  │
  ▼
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Harvester │───▶│  Brain   │───▶│  Hands   │
│ (感知)    │    │ (推理)   │    │ (执行)   │
└──────────┘    └────┬─────┘    └──────────┘
                     │
              ┌──────┼──────┐
              ▼      ▼      ▼
         ┌────────┐ ┌────────┐ ┌──────────┐
         │Memory  │ │Compactor│ │Permission│
         │(记忆)  │ │(压缩)   │ │(权限)    │
         └────────┘ └────────┘ └──────────┘
```

## Brain（推理大脑）

封装 LangGraph `create_react_agent`，是 harness 的核心调度器。

**功能**：接收用户输入，驱动 LLM 进行 ReAct 循环推理，协调工具调用与权限审批。

**实现方式**：
- 使用 LangGraph `create_react_agent` 构建 agent，`prompt` 参数注入系统提示（含 MEMORY.md 索引）
- `think()` 发起推理：先检查残留 interrupt → 调用 `agent.invoke()` → 返回 `ThinkResult`（回复或待审批）
- `resume()` 通过 `Command(resume=approved)` 恢复被 interrupt 暂停的执行
- `pre_model_hook` 在每次 LLM 调用前触发 Compactor，返回 `{"llm_input_messages": [...]}`，只压缩发给模型的内容，不修改 state

## Memory（记忆系统）

上下文与记忆分离：上下文是对话可见的短期消息流，记忆是跨对话的持久知识。

### 短期记忆（ShortTermMemory）

**功能**：维护当前对话的消息历史，支持跨进程恢复。

**实现方式**：
- 使用 LangGraph 的 `SqliteSaver` 作为 checkpointer，持久化到 `.agent_memory/checkpoint.db`
- `check_same_thread=False` 兼容多线程访问
- `make_config(thread_id)` 生成 config，不同 thread_id 隔离不同对话
- agent 每次 invoke 时自动通过 checkpointer 读写状态，对话历史随 checkpoint 持久化

### 长期记忆（LongTermMemory）

**功能**：跨对话持久化存储 LLM 判断值得记住的信息，对话重启后仍可召回。

**实现方式**：
- 每条记忆一个 Markdown 文件（frontmatter + body），存储在 `.agent_memory/` 目录
- `MEMORY.md` 作为索引文件，每行一条：`- [name](name.md) — 摘要`
- `remember()`：生成 kebab-case 文件名 → 写入 .md → 追加索引行
- `recall()`：遍历所有 .md 文件，在 description/content/tags 中按关键字搜索
- `forget()`：删除 .md 文件 + 移除索引行
- `load_index()`：读取 MEMORY.md 全文，在 Brain 构建时注入系统提示
- 四种记忆类型：user（用户身份/偏好）、feedback（行为纠正）、project（项目上下文）、reference（外部指针）

## Compactor（上下文压缩）

**功能**：防止对话历史超出模型上下文窗口，在 LLM 调用前自动压缩。

**实现方式**：
- 触发：`_estimate_tokens(messages)` 估算 token 数（字符数/4），超过 `max_tokens`（默认80000）时触发
- 压缩：保留最近 `keep_recent`（默认10）条 → 旧消息交给 LLM 生成摘要 → 替换为一条 `[对话摘要]` SystemMessage
- 累积摘要：`_summary` 字段保存历次压缩结果，新压缩时合并之前的摘要
- 降级：LLM 不可用时 `_fallback()` 截断每条消息至100字符，保留20条
- `make_pre_model_hook()` 返回闭包，作为 `pre_model_hook` 参数注入 `create_react_agent`

## Permission（权限控制）

**功能**：管控工具执行的权限，防止危险操作未经用户确认执行。

**实现方式**：
- `PermissionLevel` 枚举：AUTO / CONFIRM / DENY
- `PermissionManager` 维护工具名 → 权限级别的映射，未配置的默认 CONFIRM
- 工具内部调用 `_confirm(tool_name, args)`：
  - DENY → 抛出 `PermissionDenied`
  - CONFIRM → 调用 `interrupt({"tool": ..., "args": ...})` 暂停图执行
  - AUTO → 直接放行
- 用户审批后 `Brain.resume(approved)` → `Command(resume=approved)` 恢复
- `PermissionDenied` 是自定义异常（非内置 `PermissionError`），ToolNode 能捕获并生成 ToolMessage 回传 LLM

## Hands（工具执行）

**功能**：将各模块能力封装为 LangChain `@tool`，供 LLM 调用。

**实现方式**：
- 每个 `@tool` 函数先调用 `_confirm()` 检查权限，再调用对应模块执行
- 工具清单：fetch_url（Harvester）、read_local_file（Harvester）、remember/recall（LongTermMemory）、run_python（Sandbox）、add（基础计算）
- `default_toolset(permission)` 返回工具列表并注入权限管理器
- 工具异常由 LangGraph ToolNode 捕获，转化为 ToolMessage 回传 LLM 继续推理

## Harvester（感知采集）

**功能**：统一封装多源数据获取，是 Agent 感知外部世界的入口。

**实现方式**：
- `HarvestResult` 统一返回结构：source（来源类型）、content（文本内容）、metadata（元数据）
- `from_user(text)`：包装用户输入
- `from_file(path)`：读取本地文件内容
- `from_web(url)`：通过 urllib 抓取网页（占位实现，可替换为 requests/playwright）
- `from_api(name, payload)`：占位，未来适配业务 API
- `harvest_many(tasks)`：批量调度多个采集任务

## Sandbox（沙箱执行）

**功能**：在受控环境中执行代码，隔离风险。

**实现方式**：
- `run_python(code)`：通过 `exec()` 在受限命名空间中执行，`_safe_builtins()` 只暴露安全内置函数（abs/len/print 等），重定向 stdout/stderr
- `run_shell(command)`：默认禁用（`allow_shell=False`），启用后有命令黑名单（rm/sudo/dd 等）和超时限制
- `SandboxResult` 统一返回：ok、stdout、stderr、return_value

---

## 与 Claude Code 的对照

| 能力 | Claude Code | NubAgent |
|------|-------------|----------|
| IDE 上下文注入 | 扩展自动注入打开文件/光标位置 | 无 |
| 持久化记忆 | Markdown + MEMORY.md | ✅ 相同架构 |
| 权限审批 | 分级权限 | ✅ 三级管控 |
| 上下文压缩 | token 级别 | ✅ 字符粗估 |
| 子 Agent 调度 | Agent 工具，可并行/后台 | 无 |
| 沙箱执行 | 内置安全沙箱 | 无 |
