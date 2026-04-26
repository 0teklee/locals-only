# locals-only — White-Box Local AI Agent

> **완전 로컬 · 모델 무관 · 투명한 AI 코딩 에이전트**
> Fully local · Model-agnostic · Observable AI coding agent

---

## 한국어

### 개요

**locals-only**는 외부 API 없이 로컬 머신(Apple Silicon M1 기준)에서 완전히 동작하는 AI 코딩 에이전트 시스템입니다.  
Ollama 호환 모델이라면 설정 파일 한 줄로 교체 가능하며, 파이프라인의 모든 단계를 관측하고 개입할 수 있습니다.

### 핵심 설계 철학

| 원칙 | 내용 |
|------|------|
| **White-Box** | 모든 LLM 호출·도구 실행의 입출력, 토큰 수, 지연 시간을 JSONL로 기록 |
| **Model-Agnostic** | 코드 내 모델명 하드코딩 없음. Qwen, Llama, Mistral, Gemma, DeepSeek 등 모든 GGUF 지원 |
| **Offline-First** | 임베딩·벡터DB·에이전트 모두 로컬. 인터넷 없이 전 기능 동작 |
| **CLI-First** | 서버 없이 터미널 한 줄로 즉시 실행 |

### 아키텍처 (4-Layer)

```
┌──────────────────────────────────────────────────┐
│  L4: Interface    CLI · WebUI · REST API          │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  L3: Orchestration                                 │
│  AgentRunner · RAGPipeline · MemoryManager        │
│  ToolRouter · ContextBuilder · ObservabilityBus   │
└──────────────────────┬───────────────────────────┘
                       │ HTTP localhost:11434
┌──────────────────────▼───────────────────────────┐
│  L2: Model    Ollama · ModelRegistry              │
│  (런타임 모델 교체 가능 — GGUF 무관)               │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  L1: Storage   ChromaDB · SQLite · FileSystem     │
└──────────────────────────────────────────────────┘
```

### 요청 처리 흐름

```
사용자 입력
  → [1] IntentClassifier  (code / chat / agent / rag)
  → [2] ContextBuilder    (토큰 예산: 시스템 300 + 히스토리 1500 + RAG 2000 + 입력 500)
  → [3] ModelAdapter.chat()  (Ollama 스트리밍, 자동 로깅)
  → [4] ToolRouter        (tool_call 감지 → 실행 → [3] 재순환, 최대 10회)
  → [5] ResponseStreamer  (사용자 스트리밍 출력)
  → [6] MemoryManager    (슬라이딩 윈도우 + LLM 요약 압축)
  → [7] ObservabilityBus (전 단계 이벤트 로그)
```

### 주요 컴포넌트

| 컴포넌트 | 파일 | 역할 |
|---------|------|------|
| `ModelAdapter` | `src/models/adapter.py` | Ollama API 래퍼, 자동 로깅, 런타임 모델 전환 |
| `AgentRunner` | `src/agent/runner.py` | 도구 호출 루프, 스텝 추적 |
| `RAGPipeline` | `src/rag/pipeline.py` | 임베딩 → 검색 → LLM 압축 |
| `MemoryManager` | `src/memory/manager.py` | 슬라이딩 윈도우 + 요약, SQLite 저장 |
| `ToolRegistry` | `src/tools/registry.py` | 도구 등록·탐색·실행 (런타임 등록) |
| `ContextBuilder` | `src/context/builder.py` | 토큰 예산 할당·조립 |
| `ObservabilityBus` | `src/observe/bus.py` | 전 단계 SSE 이벤트 스트림 |

### 사용 가능한 도구 (Skills)

- **FILE**: `read_file`, `write_file`, `patch_file`, `list_directory`, `find_files`
- **SHELL**: `run_command`, `run_python`
- **GIT**: `git_status`, `git_diff`, `git_log`, `git_commit`
- **RAG**: `search_codebase`, `search_docs`, `index_path`
- **MODEL**: `list_models`, `switch_model`, `get_model_info`
- **SYS**: `get_token_usage`, `clear_memory`, `health_check`

### 설치 및 실행

**사전 요구사항**

- Python 3.12+
- [Ollama](https://ollama.com) 설치 및 모델 사전 다운로드
- (선택) ChromaDB, Open WebUI

```bash
# 1. 의존성 설치
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. 모델 준비 (예시)
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text

# 3. 환경 설정
cp .env.local.example .env.local   # 필요한 경우 수정

# 4-A. CLI 실행 (서버 불필요)
local-ai chat "안녕, 코드 리뷰 해줘"
local-ai code "FastAPI 라우터 작성해줘"
local-ai index ./src

# 4-B. API 서버 실행 (선택)
uvicorn src.api.main:app --reload --port 8080
```

### 포트 구성

| 서비스 | 포트 | 비고 |
|--------|------|------|
| Ollama | 11434 | OpenAI 호환 API |
| FastAPI Agent | 8080 | REST + SSE 관측 |
| ChromaDB | 8000 | 벡터 DB |
| Open WebUI | 3000 | 브라우저 인터페이스 |

### 런타임 모델 전환

```bash
# API로 전환
curl -X POST http://localhost:8080/api/switch-model \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:3b"}'

# 환경변수로 전환
export DEFAULT_MODEL=deepseek-coder:6.7b
```

### 개발 명령어

```bash
# 린트 / 포맷
ruff check src/ && ruff format src/

# 테스트
pytest tests/unit/ -v          # MockAdapter 사용 (Ollama 불필요)
pytest tests/integration/ -v   # Ollama 실행 필요

# 관측 스트림 확인
curl -N http://localhost:8080/api/observe
```

### 프로젝트 구조

```
locals-only/
├── src/
│   ├── models/     ModelAdapter, ModelRegistry
│   ├── agent/      AgentRunner, IntentClassifier
│   ├── rag/        RAGPipeline, Indexer, Compressor
│   ├── memory/     MemoryManager, SlidingWindow
│   ├── context/    ContextBuilder, TokenBudget
│   ├── tools/      ToolRegistry + 도구들
│   ├── api/        FastAPI 라우터
│   └── observe/    ObservabilityBus
├── config/
│   ├── models.yaml  모델 파라미터 단일 진실 소스
│   └── tools.yaml   도구 활성화 목록
├── modelfiles/      Ollama Modelfile 프리셋
├── data/            런타임 데이터 (gitignore)
│   ├── chroma/
│   └── logs/        llm_calls.jsonl, tool_calls.jsonl
├── tests/
│   ├── unit/
│   └── integration/
└── docs/
    └── dev-plan.md
```

---

## English

### Overview

**locals-only** is a fully local AI coding agent that runs entirely on your machine (optimized for Apple Silicon M1) with zero external API calls.  
Any Ollama-compatible model can be swapped in via a single config change, and every step of the pipeline is observable and interruptible.

### Core Design Principles

| Principle | Description |
|-----------|-------------|
| **White-Box** | Every LLM call and tool execution is logged to JSONL — tokens, latency, and full I/O |
| **Model-Agnostic** | No model names hardcoded. Supports any GGUF: Qwen, Llama, Mistral, Gemma, DeepSeek, Phi |
| **Offline-First** | Embeddings, vector DB, and agent all run locally. No internet required |
| **CLI-First** | Full functionality from the terminal without starting a server |

### Architecture (4-Layer)

```
┌──────────────────────────────────────────────────┐
│  L4: Interface    CLI · WebUI · REST API          │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  L3: Orchestration                                 │
│  AgentRunner · RAGPipeline · MemoryManager        │
│  ToolRouter · ContextBuilder · ObservabilityBus   │
└──────────────────────┬───────────────────────────┘
                       │ HTTP localhost:11434
┌──────────────────────▼───────────────────────────┐
│  L2: Model    Ollama · ModelRegistry              │
│  (runtime model swap — any GGUF)                  │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  L1: Storage   ChromaDB · SQLite · FileSystem     │
└──────────────────────────────────────────────────┘
```

### Request Flow

```
User input
  → [1] IntentClassifier  (code / chat / agent / rag)
  → [2] ContextBuilder    (token budget: system 300 + history 1500 + RAG 2000 + input 500)
  → [3] ModelAdapter.chat()  (Ollama streaming, auto-logged)
  → [4] ToolRouter        (detect tool_call → execute → loop back to [3], max 10 iterations)
  → [5] ResponseStreamer  (streaming output to user)
  → [6] MemoryManager    (sliding window + LLM summarization)
  → [7] ObservabilityBus (full pipeline event log)
```

### Key Components

| Component | File | Role |
|-----------|------|------|
| `ModelAdapter` | `src/models/adapter.py` | Ollama API wrapper, auto-logging, runtime model switch |
| `AgentRunner` | `src/agent/runner.py` | Tool-call loop with step tracking |
| `RAGPipeline` | `src/rag/pipeline.py` | Embed → retrieve → LLM-compress |
| `MemoryManager` | `src/memory/manager.py` | Sliding window + summarization, SQLite-backed |
| `ToolRegistry` | `src/tools/registry.py` | Register, discover, execute tools at runtime |
| `ContextBuilder` | `src/context/builder.py` | Token budget allocation and prompt assembly |
| `ObservabilityBus` | `src/observe/bus.py` | SSE event stream for every pipeline stage |

### Available Tools (Skills)

- **FILE**: `read_file`, `write_file`, `patch_file`, `list_directory`, `find_files`
- **SHELL**: `run_command`, `run_python`
- **GIT**: `git_status`, `git_diff`, `git_log`, `git_commit`
- **RAG**: `search_codebase`, `search_docs`, `index_path`
- **MODEL**: `list_models`, `switch_model`, `get_model_info`
- **SYS**: `get_token_usage`, `clear_memory`, `health_check`

### Installation & Usage

**Prerequisites**

- Python 3.12+
- [Ollama](https://ollama.com) installed with models pre-downloaded
- (Optional) ChromaDB, Open WebUI

```bash
# 1. Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Pull models
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text

# 3. Configure environment
cp .env.local.example .env.local   # edit as needed

# 4-A. Run via CLI (no server needed)
local-ai chat "review this code"
local-ai code "write a FastAPI router"
local-ai index ./src

# 4-B. Run the API server (optional)
uvicorn src.api.main:app --reload --port 8080
```

### Port Reference

| Service | Port | Notes |
|---------|------|-------|
| Ollama | 11434 | OpenAI-compatible API |
| FastAPI Agent | 8080 | REST + SSE observability |
| ChromaDB | 8000 | Vector database |
| Open WebUI | 3000 | Browser interface |

### Runtime Model Switching

```bash
# Via API
curl -X POST http://localhost:8080/api/switch-model \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:3b"}'

# Via environment variable
export DEFAULT_MODEL=deepseek-coder:6.7b
```

### Development Commands

```bash
# Lint / format
ruff check src/ && ruff format src/

# Tests
pytest tests/unit/ -v          # uses MockAdapter (no Ollama needed)
pytest tests/integration/ -v   # requires running Ollama

# Watch observability stream
curl -N http://localhost:8080/api/observe
```

### Project Structure

```
locals-only/
├── src/
│   ├── models/     ModelAdapter, ModelRegistry
│   ├── agent/      AgentRunner, IntentClassifier
│   ├── rag/        RAGPipeline, Indexer, Compressor
│   ├── memory/     MemoryManager, SlidingWindow
│   ├── context/    ContextBuilder, TokenBudget
│   ├── tools/      ToolRegistry + concrete tools
│   ├── api/        FastAPI routers
│   └── observe/    ObservabilityBus
├── config/
│   ├── models.yaml  Single source of truth for model params
│   └── tools.yaml   Tool activation flags
├── modelfiles/      Ollama Modelfile presets
├── data/            Runtime data (gitignored)
│   ├── chroma/
│   └── logs/        llm_calls.jsonl, tool_calls.jsonl
├── tests/
│   ├── unit/
│   └── integration/
└── docs/
    └── dev-plan.md
```

### Observability

All LLM calls and tool executions are logged automatically:

```jsonl
// data/logs/llm_calls.jsonl
{"ts": "2026-04-26T10:00:00Z", "model": "qwen2.5-coder:7b", "input_tokens": 312, "output_tokens": 87, "latency_ms": 1420}

// data/logs/tool_calls.jsonl
{"ts": "2026-04-26T10:00:01Z", "tool": "read_file", "args": {"path": "src/agent/runner.py"}, "duration_ms": 3}
```

Enable full context dump for debugging:

```bash
DEBUG_DUMP_CONTEXT=true local-ai chat "your query"
```

---

## License

[PolyForm Noncommercial License 1.0.0](LICENSE) — 자유롭게 사용·수정·배포 가능, 수익화(상업적 이용) 금지  
Free to use, modify, and distribute for any noncommercial purpose. Commercial use is prohibited.
