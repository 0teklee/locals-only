"""
OpenAI 호환 채팅 엔드포인트.

POST /v1/chat/completions

에디터 연동 (Cline, Continue, Cursor 등) 용도.
스트리밍/비스트리밍 모두 지원.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agent.dispatcher import TaskDispatcher
from src.agent.runner import AgentRunner
from src.api.state import AppState
from src.context.builder import ContextBuilder
from src.memory.manager import MemoryManager
from src.models.adapter import Message
from src.tools.registry import ToolRegistry
from src.tools import file_tools, shell_tools, git_tools
from src.config import settings

router = APIRouter(tags=["chat"])


# ------------------------------------------------------------------
# Request / Response 스키마 (OpenAI 호환 최소 구현)
# ------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------

def _make_runner(state: AppState) -> AgentRunner:
    """요청당 AgentRunner 생성 (Pool은 공유)."""
    obs = state.obs
    memory = MemoryManager()

    ctx = ContextBuilder(
        memory=memory,
        rag=None,
        system_prompt=settings.SYSTEM_PROMPT,
    )

    tools = ToolRegistry(obs)
    file_tools.register(tools)
    shell_tools.register(tools)
    git_tools.register(tools)

    dispatcher = TaskDispatcher(state.pool, obs)
    return AgentRunner(state.pool, dispatcher, tools, ctx, memory, obs)


def _sse_chunk(content: str, model: str, req_id: str) -> str:
    data = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return f"data: {json.dumps(data)}\n\n"


def _sse_done(model: str, req_id: str) -> str:
    data = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return f"data: {json.dumps(data)}\n\ndata: [DONE]\n\n"


# ------------------------------------------------------------------
# 엔드포인트
# ------------------------------------------------------------------

@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is empty")

    state = AppState.get()
    runner = _make_runner(state)
    req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    model = req.model or settings.DEFAULT_MODEL

    # 마지막 user 메시지를 user_input으로 사용
    user_input = next(
        (m.content for m in reversed(req.messages) if m.role == "user"),
        req.messages[-1].content,
    )

    if req.stream:
        async def stream_gen() -> AsyncIterator[str]:
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            def on_token(t: str) -> None:
                queue.put_nowait(t)

            async def producer() -> None:
                try:
                    await runner.run(user_input, on_token=on_token)
                finally:
                    queue.put_nowait(None)  # sentinel

            asyncio.create_task(producer())

            while True:
                token = await queue.get()
                if token is None:
                    break
                yield _sse_chunk(token, model, req_id)
            yield _sse_done(model, req_id)

        return StreamingResponse(stream_gen(), media_type="text/event-stream")

    else:
        full_response = await runner.run(user_input)
        return {
            "id": req_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": full_response},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": sum(len(m.content.split()) for m in req.messages),
                "completion_tokens": len(full_response.split()),
                "total_tokens": sum(len(m.content.split()) for m in req.messages) + len(full_response.split()),
            },
        }
