"""
SSE 관측 엔드포인트 — 실시간 파이프라인 이벤트 스트림.

구독:
  curl -N http://localhost:8080/api/observe
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.observe.bus import ObservabilityBus

router = APIRouter(tags=["observe"])


@router.get("/api/observe")
async def observe_stream() -> StreamingResponse:
    """SSE 스트림으로 실시간 파이프라인 이벤트 수신."""
    bus = ObservabilityBus.get_default()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    cb = queue.put_nowait
    bus.subscribe(cb)

    async def event_gen():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            bus.unsubscribe(cb)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
