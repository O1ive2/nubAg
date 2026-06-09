"""
轻量沙箱：在受控环境中执行 Python 代码片段或 shell 命令。
注意：本实现是基础版本，生产环境应使用 docker / firejail / nsjail / E2B 等真正的隔离。
"""
from __future__ import annotations

import io
import shlex
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import Any

# 命令白名单：禁止超出范围的危险命令
COMMAND_DENYLIST = {"rm", "sudo", "shutdown", "reboot", "mkfs", "dd"}


@dataclass
class SandboxResult:
    """统一执行结果。"""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None


class Sandbox:
    """轻量级沙箱。"""

    def __init__(self, timeout: int = 10, allow_shell: bool = False):
        self.timeout = timeout
        self.allow_shell = allow_shell

    # ---------- Python 代码 ----------
    def run_python(self, code: str, globals_ctx: dict[str, Any] | None = None) -> SandboxResult:
        """在受限命名空间中执行 Python 代码片段。"""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        local_ns: dict[str, Any] = {}
        global_ns: dict[str, Any] = {"__builtins__": _safe_builtins()}
        if globals_ctx:
            global_ns.update(globals_ctx)

        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                exec(code, global_ns, local_ns)  # noqa: S102
            return SandboxResult(
                ok=True,
                stdout=out_buf.getvalue(),
                stderr=err_buf.getvalue(),
                return_value=local_ns.get("_"),
            )
        except Exception as e:  # noqa: BLE001
            return SandboxResult(ok=False, stdout=out_buf.getvalue(), stderr=f"{e}")

    # ---------- Shell 命令 ----------
    def run_shell(self, command: str) -> SandboxResult:
        """执行 shell 命令（默认禁用，需 allow_shell=True）。"""
        if not self.allow_shell:
            return SandboxResult(ok=False, stderr="shell execution disabled")

        parts = shlex.split(command)
        if not parts or parts[0] in COMMAND_DENYLIST:
            return SandboxResult(ok=False, stderr=f"command not allowed: {command}")

        try:
            proc = subprocess.run(  # noqa: S603
                parts,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            return SandboxResult(
                ok=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(ok=False, stderr=f"timeout > {self.timeout}s")
        except Exception as e:  # noqa: BLE001
            return SandboxResult(ok=False, stderr=str(e))


def _safe_builtins() -> dict[str, Any]:
    """裁剪过的内置函数集合。"""
    import builtins

    safe_names = {
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "int",
        "len", "list", "map", "max", "min", "print", "range", "round",
        "set", "sorted", "str", "sum", "tuple", "zip",
    }
    return {name: getattr(builtins, name) for name in safe_names}