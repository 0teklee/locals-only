"""
단위 테스트 — ContextBuilder.
"""
from __future__ import annotations

import pytest

from src.context.builder import ContextBuilder, TokenBudget
from src.memory.manager import MemoryManager
from src.models.adapter import Message


@pytest.fixture
def memory(tmp_path) -> MemoryManager:
    return MemoryManager(db_path=str(tmp_path / "test.db"), window_turns=5)


@pytest.fixture
def builder(memory) -> ContextBuilder:
    return ContextBuilder(
        memory=memory,
        rag=None,
        system_prompt="You are a test assistant.",
        budget=TokenBudget(total=4096, system=100, history=500, rag=500, input=200, output_reserved=1024),
    )


@pytest.mark.asyncio
async def test_build_includes_system_and_user(builder) -> None:
    messages = await builder.build("Hello!")
    roles = [m.role for m in messages]
    assert "system" in roles
    assert messages[-1].role == "user"
    assert messages[-1].content == "Hello!"


@pytest.mark.asyncio
async def test_build_returns_list_of_message(builder) -> None:
    messages = await builder.build("test")
    for m in messages:
        assert isinstance(m, Message)


@pytest.mark.asyncio
async def test_build_with_history(builder, memory) -> None:
    await memory.update("prev question", "prev answer")
    messages = await builder.build("new question")
    roles = [m.role for m in messages]
    # 히스토리 메시지가 포함되어야 함
    assert roles.count("user") >= 2 or roles.count("assistant") >= 1


@pytest.mark.asyncio
async def test_last_budget_populated(builder) -> None:
    await builder.build("What is 2+2?")
    assert "system_tokens" in builder.last_budget
    assert "input_tokens" in builder.last_budget


@pytest.mark.asyncio
async def test_system_truncation(memory) -> None:
    long_prompt = "x " * 1000  # 2000 chars
    builder = ContextBuilder(
        memory=memory,
        rag=None,
        system_prompt=long_prompt,
        budget=TokenBudget(total=4096, system=10, history=500, rag=0, input=200, output_reserved=512),
    )
    messages = await builder.build("hi")
    sys_msg = next(m for m in messages if m.role == "system")
    # system budget = 10 tokens × 4 chars = 40 chars max
    assert len(sys_msg.content) <= 40 + 5  # 약간의 여유
