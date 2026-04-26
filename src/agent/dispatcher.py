"""
TaskDispatcher — 의도 분류 + 모델 슬롯 라우팅.

경량 1.5b 모델로 의도를 먼저 분류 (~0.3초),
그 결과에 따라 ModelPool의 적절한 슬롯을 획득.
"""
from __future__ import annotations

import json

from src.models.adapter import Message
from src.models.pool import ModelPool
from src.models.ollama_adapter import OllamaAdapter
from src.observe.bus import ObservabilityBus

_INTENT_PROMPT = """\
Classify the user request into ONE category. Reply with JSON only, no explanation.

Categories:
  code_gen    - write new code, implement feature
  code_review - review, explain, or analyze existing code
  file_edit   - modify a specific file
  chat        - general question or conversation
  rag_query   - search codebase or documentation
  system      - agent/tool management, model switching

Request: {query}

JSON reply format: {{"intent": "<category>", "confidence": 0.0}}"""

_INTENT_TO_PURPOSE: dict[str, str] = {
    "code_gen":     "code",
    "code_review":  "code",
    "file_edit":    "agent",
    "chat":         "chat",
    "rag_query":    "chat",
    "system":       "agent",
}


class TaskDispatcher:
    def __init__(self, pool: ModelPool, obs: ObservabilityBus) -> None:
        self._pool = pool
        self._obs = obs

    async def classify(self, user_input: str) -> str:
        """경량 classifier 모델로 의도 분류. 실패 시 'chat' 폴백."""
        adapter = await self._pool.acquire("classifier")
        try:
            result = await adapter.chat(
                [Message(
                    role="user",
                    content=_INTENT_PROMPT.format(query=user_input[:300]),
                )],
                stream=False,
            )
            # JSON 파싱 (마크다운 코드블록 제거)
            raw = result.content.strip().strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
            data = json.loads(raw)
            intent = data.get("intent", "chat")
        except Exception:
            intent = "chat"
        finally:
            await self._pool.release("classifier")

        self._obs.emit("intent_classified", {
            "intent": intent,
            "input_preview": user_input[:80],
        })
        return intent

    async def dispatch(self, user_input: str) -> tuple[str, OllamaAdapter]:
        """의도 분류 + 슬롯 획득. Returns (intent, adapter)."""
        intent = await self.classify(user_input)
        purpose = _INTENT_TO_PURPOSE.get(intent, "chat")
        adapter = await self._pool.acquire(purpose)
        return intent, adapter

    async def release(self, intent: str) -> None:
        purpose = _INTENT_TO_PURPOSE.get(intent, "chat")
        await self._pool.release(purpose)
