"""
ModelAdapterBase — 모든 LLM 백엔드의 공통 인터페이스.

Message: 대화 메시지 단위
ChatResult: chat() 호출의 최종 결과 (스트리밍 완료 후)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ModelInfo:
    name: str
    size_gb: float
    context_length: int
    supports_tools: bool
    quantization: str  # "Q4_K_M", "Q8_0", "F16", ...


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[dict] | None = field(default=None)
    tool_call_id: str | None = field(default=None)

    def to_dict(self) -> dict:
        d: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class ChatResult:
    """chat() 완료 후 반환되는 최종 결과."""

    content: str
    tool_calls: list[dict]      # Ollama message.tool_calls (done 청크에서 추출)
    input_tokens: int           # prompt_eval_count
    output_tokens: int          # eval_count
    elapsed_sec: float


class ModelAdapterBase(ABC):
    """모든 LLM 백엔드의 공통 인터페이스."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
    ) -> ChatResult:
        """
        LLM 대화 호출.

        on_token: 스트리밍 토큰을 받을 콜백 (None이면 스트리밍 없음).
        반환값: ChatResult (content + tool_calls 포함).
        """
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 리스트를 임베딩 벡터로 변환."""
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """로컬에 설치된 모델 목록 반환."""
        ...

    @abstractmethod
    async def switch_model(self, model_name: str) -> None:
        """활성 모델 교체 (재시작 불필요)."""
        ...

    @abstractmethod
    def get_current_model(self) -> str:
        """현재 활성 모델명 반환."""
        ...
