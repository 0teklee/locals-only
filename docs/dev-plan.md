# M1 Mac Mini — White-Box Local AI Agent 설계서

> **버전**: 2.1.0 | **환경**: Apple Silicon M1 (Mac Mini) | **네트워크**: 완전 오프라인(Air-gap)
> **설계 원칙**: White-Box (투명·관측 가능) + Model-Agnostic (모델 무관) + Offline-First + CLI-First

---

## 목차

1. [프로젝트 개요 및 설계 철학](#1-프로젝트-개요-및-설계-철학)
2. [하드웨어 제약 및 최적화 전략](#2-하드웨어-제약-및-최적화-전략)
3. [모델 선택 전략](#3-모델-선택-전략)
4. [White-Box 시스템 아키텍처](#4-white-box-시스템-아키텍처)
5. [Model-Agnostic 어댑터 설계](#5-model-agnostic-어댑터-설계)
6. [컴포넌트별 상세 설계](#6-컴포넌트별-상세-설계)
7. [관측성(Observability) 설계](#7-관측성observability-설계)
8. [토큰 효율화 전략](#8-토큰-효율화-전략)
9. [오픈소스 연동 매트릭스](#9-오픈소스-연동-매트릭스)
10. [디렉토리 구조](#10-디렉토리-구조)
11. [설치 및 구성 가이드](#11-설치-및-구성-가이드)
12. [에이전트 워크플로우](#12-에이전트-워크플로우)
13. [성능 튜닝 파라미터](#13-성능-튜닝-파라미터)
14. [확장 로드맵](#14-확장-로드맵)
15. [효율성 검증 결과 (v2.1 개정 이유)](#15-효율성-검증-결과-v21-개정-이유)

---

## 1. 프로젝트 개요 및 설계 철학

### 목적

외부 API 없이 M1 Mac Mini에서 완전 로컬로 동작하는 **투명한(white-box) AI 코딩 에이전트** 시스템 구축.
어떤 Ollama 호환 모델이든 설정 변경만으로 교체 가능. **CLI 한 줄로 즉시 실행.**

### 핵심 설계 철학 4가지

#### 1. White-Box (투명성)
```
블랙박스 AI가 아닌, 모든 단계를 관측하고 개입할 수 있는 투명한 파이프라인.
- 모든 LLM 호출의 입출력 토큰, 지연 시간 기록
- 최종 프롬프트를 파일로 덤프 가능 (DEBUG_DUMP_CONTEXT=true)
- 도구 실행 전후 감사 로그 (audit log)
- 실시간 관측 대시보드 (SSE 스트림)
```

#### 2. Model-Agnostic (모델 무관)
```
코드 어디에도 모델명 하드코딩 금지. 어떤 GGUF 모델이든 교체 가능.
- 모든 모델 파라미터는 config/models.yaml 에서 관리
- ModelAdapter 인터페이스로 Ollama API 추상화
- 런타임 모델 전환 (모델 재시작 없이)
- 지원 모델: Qwen, Llama, Mistral, Gemma, DeepSeek, Phi 등 모든 GGUF
```

#### 3. Offline-First (오프라인 우선)
```
인터넷이 없어도 모든 기능이 동작해야 함.
- 임베딩/벡터DB/에이전트 모두 로컬
- 다운로드 없는 실행 (모델 사전 배치 필수)
- LAN 네트워크에서 다른 기기 접근 가능
```

#### 4. CLI-First (터미널 우선)
```
FastAPI 서버 실행 없이 CLI 단독으로 모든 기능 동작.
- local-ai chat "질문"        → 즉시 대화
- local-ai code "코드 작성"   → 코드 에이전트
- local-ai index /path        → RAG 인덱싱
- local-ai models list        → 모델 관리
서버가 있으면 API·WebUI도 사용 가능 (선택적)
```

### 핵심 요구사항

| 요구사항 | 세부 내용 | 우선순위 |
|---------|---------|---------|
| **CLI 단독 실행** | 서버 없이 터미널에서 즉시 사용 | P0 |
| **모델 무관 연동** | 어떤 Ollama 모델이든 설정만으로 교체 | P0 |
| **파이프라인 투명성** | 모든 단계 관측·로깅·개입 가능 | P0 |
| **오프라인 완전 동작** | 인터넷 없이 모든 기능 작동 | P0 |
| **다중 LLM 오케스트레이션** | 용도별 모델 자동 라우팅·병렬 실행 | P1 |
| **토큰 효율** | 컨텍스트 압축, 청킹, 캐싱 전략 | P1 |
| **코드 에디터 연동** | Cline, Continue, Aider 등 | P1 |
| **다중 인터페이스** | TUI, GUI(브라우저), API | P2 |

---

## 2. 하드웨어 제약 및 최적화 전략

### M1 Mac Mini 스펙

```
CPU  : Apple M1 (8-core, 4E+4P)
GPU  : 8-core GPU (통합, Metal 지원)
RAM  : 8GB ~ 16GB Unified Memory (CPU+GPU 공유)
SSD  : NVMe (고속 스왑, ~7GB/s)
```

### Unified Memory 할당 계획

```
┌──────────────────────────────────────────────────────────┐
│              Unified Memory — 16GB 기준                   │
├─────────────────┬──────────────┬─────────────────────────┤
│  LLM 모델 가중치 │   KV Cache   │   OS + 에이전트 스택     │
│    ~8-10GB      │   ~2-3GB     │       ~3-4GB            │
│  (Q4_K_M 기준)  │  (Flash Attn)│  (Python, ChromaDB 등)  │
└─────────────────┴──────────────┴─────────────────────────┘

8GB 환경: 모델 ~4-5GB / KV ~1GB / OS ~2-3GB
→ 7B 모델 Q4 불가. 3B Q4 또는 7B Q2 권장

다중 LLM 오케스트레이션 시 메모리 할당:
  16GB: 메인 모델(7B, ~5GB) + 임베딩(270MB) + 스택(~3GB) ← 동시 로드 가능
  8GB:  메인 모델(3B, ~2.5GB) + 임베딩(270MB) + 스택(~2GB) ← 임베딩만 병렬
```

### 메모리 절감 원칙

| 기법 | 효과 | 설정 |
|------|------|------|
| Q4_K_M 양자화 | Q8 대비 2배 절약, 품질 손실 최소 | Modelfile |
| Flash Attention | KV 캐시 메모리 40% 절감 | `OLLAMA_FLASH_ATTENTION=1` |
| KV 캐시 양자화 | `q8_0` 캐시 → 추가 20% 절감 | `OLLAMA_KV_CACHE_TYPE=q8_0` |
| 컨텍스트 제한 | num_ctx=8192 기본 (모델 최대치 미사용) | Modelfile |
| 임베딩 전용 슬롯 | nomic-embed-text 항상 로드 유지 (270MB) | ModelPool 설계 |
| Metal GPU 오프로드 | 모든 레이어 GPU 처리 | `-ngl 99` (자동) |

---

## 3. 모델 선택 전략

### 3.1 용도별 모델 매트릭스

| 용도 | 모델 (16GB) | 모델 (8GB) | 크기(Q4_K_M) | 컨텍스트 | 특징 |
|------|------------|-----------|-------------|---------|------|
| 코드 생성 (메인) | `qwen2.5-coder:7b` | `qwen2.5-coder:3b` | 4.7GB / 2.0GB | 32K | 함수 호출, JSON 안정 |
| 범용 대화 | `gemma3:4b` | `gemma3:2b` | 3.3GB / 1.6GB | 128K | 다국어, 긴 컨텍스트 |
| 에이전트 추론 | `qwen2.5:7b` | `qwen2.5:3b` | 4.7GB / 2.0GB | 128K | 도구 호출, ReAct |
| 코드 리뷰 | `deepseek-coder:6.7b` | `deepseek-coder:1.3b` | 4.0GB / 0.8GB | 16K | 코드 이해력 우수 |
| 빠른 완성/분류 | `qwen2.5-coder:1.5b` | `qwen2.5-coder:1.5b` | 1.0GB | 32K | 탭 완성, 의도 분류 |
| 임베딩 | `nomic-embed-text` | `nomic-embed-text` | 270MB | 8K | RAG 전용, 상시 로드 |
| 백업/범용 | `mistral:7b` | `phi3:3.8b` | 4.1GB / 2.2GB | 32K / 128K | 범용 폴백 |

> **새 모델 추가 방법**: `config/models.yaml`에 항목 추가만으로 즉시 사용 가능.
> 코드 수정 불필요 — ModelAdapter가 자동으로 처리.

### 3.2 config/models.yaml 구조

```yaml
# config/models.yaml
# 이 파일이 모든 모델 설정의 단일 진실 소스(Single Source of Truth)

defaults:
  code: qwen2.5-coder:7b
  chat: gemma3:4b
  agent: qwen2.5:7b
  embed: nomic-embed-text
  classifier: qwen2.5-coder:1.5b   # 의도 분류용 경량 모델
  fallback: mistral:7b

# RAM 기반 자동 선택 (ModelRegistry가 참조)
profiles:
  ram_8gb:
    code: qwen2.5-coder:3b
    chat: gemma3:2b
    agent: qwen2.5:3b
    classifier: qwen2.5-coder:1.5b
    embed: nomic-embed-text

  ram_16gb:
    code: qwen2.5-coder:7b
    chat: gemma3:4b
    agent: qwen2.5:7b
    classifier: qwen2.5-coder:1.5b
    embed: nomic-embed-text

# 모델별 파라미터 프리셋
presets:
  qwen2.5-coder:7b:
    temperature: 0.1
    top_p: 0.9
    top_k: 20
    repeat_penalty: 1.1
    num_ctx: 8192
    num_predict: 2048
    system_prompt: "modelfiles/code-assist.Modelfile"

  gemma3:4b:
    temperature: 0.7
    top_p: 0.95
    top_k: 40
    num_ctx: 32768   # 긴 컨텍스트 활용
    num_predict: 1024
    system_prompt: "modelfiles/chat-assistant.Modelfile"

  qwen2.5:7b:
    temperature: 0.2
    top_p: 0.9
    top_k: 30
    num_ctx: 8192
    num_predict: 1024
    system_prompt: "modelfiles/agent-tools.Modelfile"

  qwen2.5-coder:1.5b:
    temperature: 0.0   # 분류는 결정론적으로
    top_p: 0.9
    top_k: 10
    num_ctx: 2048
    num_predict: 64

  nomic-embed-text:
    # 임베딩 전용 — num_ctx만 관리
    num_ctx: 8192

  # 새 모델 추가 예시
  llama3.2:3b:
    temperature: 0.5
    num_ctx: 8192
    num_predict: 1024
```

### 3.3 GGUF 직접 등록 (오프라인 환경)

```bash
# 방법 A: ollama pull (간편)
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text

# 방법 B: GGUF 파일 직접 등록
cat > /tmp/Modelfile << 'EOF'
FROM /path/to/model.gguf
PARAMETER temperature 0.1
PARAMETER num_ctx 8192
EOF
ollama create my-custom-model -f /tmp/Modelfile

# 방법 C: scripts/import-gguf.sh 사용
./scripts/import-gguf.sh /Volumes/ExternalSSD/models/some-model-q4.gguf
```

---

## 4. White-Box 시스템 아키텍처

### 전체 아키텍처 (상세)

```
┌──────────────────────────────────────────────────────────────┐
│                    L4: Interface Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │  CLI     │  │  VS Code │  │ Browser  │  │  Terminal   │  │
│  │(Typer)   │  │(Cline/   │  │(Open     │  │ (Aider/TUI) │  │
│  │★ 메인    │  │Continue) │  │ WebUI)   │  │             │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘  │
└───────┼─────────────┼─────────────┼────────────────┼─────────┘
        │             │             │                │
        └─────────────┴──────┬──────┴────────────────┘
                             │ OpenAI-compat / Ollama native
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                 L3: Orchestration Layer                        │
│  ┌──────────────────┐    ┌──────────────────────────────────┐ │
│  │   FastAPI Server  │    │      TaskDispatcher             │ │
│  │   (port: 8080)    │    │  ┌────────────┐                 │ │
│  │  /v1/chat         │───▶│  │IntentClass │ 의도→모델 라우팅 │ │
│  │  /v1/completions  │    │  ├────────────┤                 │ │
│  │  /api/switch-model│    │  │ModelPool   │ 슬롯 할당·반환  │ │
│  │  /api/observe     │    │  ├────────────┤                 │ │
│  └──────────────────┘    │  │AgentRunner │ 도구 호출 루프  │ │
│                           │  ├────────────┤                 │ │
│  ┌──────────────────┐    │  │ContextBuild│ 토큰 예산 조립  │ │
│  │ ObservabilityBus  │◀──│  ├────────────┤                 │ │
│  │  (SSE /api/obs)   │    │  │MemoryMgr   │ 히스토리 관리   │ │
│  │  실시간 이벤트     │    │  └────────────┘                 │ │
│  └──────────────────┘    └──────────────────────────────────┘ │
│                                       │                        │
│                                       ▼                        │
│                           ┌──────────────────────────────────┐ │
│                           │       RAGPipeline                │ │
│                           │  Embed → Search → Truncate       │ │
│                           └──────────────────────────────────┘ │
└───────────────────────────────────┬──────────────────────────┘
                                    │ HTTP (localhost:11434)
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    L2: Model Layer                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  ModelPool (다중 LLM 관리)              │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ 슬롯 A: 메인 모델 (code/chat/agent, 필요 시 교체) │  │  │
│  │  │ 슬롯 B: 임베딩 모델 (nomic-embed-text, 상시 고정) │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │  ModelRegistry (RAM 기반 모델 선택)                     │  │
│  │  OllamaAdapter (HTTP 래퍼 + white-box 로깅)            │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  Ollama Server (11434)                  │  │
│  │   /api/chat  /api/generate  /v1/*  /api/embed          │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────────────┬──────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────┐
│                    L1: Storage Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  ChromaDB    │  │  SQLite      │  │  FileSystem        │  │
│  │  (port:8000) │  │  (메모리DB)  │  │  (코드베이스)      │  │
│  │  벡터 검색   │  │  대화 히스토리│  │  Git 인덱스        │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Audit Log (data/logs/)                       │ │
│  │  llm_calls.jsonl │ tool_calls.jsonl │ context_dumps/    │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### White-Box 관측 포인트

```
각 ● 지점에서 이벤트가 ObservabilityBus로 발행됨

사용자 입력 ●─→ [IntentClassifier] ●─→ [TaskDispatcher] ●
                    (1.5b 경량 모델)      (모델 슬롯 할당)
                                                 │
        ┌────────────────────────────────────────┘
        ▼
[ContextBuilder] ●─────────────────────────── 토큰 예산 계산
        │
        ▼
[ModelAdapter.chat()] ●──────────────────── 토큰 수, 지연 시간
        │
        ▼ (tool_calls 감지 — 스트림 완료 후 final chunk에서)
[ToolRouter] ●─→ [Tool 실행] ●─→ 결과 반환 ─→ 재순환
        │
        ▼ (최종 응답)
[ResponseStreamer] ●─→ [MemoryManager.update()] ●
```

---

## 5. Model-Agnostic 어댑터 설계

### 5.1 ModelAdapter 인터페이스

```python
# src/models/adapter.py
from __future__ import annotations
from typing import AsyncIterator
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class ModelInfo:
    name: str
    size_gb: float
    context_length: int
    supports_tools: bool
    quantization: str  # "Q4_K_M", "Q8_0", "F16", etc.


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[dict] | None = field(default=None)
    tool_call_id: str | None = field(default=None)

    def to_dict(self) -> dict:
        d: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class ChatResult:
    """chat() 호출의 최종 결과 (스트리밍 완료 후)"""
    content: str
    tool_calls: list[dict]          # Ollama tool_calls 필드
    input_tokens: int
    output_tokens: int
    elapsed_sec: float


class ModelAdapterBase(ABC):
    """모든 LLM 백엔드의 공통 인터페이스"""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
        on_token: "Callable[[str], None] | None" = None,
    ) -> ChatResult: ...
    # ↑ 스트리밍은 on_token 콜백으로 처리.
    #   반환값은 항상 ChatResult (tool_calls 포함).

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    async def switch_model(self, model_name: str) -> None: ...

    @abstractmethod
    def get_current_model(self) -> str: ...
```

### 5.2 OllamaAdapter 구현 (수정: async I/O, 올바른 tool_call 감지)

```python
# src/models/ollama_adapter.py
import time
import json
import uuid
import asyncio
from pathlib import Path
from typing import AsyncIterator, Callable
from collections.abc import Callable

import httpx
from src.models.adapter import ModelAdapterBase, Message, ModelInfo, ChatResult
from src.observe.bus import ObservabilityBus
from src.config import settings


class OllamaAdapter(ModelAdapterBase):
    """
    Ollama HTTP API 래퍼.
    - 모든 호출에 자동 로깅 (white-box)
    - 모델은 외부 설정에서 결정 (model-agnostic)
    - tool_calls는 Ollama 스트림 done 청크에서 추출
    - 파일 I/O는 asyncio.to_thread()로 이벤트 루프 블로킹 방지
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str | None = None,
        obs_bus: ObservabilityBus | None = None,
    ):
        self.base_url = base_url
        self._model = model or settings.DEFAULT_MODEL
        self._params = settings.get_model_params(self._model)
        self._obs = obs_bus or ObservabilityBus.get_default()
        self._log_path = Path("data/logs/llm_calls.jsonl")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
    ) -> ChatResult:
        payload = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,   # 항상 스트리밍 (토큰 단위 처리)
            "options": self._params,
        }

        call_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()
        await self._log_async(self._build_start_log(call_id, messages))
        self._obs.emit("llm_call_start", {"id": call_id, "model": self._model})

        output_parts: list[str] = []
        tool_calls: list[dict] = []
        eval_count = 0
        prompt_eval_count = 0

        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})

                    # 텍스트 토큰 스트리밍
                    if token := msg.get("content", ""):
                        output_parts.append(token)
                        if on_token:
                            on_token(token)

                    # done 청크에서 tool_calls 추출 (Ollama 실제 API 형식)
                    if chunk.get("done"):
                        tool_calls = msg.get("tool_calls") or []
                        eval_count = chunk.get("eval_count", 0)
                        prompt_eval_count = chunk.get("prompt_eval_count", 0)

        elapsed = time.monotonic() - start_time
        result = ChatResult(
            content="".join(output_parts),
            tool_calls=tool_calls,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            elapsed_sec=round(elapsed, 3),
        )
        await self._log_async(self._build_end_log(call_id, result))
        self._obs.emit("llm_call_end", {
            "id": call_id,
            "output_tokens": result.output_tokens,
            "elapsed_sec": result.elapsed_sec,
            "tokens_per_sec": round(result.output_tokens / elapsed, 1) if elapsed > 0 else 0,
            "has_tool_calls": bool(tool_calls),
        })
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]

    async def switch_model(self, model_name: str) -> None:
        self._model = model_name
        self._params = settings.get_model_params(model_name)
        self._obs.emit("model_switched", {"model": model_name})

    def get_current_model(self) -> str:
        return self._model

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            data = resp.json()
        return [
            ModelInfo(
                name=m["name"],
                size_gb=m["size"] / 1e9,
                context_length=m.get("details", {}).get("context_length", 4096),
                supports_tools="tools" in m.get("details", {}).get("capabilities", []),
                quantization=m.get("details", {}).get("quantization_level", "unknown"),
            )
            for m in data.get("models", [])
        ]

    # --- Private helpers ---

    async def _log_async(self, entry: dict) -> None:
        """이벤트 루프를 블로킹하지 않는 비동기 파일 로그"""
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        await asyncio.to_thread(self._write_log, line)

    def _write_log(self, line: str) -> None:
        with open(self._log_path, "a") as f:
            f.write(line)

    def _build_start_log(self, call_id: str, messages: list[Message]) -> dict:
        return {
            "id": call_id,
            "type": "llm_call_start",
            "model": self._model,
            "input_messages": len(messages),
            "input_tokens_estimate": sum(len(m.content.split()) * 1.3 for m in messages),
            "params": self._params,
            "timestamp": time.time(),
        }

    def _build_end_log(self, call_id: str, result: ChatResult) -> dict:
        return {
            "id": call_id,
            "type": "llm_call_end",
            "output_tokens": result.output_tokens,
            "input_tokens": result.input_tokens,
            "elapsed_sec": result.elapsed_sec,
            "tokens_per_sec": round(result.output_tokens / result.elapsed_sec, 1)
            if result.elapsed_sec > 0 else 0,
            "has_tool_calls": bool(result.tool_calls),
            "timestamp": time.time(),
        }
```

### 5.3 ModelRegistry — 런타임 모델 탐색

```python
# src/models/registry.py
import psutil
import yaml
from pathlib import Path


class ModelRegistry:
    """
    로컬 RAM에 따라 최적 모델을 자동 선택.
    새 모델 추가: config/models.yaml 수정만으로 완료.
    """

    def __init__(self, config_path: str = "config/models.yaml"):
        with open(config_path) as f:
            self._config = yaml.safe_load(f)

    def get_default(self, purpose: str) -> str:
        """
        purpose: "code" | "chat" | "agent" | "embed" | "classifier"
        RAM에 따라 자동 선택
        """
        ram_gb = psutil.virtual_memory().total / 1e9
        profile = "ram_16gb" if ram_gb >= 14 else "ram_8gb"
        return (
            self._config["profiles"].get(profile, {}).get(purpose)
            or self._config["defaults"][purpose]
        )

    def get_params(self, model_name: str) -> dict:
        return self._config["presets"].get(model_name, self._config.get("default_params", {}))

    def list_supported(self) -> list[str]:
        return list(self._config["presets"].keys())
```

### 5.4 ModelPool — 다중 LLM 슬롯 관리 (신규)

```python
# src/models/pool.py
import asyncio
from dataclasses import dataclass, field
from src.models.ollama_adapter import OllamaAdapter
from src.models.registry import ModelRegistry
from src.observe.bus import ObservabilityBus


@dataclass
class ModelSlot:
    purpose: str              # "main" | "embed"
    adapter: OllamaAdapter
    locked: bool = False      # 현재 사용 중 여부


class ModelPool:
    """
    다중 LLM 슬롯 관리자.

    슬롯 구성:
      - embed 슬롯: nomic-embed-text 상시 고정 (270MB, 교체 안 함)
      - main 슬롯:  요청 의도에 따라 code/chat/agent 모델로 전환

    RAM 절감 원칙:
      - 8GB:  main 1개 + embed 1개 동시 가능 (합계 ~3GB)
      - 16GB: main 1개 + embed 1개 동시 가능 (합계 ~6GB)
      - main 슬롯의 모델 전환은 직렬 (Ollama가 자동 언로드)
    """

    def __init__(self, registry: ModelRegistry, obs: ObservabilityBus):
        self._registry = registry
        self._obs = obs
        self._slots: dict[str, ModelSlot] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """시작 시 슬롯 초기화 — embed 슬롯은 고정 로드"""
        embed_model = self._registry.get_default("embed")
        main_model = self._registry.get_default("code")  # 초기값

        self._slots["embed"] = ModelSlot(
            purpose="embed",
            adapter=OllamaAdapter(model=embed_model, obs_bus=self._obs),
        )
        self._slots["main"] = ModelSlot(
            purpose="main",
            adapter=OllamaAdapter(model=main_model, obs_bus=self._obs),
        )
        self._obs.emit("pool_initialized", {
            "embed": embed_model,
            "main": main_model,
        })

    async def acquire(self, purpose: str) -> OllamaAdapter:
        """
        슬롯 획득. purpose에 맞는 모델로 전환 후 반환.
        동시에 같은 슬롯 요청이 오면 대기.
        """
        slot_key = "embed" if purpose == "embed" else "main"

        async with self._lock:
            slot = self._slots[slot_key]
            while slot.locked:
                # 슬롯이 사용 중이면 100ms 대기 후 재시도
                await asyncio.sleep(0.1)

            # main 슬롯: 목적에 맞는 모델로 전환 필요 시 전환
            if slot_key == "main":
                target_model = self._registry.get_default(purpose)
                if slot.adapter.get_current_model() != target_model:
                    await slot.adapter.switch_model(target_model)

            slot.locked = True
            return slot.adapter

    async def release(self, purpose: str) -> None:
        slot_key = "embed" if purpose == "embed" else "main"
        async with self._lock:
            self._slots[slot_key].locked = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """임베딩은 embed 슬롯 직접 사용 (acquire/release 없이)"""
        return await self._slots["embed"].adapter.embed(texts)
```

### 5.5 TaskDispatcher — 의도 기반 모델 라우팅 (신규)

```python
# src/agent/dispatcher.py
import asyncio
import json
from src.models.pool import ModelPool
from src.models.adapter import Message
from src.observe.bus import ObservabilityBus


INTENT_PROMPT = """\
Classify the user request into ONE category. Reply with JSON only.
Categories: code_gen, code_review, file_edit, chat, rag_query, system

Request: {query}

Reply format: {"intent": "<category>", "confidence": 0.0-1.0}"""


class TaskDispatcher:
    """
    사용자 요청을 의도 분류 → 적절한 모델 슬롯으로 라우팅.
    의도 분류 자체는 경량 모델(1.5b)로 수행하여 오버헤드 최소화.
    """

    INTENT_TO_PURPOSE: dict[str, str] = {
        "code_gen":     "code",
        "code_review":  "code",
        "file_edit":    "agent",
        "chat":         "chat",
        "rag_query":    "chat",
        "system":       "agent",
    }

    def __init__(self, pool: ModelPool, obs: ObservabilityBus):
        self._pool = pool
        self._obs = obs

    async def classify(self, user_input: str) -> str:
        """경량 모델로 의도 분류. 실패 시 'chat' 폴백."""
        adapter = await self._pool.acquire("classifier")
        try:
            result = await adapter.chat(
                [Message(role="user", content=INTENT_PROMPT.format(query=user_input[:200]))],
                stream=False,
            )
            data = json.loads(result.content.strip())
            intent = data.get("intent", "chat")
        except Exception:
            intent = "chat"
        finally:
            await self._pool.release("classifier")

        self._obs.emit("intent_classified", {"intent": intent, "input": user_input[:100]})
        return intent

    async def dispatch(self, user_input: str) -> tuple[str, "OllamaAdapter"]:
        """
        의도 분류 + 슬롯 할당을 동시에 처리.
        Returns: (intent, adapter)
        """
        intent = await self.classify(user_input)
        purpose = self.INTENT_TO_PURPOSE.get(intent, "chat")
        adapter = await self._pool.acquire(purpose)
        return intent, adapter

    async def release(self, intent: str) -> None:
        purpose = self.INTENT_TO_PURPOSE.get(intent, "chat")
        await self._pool.release(purpose)
```

---

## 6. 컴포넌트별 상세 설계

### 6.1 AgentRunner — 도구 호출 루프 (수정: 올바른 tool_calls 처리)

```python
# src/agent/runner.py
import asyncio
import json
import time
from typing import AsyncIterator, Callable

from src.models.adapter import ModelAdapterBase, Message, ChatResult
from src.models.pool import ModelPool
from src.agent.dispatcher import TaskDispatcher
from src.tools.registry import ToolRegistry
from src.context.builder import ContextBuilder
from src.memory.manager import MemoryManager
from src.observe.bus import ObservabilityBus


class AgentRunner:
    """
    White-Box 에이전트 실행 루프.

    핵심 수정사항:
    - tool_calls는 스트리밍 텍스트에서 감지하지 않음
    - ChatResult.tool_calls (Ollama done 청크의 message.tool_calls)에서 추출
    - 스트리밍 출력은 on_token 콜백으로 처리
    """

    MAX_ITERATIONS = 10

    def __init__(
        self,
        pool: ModelPool,
        dispatcher: TaskDispatcher,
        tool_registry: ToolRegistry,
        context_builder: ContextBuilder,
        memory: MemoryManager,
        obs: ObservabilityBus,
    ):
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
    ) -> str:
        """
        on_token: 스트리밍 토큰을 받을 콜백 (CLI 출력 등)
        반환값: 최종 응답 전문
        """
        # 1. 의도 분류 + 슬롯 할당
        self._obs.emit("step", {"name": "dispatch", "status": "start"})
        intent, adapter = await self._dispatcher.dispatch(user_input)
        self._obs.emit("step", {"name": "dispatch", "status": "done", "intent": intent})

        try:
            # 2. 컨텍스트 조립
            self._obs.emit("step", {"name": "context_build", "status": "start"})
            messages = await self._ctx.build(user_input)
            self._obs.emit("step", {
                "name": "context_build",
                "status": "done",
                "budget": self._ctx.last_budget,
            })

            full_response = ""

            # 3. 도구 호출 루프
            for iteration in range(self.MAX_ITERATIONS):
                self._obs.emit("step", {"name": "llm_call", "iteration": iteration})

                result: ChatResult = await adapter.chat(
                    messages,
                    on_token=on_token,
                )
                full_response = result.content

                # tool_calls가 없으면 최종 응답 — 루프 종료
                if not result.tool_calls:
                    break

                # assistant 메시지 추가 (tool_calls 포함)
                messages.append(Message(
                    role="assistant",
                    content=result.content,
                    tool_calls=result.tool_calls,
                ))

                # 각 도구 실행
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
        await self._memory.update(user_input, full_response)
        return full_response
```

### 6.2 ContextBuilder — 토큰 예산 관리 (수정: 타입 일관성)

```python
# src/context/builder.py
from dataclasses import dataclass
from src.models.adapter import Message
from src.memory.manager import MemoryManager
from src.rag.pipeline import RAGPipeline


@dataclass
class TokenBudget:
    total: int
    system: int
    history: int
    rag: int
    input: int
    output_reserved: int

    @property
    def remaining(self) -> int:
        return self.total - self.system - self.history - self.rag - self.input - self.output_reserved


class ContextBuilder:
    """
    토큰 예산을 관리하며 Message 객체 리스트를 반환.
    반환 타입은 항상 list[Message] — dict 혼용 금지.
    """

    DEFAULT_BUDGET = TokenBudget(
        total=8192,
        system=300,
        history=1500,
        rag=2000,
        input=500,
        output_reserved=2048,
    )

    def __init__(
        self,
        memory: MemoryManager,
        rag: RAGPipeline,
        system_prompt: str = "",
        budget: TokenBudget | None = None,
    ):
        self._memory = memory
        self._rag = rag
        self._system_prompt = system_prompt
        self.budget = budget or self.DEFAULT_BUDGET
        self.last_budget: dict = {}

    async def build(self, user_input: str) -> list[Message]:
        messages: list[Message] = []

        # 1. 시스템 프롬프트 (최대 budget.system 토큰 × 4자)
        if self._system_prompt:
            truncated = self._system_prompt[: self.budget.system * 4]
            messages.append(Message(role="system", content=truncated))

        # 2. 대화 히스토리 (슬라이딩 윈도우 + 요약)
        history: list[Message] = await self._memory.get_compressed(
            max_tokens=self.budget.history
        )
        messages.extend(history)

        # 3. RAG 컨텍스트 (토큰 예산 내 단순 트런케이션)
        rag_ctx = await self._rag.search(user_input, max_tokens=self.budget.rag)
        if rag_ctx:
            messages.append(Message(role="system", content=f"[Context]\n{rag_ctx}"))

        # 4. 현재 입력
        messages.append(Message(role="user", content=user_input))

        self.last_budget = {
            "system_tokens": len(self._system_prompt.split()) if self._system_prompt else 0,
            "history_messages": len(history),
            "rag_tokens": len(rag_ctx.split()) if rag_ctx else 0,
            "input_tokens": len(user_input.split()),
        }
        return messages
```

### 6.3 ToolRegistry — 동적 도구 등록

```python
# src/tools/registry.py
import time
import asyncio
import inspect
from typing import Callable, Any
from dataclasses import dataclass

from src.observe.bus import ObservabilityBus


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable
    requires_confirm: bool = False


class ToolRegistry:
    """런타임에 도구를 등록/탐색/실행."""

    def __init__(self, obs: ObservabilityBus):
        self._tools: dict[str, ToolSpec] = {}
        self._obs = obs

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get_schema(self) -> list[dict]:
        """LLM에게 전달할 도구 스키마 (OpenAI 형식)"""
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
        try:
            if inspect.iscoroutinefunction(spec.handler):
                result = await spec.handler(**args)
            else:
                result = await asyncio.to_thread(spec.handler, **args)
        except Exception as e:
            result = f"Error: {e}"

        elapsed = time.monotonic() - start
        self._obs.emit("tool_executed", {
            "name": name,
            "elapsed_sec": round(elapsed, 3),
            "result_size": len(str(result)),
        })
        return result
```

### 6.4 RAGPipeline (수정: LLM 압축 제거 → 토큰 트런케이션)

```python
# src/rag/pipeline.py
"""
v2.1 변경사항:
  LLMChainExtractor(contextual compression) 제거.
  이유: 청크당 추가 LLM 호출 → M1 8GB에서 심각한 지연 + 메모리 압박.
  대안: 토큰 수 기반 트런케이션 + MMR 다양성 검색으로 충분한 품질 확보.
"""
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader
from src.config import settings


class RAGPipeline:
    """
    임베딩 모델도 model-agnostic — config에서 교체 가능.
    압축은 LLM 없이 토큰 기반 트런케이션으로 처리.
    """

    def __init__(self, embed_model: str | None = None):
        self._embed_model = embed_model or settings.EMBED_MODEL
        self._embeddings = OllamaEmbeddings(
            model=self._embed_model,
            base_url=settings.OLLAMA_HOST,
        )
        self._vectordb = Chroma(
            collection_name="codebase",
            embedding_function=self._embeddings,
            persist_directory=settings.CHROMA_PATH,
        )

    def index_codebase(self, path: str) -> int:
        loader = DirectoryLoader(
            path,
            glob="**/*.{py,ts,js,go,rs,md,yaml,json}",
            recursive=True,
            exclude=["**/node_modules/**", "**/.git/**", "**/dist/**", "**/__pycache__/**"],
        )
        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\nclass ", "\ndef ", "\nasync def ", "\n\n", "\n", " "],
        )
        chunks = splitter.split_documents(docs)
        self._vectordb.add_documents(chunks)
        return len(chunks)

    async def search(self, query: str, max_tokens: int = 2000) -> str:
        """
        MMR 검색 후 토큰 예산 내 조합.
        LLM 압축 없음 — 추가 모델 호출 없이 빠른 반환.
        """
        retriever = self._vectordb.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 8, "fetch_k": 25, "lambda_mult": 0.7},
        )
        docs = await retriever.ainvoke(query)

        result_parts: list[str] = []
        token_count = 0
        seen_sources: set[str] = set()

        for doc in docs:
            source = doc.metadata.get("source", "unknown")
            chunk_tokens = len(doc.page_content.split())

            # 중복 소스 스킵 (같은 파일의 연속 청크 과다 방지)
            if source in seen_sources and chunk_tokens < 50:
                continue

            if token_count + chunk_tokens > max_tokens:
                break

            result_parts.append(f"# {source}\n{doc.page_content}")
            token_count += chunk_tokens
            seen_sources.add(source)

        return "\n\n---\n\n".join(result_parts)
```

### 6.5 MemoryManager — 슬라이딩 윈도우 (수정: LangChain 의존성 제거)

```python
# src/memory/manager.py
"""
v2.1 변경사항:
  ConversationSummaryBufferMemory(deprecated LangChain) 제거.
  대안: 순수 Python 슬라이딩 윈도우 + SQLite 영속.
  요약 압축은 Phase 2에서 필요 시 OllamaAdapter.chat()으로 구현.
"""
import json
import time
import sqlite3
import asyncio
from pathlib import Path
from src.models.adapter import Message


class MemoryManager:
    """
    슬라이딩 윈도우로 최근 N 턴 유지.
    SQLite로 전체 대화 영속 저장.
    LangChain 의존성 없음.
    """

    def __init__(self, max_tokens: int = 1500, window_turns: int = 10):
        self._max_tokens = max_tokens
        self._window_turns = window_turns
        self._buffer: list[Message] = []    # 메모리 내 슬라이딩 윈도우
        self._db_path = Path("data/memory.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    role      TEXT NOT NULL,
                    content   TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    session   TEXT NOT NULL DEFAULT 'default'
                )
            """)

    async def get_compressed(self, max_tokens: int) -> list[Message]:
        """토큰 예산 내 최신 메시지 우선으로 반환"""
        result: list[Message] = []
        token_count = 0
        # 최신 메시지부터 역순으로 추가
        for msg in reversed(self._buffer):
            tokens = len(msg.content.split())
            if token_count + tokens > max_tokens:
                break
            result.insert(0, msg)
            token_count += tokens
        return result

    async def update(self, user_input: str, assistant_response: str) -> None:
        """대화 추가 + 슬라이딩 윈도우 유지"""
        new_msgs = [
            Message(role="user", content=user_input),
            Message(role="assistant", content=assistant_response),
        ]
        self._buffer.extend(new_msgs)

        # 윈도우 크기 초과 시 오래된 턴 제거
        max_messages = self._window_turns * 2
        if len(self._buffer) > max_messages:
            self._buffer = self._buffer[-max_messages:]

        # SQLite 비동기 저장
        await asyncio.to_thread(self._save_to_db, new_msgs)

    def _save_to_db(self, messages: list[Message]) -> None:
        with sqlite3.connect(self._db_path) as conn:
            now = time.time()
            conn.executemany(
                "INSERT INTO messages (role, content, timestamp) VALUES (?, ?, ?)",
                [(m.role, m.content, now) for m in messages],
            )

    def clear(self) -> None:
        self._buffer.clear()

    def load_session(self, session: str = "default", last_n: int = 20) -> None:
        """재시작 후 DB에서 최근 세션 복원"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session=? ORDER BY id DESC LIMIT ?",
                (session, last_n),
            ).fetchall()
        self._buffer = [Message(role=r, content=c) for r, c in reversed(rows)]
```

### 6.6 CLI 진입점 (신규)

```python
# src/cli/main.py
"""
CLI-First 진입점. FastAPI 서버 불필요.
사용:
  local-ai chat "질문"
  local-ai code "코드 작성 요청"
  local-ai index /path/to/project
  local-ai models list
  local-ai models switch qwen2.5-coder:7b
"""
import asyncio
import typer
from pathlib import Path
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from src.models.registry import ModelRegistry
from src.models.pool import ModelPool
from src.agent.dispatcher import TaskDispatcher
from src.agent.runner import AgentRunner
from src.context.builder import ContextBuilder
from src.memory.manager import MemoryManager
from src.rag.pipeline import RAGPipeline
from src.tools.registry import ToolRegistry
from src.tools import file_tools, shell_tools, git_tools, rag_tools
from src.observe.bus import ObservabilityBus
from src.config import settings

app = typer.Typer(name="local-ai", help="Local LLM Agent (Offline, White-Box)")
console = Console()


def _build_runner() -> AgentRunner:
    """공통 AgentRunner 초기화"""
    obs = ObservabilityBus.get_default()
    registry = ModelRegistry()
    pool = ModelPool(registry, obs)
    asyncio.get_event_loop().run_until_complete(pool.initialize())

    memory = MemoryManager()
    rag = RAGPipeline()
    ctx = ContextBuilder(memory=memory, rag=rag, system_prompt=settings.SYSTEM_PROMPT)
    tools = ToolRegistry(obs)
    file_tools.register(tools)
    shell_tools.register(tools)
    git_tools.register(tools)
    rag_tools.register(tools, rag)

    dispatcher = TaskDispatcher(pool, obs)
    return AgentRunner(pool, dispatcher, tools, ctx, memory, obs)


@app.command()
def chat(
    message: str = typer.Argument(..., help="사용자 메시지"),
    model: str | None = typer.Option(None, "--model", "-m", help="모델 오버라이드"),
    stream: bool = typer.Option(True, help="스트리밍 출력"),
) -> None:
    """일반 대화 모드"""
    runner = _build_runner()
    tokens: list[str] = []

    def on_token(t: str) -> None:
        tokens.append(t)
        console.print(t, end="", highlight=False)

    asyncio.run(runner.run(message, on_token=on_token if stream else None))
    if not stream:
        # 비스트리밍: 완료 후 한 번에 출력
        pass


@app.command()
def code(
    request: str = typer.Argument(..., help="코드 생성/수정 요청"),
    file: Path | None = typer.Option(None, "--file", "-f", help="대상 파일"),
) -> None:
    """코드 에이전트 모드"""
    prompt = request
    if file and file.exists():
        content = file.read_text()
        prompt = f"File: {file}\n\n```\n{content}\n```\n\nRequest: {request}"
    runner = _build_runner()
    asyncio.run(runner.run(prompt, on_token=lambda t: console.print(t, end="", highlight=False)))


@app.command()
def index(
    path: Path = typer.Argument(..., help="인덱싱할 경로"),
) -> None:
    """코드베이스 RAG 인덱싱"""
    rag = RAGPipeline()
    with console.status(f"[bold green]인덱싱 중: {path}"):
        count = rag.index_codebase(str(path))
    console.print(f"[green]완료: {count}개 청크 인덱싱됨[/green]")


models_app = typer.Typer(help="모델 관리")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list() -> None:
    """설치된 모델 목록"""
    import httpx, asyncio
    async def _list():
        from src.models.ollama_adapter import OllamaAdapter
        adapter = OllamaAdapter()
        return await adapter.list_models()
    models = asyncio.run(_list())
    for m in models:
        console.print(f"  {m.name:<40} {m.size_gb:.1f}GB  ctx:{m.context_length}")


@models_app.command("switch")
def models_switch(name: str = typer.Argument(..., help="전환할 모델명")) -> None:
    """활성 모델 전환"""
    console.print(f"모델 전환: [bold]{name}[/bold]")
    # 다음 실행부터 적용 — .env.local의 DEFAULT_MODEL 업데이트
    env_path = Path(".env.local")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updated = [l for l in lines if not l.startswith("DEFAULT_MODEL=")]
    updated.append(f"DEFAULT_MODEL={name}")
    env_path.write_text("\n".join(updated) + "\n")
    console.print(f"[green].env.local 업데이트 완료[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

`pyproject.toml` 진입점 등록:

```toml
[project.scripts]
local-ai = "src.cli.main:main"
```

---

## 7. 관측성(Observability) 설계

### 7.1 ObservabilityBus (수정: async I/O)

```python
# src/observe/bus.py
import json
import asyncio
import time
from pathlib import Path
from typing import Callable


class ObservabilityBus:
    """
    White-Box 핵심 컴포넌트.
    v2.1 수정: emit()은 동기 유지 (어디서든 호출 가능),
              파일 쓰기는 asyncio.to_thread()로 이벤트 루프 블로킹 방지.
    """

    _default: "ObservabilityBus | None" = None

    def __init__(self):
        self._subscribers: list[Callable] = []
        self._log_path = Path("data/logs/events.jsonl")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get_default(cls) -> "ObservabilityBus":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def subscribe(self, callback: Callable) -> None:
        self._subscribers.append(callback)

    def emit(self, event_type: str, data: dict) -> None:
        event = {"type": event_type, "data": data, "timestamp": time.time()}
        line = json.dumps(event, ensure_ascii=False) + "\n"

        # 파일 쓰기: 이벤트 루프가 실행 중이면 비동기, 아니면 동기
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._write_log, line)
        except RuntimeError:
            # 이벤트 루프 없음 (초기화 단계) → 동기 쓰기
            self._write_log(line)

        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                pass

    def _write_log(self, line: str) -> None:
        with open(self._log_path, "a") as f:
            f.write(line)
```

### 7.2 FastAPI 관측 엔드포인트

```python
# src/api/routes/observe.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json

from src.observe.bus import ObservabilityBus

router = APIRouter()

@router.get("/api/observe")
async def observe_stream():
    """SSE 스트림으로 실시간 파이프라인 이벤트 수신"""
    bus = ObservabilityBus.get_default()
    queue: asyncio.Queue = asyncio.Queue()
    bus.subscribe(queue.put_nowait)

    async def event_stream():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

### 7.3 컨텍스트 덤프 (디버깅)

```bash
# 환경변수로 활성화
export DEBUG_DUMP_CONTEXT=true

# 덤프 위치: data/logs/context_dumps/YYYYMMDD_HHMMSS.md
# 내용: 시스템 프롬프트, 히스토리, RAG 컨텍스트, 최종 사용자 입력 전체
```

---

## 8. 토큰 효율화 전략

### 8.1 토큰 예산 할당 (8192 컨텍스트 기준)

```
┌──────────────────────────────────────────────────────┐
│              토큰 예산 (8192 총합)                     │
├────────────────────┬─────────────────────────────────┤
│ 시스템 프롬프트     │  ~300 tok  (3.7%)               │
│ 대화 히스토리       │  ~1500 tok (18.3%)  → 슬라이딩   │
│ RAG 컨텍스트        │  ~2000 tok (24.4%)  → MMR+트런케 │
│ 현재 입력           │  ~500 tok  (6.1%)               │
│ 출력 예약           │  ~2048 tok (25.0%)              │
│ 여유분             │  ~1844 tok (22.5%)              │
└────────────────────┴─────────────────────────────────┘
```

### 8.2 시스템 프롬프트 최적화 템플릿

```
# 최적화된 시스템 프롬프트 (< 300 토큰)
[ROLE] Local coding agent. Offline. M1 Mac.
[MODEL] {model_name} | ctx:{context_length} | {purpose}
[FORMAT] Concise. Code blocks for code. No preamble. No apologies.
[TOOLS] Use tools for file/shell ops. Confirm before destructive actions.
[RULES] See Rules.md for constraints.
```

### 8.3 대화 히스토리 슬라이딩 윈도우

```
최근 10 턴 원본 유지 (~1500 tok)
초과 시 오래된 턴부터 제거 (요약 없음 — 추가 LLM 호출 없음)

Phase 3에서 LLM 요약 압축 추가 예정:
  오래된 턴 → OllamaAdapter.chat()으로 요약 → 1줄로 압축
```

### 8.4 RAG 중복 제거

```python
# 코사인 유사도 0.95 이상인 청크는 중복으로 판단, 하나만 유지
def deduplicate_chunks(chunks: list, threshold: float = 0.95) -> list:
    unique = []
    for chunk in chunks:
        if not any(cosine_sim(chunk, u) > threshold for u in unique):
            unique.append(chunk)
    return unique
```

### 8.5 조기 종료 핸들러

```python
class EarlyStopHandler:
    """반복 패턴 감지 시 LLM 출력 조기 종료"""
    STOP_PATTERNS = [
        "```\n\n```",   # 빈 코드 블록 반복
        "...\n\n...",   # 말줄임표 반복
        "\n\n\n\n",     # 과도한 빈 줄
    ]

    def check(self, buffer: str) -> bool:
        return any(p in buffer for p in self.STOP_PATTERNS)
```

---

## 9. 오픈소스 연동 매트릭스

### 9.1 코드 에디터 연동

| 도구 | 연동 방식 | 설정 위치 | 비고 |
|------|---------|---------|------|
| **VS Code + Cline** | OpenAI API (Ollama 호환) | `.vscode/settings.json` | 에이전트 + 자동완성 |
| **VS Code + Continue** | Ollama 직접 | `~/.continue/config.json` | 인라인 완성 강점 |
| **Neovim + Avante** | OpenAI API | `init.lua` | Lazy.nvim 플러그인 |
| **Neovim + CodeCompanion** | Ollama 직접 | `init.lua` | 채팅 UI 포함 |
| **Zed** | Ollama 내장 | `~/.config/zed/settings.json` | 네이티브 지원 |
| **Cursor** | OpenAI API (로컬 프록시) | `.cursor/settings.json` | 프록시 필요 |

**Cline 설정 (`settings.json`)**
```json
{
  "cline.apiProvider": "openai",
  "cline.openAiBaseUrl": "http://localhost:11434/v1",
  "cline.openAiApiKey": "ollama",
  "cline.openAiModelId": "qwen2.5-coder:7b",
  "cline.maxTokens": 8192,
  "cline.autoApproveAll": false
}
```

**Continue 설정 (`~/.continue/config.json`)**
```json
{
  "models": [{
    "title": "Local Model",
    "provider": "ollama",
    "model": "qwen2.5-coder:7b",
    "contextLength": 8192,
    "completionOptions": {"temperature": 0.1}
  }],
  "tabAutocompleteModel": {
    "title": "Fast Autocomplete",
    "provider": "ollama",
    "model": "qwen2.5-coder:1.5b"
  },
  "embeddingsProvider": {
    "provider": "ollama",
    "model": "nomic-embed-text"
  }
}
```

### 9.2 TUI 연동

**Aider (코드 특화)**
```bash
aider \
  --model ollama/qwen2.5-coder:7b \
  --openai-api-base http://localhost:11434/v1 \
  --openai-api-key ollama \
  --no-auto-commits \
  --map-tokens 2048
```

**Shell-GPT (범용)**
```bash
# ~/.config/shell_gpt/.sgptrc
OPENAI_API_HOST=http://localhost:11434
DEFAULT_MODEL=qwen2.5-coder:7b
```

### 9.3 기타 도구 연동

| 도구 | API 엔드포인트 | 용도 |
|------|--------------|------|
| **Open WebUI** | Ollama 네이티브 | 브라우저 GUI |
| **AnythingLLM** | `http://localhost:11434` | 지식베이스 |
| **LM Studio** | GGUF 직접 로드 | 백업 모델 서버 |
| **Hollama** | `http://localhost:11434` | 경량 WebUI |

---

## 10. 디렉토리 구조

```
locals-only/
├── ARCHITECTURE.md          ← 아키텍처 레퍼런스 (LLM 컨텍스트용)
├── SKILL.md                 ← 스킬/도구 카탈로그 (LLM 컨텍스트용)
├── Rules.md                 ← 운영 규칙 (코드보다 우선)
├── CLAUDE.md                ← Claude Code 전용 지시 (이 프로젝트 작업 시)
├── README.md                ← 빠른 시작 가이드
├── pyproject.toml           ← 패키지 메타데이터 + CLI 진입점
├── .env.local               ← 환경변수 (gitignore)
│
├── src/                     ← 핵심 소스코드
│   ├── cli/
│   │   └── main.py          ← CLI 진입점 (Typer) ★ 메인 인터페이스
│   │
│   ├── models/
│   │   ├── adapter.py       ← ModelAdapterBase + Message + ChatResult
│   │   ├── ollama_adapter.py← OllamaAdapter (white-box 로깅, async I/O)
│   │   ├── registry.py      ← ModelRegistry (RAM 기반 자동 선택)
│   │   └── pool.py          ← ModelPool (다중 LLM 슬롯 관리)
│   │
│   ├── agent/
│   │   ├── runner.py        ← AgentRunner (도구 호출 루프)
│   │   ├── dispatcher.py    ← TaskDispatcher (의도→모델 라우팅)
│   │   └── intent.py        ← IntentClassifier (경량 모델 사용)
│   │
│   ├── rag/
│   │   ├── pipeline.py      ← RAGPipeline (임베딩+MMR검색+트런케이션)
│   │   ├── indexer.py       ← 코드베이스 인덱싱
│   │   └── dedup.py         ← 중복 청크 제거
│   │
│   ├── memory/
│   │   ├── manager.py       ← MemoryManager (슬라이딩윈도우+SQLite)
│   │   └── sqlite_store.py  ← SQLite 영속 저장
│   │
│   ├── context/
│   │   ├── builder.py       ← ContextBuilder (list[Message] 반환)
│   │   └── budget.py        ← TokenBudget 계산
│   │
│   ├── tools/
│   │   ├── registry.py      ← ToolRegistry (동적 등록/실행)
│   │   ├── file_tools.py    ← read, write, patch, find
│   │   ├── shell_tools.py   ← run_command, run_python (허용목록)
│   │   ├── git_tools.py     ← status, diff, log, commit
│   │   └── rag_tools.py     ← search_codebase, index_path
│   │
│   ├── api/                 ← FastAPI (선택적 — CLI 없이도 동작)
│   │   ├── main.py
│   │   └── routes/
│   │       ├── chat.py      ← OpenAI 호환 /v1/chat/completions
│   │       ├── models.py    ← 모델 전환 /api/switch-model
│   │       └── observe.py   ← SSE 관측 /api/observe
│   │
│   ├── observe/
│   │   └── bus.py           ← ObservabilityBus (async-safe 이벤트 허브)
│   │
│   └── config.py            ← Settings (환경변수 + models.yaml 로드)
│
├── config/
│   ├── models.yaml          ← 모델 프리셋 (단일 진실 소스)
│   └── tools.yaml           ← 도구 활성화 목록
│
├── modelfiles/              ← Ollama Modelfile 프리셋
│   ├── code-assist.Modelfile
│   ├── chat-assistant.Modelfile
│   └── agent-tools.Modelfile
│
├── scripts/
│   ├── setup.sh             ← 초기 설정
│   ├── import-gguf.sh       ← GGUF 모델 직접 등록
│   ├── index-codebase.sh    ← RAG 인덱싱
│   └── switch-model.sh      ← 모델 전환 헬퍼
│
├── data/                    ← 런타임 데이터 (gitignore)
│   ├── chroma/              ← 벡터 DB
│   ├── memory.db            ← 대화 히스토리 (SQLite)
│   └── logs/
│       ├── llm_calls.jsonl  ← LLM 호출 감사 로그
│       ├── tool_calls.jsonl ← 도구 실행 감사 로그
│       ├── events.jsonl     ← 전체 이벤트 스트림
│       └── context_dumps/   ← 디버그 프롬프트 덤프
│
└── tests/
    ├── unit/
    │   ├── test_adapter.py  ← MockAdapter 사용
    │   ├── test_context.py
    │   ├── test_pool.py     ← ModelPool 슬롯 관리
    │   └── test_tools.py
    └── integration/         ← 실제 Ollama 필요
        ├── test_rag.py
        ├── test_agent.py
        └── test_dispatcher.py
```

---

## 11. 설치 및 구성 가이드

### 11.1 초기 설정 스크립트

```bash
#!/bin/bash
# scripts/setup.sh
set -e

echo "=== Local AI Agent Setup (White-Box Edition) ==="

# 1. 시스템 패키지
brew install ollama python@3.12 git

# 2. Python 환경
python3 -m venv .venv
source .venv/bin/activate

pip install \
  langchain langchain-ollama langchain-chroma \
  chromadb fastapi uvicorn httpx \
  typer rich \
  open-webui \
  pydantic pyyaml psutil \
  aider-chat shell-gpt \
  ruff pytest pytest-asyncio

# CLI 로컬 설치 (local-ai 명령 활성화)
pip install -e .

# 3. Ollama 서비스 시작
brew services start ollama
sleep 3

# 4. 모델 다운로드 (인터넷 환경에서 실행)
echo "모델 다운로드 중..."
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-coder:1.5b   # 의도 분류용
ollama pull qwen2.5:7b
ollama pull gemma3:4b
ollama pull nomic-embed-text

# 5. 커스텀 Modelfile 등록
ollama create code-assist -f modelfiles/code-assist.Modelfile
ollama create agent-tools -f modelfiles/agent-tools.Modelfile

# 6. 디렉토리 초기화
mkdir -p data/{chroma,logs,logs/context_dumps}

echo "=== 설치 완료 ==="
echo "CLI 사용:"
echo "  local-ai chat '질문'"
echo "  local-ai code '코드 작성'"
echo "  local-ai index /path/to/project"
echo "  local-ai models list"
echo ""
echo "API 서버 (선택적):"
echo "  uvicorn src.api.main:app --port 8080"
```

### 11.2 환경변수 `.env.local`

```bash
# Ollama 서버
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_MAX_LOADED_MODELS=2        # 항상 2 — main(1) + embed(1) 동시 유지
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_PARALLEL=1             # 직렬 처리 (RAM 절약)

# 모델 설정 (models.yaml의 기본값을 오버라이드)
DEFAULT_MODEL=qwen2.5-coder:7b
EMBED_MODEL=nomic-embed-text

# 스토리지
CHROMA_PATH=./data/chroma
MEMORY_DB_PATH=./data/memory.db

# 에이전트
MAX_CONTEXT_TOKENS=8192
MAX_OUTPUT_TOKENS=2048
MAX_AGENT_ITERATIONS=10
MEMORY_WINDOW_TURNS=10

# OpenAI 호환 (에디터 연동용)
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama

# White-Box 디버그
DEBUG_DUMP_CONTEXT=false
LOG_LEVEL=INFO

# 시스템 프롬프트
SYSTEM_PROMPT="[ROLE] Local coding agent. Offline. M1 Mac.\n[FORMAT] Concise. Code blocks only. No preamble."
```

### 11.3 GGUF 모델 직접 등록 스크립트

```bash
#!/bin/bash
# scripts/import-gguf.sh
GGUF_PATH="$1"
MODEL_NAME="${2:-$(basename "$GGUF_PATH" .gguf)}"

if [ ! -f "$GGUF_PATH" ]; then
  echo "Error: $GGUF_PATH not found"
  exit 1
fi

MODELFILE=$(mktemp)
cat > "$MODELFILE" << EOF
FROM $GGUF_PATH
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
PARAMETER num_predict 2048
EOF

echo "Registering $MODEL_NAME from $GGUF_PATH..."
ollama create "$MODEL_NAME" -f "$MODELFILE"
rm "$MODELFILE"

echo "Done. Test with: ollama run $MODEL_NAME"
echo "Use in CLI: local-ai models switch $MODEL_NAME"
```

### 11.4 launchd 자동 시작 (API 서버, 선택적)

```xml
<!-- ~/Library/LaunchAgents/com.local.ai-agent.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.ai-agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-c</string>
    <string>source /Users/USERNAME/locals-only/.venv/bin/activate && uvicorn src.api.main:app --host 0.0.0.0 --port 8080</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/USERNAME/locals-only</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key>
    <string>0.0.0.0:11434</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key>
    <string>2</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/ai-agent.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/ai-agent-error.log</string>
</dict>
</plist>
```

---

## 12. 에이전트 워크플로우

### 12.1 요청 처리 흐름

```
사용자 요청 (CLI or API)
     │
     ▼
[TaskDispatcher.dispatch()]
  ├─ classify()  →  경량 1.5b 모델로 의도 분류 (빠름, ~0.3초)
  │               intent: code_gen / code_review / chat / rag_query / ...
  └─ acquire()   →  ModelPool에서 해당 목적 슬롯 획득
                     main 슬롯: 필요 시 모델 전환
                     embed 슬롯: 항상 nomic-embed-text 고정
     │
     ▼
[ContextBuilder.build()] → list[Message]
  ├─ system_prompt    (< 300 tok, Message)
  ├─ history          (< 1500 tok, 슬라이딩 윈도우, list[Message])
  ├─ rag_context      (< 2000 tok, MMR+트런케이션, Message)
  └─ user_input       (< 500 tok, Message)
     │
     ▼
[ObservabilityBus] ← context_built 이벤트 발행
     │
     ▼
[OllamaAdapter.chat()] ← 자동 로깅 (async I/O)
  스트리밍: on_token 콜백으로 터미널 출력
  완료: ChatResult 반환 (content + tool_calls)
     │
     ├── result.tool_calls 있음?
     │       │
     │       ▼
     │   [ToolRegistry.execute()]
     │   ├─ 허용 목록 확인
     │   ├─ asyncio.to_thread()로 동기 도구 실행
     │   ├─ 실행 + 감사 로그
     │   └─ tool 메시지 추가 → 재순환 (max 10회)
     │
     └── 최종 응답 (tool_calls 없음)
           │
           ▼
     [MemoryManager.update()] → 슬라이딩 윈도우 + SQLite 비동기 저장
           │
           ▼
     [ModelPool.release()] → 슬롯 반환
           │
           ▼
     [ObservabilityBus] ← request_done 이벤트
```

### 12.2 다중 LLM 오케스트레이션 흐름

```
요청 A (code_gen) ─→ [TaskDispatcher] ─→ main 슬롯(qwen2.5-coder:7b) ─→ 처리 중
                                       │
요청 B (embed)    ─→ [TaskDispatcher] ─→ embed 슬롯(nomic-embed-text) ─→ 병렬 처리 가능
                                       │
요청 C (code_gen) ─→ [TaskDispatcher] ─→ main 슬롯 locked → 대기 → 완료 후 처리

※ main 슬롯과 embed 슬롯은 병렬 실행 가능
※ main 슬롯 내 요청은 직렬 (Ollama 단일 모델 제약)
```

### 12.3 모델 전환 플로우

```
ModelPool.acquire("code") 호출
     │
     ▼
현재 main 슬롯 모델이 qwen2.5:7b (agent용)?
     │
     ├─ YES → OllamaAdapter.switch_model("qwen2.5-coder:7b")
     │         Ollama가 자동으로 이전 모델 언로드 + 신규 로드
     │
     └─ NO (이미 qwen2.5-coder:7b) → 즉시 반환
```

---

## 13. 성능 튜닝 파라미터

### 13.1 Ollama 서버 튜닝

```bash
# 다중 LLM 오케스트레이션 (main + embed 동시)
export OLLAMA_MAX_LOADED_MODELS=2   # 항상 2 권장
export OLLAMA_NUM_PARALLEL=1        # 모델당 직렬 (RAM 절약)

# 공통
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
```

### 13.2 모델별 파라미터 (config/models.yaml 기준)

| 파라미터 | 코드 생성 | 채팅 | 에이전트 | 의도 분류 |
|---------|---------|------|---------|---------|
| temperature | 0.1 | 0.7 | 0.2 | 0.0 |
| top_p | 0.9 | 0.95 | 0.9 | 0.9 |
| top_k | 20 | 40 | 30 | 10 |
| repeat_penalty | 1.1 | 1.05 | 1.1 | 1.0 |
| num_ctx | 8192 | 32768 | 8192 | 2048 |
| num_predict | 2048 | 1024 | 1024 | 64 |

### 13.3 벤치마크 기준 (M1 16GB, Q4_K_M)

| 모델 | 토큰/초 | 첫 토큰 지연 | 메모리 | 권장 용도 |
|------|--------|------------|--------|---------|
| qwen2.5-coder:1.5b | ~85 t/s | ~0.3s | ~1.0GB | 의도 분류, 탭 완성 |
| qwen2.5-coder:3b | ~45 t/s | ~0.8s | ~2.5GB | 코드 (8GB 환경) |
| gemma3:4b | ~38 t/s | ~1.0s | ~3.1GB | 채팅 |
| qwen2.5-coder:7b | ~22 t/s | ~1.5s | ~5.2GB | 코드 (16GB 환경) |
| qwen2.5:7b | ~22 t/s | ~1.5s | ~5.2GB | 에이전트 |
| mistral:7b | ~20 t/s | ~1.6s | ~4.5GB | 폴백 |
| nomic-embed-text | N/A | ~0.05s | ~270MB | 임베딩 전용 |

---

## 14. 확장 로드맵

### Phase 1 — 기반 구축 (CLI 우선) ✅ 완료
- [x] `ModelAdapter` + `OllamaAdapter` 구현 (ChatResult, async I/O)
- [x] `ModelRegistry` (config/models.yaml 연동)
- [x] `ModelPool` (embed 고정 슬롯 + main 슬롯)
- [x] `ObservabilityBus` (async-safe)
- [x] `ToolRegistry` + 기본 도구 (file, shell, git)
- [x] `ContextBuilder` (list[Message] 반환, 타입 일관성)
- [x] `MemoryManager` (슬라이딩 윈도우 + SQLite)
- [x] **CLI 진입점** (`local-ai chat`, `local-ai code`, `local-ai models`)
- [x] 단위 테스트 36개 (MockAdapter 기반, Ollama 불필요)

### Phase 2 — RAG + 에이전트 ✅ 완료
- [x] `RAGPipeline` (임베딩 + MMR 검색 + 토큰 트런케이션)
- [x] `TaskDispatcher` (의도 분류 + 슬롯 라우팅)
- [x] `AgentRunner` (도구 호출 루프, ChatResult 기반)
- [x] 코드베이스 인덱싱 스크립트
- [ ] FastAPI 서버 (OpenAI 호환, 에디터 연동용)

### Phase 3 — 고도화
- [ ] LLM 요약 압축 (MemoryManager — 오래된 턴 요약)
- [ ] 실시간 관측 대시보드 (SSE + 브라우저 UI)
- [ ] 컨텍스트 덤프 + 분석 도구
- [ ] 프로젝트별 컨텍스트 격리 (멀티 ChromaDB 컬렉션)
- [ ] 자동 모델 선택 (쿼리 복잡도 기반)

### Phase 4 — 멀티 에이전트 (선택)
- [ ] Planner + Executor 분리
- [ ] 에이전트 간 메시지 패싱
- [ ] 병렬 서브태스크 처리

---

## 15. 효율성 검증 결과 (v2.1 개정 이유)

v2.0 설계서의 7가지 효율성 문제를 검증하고 수정했습니다.

### 검증된 문제점 및 수정사항

| # | 문제 | 위치 (v2.0) | 영향 | 수정 |
|---|------|-----------|------|------|
| 1 | **tool_call 감지 로직 오류** | `AgentRunner.run()` | 도구 호출 불가 (버그) | ChatResult.tool_calls (done 청크) 사용 |
| 2 | **동기 파일 I/O 이벤트 루프 블로킹** | `ObservabilityBus.emit()` | async 성능 저하 | `loop.run_in_executor()` / `asyncio.to_thread()` |
| 3 | **ContextBuilder 타입 불일치** | `ContextBuilder.build()` | 런타임 타입 오류 | 항상 `list[Message]` 반환 |
| 4 | **RAGPipeline LLMChainExtractor** | `RAGPipeline.search_and_compress()` | 청크당 추가 LLM 호출, 8GB에서 과부하 | 제거 → MMR + 토큰 트런케이션 |
| 5 | **MemoryManager 구 LangChain API** | `MemoryManager.__init__()` | deprecated, LangChain 버전 충돌 | 순수 Python 슬라이딩 윈도우로 교체 |
| 6 | **다중 LLM 오케스트레이션 부재** | 전체 설계 | 의도별 모델 라우팅 불가 | ModelPool + TaskDispatcher 신규 추가 |
| 7 | **CLI 진입점 없음** | 전체 설계 | 서버 없이 사용 불가 | Typer 기반 `local-ai` CLI 추가 |

### 아키텍처 변경 요약

```
v2.0: API-First → FastAPI → AgentRunner → ModelAdapter (단일)
v2.1: CLI-First → AgentRunner → TaskDispatcher → ModelPool → OllamaAdapter (다중)

핵심 개선:
  - CLI 한 줄로 즉시 실행 (서버 불필요)
  - embed 슬롯 상시 고정으로 RAG 오버헤드 제거
  - 의도 분류를 1.5b 경량 모델로 처리 (~0.3초)
  - tool_calls Ollama 실제 API 형식 준수
  - 모든 async 컨텍스트에서 non-blocking I/O
```

---

## 부록: 빠른 참조

### CLI 명령어

```bash
# 설치
pip install -e .

# 대화
local-ai chat "파이썬으로 퀵소트 구현해줘"

# 코드 에이전트 (파일 컨텍스트 포함)
local-ai code "버그 수정해줘" --file src/models/adapter.py

# RAG 인덱싱
local-ai index /path/to/project

# 모델 관리
local-ai models list
local-ai models switch deepseek-coder:6.7b

# 스트리밍 비활성화
local-ai chat "질문" --no-stream
```

### API 명령어 (서버 실행 시)

```bash
# API 서버 시작
uvicorn src.api.main:app --reload --port 8080

# 모델 전환
curl -X POST http://localhost:8080/api/switch-model \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-coder:6.7b"}'

# 관측 스트림 구독
curl -N http://localhost:8080/api/observe

# 토큰 사용량 확인
curl http://localhost:8080/api/token-usage

# 서비스 상태 확인
curl http://localhost:8080/api/health
```

### 새 GGUF 모델 등록

```bash
./scripts/import-gguf.sh /path/to/model.gguf my-model-name
local-ai models switch my-model-name
```

### 연관 문서

| 문서 | 목적 |
|------|------|
| `ARCHITECTURE.md` | 시스템 구조 레퍼런스 (LLM 컨텍스트용) |
| `SKILL.md` | 사용 가능한 도구 카탈로그 |
| `Rules.md` | 운영 규칙 및 안전 제약 |
| `config/models.yaml` | 모델 파라미터 단일 진실 소스 |
| `data/logs/llm_calls.jsonl` | LLM 호출 감사 로그 |
