"""
단위 테스트 — ModelAdapter / MockAdapter.
실제 Ollama 서버 불필요.
"""
from __future__ import annotations

import pytest
from typing import Callable

from src.models.adapter import ChatResult, Message, ModelAdapterBase, ModelInfo


class MockAdapter(ModelAdapterBase):
    """테스트용 Mock. 실제 Ollama 호출 없음."""

    def __init__(self, response: str = "mock response", tool_calls: list[dict] | None = None) -> None:
        self._model = "mock-model"
        self._response = response
        self._tool_calls = tool_calls or []
        self.calls: list[list[Message]] = []

    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
    ) -> ChatResult:
        self.calls.append(messages)
        if on_token and stream:
            for word in self._response.split():
                on_token(word + " ")
        return ChatResult(
            content=self._response,
            tool_calls=self._tool_calls,
            input_tokens=len(" ".join(m.content for m in messages).split()),
            output_tokens=len(self._response.split()),
            elapsed_sec=0.1,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("mock-model", 1.0, 4096, False, "Q4_K_M")]

    async def switch_model(self, model_name: str) -> None:
        self._model = model_name

    def get_current_model(self) -> str:
        return self._model


# ------------------------------------------------------------------
# 테스트
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_returns_result() -> None:
    adapter = MockAdapter(response="hello world")
    messages = [Message(role="user", content="hi")]
    result = await adapter.chat(messages)
    assert result.content == "hello world"
    assert result.tool_calls == []
    assert result.output_tokens > 0


@pytest.mark.asyncio
async def test_chat_streaming_calls_on_token() -> None:
    tokens: list[str] = []
    adapter = MockAdapter(response="foo bar baz")
    await adapter.chat(
        [Message(role="user", content="test")],
        on_token=tokens.append,
    )
    assert "".join(tokens).strip() == "foo bar baz"


@pytest.mark.asyncio
async def test_chat_tool_calls() -> None:
    tc = [{"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}}]
    adapter = MockAdapter(response="", tool_calls=tc)
    result = await adapter.chat([Message(role="user", content="read x.py")])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["function"]["name"] == "read_file"


@pytest.mark.asyncio
async def test_switch_model() -> None:
    adapter = MockAdapter()
    assert adapter.get_current_model() == "mock-model"
    await adapter.switch_model("new-model")
    assert adapter.get_current_model() == "new-model"


@pytest.mark.asyncio
async def test_embed() -> None:
    adapter = MockAdapter()
    vecs = await adapter.embed(["hello", "world"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 3


def test_message_to_dict_basic() -> None:
    m = Message(role="user", content="hello")
    d = m.to_dict()
    assert d == {"role": "user", "content": "hello"}


def test_message_to_dict_with_tool_call_id() -> None:
    m = Message(role="tool", content="result", tool_call_id="abc")
    d = m.to_dict()
    assert d["tool_call_id"] == "abc"
    assert "tool_calls" not in d


def test_message_to_dict_with_tool_calls() -> None:
    tc = [{"id": "1", "function": {"name": "f", "arguments": "{}"}}]
    m = Message(role="assistant", content="", tool_calls=tc)
    d = m.to_dict()
    assert d["tool_calls"] == tc
