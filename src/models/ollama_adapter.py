"""
OllamaAdapter — Ollama HTTP API 래퍼.

White-Box 로깅: 모든 호출 전후 JSONL 기록.
Model-Agnostic: 모델명은 항상 외부(config/settings)에서 주입.
Async-Safe: 파일 I/O는 asyncio.to_thread()로 이벤트 루프 블로킹 방지.
tool_calls: 스트리밍 텍스트가 아닌 done 청크의 message.tool_calls에서 추출.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Callable

import httpx

from src.models.adapter import ChatResult, Message, ModelAdapterBase, ModelInfo
from src.observe.bus import ObservabilityBus
from src.config import settings


class OllamaAdapter(ModelAdapterBase):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        obs_bus: ObservabilityBus | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_HOST).rstrip("/")
        self._model = model or settings.DEFAULT_MODEL
        self._params = settings.get_model_params(self._model)
        self._obs = obs_bus or ObservabilityBus.get_default()
        self._log_path = Path("data/logs/llm_calls.jsonl")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
    ) -> ChatResult:
        payload = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,  # 항상 스트리밍 — done 청크에서 tool_calls 수집
            "options": self._params,
        }

        call_id = str(uuid.uuid4())[:8]
        start = time.monotonic()
        await self._log_async(self._start_entry(call_id, messages))
        self._obs.emit("llm_call_start", {"id": call_id, "model": self._model})

        output_parts: list[str] = []
        tool_calls: list[dict] = []
        eval_count = 0
        prompt_eval_count = 0

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = chunk.get("message", {})

                    # 텍스트 토큰 수집 + 스트리밍 콜백
                    if token := msg.get("content", ""):
                        output_parts.append(token)
                        if on_token and stream:
                            on_token(token)

                    # done 청크: tool_calls + 토큰 카운트 추출
                    if chunk.get("done"):
                        tool_calls = msg.get("tool_calls") or []
                        eval_count = chunk.get("eval_count", 0)
                        prompt_eval_count = chunk.get("prompt_eval_count", 0)

        elapsed = time.monotonic() - start
        result = ChatResult(
            content="".join(output_parts),
            tool_calls=tool_calls,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            elapsed_sec=round(elapsed, 3),
        )
        await self._log_async(self._end_entry(call_id, result))
        self._obs.emit("llm_call_end", {
            "id": call_id,
            "output_tokens": result.output_tokens,
            "elapsed_sec": result.elapsed_sec,
            "tps": round(result.output_tokens / elapsed, 1) if elapsed > 0 else 0,
            "has_tool_calls": bool(tool_calls),
        })
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama /api/embed returns {"embeddings": [[...]]}
            return data.get("embeddings", [])

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        result: list[ModelInfo] = []
        for m in data.get("models", []):
            details = m.get("details", {})
            result.append(ModelInfo(
                name=m["name"],
                size_gb=round(m.get("size", 0) / 1e9, 2),
                context_length=details.get("context_length", 4096),
                supports_tools="tools" in details.get("capabilities", []),
                quantization=details.get("quantization_level", "unknown"),
            ))
        return result

    async def switch_model(self, model_name: str) -> None:
        self._model = model_name
        self._params = settings.get_model_params(model_name)
        self._obs.emit("model_switched", {"model": model_name, "params": self._params})

    def get_current_model(self) -> str:
        return self._model

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _log_async(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        await asyncio.to_thread(self._write_log, line)

    def _write_log(self, line: str) -> None:
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def _start_entry(self, call_id: str, messages: list[Message]) -> dict:
        return {
            "id": call_id,
            "type": "llm_call_start",
            "model": self._model,
            "input_messages": len(messages),
            "input_tokens_est": int(sum(len(m.content.split()) * 1.3 for m in messages)),
            "params": self._params,
            "ts": time.time(),
        }

    def _end_entry(self, call_id: str, result: ChatResult) -> dict:
        return {
            "id": call_id,
            "type": "llm_call_end",
            "output_tokens": result.output_tokens,
            "input_tokens": result.input_tokens,
            "elapsed_sec": result.elapsed_sec,
            "tps": round(result.output_tokens / result.elapsed_sec, 1)
            if result.elapsed_sec > 0
            else 0,
            "has_tool_calls": bool(result.tool_calls),
            "ts": time.time(),
        }
