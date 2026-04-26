"""
ModelPool — 다중 LLM 슬롯 관리자.

슬롯 구성:
  embed: nomic-embed-text 상시 고정 (270MB, 교체 안 함)
  main:  요청 의도에 따라 code/chat/agent 모델로 전환

병렬 가능:
  embed 슬롯 ↔ main 슬롯은 동시 실행 가능.
  main 슬롯 내 요청은 직렬 (Ollama 단일 모델 처리 제약).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from src.models.ollama_adapter import OllamaAdapter
from src.models.registry import ModelRegistry
from src.observe.bus import ObservabilityBus


@dataclass
class _Slot:
    purpose: str
    adapter: OllamaAdapter
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ModelPool:
    def __init__(self, registry: ModelRegistry, obs: ObservabilityBus) -> None:
        self._registry = registry
        self._obs = obs
        self._slots: dict[str, _Slot] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """시작 시 슬롯 초기화. embed 슬롯은 항상 고정."""
        if self._initialized:
            return

        embed_model = self._registry.get_default("embed")
        main_model = self._registry.get_default("code")

        self._slots["embed"] = _Slot(
            purpose="embed",
            adapter=OllamaAdapter(model=embed_model, obs_bus=self._obs),
        )
        self._slots["main"] = _Slot(
            purpose="main",
            adapter=OllamaAdapter(model=main_model, obs_bus=self._obs),
        )
        self._initialized = True
        self._obs.emit("pool_initialized", {"embed": embed_model, "main": main_model})

    # ------------------------------------------------------------------

    async def acquire(self, purpose: str) -> OllamaAdapter:
        """
        슬롯 획득 + 필요 시 모델 전환.
        purpose == "embed" → embed 슬롯 (모델 고정).
        그 외 → main 슬롯 (목적에 맞는 모델로 전환).
        """
        if not self._initialized:
            await self.initialize()

        slot_key = "embed" if purpose == "embed" else "main"
        slot = self._slots[slot_key]
        await slot.lock.acquire()

        if slot_key == "main":
            target = self._registry.get_default(purpose)
            if slot.adapter.get_current_model() != target:
                await slot.adapter.switch_model(target)

        return slot.adapter

    async def release(self, purpose: str) -> None:
        slot_key = "embed" if purpose == "embed" else "main"
        slot = self._slots[slot_key]
        if slot.lock.locked():
            slot.lock.release()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """임베딩 전용 단축 메서드 (acquire/release 없이)."""
        if not self._initialized:
            await self.initialize()
        return await self._slots["embed"].adapter.embed(texts)

