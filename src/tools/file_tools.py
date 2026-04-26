"""
FILE 도구 — 파일시스템 읽기/쓰기.

read_file, write_file, patch_file, list_directory, find_files
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

from src.tools.registry import ToolRegistry, ToolSpec

_MAX_READ_BYTES = 100 * 1024  # 100KB


def _read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"
    raw = p.read_bytes()
    if len(raw) > _MAX_READ_BYTES:
        return raw[:_MAX_READ_BYTES].decode("utf-8", errors="replace") + "\n... [truncated]"
    return raw.decode("utf-8", errors="replace")


def _write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {path}"


def _patch_file(path: str, search: str, replace: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    text = p.read_text(encoding="utf-8")
    count = text.count(search)
    if count == 0:
        return "Error: search string not found"
    if count > 1:
        return f"Error: search string found {count} times (must be unique)"
    p.write_text(text.replace(search, replace, 1), encoding="utf-8")
    return f"Patched 1 occurrence in {path}"


def _list_directory(path: str = ".", pattern: str = "*") -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: path not found: {path}"
    entries = sorted(p.glob(pattern))[:50]
    lines = []
    for e in entries:
        tag = "d" if e.is_dir() else "f"
        lines.append(f"[{tag}] {e.name}")
    return "\n".join(lines) if lines else "(empty)"


def _find_files(pattern: str, root: str = ".") -> str:
    matches = sorted(glob.glob(os.path.join(root, "**", pattern), recursive=True))[:100]
    return "\n".join(matches) if matches else "(no matches)"


# ------------------------------------------------------------------
# 등록 함수
# ------------------------------------------------------------------

def register(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="read_file",
        description="Read file contents (max 100KB). Returns text.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (relative or absolute)"},
            },
            "required": ["path"],
        },
        handler=_read_file,
    ))
    registry.register(ToolSpec(
        name="write_file",
        description="Write (create or overwrite) a file with content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        handler=_write_file,
        requires_confirm=True,
    ))
    registry.register(ToolSpec(
        name="patch_file",
        description="Replace exactly one occurrence of a search string in a file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "search": {"type": "string", "description": "Exact text to find (must be unique)"},
                "replace": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "search", "replace"],
        },
        handler=_patch_file,
        requires_confirm=True,
    ))
    registry.register(ToolSpec(
        name="list_directory",
        description="List directory contents (max 50 entries).",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "pattern": {"type": "string", "default": "*"},
            },
        },
        handler=_list_directory,
    ))
    registry.register(ToolSpec(
        name="find_files",
        description="Find files matching a glob pattern recursively (max 100).",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern e.g. '*.py'"},
                "root": {"type": "string", "default": "."},
            },
            "required": ["pattern"],
        },
        handler=_find_files,
    ))
