"""
AgentRunner — White-Box 에이전트 실행 루프.

tool_calls: ChatResult.tool_calls (Ollama done 청크)에서 추출.
스트리밍: on_token 콜백으로 처리.
"""
from __future__ import annotations

import json
from typing import Callable

from src.models.adapter import Message, ChatResult
from src.models.pool import ModelPool
from src.agent.dispatcher import TaskDispatcher
from src.context.builder import ContextBuilder
from src.memory.manager import MemoryManager
from src.tools.registry import ToolRegistry
from src.observe.bus import ObservabilityBus
from src.config import settings


class AgentRunner:
    def __init__(
        self,
        pool: ModelPool,
        dispatcher: TaskDispatcher,
        tool_registry: ToolRegistry,
        context_builder: ContextBuilder,
        memory: MemoryManager,
        obs: ObservabilityBus,
    ) -> None:
        self._pool = pool
        self._dispatcher = dispatcher
        self._tools = tool_registry
        self._ctx = context_builder
        self._memory = memory
        self._obs = obs

    async def run(
        self,
        user_input: str,
        on_token: Callable[[str], None] | None = None,
        session: str = "default",
    ) -> str:
        """
        에이전트 실행.

        on_token: 스트리밍 토큰 콜백 (CLI 출력 등).
        반환값: 최종 응답 전문.
        """
        # 1. 의도 분류 + 슬롯 획득
        self._obs.emit("step", {"name": "dispatch", "status": "start"})
        intent, adapter = await self._dispatcher.dispatch(user_input)
        self._obs.emit("step", {"name": "dispatch", "status": "done", "intent": intent})

        full_response = ""
        try:
            # 2. 컨텍스트 조립
            self._obs.emit("step", {"name": "context_build", "status": "start"})
            messages: list[Message] = await self._ctx.build(user_input)
            self._obs.emit("step", {
                "name": "context_build",
                "status": "done",
                "budget": self._ctx.last_budget,
            })

            # 3. 도구 호출 루프
            for iteration in range(settings.MAX_AGENT_ITERATIONS):
                self._obs.emit("step", {"name": "llm_call", "iteration": iteration})

                result: ChatResult = await adapter.chat(
                    messages,
                    stream=True,
                    on_token=on_token,
                )
                full_response = result.content

                # tool_calls 없으면 최종 응답 — 루프 종료
                if not result.tool_calls:
                    break

                # assistant 메시지 추가 (tool_calls 포함)
                messages.append(Message(
                    role="assistant",
                    content=result.content,
                    tool_calls=result.tool_calls,
                ))

                # 각 도구 실행 + tool 응답 메시지 추가
                for tc in result.tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}

                    self._obs.emit("step", {
                        "name": "tool_call",
                        "tool": tool_name,
                        "args": args,
                        "iteration": iteration,
                    })

                    tool_result = await self._tools.execute(tool_name, args)

                    self._obs.emit("step", {
                        "name": "tool_result",
                        "tool": tool_name,
                        "result_size": len(str(tool_result)),
                    })

                    messages.append(Message(
                        role="tool",
                        content=str(tool_result),
                        tool_call_id=tc.get("id"),
                    ))

        finally:
            await self._dispatcher.release(intent)

        # 4. 메모리 업데이트
        if full_response:
            await self._memory.update(user_input, full_response, session=session)

        self._obs.emit("request_done", {
            "intent": intent,
            "response_len": len(full_response),
        })
        return full_response
