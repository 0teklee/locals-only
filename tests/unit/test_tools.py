"""
단위 테스트 — ToolRegistry + 기본 도구들.
"""
from __future__ import annotations

import asyncio
import pytest
from pathlib import Path

from src.observe.bus import ObservabilityBus
from src.tools.registry import ToolRegistry, ToolSpec
from src.tools import file_tools, shell_tools, git_tools


@pytest.fixture
def obs() -> ObservabilityBus:
    return ObservabilityBus(log_path="/tmp/test_events.jsonl")


@pytest.fixture
def registry(obs) -> ToolRegistry:
    reg = ToolRegistry(obs)
    file_tools.register(reg)
    shell_tools.register(reg)
    git_tools.register(reg)
    return reg


# ------------------------------------------------------------------
# ToolRegistry
# ------------------------------------------------------------------

def test_register_and_list(registry) -> None:
    names = registry.list_tools()
    assert "read_file" in names
    assert "write_file" in names
    assert "run_command" in names
    assert "git_status" in names


def test_get_schema(registry) -> None:
    schema = registry.get_schema()
    assert isinstance(schema, list)
    assert all("function" in s for s in schema)


@pytest.mark.asyncio
async def test_execute_unknown_tool(registry) -> None:
    result = await registry.execute("nonexistent", {})
    assert "Error" in result


# ------------------------------------------------------------------
# file_tools
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_write_file(registry, tmp_path) -> None:
    test_file = str(tmp_path / "test.txt")

    # write
    result = await registry.execute("write_file", {"path": test_file, "content": "hello"})
    assert "Written" in result

    # read
    content = await registry.execute("read_file", {"path": test_file})
    assert content == "hello"


@pytest.mark.asyncio
async def test_read_nonexistent_file(registry) -> None:
    result = await registry.execute("read_file", {"path": "/tmp/nonexistent_xyz.txt"})
    assert "Error" in result


@pytest.mark.asyncio
async def test_patch_file(registry, tmp_path) -> None:
    p = tmp_path / "patch_test.txt"
    p.write_text("hello world")

    result = await registry.execute("patch_file", {
        "path": str(p),
        "search": "hello",
        "replace": "goodbye",
    })
    assert "Patched" in result
    assert p.read_text() == "goodbye world"


@pytest.mark.asyncio
async def test_list_directory(registry, tmp_path) -> None:
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("y")
    result = await registry.execute("list_directory", {"path": str(tmp_path)})
    assert "a.py" in result
    assert "b.py" in result


@pytest.mark.asyncio
async def test_find_files(registry, tmp_path) -> None:
    (tmp_path / "foo.py").write_text("")
    (tmp_path / "bar.txt").write_text("")
    result = await registry.execute("find_files", {"pattern": "*.py", "root": str(tmp_path)})
    assert "foo.py" in result
    assert "bar.txt" not in result


# ------------------------------------------------------------------
# shell_tools
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_allowed_command(registry) -> None:
    result = await registry.execute("run_command", {"command": "echo hello"})
    assert "hello" in result


@pytest.mark.asyncio
async def test_run_blocked_command(registry) -> None:
    result = await registry.execute("run_command", {"command": "rm -rf /"})
    assert "allowlist" in result.lower() or "Error" in result


@pytest.mark.asyncio
async def test_run_python(registry) -> None:
    result = await registry.execute("run_python", {"code": "print(1 + 1)"})
    assert "2" in result


# ------------------------------------------------------------------
# ObservabilityBus
# ------------------------------------------------------------------

def test_bus_emit_and_subscribe(obs) -> None:
    received: list[dict] = []
    obs.subscribe(received.append)
    obs.emit("test_event", {"key": "value"})
    assert len(received) == 1
    assert received[0]["type"] == "test_event"
    assert received[0]["data"]["key"] == "value"


def test_bus_unsubscribe(obs) -> None:
    received: list[dict] = []

    def cb(e: dict) -> None:
        received.append(e)

    obs.subscribe(cb)
    obs.emit("e1", {})
    obs.unsubscribe(cb)
    obs.emit("e2", {})
    assert len(received) == 1
