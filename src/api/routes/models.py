"""
모델 관리 엔드포인트.

POST /api/switch-model  {"model": "qwen2.5-coder:7b"}
GET  /api/models
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.state import AppState

router = APIRouter(tags=["models"])


class SwitchModelRequest(BaseModel):
    model: str


@router.post("/api/switch-model")
async def switch_model(req: SwitchModelRequest) -> dict:
    """런타임 모델 전환. 재시작 불필요."""
    state = AppState.get()
    adapter = await state.pool.acquire("code")
    try:
        await adapter.switch_model(req.model)
    finally:
        await state.pool.release("code")
    return {"status": "ok", "model": req.model}


@router.get("/api/models")
async def list_models() -> dict:
    """로컬에 설치된 Ollama 모델 목록."""
    state = AppState.get()
    adapter = await state.pool.acquire("code")
    try:
        models = await adapter.list_models()
    finally:
        await state.pool.release("code")
    return {
        "models": [
            {
                "name": m.name,
                "size_gb": m.size_gb,
                "context_length": m.context_length,
                "quantization": m.quantization,
                "supports_tools": m.supports_tools,
            }
            for m in models
        ]
    }
