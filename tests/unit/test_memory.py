"""
단위 테스트 — MemoryManager.
"""
from __future__ import annotations

import pytest
from src.memory.manager import MemoryManager
from src.models.adapter import Message


@pytest.fixture
def memory(tmp_path) -> MemoryManager:
    return MemoryManager(db_path=str(tmp_path / "mem.db"), window_turns=3)


@pytest.mark.asyncio
async def test_empty_history(memory) -> None:
    msgs = await memory.get_compressed()
    assert msgs == []


@pytest.mark.asyncio
async def test_update_adds_messages(memory) -> None:
    await memory.update("hello", "hi there")
    msgs = await memory.get_compressed()
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].role == "assistant"


@pytest.mark.asyncio
async def test_sliding_window(memory) -> None:
    """window_turns=3 이므로 최대 6개 메시지 유지."""
    for i in range(5):
        await memory.update(f"q{i}", f"a{i}")
    msgs = await memory.get_compressed()
    # 3턴 × 2 = 6개
    assert len(msgs) <= 6


@pytest.mark.asyncio
async def test_token_budget(memory) -> None:
    await memory.update("question", "answer " * 200)  # 긴 답변
    # max_tokens=10으로 제한 시 빈 리스트 (너무 큼)
    msgs = await memory.get_compressed(max_tokens=5)
    # 단어 200개 답변은 5 토큰 예산 초과 → 포함 안 됨
    assert all(len(m.content.split()) <= 5 for m in msgs)


@pytest.mark.asyncio
async def test_clear(memory) -> None:
    await memory.update("q", "a")
    memory.clear()
    msgs = await memory.get_compressed()
    assert msgs == []


@pytest.mark.asyncio
async def test_sqlite_persistence(tmp_path) -> None:
    db_path = str(tmp_path / "persist.db")
    m1 = MemoryManager(db_path=db_path, window_turns=10)
    await m1.update("stored", "response")

    # 새 인스턴스로 복원
    m2 = MemoryManager(db_path=db_path, window_turns=10)
    m2.load_session()
    msgs = await m2.get_compressed()
    assert len(msgs) == 2
    assert msgs[0].content == "stored"
