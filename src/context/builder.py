"""
ContextBuilder — 토큰 예산 기반 컨텍스트 조립.

항상 list[Message]를 반환 (dict 혼용 없음).
각 슬롯이 예산을 초과하면 자동 트런케이션.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from src.models.adapter import Message
from src.config import settings


@dataclass
class TokenBudget:
    total: int = 8192
    system: int = 300
    history: int = 1500
    rag: int = 2000
    input: int = 500
    output_reserved: int = 2048

    @property
    def remaining(self) -> int:
        return self.total - self.system - self.history - self.rag - self.input - self.output_reserved


class ContextBuilder:
    def __init__(
        self,
        memory: "MemoryManager",
        rag: "RAGPipeline | None" = None,
        system_prompt: str | None = None,
        budget: TokenBudget | None = None,
    ) -> None:
        self._memory = memory
        self._rag = rag
        self._system_prompt = system_prompt or settings.SYSTEM_PROMPT
        self.budget = budget or TokenBudget()
        self.last_budget: dict = {}

    async def build(self, user_input: str) -> list[Message]:
        """
        컨텍스트를 list[Message]로 조립.

        순서: [system] → [history] → [rag_context] → [user]
        """
        messages: list[Message] = []

        # 1. 시스템 프롬프트
        if self._system_prompt:
            # budget.system 토큰 × 4자 (한국어 포함 여유)
            truncated = self._system_prompt[: self.budget.system * 4]
            messages.append(Message(role="system", content=truncated))

        # 2. 대화 히스토리
        history = await self._memory.get_compressed(max_tokens=self.budget.history)
        messages.extend(history)

        # 3. RAG 컨텍스트 (pipeline이 주입된 경우에만)
        rag_ctx = ""
        if self._rag is not None:
            try:
                rag_ctx = await self._rag.search(user_input, max_tokens=self.budget.rag)
            except Exception:
                rag_ctx = ""
        if rag_ctx:
            messages.append(Message(role="system", content=f"[Context]\n{rag_ctx}"))

        # 4. 사용자 입력
        messages.append(Message(role="user", content=user_input))

        # White-Box: 예산 현황 기록
        self.last_budget = {
            "system_tokens": len(self._system_prompt.split()) if self._system_prompt else 0,
            "history_messages": len(history),
            "rag_tokens": len(rag_ctx.split()) if rag_ctx else 0,
            "input_tokens": len(user_input.split()),
            "remaining": self.budget.remaining,
        }

        # 컨텍스트 덤프 (디버그 모드)
        if settings.DEBUG_DUMP_CONTEXT:
            self._dump_context(messages)

        return messages

    def _dump_context(self, messages: list[Message]) -> None:
        dump_dir = Path("data/logs/context_dumps")
        dump_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = dump_dir / f"{ts}.md"
        lines = [f"# Context Dump — {ts}\n"]
        for m in messages:
            lines.append(f"## [{m.role.upper()}]\n{m.content}\n")
        path.write_text("\n".join(lines), encoding="utf-8")
