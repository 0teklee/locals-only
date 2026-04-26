"""
SHELL 도구 — 쉘 명령 실행 (허용 목록 기반).

Rules.md의 SHELL_ALLOWLIST를 준수.
허용 목록에 없는 명령은 실행 거부.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from src.tools.registry import ToolRegistry, ToolSpec

# Rules.md > SHELL_ALLOWLIST
_ALLOWLIST: frozenset[str] = frozenset([
    "git", "python3", "python", "pip", "pip3", "uv",
    "brew", "make", "cmake",
    "npm", "npx", "node",
    "cargo", "rustc",
    "ollama",
    "ls", "cat", "head", "tail", "grep", "find", "wc",
    "echo", "pwd", "which", "env",
    "ruff", "pytest",
])


def _run_command(command: str, cwd: str = ".", timeout: int = 30) -> str:
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"Error: invalid command: {e}"

    if not parts:
        return "Error: empty command"

    base_cmd = Path(parts[0]).name  # e.g. "/usr/bin/git" → "git"
    if base_cmd not in _ALLOWLIST:
        return (
            f"Error: command '{base_cmd}' is not in the allowlist.\n"
            f"Allowed: {', '.join(sorted(_ALLOWLIST))}"
        )

    try:
        result = subprocess.run(
            parts,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return output.strip() or f"(exit code {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except FileNotFoundError:
        return f"Error: command not found: {parts[0]}"
    except Exception as e:
        return f"Error: {e}"


def _run_python(code: str, timeout: int = 60) -> str:
    """Python 코드 인라인 실행."""
    import io
    import contextlib

    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            exec(code, {})  # noqa: S102
        return stdout.getvalue() or "(no output)"
    except Exception as e:
        return f"Error: {e}"


# ------------------------------------------------------------------

def register(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="run_command",
        description=(
            "Run a shell command. Only allowlisted commands are permitted "
            "(git, python3, pip, brew, make, npm, cargo, ollama, ls, cat, grep, find, etc.)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Full shell command string"},
                "cwd": {"type": "string", "description": "Working directory", "default": "."},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"],
        },
        handler=_run_command,
        requires_confirm=True,
    ))
    registry.register(ToolSpec(
        name="run_python",
        description="Execute a Python code snippet inline and return stdout.",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "default": 60},
            },
            "required": ["code"],
        },
        handler=_run_python,
        requires_confirm=True,
    ))
