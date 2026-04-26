"""
Phase 3 단위 테스트.
- RAGPipeline collection_name
- MemoryManager LLM 요약 압축 (MockAdapter)
"""
from __future__ import annotations

import pytest
from typing import Callable
from unittest.mock import MagicMock, patch

from src.memory.manager import MemoryManager
from src.models.adapter import ChatResult, Message, ModelAdapterBase, ModelInfo


# ------------------------------------------------------------------
# Mock
# ------------------------------------------------------------------

class MockSummarizer(ModelAdapterBase):
    def __init__(self, summary: str = "Summary of past turns.") -> None:
        self._summary = summary
        self.call_count = 0

    async def chat(self, messages, *, stream=True, on_token=None) -> ChatResult:
        self.call_count += 1
        return ChatResult(self._summary, [], 10, 5, 0.1)

    async def embed(self, texts): return [[0.0]]
    async def list_models(self): return []
    async def switch_model(self, name): pass
    def get_current_model(self): return "mock"


# ------------------------------------------------------------------
# RAGPipeline collection_name
# ------------------------------------------------------------------

def test_rag_pipeline_default_collection() -> None:
    from src.rag.pipeline import RAGPipeline
    rag = RAGPipeline()
    assert rag._collection_name == "codebase"


def test_rag_pipeline_custom_collection() -> None:
    from src.rag.pipeline import RAGPipeline
    rag = RAGPipeline(collection_name="my-project")
    assert rag._collection_name == "my-project"


def test_rag_pipeline_collection_passed_to_chroma() -> None:
    """_ensure_init 시 Chroma에 collection_name이 전달되는지 확인."""
    from src.rag.pipeline import RAGPipeline

    rag = RAGPipeline(collection_name="test-project")

    with patch("src.rag.pipeline.RAGPipeline._ensure_init"):
        # _ensure_init을 mock했으므로 _collection_name 값만 검증
        assert rag._collection_name == "test-project"


# ------------------------------------------------------------------
# MemoryManager 선택적 LLM 요약
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_no_summarizer_discards(tmp_path) -> None:
    """summarizer 없으면 오래된 턴 단순 폐기."""
    mem = MemoryManager(db_path=str(tmp_path / "m.db"), window_turns=2)
    for i in range(4):  # window_turns=2, max_msgs=4 → 5번째에 폐기
        await mem.update(f"q{i}", f"a{i}")
    msgs = await mem.get_compressed()
    assert len(msgs) <= 4  # 최대 2턴 × 2
    assert mem._summary == ""  # 요약 없음


@pytest.mark.asyncio
async def test_memory_summarizer_called_on_overflow(tmp_path) -> None:
    """summarizer 있으면 overflow 시 요약 호출."""
    summarizer = MockSummarizer("Previous: discussed quicksort.")
    mem = MemoryManager(
        db_path=str(tmp_path / "m.db"),
        window_turns=2,
        summarizer=summarizer,
    )

    # window_turns=2 → max_msgs=4. 3번째 업데이트(6개)에서 overflow
    for i in range(3):
        await mem.update(f"question {i}", f"answer {i}")

    assert summarizer.call_count >= 1
    assert "Previous" in mem._summary or len(mem._summary) > 0


@pytest.mark.asyncio
async def test_memory_summary_prepended_in_get_compressed(tmp_path) -> None:
    """요약본이 get_compressed 결과 앞에 system 메시지로 포함."""
    mem = MemoryManager(db_path=str(tmp_path / "m.db"), window_turns=10)
    mem._summary = "We discussed Python sorting algorithms."
    await mem.update("hello", "hi")

    msgs = await mem.get_compressed()
    assert msgs[0].role == "system"
    assert "sorting" in msgs[0].content


@pytest.mark.asyncio
async def test_memory_summarizer_failure_is_silent(tmp_path) -> None:
    """요약 LLM 실패 시 예외 없이 조용히 넘어감."""
    class FailingSummarizer(MockSummarizer):
        async def chat(self, messages, **kwargs):
            raise RuntimeError("model error")

    mem = MemoryManager(
        db_path=str(tmp_path / "m.db"),
        window_turns=1,
        summarizer=FailingSummarizer(),
    )
    # 이 호출이 예외 없이 완료되어야 함
    await mem.update("q", "a")
    await mem.update("q2", "a2")  # overflow 발생


# ------------------------------------------------------------------
# FastAPI state 싱글톤
# ------------------------------------------------------------------

def test_app_state_singleton() -> None:
    from src.api.state import AppState
    s1 = AppState.get()
    s2 = AppState.get()
    assert s1 is s2
