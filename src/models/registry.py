"""
ModelRegistry — RAM 기반 최적 모델 자동 선택.

새 모델 추가: config/models.yaml 수정만으로 완료.
"""
from __future__ import annotations

import psutil
import yaml
from pathlib import Path


class ModelRegistry:
    def __init__(self, config_path: str = "config/models.yaml") -> None:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                self._cfg: dict = yaml.safe_load(f) or {}
        else:
            self._cfg = {}

    # ------------------------------------------------------------------

    @property
    def _ram_gb(self) -> float:
        return psutil.virtual_memory().total / 1e9

    def get_default(self, purpose: str) -> str:
        """
        purpose: "code" | "chat" | "agent" | "embed" | "classifier"
        RAM에 따라 자동 프로파일 선택.
        """
        profile_key = "ram_16gb" if self._ram_gb >= 14 else "ram_8gb"
        profiles: dict = self._cfg.get("profiles", {})
        defaults: dict = self._cfg.get("defaults", {})
        return (
            profiles.get(profile_key, {}).get(purpose)
            or defaults.get(purpose)
            or "qwen2.5-coder:7b"
        )

    def get_params(self, model_name: str) -> dict:
        """모델별 파라미터 반환. 등록 안 된 모델은 기본값."""
        presets: dict = self._cfg.get("presets", {})
        defaults: dict = self._cfg.get("default_params", {})
        return presets.get(model_name, defaults)

    def list_supported(self) -> list[str]:
        return list(self._cfg.get("presets", {}).keys())
