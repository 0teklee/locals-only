"""
Settings — 환경변수 + config/models.yaml 로드.
우선순위: 환경변수 > .env.local > config/*.yaml 기본값
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

# .env.local 로드 (python-dotenv 없어도 동작)
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
    except ImportError:
        # python-dotenv 없으면 직접 파싱
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

_load_env_file(Path(__file__).parent.parent / ".env.local")


class Settings:
    """환경변수 + models.yaml 기반 설정."""

    def __init__(self) -> None:
        # Ollama
        self.OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

        # 모델
        self.DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "qwen2.5-coder:7b")
        self.EMBED_MODEL: str = os.getenv("EMBED_MODEL", "nomic-embed-text")

        # 스토리지
        self.CHROMA_PATH: str = os.getenv("CHROMA_PATH", "./data/chroma")
        self.MEMORY_DB_PATH: str = os.getenv("MEMORY_DB_PATH", "./data/memory.db")

        # 에이전트
        self.MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "8192"))
        self.MAX_OUTPUT_TOKENS: int = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))
        self.MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
        self.MEMORY_WINDOW_TURNS: int = int(os.getenv("MEMORY_WINDOW_TURNS", "10"))

        # 디버그
        self.DEBUG_DUMP_CONTEXT: bool = os.getenv("DEBUG_DUMP_CONTEXT", "false").lower() == "true"
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

        # 시스템 프롬프트
        self.SYSTEM_PROMPT: str = os.getenv(
            "SYSTEM_PROMPT",
            "[ROLE] Local coding agent. Offline. M1 Mac.\n"
            "[FORMAT] Concise. Code blocks only. No preamble.\n"
            "[TOOLS] Use tools for file/shell ops. Confirm before destructive actions.",
        )

        # models.yaml 로드
        self._models_config: dict = {}
        self._load_models_yaml()

    def _load_models_yaml(self) -> None:
        config_path = Path(__file__).parent.parent / "config" / "models.yaml"
        if config_path.exists():
            with open(config_path) as f:
                self._models_config = yaml.safe_load(f) or {}

    def get_model_params(self, model_name: str) -> dict:
        """모델별 파라미터 반환. 등록 안 된 모델은 기본값."""
        presets: dict = self._models_config.get("presets", {})
        defaults: dict = self._models_config.get("default_params", {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_ctx": 8192,
            "num_predict": 1024,
        })
        return presets.get(model_name, defaults)

    def get_profile_model(self, purpose: str, ram_gb: float) -> str:
        """RAM 프로파일에 따른 모델 선택."""
        profile_key = "ram_16gb" if ram_gb >= 14 else "ram_8gb"
        profiles: dict = self._models_config.get("profiles", {})
        defaults_map: dict = self._models_config.get("defaults", {})
        return (
            profiles.get(profile_key, {}).get(purpose)
            or defaults_map.get(purpose)
            or self.DEFAULT_MODEL
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# 편의 싱글톤
settings = get_settings()
