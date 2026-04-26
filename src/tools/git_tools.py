"""
GIT 도구 — Git 연산.

git_status, git_diff, git_log, git_commit
파괴적 작업(commit)은 requires_confirm=True.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.tools.registry import ToolRegistry, ToolSpec


def _run_git(args: list[str], cwd: str = ".") -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return (result.stdout + result.stderr).strip() or "(no output)"
    except FileNotFoundError:
        return "Error: git not found"
    except subprocess.TimeoutExpired:
        return "Error: git timed out"
    except Exception as e:
        return f"Error: {e}"


def _git_status(repo_path: str = ".") -> str:
    return _run_git(["status", "--short", "--branch"], cwd=repo_path)


def _git_diff(repo_path: str = ".", target: str = "HEAD") -> str:
    output = _run_git(["diff", target], cwd=repo_path)
    # 너무 길면 트런케이션
    if len(output) > 8000:
        return output[:8000] + "\n... [truncated]"
    return output


def _git_log(repo_path: str = ".", n: int = 10) -> str:
    return _run_git(
        ["log", f"-{n}", "--oneline", "--decorate"],
        cwd=repo_path,
    )


def _git_commit(message: str, repo_path: str = ".") -> str:
    # stage all tracked changes
    _run_git(["add", "-u"], cwd=repo_path)
    return _run_git(["commit", "-m", message], cwd=repo_path)


# ------------------------------------------------------------------

def register(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="git_status",
        description="Show current git branch and changed files.",
        parameters={
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "default": "."},
            },
        },
        handler=_git_status,
    ))
    registry.register(ToolSpec(
        name="git_diff",
        description="Show git diff against a target (default HEAD).",
        parameters={
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "default": "."},
                "target": {"type": "string", "default": "HEAD"},
            },
        },
        handler=_git_diff,
    ))
    registry.register(ToolSpec(
        name="git_log",
        description="Show recent git commit history.",
        parameters={
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "default": "."},
                "n": {"type": "integer", "default": 10, "description": "Number of commits"},
            },
        },
        handler=_git_log,
    ))
    registry.register(ToolSpec(
        name="git_commit",
        description="Stage tracked changes and create a commit.",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
                "repo_path": {"type": "string", "default": "."},
            },
            "required": ["message"],
        },
        handler=_git_commit,
        requires_confirm=True,
    ))
