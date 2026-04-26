"""
AppState — FastAPI 앱 전역 공유 상태.

ModelPool, AgentRunner 등 무거운 객체를 요청 간에 공유.
싱글톤 패턴으로 lifespan에서 초기화 후 재사용.
"""
from __future__ import annotations

from functools import lru_cache

from src.models.registry import ModelRegistry
from src.models.pool import ModelPool
from src.observe.bus import ObservabilityBus


class AppState:
    _instance: AppState | None = None

    def __init__(self) -> None:
        self.obs = ObservabilityBus.get_default()
        self.registry = ModelRegistry()
        self.pool = ModelPool(self.registry, self.obs)

    @classmethod
    def get(cls) -> AppState:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
