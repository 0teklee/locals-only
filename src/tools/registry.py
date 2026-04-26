"""
ToolRegistry — 런타임 도구 등록·탐색·실행.

도구 추가: register(ToolSpec(...)) 호출만으로 완료.
모든 실행은 감사 로그에 기록 (white-box).
동기 핸들러는 asyncio.to_thread()로 자동 래핑.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.observe.bus import ObservabilityBus


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON Schema (OpenAI 형식)
    handler: Callable
    requires_confirm: bool = False  # 파괴적 작업 여부


class ToolRegistry:
    def __init__(self, obs: ObservabilityBus) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._obs = obs
        self._log_path = Path("data/logs/tool_calls.jsonl")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get_schema(self) -> list[dict]:
        """LLM에게 전달할 도구 스키마 (OpenAI function-calling 형식)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def execute(self, name: str, args: dict) -> Any:
        spec = self._tools.get(name)
        if not spec:
            return f"Error: unknown tool '{name}'"

        start = time.monotonic()
        self._obs.emit("tool_call_start", {"name": name, "args": args})
        self._log_call(name, args, "start")

        try:
            if inspect.iscoroutinefunction(spec.handler):
                result = await spec.handler(**args)
            else:
                result = await asyncio.to_thread(spec.handler, **args)
        except Exception as e:
            result = f"Error: {e}"

        elapsed = round(time.monotonic() - start, 3)
        self._obs.emit("tool_call_end", {
            "name": name,
            "elapsed_sec": elapsed,
            "result_size": len(str(result)),
        })
        self._log_call(name, args, "end", elapsed=elapsed, result_size=len(str(result)))
        return result

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _log_call(
        self,
        name: str,
        args: dict,
        phase: str,
        *,
        elapsed: float | None = None,
        result_size: int | None = None,
    ) -> None:
        entry: dict = {"name": name, "phase": phase, "ts": time.time()}
        if phase == "start":
            entry["args"] = args
        else:
            entry["elapsed_sec"] = elapsed
            entry["result_size"] = result_size
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(line)
