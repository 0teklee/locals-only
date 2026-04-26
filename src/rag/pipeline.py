"""
RAGPipeline — 임베딩 + MMR 검색 + 토큰 트런케이션.

LLM 압축(LLMChainExtractor) 없음.
이유: 청크당 추가 LLM 호출 → M1 8GB에서 심각한 지연 + 메모리 압박.
대안: MMR 다양성 검색 + 토큰 기반 트런케이션으로 충분한 품질 확보.
"""
from __future__ import annotations

from src.config import settings


class RAGPipeline:
    def __init__(
        self,
        embed_model: str | None = None,
        collection_name: str = "codebase",
    ) -> None:
        self._embed_model = embed_model or settings.EMBED_MODEL
        self._collection_name = collection_name
        self._embeddings = None
        self._vectordb = None
        self._initialized = False

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        try:
            from langchain_ollama import OllamaEmbeddings
            from langchain_chroma import Chroma

            self._embeddings = OllamaEmbeddings(
                model=self._embed_model,
                base_url=settings.OLLAMA_HOST,
            )
            self._vectordb = Chroma(
                collection_name=self._collection_name,
                embedding_function=self._embeddings,
                persist_directory=settings.CHROMA_PATH,
            )
            self._initialized = True
        except ImportError as e:
            raise RuntimeError(
                f"RAG dependencies not installed: {e}\n"
                "Run: pip install langchain-ollama langchain-chroma chromadb"
            ) from e

    def index_codebase(self, path: str) -> int:
        """디렉토리를 청킹하여 벡터 DB에 인덱싱. 청크 수 반환."""
        self._ensure_init()
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain_community.document_loaders import DirectoryLoader

        loader = DirectoryLoader(
            path,
            glob="**/*.{py,ts,js,go,rs,md,yaml,json}",
            recursive=True,
            exclude=[
                "**/node_modules/**",
                "**/.git/**",
                "**/dist/**",
                "**/__pycache__/**",
                "**/data/**",
            ],
        )
        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\nclass ", "\ndef ", "\nasync def ", "\n\n", "\n", " "],
        )
        chunks = splitter.split_documents(docs)
        if chunks:
            self._vectordb.add_documents(chunks)  # type: ignore[union-attr]
        return len(chunks)

    async def search(self, query: str, max_tokens: int = 2000) -> str:
        """
        MMR 검색 후 토큰 예산 내 조합.
        동기 retriever를 asyncio.to_thread()로 래핑.
        """
        import asyncio

        self._ensure_init()

        def _sync_search() -> list:
            retriever = self._vectordb.as_retriever(  # type: ignore[union-attr]
                search_type="mmr",
                search_kwargs={"k": 8, "fetch_k": 25, "lambda_mult": 0.7},
            )
            return retriever.invoke(query)

        try:
            docs = await asyncio.to_thread(_sync_search)
        except Exception:
            return ""

        result_parts: list[str] = []
        token_count = 0
        seen_sources: set[str] = set()

        for doc in docs:
            source = doc.metadata.get("source", "unknown")
            chunk_tokens = len(doc.page_content.split())

            # 같은 파일의 짧은 중복 청크 스킵
            if source in seen_sources and chunk_tokens < 50:
                continue

            if token_count + chunk_tokens > max_tokens:
                break

            result_parts.append(f"# {source}\n{doc.page_content}")
            token_count += chunk_tokens
            seen_sources.add(source)

        return "\n\n---\n\n".join(result_parts)
