"""
ObservabilityBus — White-Box 이벤트 허브.

모든 파이프라인 단계에서 emit()으로 이벤트를 발행.
구독자(SSE, 로그 파일 등)가 실시간으로 수신.
파일 I/O는 이벤트 루프를 블로킹하지 않도록 executor로 처리.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable


class ObservabilityBus:
    """
    동기 emit() + 비동기 안전 파일 쓰기.

    emit()은 동기 메서드이므로 async/sync 어디서든 호출 가능.
    파일 I/O는 이벤트 루프가 실행 중이면 executor,
    아니면(초기화 단계 등) 동기로 처리.
    """

    _default: ObservabilityBus | None = None

    def __init__(self, log_path: str = "data/logs/events.jsonl") -> None:
        self._subscribers: list[Callable[[dict], None]] = []
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 싱글톤
    # ------------------------------------------------------------------

    @classmethod
    def get_default(cls) -> ObservabilityBus:
        if cls._default is None:
            cls._default = cls()
        return cls._default

    # ------------------------------------------------------------------
    # 구독
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[dict], None]) -> None:
        self._subscribers = [s for s in self._subscribers if s is not callback]

    # ------------------------------------------------------------------
    # 발행
    # ------------------------------------------------------------------

    def emit(self, event_type: str, data: dict) -> None:
        event = {"type": event_type, "data": data, "ts": round(time.time(), 3)}
        line = json.dumps(event, ensure_ascii=False) + "\n"

        # 파일 쓰기: 이벤트 루프 실행 중이면 executor, 아니면 동기
        try:
            import asyncio

            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._write_log, line)
        except RuntimeError:
            self._write_log(line)

        # 구독자 알림 (예외 무시)
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                pass

    def _write_log(self, line: str) -> None:
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(line)
