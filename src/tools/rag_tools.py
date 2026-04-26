"""
RAG 도구 — 코드베이스 벡터 검색 및 인덱싱.
"""
from __future__ import annotations

from src.tools.registry import ToolRegistry, ToolSpec


def register(registry: ToolRegistry, rag: "RAGPipeline") -> None:
    async def _search_codebase(query: str, k: int = 5) -> str:
        result = await rag.search(query, max_tokens=k * 300)
        return result or "(no results)"

    def _index_path(path: str) -> str:
        count = rag.index_codebase(path)
        return f"Indexed {count} chunks from {path}"

    registry.register(ToolSpec(
        name="search_codebase",
        description="Semantic search over the indexed codebase using vector similarity.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "k": {"type": "integer", "default": 5, "description": "Max results"},
            },
            "required": ["query"],
        },
        handler=_search_codebase,
    ))
    registry.register(ToolSpec(
        name="index_path",
        description="Index a directory into the vector database for codebase search.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to index"},
            },
            "required": ["path"],
        },
        handler=_index_path,
        requires_confirm=True,
    ))
