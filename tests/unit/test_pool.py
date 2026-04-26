"""
단위 테스트 — ModelPool + TaskDispatcher (MockAdapter 사용).
"""
from __future__ import annotations

import asyncio
import pytest
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.adapter import ChatResult, Message, ModelAdapterBase, ModelInfo
from src.models.pool import ModelPool
from src.models.registry import ModelRegistry
from src.observe.bus import ObservabilityBus


class MockAdapter(ModelAdapterBase):
    def __init__(self) -> None:
        self._model = "mock"
        self.switch_calls: list[str] = []

    async def chat(self, messages, *, stream=True, on_token=None) -> ChatResult:
        return ChatResult("ok", [], 5, 3, 0.1)

    async def embed(self, texts) -> list[list[float]]:
        return [[0.0] * 3 for _ in texts]

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def switch_model(self, name: str) -> None:
        self._model = name
        self.switch_calls.append(name)

    def get_current_model(self) -> str:
        return self._model


@pytest.fixture
def obs() -> ObservabilityBus:
    return ObservabilityBus(log_path="/tmp/test_pool_events.jsonl")


@pytest.fixture
def registry() -> ModelRegistry:
    reg = MagicMock(spec=ModelRegistry)
    reg.get_default.side_effect = lambda purpose: {
        "embed": "nomic-embed-text",
        "code": "qwen2.5-coder:7b",
        "chat": "gemma3:4b",
        "agent": "qwen2.5:7b",
        "classifier": "qwen2.5-coder:1.5b",
    }.get(purpose, "qwen2.5:7b")
    return reg


@pytest.mark.asyncio
async def test_pool_initializes_slots(registry, obs) -> None:
    with patch("src.models.pool.OllamaAdapter", return_value=MockAdapter()):
        pool = ModelPool(registry, obs)
        await pool.initialize()
        assert "embed" in pool._slots
        assert "main" in pool._slots


@pytest.mark.asyncio
async def test_pool_acquire_release(registry, obs) -> None:
    with patch("src.models.pool.OllamaAdapter", return_value=MockAdapter()):
        pool = ModelPool(registry, obs)
        await pool.initialize()

        adapter = await pool.acquire("code")
        assert adapter is not None

        await pool.release("code")
        # 릴리즈 후 다시 획득 가능
        adapter2 = await pool.acquire("code")
        assert adapter2 is not None
        await pool.release("code")


@pytest.mark.asyncio
async def test_pool_embed_slot_fixed(registry, obs) -> None:
    """embed 슬롯은 모델 전환 없이 항상 nomic-embed-text 유지."""
    mock = MockAdapter()
    with patch("src.models.pool.OllamaAdapter", return_value=mock):
        pool = ModelPool(registry, obs)
        await pool.initialize()

        await pool.acquire("embed")
        # embed 슬롯에서는 switch_model이 호출되지 않아야 함
        assert mock.switch_calls == []
        await pool.release("embed")


@pytest.mark.asyncio
async def test_pool_initialize_idempotent(registry, obs) -> None:
    with patch("src.models.pool.OllamaAdapter", return_value=MockAdapter()):
        pool = ModelPool(registry, obs)
        await pool.initialize()
        await pool.initialize()  # 두 번 호출해도 슬롯 재생성 안 함
        assert len(pool._slots) == 2
