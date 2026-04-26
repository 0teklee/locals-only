from __future__ import annotations

import httpx
from fastapi import APIRouter
from src.config import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check() -> dict:
    """서비스 상태 확인."""
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama": ollama_ok,
        "version": "0.1.0",
    }
