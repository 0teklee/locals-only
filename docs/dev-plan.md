# M1 Mac Mini — White-Box Local AI Agent 설계서

> **버전**: 2.0.0 | **환경**: Apple Silicon M1 (Mac Mini) | **네트워크**: 완전 오프라인(Air-gap)
> **설계 원칙**: White-Box (투명·관측 가능) + Model-Agnostic (모델 무관) + Offline-First

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

---

## 1. 프로젝트 개요 및 설계 철학

### 목적

외부 API 없이 M1 Mac Mini에서 완전 로컬로 동작하는 **투명한(white-box) AI 코딩 에이전트** 시스템 구축.
어떤 Ollama 호환 모델이든 설정 변경만으로 교체 가능.

### 핵심 설계 철학 3가지

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

### 핵심 요구사항

| 요구사항 | 세부 내용 | 우선순위 |
|---------|---------|---------|
| **모델 무관 연동** | 어떤 Ollama 모델이든 설정만으로 교체 | P0 |
| **파이프라인 투명성** | 모든 단계 관측·로깅·개입 가능 | P0 |
| **오프라인 완전 동작** | 인터넷 없이 모든 기능 작동 | P0 |
| **토큰 효율** | 컨텍스트 압축, 청킹, 캐싱 전략 | P1 |
| **코드 에디터 연동** | Cline, Continue, Aider 등 | P1 |
| **다중 인터페이스** | TUI, GUI(브라우저), API | P2 |
| **에이전트 프레임워크** | 도구 호출, RAG, 멀티스텝 추론 | P2 |

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
```

### 메모리 절감 원칙

| 기법 | 효과 | 설정 |
|------|------|------|
| Q4_K_M 양자화 | Q8 대비 2배 절약, 품질 손실 최소 | Modelfile |
| Flash Attention | KV 캐시 메모리 40% 절감 | `OLLAMA_FLASH_ATTENTION=1` |
| KV 캐시 양자화 | `q8_0` 캐시 → 추가 20% 절감 | `OLLAMA_KV_CACHE_TYPE=q8_0` |
| 컨텍스트 제한 | num_ctx=8192 기본 (모델 최대치 미사용) | Modelfile |
| 단일 모델 상주 | 동시 2개 로드 시 스왑 발생 | `OLLAMA_MAX_LOADED_MODELS=1` |
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
| 빠른 완성 | `qwen2.5-coder:1.5b` | `qwen2.5-coder:1.5b` | 1.0GB | 32K | 탭 완성용 |
| 임베딩 | `nomic-embed-text` | `nomic-embed-text` | 270MB | 8K | RAG 전용 |
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
  fallback: mistral:7b

# RAM 기반 자동 선택 (ModelRegistry가 참조)
profiles:
  ram_8gb:
    code: qwen2.5-coder:3b
    chat: gemma3:2b
    agent: qwen2.5:3b

  ram_16gb:
    code: qwen2.5-coder:7b
    chat: gemma3:4b
    agent: qwen2.5:7b

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

  # 새 모델 추가 예시
  llama3.2:3b:
    temperature: 0.5
    num_ctx: 8192
    num_predict: 1024
```

### 3.3 GGUF 직접 등록 (오프라인 환경)

```bash
# Hugging Face에서 사전 다운로드 후 Ollama에 직접 등록
# 인터넷 연결 가능한 환경에서 먼저 실행

# 방법 A: ollama pull (간편)
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text

# 방법 B: GGUF 파일 직접 등록 (오프라인 이전 후)
# 1) Hugging Face에서 .gguf 파일 다운로드
# 2) Modelfile 작성
cat > /tmp/Modelfile << 'EOF'
FROM /path/to/model.gguf
PARAMETER temperature 0.1
PARAMETER num_ctx 8192
EOF
# 3) ollama create로 등록
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
│  │  VS Code │  │  Neovim  │  │ Browser  │  │  Terminal   │  │
│  │(Cline/   │  │(Avante/  │  │(Open     │  │ (Aider/TUI) │  │
│  │Continue) │  │CodeComp) │  │ WebUI)   │  │             │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘  │
└───────┼─────────────┼─────────────┼────────────────┼─────────┘
        │             │             │                │
        └─────────────┴──────┬──────┴────────────────┘
                             │ OpenAI-compat / Ollama native
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                 L3: Orchestration Layer                        │
│  ┌──────────────────┐    ┌──────────────────────────────────┐ │
│  │   FastAPI Server  │    │      AgentRunner                │ │
│  │   (port: 8080)    │    │  ┌────────────┐                 │ │
│  │  /v1/chat         │───▶│  │IntentClass │ 의도 분류       │ │
│  │  /v1/completions  │    │  ├────────────┤                 │ │
│  │  /api/switch-model│    │  │ContextBuild│ 토큰 예산 조립  │ │
│  │  /api/observe     │    │  ├────────────┤                 │ │
│  └──────────────────┘    │  │ToolRouter  │ 도구 실행 루프  │ │
│                           │  ├────────────┤                 │ │
│  ┌──────────────────┐    │  │MemoryMgr   │ 히스토리 관리   │ │
│  │ ObservabilityBus  │◀──│  └────────────┘                 │ │
│  │  (port: 8090/SSE) │    └──────────────────────────────────┘ │
│  │  실시간 파이프라인  │                   │                     │
│  │  이벤트 스트림     │                   ▼                     │
│  └──────────────────┘    ┌──────────────────────────────────┐ │
│                           │       RAGPipeline                │ │
│                           │  Embed → Search → Compress       │ │
│                           └──────────────────────────────────┘ │
└───────────────────────────────────┬──────────────────────────┘
                                    │ HTTP (localhost:11434)
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    L2: Model Layer                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  ModelAdapter                           │  │
│  │  ┌─────────────┐    ┌──────────────┐                  │  │
│  │  │ModelRegistry│    │ OllamaClient │                  │  │
│  │  │ (모델 목록)  │    │ (HTTP 래퍼)  │                  │  │
│  │  └─────────────┘    └──────────────┘                  │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  Ollama Server (11434)                  │  │
│  │   /api/chat  /api/generate  /v1/*  /api/embed          │  │
│  │   ← 어떤 GGUF 모델이든 런타임 교체 가능 →              │  │
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

사용자 입력 ●─→ [IntentClassifier] ●─→ [ContextBuilder] ●
                                                          │
        ┌─────────────────────────────────────────────────┘
        ▼
[ModelAdapter.chat()] ●─────────────────────────── 토큰 수, 지연 시간
        │
        ▼ (tool_call 감지)
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
from dataclasses import dataclass
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
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class ModelAdapterBase(ABC):
    """모든 LLM 백엔드의 공통 인터페이스"""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    async def switch_model(self, model_name: str) -> None: ...

    @abstractmethod
    def get_current_model(self) -> ModelInfo: ...
```

### 5.2 OllamaAdapter 구현 (white-box 로깅 포함)

```python
# src/models/ollama_adapter.py
import time
import json
import asyncio
from pathlib import Path
from typing import AsyncIterator

import httpx
from src.models.adapter import ModelAdapterBase, Message, ModelInfo
from src.observe.bus import ObservabilityBus
from src.config import settings


class OllamaAdapter(ModelAdapterBase):
    """
    Ollama HTTP API 래퍼.
    - 모든 호출에 자동 로깅 (white-box)
    - 모델은 외부 설정에서 결정 (model-agnostic)
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
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": self._params,
        }

        # White-box: 호출 전 로그
        call_id = self._log_call_start(payload, messages)
        start_time = time.monotonic()

        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                output_tokens = 0
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if token := chunk.get("message", {}).get("content", ""):
                        output_tokens += 1
                        yield token
                    if chunk.get("done"):
                        # White-box: 완료 후 로그
                        elapsed = time.monotonic() - start_time
                        self._log_call_end(call_id, output_tokens, elapsed, chunk)

    async def switch_model(self, model_name: str) -> None:
        """런타임 모델 교체 — 재시작 불필요"""
        self._model = model_name
        self._params = settings.get_model_params(model_name)
        self._obs.emit("model_switched", {"model": model_name, "params": self._params})

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

    def _log_call_start(self, payload: dict, messages: list[Message]) -> str:
        import uuid
        call_id = str(uuid.uuid4())[:8]
        entry = {
            "id": call_id,
            "type": "llm_call_start",
            "model": self._model,
            "input_messages": len(messages),
            "input_tokens_estimate": sum(len(m.content.split()) * 1.3 for m in messages),
            "params": self._params,
            "timestamp": time.time(),
        }
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._obs.emit("llm_call_start", entry)
        return call_id

    def _log_call_end(self, call_id: str, output_tokens: int, elapsed: float, raw: dict) -> None:
        entry = {
            "id": call_id,
            "type": "llm_call_end",
            "output_tokens": output_tokens,
            "elapsed_sec": round(elapsed, 3),
            "tokens_per_sec": round(output_tokens / elapsed, 1) if elapsed > 0 else 0,
            "eval_count": raw.get("eval_count", 0),
            "prompt_eval_count": raw.get("prompt_eval_count", 0),
            "timestamp": time.time(),
        }
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._obs.emit("llm_call_end", entry)
```

### 5.3 ModelRegistry — 런타임 모델 탐색

```python
# src/models/registry.py
import psutil
import yaml
from pathlib import Path
from src.models.adapter import ModelInfo


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
        purpose: "code" | "chat" | "agent" | "embed"
        RAM에 따라 자동 선택
        """
        ram_gb = psutil.virtual_memory().total / 1e9
        if ram_gb >= 14:
            profile = "ram_16gb"
        else:
            profile = "ram_8gb"

        return (
            self._config["profiles"].get(profile, {}).get(purpose)
            or self._config["defaults"][purpose]
        )

    def get_params(self, model_name: str) -> dict:
        """모델별 파라미터 반환. 등록 안 된 모델은 기본값 사용."""
        return self._config["presets"].get(model_name, self._config.get("default_params", {}))

    def list_supported(self) -> list[str]:
        return list(self._config["presets"].keys())
```

---

## 6. 컴포넌트별 상세 설계

### 6.1 AgentRunner — 도구 호출 루프

```python
# src/agent/runner.py
import asyncio
import json
import time
from typing import AsyncIterator

from src.models.adapter import ModelAdapterBase, Message
from src.tools.registry import ToolRegistry
from src.context.builder import ContextBuilder
from src.memory.manager import MemoryManager
from src.observe.bus import ObservabilityBus


class AgentRunner:
    """
    White-Box 에이전트 실행 루프.
    각 단계는 ObservabilityBus를 통해 외부에서 관측 가능.
    """

    MAX_ITERATIONS = 10

    def __init__(
        self,
        adapter: ModelAdapterBase,
        tool_registry: ToolRegistry,
        context_builder: ContextBuilder,
        memory: MemoryManager,
        obs: ObservabilityBus,
    ):
        self._adapter = adapter
        self._tools = tool_registry
        self._ctx = context_builder
        self._memory = memory
        self._obs = obs

    async def run(self, user_input: str) -> AsyncIterator[str]:
        # 단계 1: 컨텍스트 조립
        self._obs.emit("step", {"name": "context_build", "status": "start"})
        messages = await self._ctx.build(user_input)
        self._obs.emit("step", {"name": "context_build", "status": "done",
                                "token_budget": self._ctx.last_budget})

        # 도구 호출 루프
        for iteration in range(self.MAX_ITERATIONS):
            self._obs.emit("step", {"name": "llm_call", "iteration": iteration})

            full_response = ""
            tool_calls = []

            async for chunk in self._adapter.chat(messages):
                # tool_call JSON 감지
                if chunk.startswith('{"tool_call":'):
                    tool_calls.append(json.loads(chunk))
                else:
                    full_response += chunk
                    yield chunk  # 스트리밍 출력

            if not tool_calls:
                # 최종 응답 — 루프 종료
                break

            # 단계 N: 도구 실행
            for tc in tool_calls:
                self._obs.emit("step", {"name": "tool_call",
                                        "tool": tc["name"], "args": tc["args"]})
                result = await self._tools.execute(tc["name"], tc["args"])
                self._obs.emit("step", {"name": "tool_result",
                                        "tool": tc["name"], "result_size": len(str(result))})

                messages.append(Message(role="tool", content=str(result),
                                        tool_call_id=tc.get("id")))

        # 메모리 업데이트
        await self._memory.update(user_input, full_response)
```

### 6.2 ContextBuilder — 토큰 예산 관리

```python
# src/context/builder.py
from dataclasses import dataclass
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
    토큰 예산을 관리하며 최적의 컨텍스트를 조립.
    각 슬롯이 예산을 초과하면 자동 압축.
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
        budget: TokenBudget | None = None,
    ):
        self._memory = memory
        self._rag = rag
        self.budget = budget or self.DEFAULT_BUDGET
        self.last_budget: dict = {}

    async def build(self, user_input: str) -> list:
        messages = []

        # 1. 시스템 프롬프트 (최대 budget.system 토큰)
        system = self._get_system_prompt()
        messages.append({"role": "system", "content": system[:self.budget.system * 4]})

        # 2. 대화 히스토리 (압축 적용)
        history = await self._memory.get_compressed(max_tokens=self.budget.history)
        messages.extend(history)

        # 3. RAG 컨텍스트 (검색 + 압축)
        rag_ctx = await self._rag.search_and_compress(user_input, max_tokens=self.budget.rag)
        if rag_ctx:
            messages.append({"role": "system", "content": f"[Context]\n{rag_ctx}"})

        # 4. 현재 입력
        messages.append({"role": "user", "content": user_input})

        # White-box: 예산 현황 기록
        self.last_budget = {
            "system_tokens": len(system.split()),
            "history_messages": len(history),
            "rag_tokens": len(rag_ctx.split()) if rag_ctx else 0,
            "input_tokens": len(user_input.split()),
            "remaining": self.budget.remaining,
        }

        return messages
```

### 6.3 ToolRegistry — 동적 도구 등록

```python
# src/tools/registry.py
from typing import Callable, Any
from dataclasses import dataclass
import json

from src.observe.bus import ObservabilityBus


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable
    requires_confirm: bool = False  # 파괴적 작업 여부


class ToolRegistry:
    """
    런타임에 도구를 등록/탐색/실행.
    도구 추가: register() 호출만으로 완료.
    """

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

        start = __import__("time").monotonic()
        try:
            result = await spec.handler(**args) if __import__("asyncio").iscoroutinefunction(spec.handler) \
                else spec.handler(**args)
        except Exception as e:
            result = f"Error: {e}"

        elapsed = __import__("time").monotonic() - start
        self._obs.emit("tool_executed", {
            "name": name,
            "args": args,
            "elapsed_sec": round(elapsed, 3),
            "result_size": len(str(result)),
        })
        return result
```

### 6.4 RAGPipeline

```python
# src/rag/pipeline.py
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain.retrievers import ContextualCompressionRetriever
from src.config import settings


class RAGPipeline:
    """
    임베딩 모델도 model-agnostic — config에서 교체 가능.
    검색 후 자동 압축으로 토큰 절감.
    """

    def __init__(self, llm, embed_model: str | None = None):
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
        self._compressor = LLMChainExtractor.from_llm(llm)

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

    async def search_and_compress(self, query: str, max_tokens: int = 2000) -> str:
        # MMR 검색 (다양성 + 관련성 균형)
        retriever = self._vectordb.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 10, "fetch_k": 30, "lambda_mult": 0.7},
        )
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=self._compressor,
            base_retriever=retriever,
        )
        docs = compression_retriever.invoke(query)

        # 토큰 예산 내로 조합
        result_parts = []
        token_count = 0
        for doc in docs:
            chunk_tokens = len(doc.page_content.split())
            if token_count + chunk_tokens > max_tokens:
                break
            result_parts.append(f"# {doc.metadata.get('source', 'unknown')}\n{doc.page_content}")
            token_count += chunk_tokens

        return "\n\n---\n\n".join(result_parts)
```

### 6.5 MemoryManager — 대화 히스토리 압축

```python
# src/memory/manager.py
import sqlite3
import json
from pathlib import Path
from langchain.memory import ConversationSummaryBufferMemory
from src.models.adapter import ModelAdapterBase


class MemoryManager:
    """
    슬라이딩 윈도우 + LLM 요약으로 무한 대화 지원.
    SQLite로 영속 저장 (재시작 후 복원 가능).
    """

    def __init__(self, llm, max_token_limit: int = 1500):
        self._llm = llm
        self._max_tokens = max_token_limit
        self._db_path = Path("data/memory.db")
        self._init_db()
        self._summary_memory = ConversationSummaryBufferMemory(
            llm=llm,
            max_token_limit=max_token_limit,
            return_messages=True,
        )

    def _init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    role TEXT,
                    content TEXT,
                    timestamp REAL,
                    session_id TEXT
                )
            """)

    async def get_compressed(self, max_tokens: int) -> list[dict]:
        """압축된 히스토리 반환 (토큰 예산 내)"""
        msgs = self._summary_memory.chat_memory.messages
        result = []
        token_count = 0
        for msg in reversed(msgs):  # 최신 메시지 우선
            tokens = len(msg.content.split())
            if token_count + tokens > max_tokens:
                break
            result.insert(0, {"role": msg.type, "content": msg.content})
            token_count += tokens
        return result

    async def update(self, user_input: str, assistant_response: str):
        self._summary_memory.save_context(
            {"input": user_input},
            {"output": assistant_response},
        )
        # SQLite 영속 저장
        with sqlite3.connect(self._db_path) as conn:
            import time
            conn.executemany(
                "INSERT INTO messages (role, content, timestamp) VALUES (?, ?, ?)",
                [
                    ("user", user_input, time.time()),
                    ("assistant", assistant_response, time.time()),
                ],
            )
```

---

## 7. 관측성(Observability) 설계

### 7.1 ObservabilityBus — 이벤트 허브

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
    파이프라인의 모든 단계 이벤트를 수집·배포.
    SSE를 통해 실시간 관측 가능.
    """

    _default: "ObservabilityBus | None" = None

    def __init__(self):
        self._subscribers: list[Callable] = []
        self._log_path = Path("data/logs/events.jsonl")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_default(cls) -> "ObservabilityBus":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def subscribe(self, callback: Callable) -> None:
        self._subscribers.append(callback)

    def emit(self, event_type: str, data: dict) -> None:
        event = {"type": event_type, "data": data, "timestamp": time.time()}
        # 파일 기록
        with open(self._log_path, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        # 구독자에게 배포
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                pass
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
│ 대화 히스토리       │  ~1500 tok (18.3%)  → 요약 압축 │
│ RAG 컨텍스트        │  ~2000 tok (24.4%)  → LLM 압축  │
│ 현재 입력           │  ~500 tok  (6.1%)               │
│ 출력 예약           │  ~2048 tok (25.0%)               │
│ 여유분             │  ~1844 tok (22.5%)               │
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

### 8.3 대화 히스토리 압축 전략

```
최근 N 턴은 원본 유지 → 이전은 LLM 요약으로 압축

┌─────────────────────────────────────────────────┐
│ 요약된 이전 대화 (LLM이 요약, ~300 tok)          │
├─────────────────────────────────────────────────┤
│ 최근 5턴 원본 유지 (~1200 tok)                   │
└─────────────────────────────────────────────────┘
전체 히스토리 예산: 1500 tok 이내 유지
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
        "```\n\n```",      # 빈 코드 블록 반복
        "...\n\n...",      # 말줄임표 반복
        "\n\n\n\n",        # 과도한 빈 줄
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
├── .env.local               ← 환경변수 (gitignore)
│
├── src/                     ← 핵심 소스코드
│   ├── models/
│   │   ├── adapter.py       ← ModelAdapterBase (인터페이스)
│   │   ├── ollama_adapter.py← OllamaAdapter (구현 + white-box 로깅)
│   │   └── registry.py      ← ModelRegistry (RAM 기반 자동 선택)
│   │
│   ├── agent/
│   │   ├── runner.py        ← AgentRunner (도구 호출 루프)
│   │   └── intent.py        ← IntentClassifier
│   │
│   ├── rag/
│   │   ├── pipeline.py      ← RAGPipeline (임베딩+검색+압축)
│   │   ├── indexer.py       ← 코드베이스 인덱싱
│   │   └── dedup.py         ← 중복 청크 제거
│   │
│   ├── memory/
│   │   ├── manager.py       ← MemoryManager (슬라이딩윈도우+요약)
│   │   └── sqlite_store.py  ← SQLite 영속 저장
│   │
│   ├── context/
│   │   ├── builder.py       ← ContextBuilder (토큰 예산 조립)
│   │   └── budget.py        ← TokenBudget 계산
│   │
│   ├── tools/
│   │   ├── registry.py      ← ToolRegistry (동적 등록/실행)
│   │   ├── file_tools.py    ← read, write, patch, find
│   │   ├── shell_tools.py   ← run_command, run_python (허용목록)
│   │   ├── git_tools.py     ← status, diff, log, commit
│   │   └── rag_tools.py     ← search_codebase, index_path
│   │
│   ├── api/
│   │   ├── main.py          ← FastAPI 앱
│   │   └── routes/
│   │       ├── chat.py      ← OpenAI 호환 /v1/chat/completions
│   │       ├── models.py    ← 모델 전환 /api/switch-model
│   │       └── observe.py   ← SSE 관측 /api/observe
│   │
│   └── observe/
│       └── bus.py           ← ObservabilityBus (이벤트 허브)
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
    │   └── test_tools.py
    └── integration/         ← 실제 Ollama 필요
        ├── test_rag.py
        └── test_agent.py
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
  open-webui \
  rich typer pydantic pyyaml psutil \
  aider-chat shell-gpt \
  ruff pytest pytest-asyncio

# 3. Ollama 서비스 시작
brew services start ollama
sleep 3

# 4. 모델 다운로드 (인터넷 환경에서 실행)
echo "모델 다운로드 중..."
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5-coder:3b   # 8GB 환경 대비
ollama pull qwen2.5:7b
ollama pull gemma3:4b
ollama pull nomic-embed-text

# 5. 커스텀 Modelfile 등록
ollama create code-assist -f modelfiles/code-assist.Modelfile
ollama create agent-tools -f modelfiles/agent-tools.Modelfile

# 6. 디렉토리 초기화
mkdir -p data/{chroma,logs,logs/context_dumps}

echo "=== 설치 완료 ==="
echo "Ollama API  : http://localhost:11434"
echo "Agent API   : http://localhost:8080"
echo "Observability: http://localhost:8090/api/observe"
```

### 11.2 환경변수 `.env.local`

```bash
# Ollama 서버
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_MAX_LOADED_MODELS=1        # RAM 8GB: 1, RAM 16GB: 2
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_PARALLEL=2

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

# OpenAI 호환 (에디터 연동용)
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama

# White-Box 디버그
DEBUG_DUMP_CONTEXT=false          # true: 프롬프트 덤프 활성화
LOG_LEVEL=INFO
```

### 11.3 GGUF 모델 직접 등록 스크립트

```bash
#!/bin/bash
# scripts/import-gguf.sh
# 사용: ./scripts/import-gguf.sh /path/to/model.gguf [model-name]

GGUF_PATH="$1"
MODEL_NAME="${2:-$(basename "$GGUF_PATH" .gguf)}"

if [ ! -f "$GGUF_PATH" ]; then
  echo "Error: $GGUF_PATH not found"
  exit 1
fi

# 임시 Modelfile 생성
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
echo "Switch in agent: POST /api/switch-model {\"model\": \"$MODEL_NAME\"}"
```

### 11.4 launchd 자동 시작

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
    <string>source /Users/USERNAME/ai-local/.venv/bin/activate && uvicorn src.api.main:app --host 0.0.0.0 --port 8080</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/USERNAME/ai-local</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key>
    <string>0.0.0.0:11434</string>
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
사용자 요청
     │
     ▼
[IntentClassifier]
  code_gen  → code-assist 모델 선택
  file_edit → agent-tools 모델 선택
  qa/chat   → chat 모델 선택
  rag_query → 검색 모드
     │
     ▼
[ContextBuilder] ← TokenBudget 계산
  ├─ system_prompt    (< 300 tok)
  ├─ compressed_hist  (< 1500 tok)
  ├─ rag_context      (< 2000 tok, 압축됨)
  └─ user_input       (< 500 tok)
     │
     ▼
[ObservabilityBus] ← context_built 이벤트 발행
     │
     ▼
[ModelAdapter.chat()] ← 자동 로깅
  스트리밍 출력 시작 →
     │
     ├── tool_call 감지?
     │       │
     │       ▼
     │   [ToolRegistry.execute()]
     │   ├─ 허용 목록 확인
     │   ├─ 파괴적 작업? → 사용자 확인
     │   ├─ 실행 + 감사 로그
     │   └─ 결과 반환 → 재순환 (max 10회)
     │
     └── 최종 응답
           │
           ▼
     [ResponseStreamer] → 사용자 출력
           │
           ▼
     [MemoryManager.update()] → SQLite 저장
           │
           ▼
     [ObservabilityBus] ← request_done 이벤트 발행
```

### 12.2 모델 전환 플로우

```
POST /api/switch-model {"model": "deepseek-coder:6.7b"}
     │
     ▼
[ModelRegistry.get_params("deepseek-coder:6.7b")]
  → config/models.yaml에서 파라미터 로드
  → 없으면 기본값 사용
     │
     ▼
[OllamaAdapter.switch_model()]
  → self._model = "deepseek-coder:6.7b"
  → self._params = 로드된 파라미터
     │
     ▼
[ObservabilityBus] ← model_switched 이벤트
  → 이후 모든 요청은 새 모델 사용
```

---

## 13. 성능 튜닝 파라미터

### 13.1 Ollama 서버 튜닝

```bash
# RAM 8GB 환경
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1

# RAM 16GB 환경
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_NUM_PARALLEL=2

# 공통
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
```

### 13.2 모델별 파라미터 (config/models.yaml 기준)

| 파라미터 | 코드 생성 | 채팅 | 에이전트 | 빠른 완성 |
|---------|---------|------|---------|---------|
| temperature | 0.1 | 0.7 | 0.2 | 0.1 |
| top_p | 0.9 | 0.95 | 0.9 | 0.9 |
| top_k | 20 | 40 | 30 | 10 |
| repeat_penalty | 1.1 | 1.05 | 1.1 | 1.05 |
| num_ctx | 8192 | 32768 | 8192 | 4096 |
| num_predict | 2048 | 1024 | 1024 | 256 |

### 13.3 벤치마크 기준 (M1 16GB, Q4_K_M)

| 모델 | 토큰/초 | 첫 토큰 지연 | 메모리 | 권장 용도 |
|------|--------|------------|--------|---------|
| qwen2.5-coder:1.5b | ~85 t/s | ~0.4s | ~1.0GB | 탭 완성 |
| qwen2.5-coder:3b | ~45 t/s | ~0.8s | ~2.5GB | 코드 (8GB 환경) |
| gemma3:4b | ~38 t/s | ~1.0s | ~3.1GB | 채팅 |
| qwen2.5-coder:7b | ~22 t/s | ~1.5s | ~5.2GB | 코드 (16GB 환경) |
| qwen2.5:7b | ~22 t/s | ~1.5s | ~5.2GB | 에이전트 |
| mistral:7b | ~20 t/s | ~1.6s | ~4.5GB | 폴백 |

---

## 14. 확장 로드맵

### Phase 1 — 기반 구축
- [x] 기존 설계서 작성
- [ ] `ModelAdapter` + `OllamaAdapter` 구현
- [ ] `ModelRegistry` (config/models.yaml 연동)
- [ ] `ObservabilityBus` 구현
- [ ] `ToolRegistry` + 기본 도구 (file, shell, git)
- [ ] FastAPI 서버 (OpenAI 호환 + switch-model + observe)

### Phase 2 — RAG + 에이전트
- [ ] `RAGPipeline` (임베딩 + 검색 + 압축)
- [ ] `ContextBuilder` (토큰 예산 관리)
- [ ] `MemoryManager` (슬라이딩 윈도우 + SQLite)
- [ ] `AgentRunner` (도구 호출 루프, white-box)
- [ ] 코드베이스 인덱싱 스크립트

### Phase 3 — 고도화
- [ ] 실시간 관측 대시보드 (SSE + 브라우저 UI)
- [ ] 컨텍스트 덤프 + 분석 도구
- [ ] 프로젝트별 컨텍스트 격리 (멀티 ChromaDB 컬렉션)
- [ ] 자동 모델 선택 (쿼리 복잡도 기반)
- [ ] 평가 파이프라인 (코드 테스트 자동 실행)

### Phase 4 — 멀티 에이전트 (선택)
- [ ] Planner + Executor 분리
- [ ] 에이전트 간 메시지 패싱
- [ ] 병렬 서브태스크 처리

---

## 부록: 빠른 참조

### 자주 쓰는 명령어

```bash
# 모델 전환 (CLI)
./scripts/switch-model.sh deepseek-coder:6.7b

# 모델 전환 (API)
curl -X POST http://localhost:8080/api/switch-model \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-coder:6.7b"}'

# 새 GGUF 모델 등록
./scripts/import-gguf.sh /path/to/model.gguf my-model-name

# RAG 인덱싱
./scripts/index-codebase.sh /path/to/project

# 관측 스트림 구독
curl -N http://localhost:8090/api/observe

# 토큰 사용량 확인
curl http://localhost:8080/api/token-usage

# 서비스 상태 확인
curl http://localhost:8080/api/health

# 컨텍스트 덤프 활성화
DEBUG_DUMP_CONTEXT=true uvicorn src.api.main:app --port 8080

# 설치된 모델 목록
ollama list
curl http://localhost:11434/api/tags | jq '.models[].name'
```

### 연관 문서

| 문서 | 목적 |
|------|------|
| `ARCHITECTURE.md` | 시스템 구조 레퍼런스 (LLM 컨텍스트용) |
| `SKILL.md` | 사용 가능한 도구 카탈로그 |
| `Rules.md` | 운영 규칙 및 안전 제약 |
| `config/models.yaml` | 모델 파라미터 단일 진실 소스 |
| `data/logs/llm_calls.jsonl` | LLM 호출 감사 로그 |
