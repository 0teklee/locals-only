# ARCHITECTURE — Local AI Agent System

> 이 문서는 LLM 컨텍스트용 아키텍처 레퍼런스입니다.
> 코드 작성 전 반드시 이 구조를 참고하여 일관성을 유지하세요.

---

## 시스템 목표

**완전 로컬(Air-gap) + 모델 무관(Model-agnostic) + 화이트박스(White-box) AI 에이전트**

- 어떤 Ollama 호환 모델이든 교체 없이 연동
- 파이프라인의 모든 단계를 관측·개입 가능 (white-box)
- 외부 API 의존성 제로

---

## 계층 구조 (4-Layer)

```
┌─────────────────────────────────────────────────────────┐
│  L4: Interface Layer (인터페이스)                          │
│  CLI(TUI) │ Browser(WebUI) │ Editor(LSP/API) │ API(REST) │
└─────────────────────────┬───────────────────────────────┘
                          │ OpenAI-compat / Ollama native
┌─────────────────────────▼───────────────────────────────┐
│  L3: Orchestration Layer (오케스트레이션)                  │
│  AgentRunner │ RAGPipeline │ MemoryManager │ ToolRouter  │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP (localhost:11434)
┌─────────────────────────▼───────────────────────────────┐
│  L2: Model Layer (모델)                                   │
│  OllamaServer │ ModelRegistry │ ModelfilePresets         │
│  ← 어떤 GGUF 모델이든 런타임 교체 가능 →                  │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  L1: Storage Layer (저장)                                 │
│  ChromaDB(벡터) │ SQLite(메모리) │ FileSystem │ GitIndex  │
└─────────────────────────────────────────────────────────┘
```

---

## 핵심 컴포넌트 맵

| 컴포넌트 | 파일 위치 | 역할 | 교체 가능성 |
|---------|----------|------|-----------|
| `ModelAdapter` | `src/models/adapter.py` | Ollama API 래퍼, 모델 전환 | ✅ 어떤 모델이든 |
| `AgentRunner` | `src/agent/runner.py` | 도구 호출 루프, 스텝 추적 | 부분적 |
| `RAGPipeline` | `src/rag/pipeline.py` | 임베딩 → 검색 → 압축 | ✅ 임베딩 모델 교체 가능 |
| `MemoryManager` | `src/memory/manager.py` | 슬라이딩 윈도우 + 요약 | 부분적 |
| `ToolRegistry` | `src/tools/registry.py` | 도구 등록/탐색/실행 | ✅ 런타임 등록 |
| `ContextBuilder` | `src/context/builder.py` | 토큰 예산 할당 + 조립 | ✅ |
| `ObservabilityBus` | `src/observe/bus.py` | 전 단계 이벤트 스트림 | — |

---

## 데이터 흐름 (요청 1건 기준)

```
사용자 입력
    │
    ▼
[1] IntentClassifier       — 의도 파악 (code/chat/agent/rag)
    │
    ▼
[2] ContextBuilder         — 토큰 예산 계산
    │   ├─ SystemPrompt    (~200 tok)
    │   ├─ MemorySlice     (~1500 tok, 요약 or 슬라이딩)
    │   ├─ RAGContext       (~2000 tok, 압축 후)
    │   └─ UserMessage     (~500 tok)
    │
    ▼
[3] ModelAdapter.chat()    — Ollama API 호출 (스트리밍)
    │   └─ 모델은 config에서 런타임 결정 (white-box)
    │
    ▼
[4] ToolRouter             — tool_call 감지 → 도구 실행
    │   └─ 결과를 [3]으로 재순환 (max 10 iterations)
    │
    ▼
[5] ResponseStreamer        — 사용자에게 스트리밍 출력
    │
    ▼
[6] MemoryManager.update() — 대화 기록 압축·저장
    │
    ▼
[7] ObservabilityBus       — 전 단계 이벤트 로그 기록
```

---

## White-Box 설계 원칙

1. **모든 LLM 호출은 로그**: 입력 프롬프트, 토큰 수, 응답 시간을 `data/logs/llm_calls.jsonl`에 기록
2. **모델 설정은 외부화**: 코드 내 하드코딩 금지. 모든 모델 파라미터는 `config/models.yaml`에서 읽음
3. **파이프라인 단계 관측**: `ObservabilityBus`를 통해 각 단계의 입출력을 구독 가능
4. **도구 실행 감사 로그**: 모든 tool_call 전후로 `data/logs/tool_calls.jsonl` 기록
5. **컨텍스트 덤프 가능**: 디버그 모드에서 최종 프롬프트를 파일로 덤프 (`DEBUG_DUMP_CONTEXT=true`)

---

## 모델 교체 인터페이스

```python
# 어떤 모델이든 이 인터페이스로 교체 가능
class ModelAdapter:
    def set_model(self, model_name: str) -> None: ...
    def chat(self, messages: list[Message]) -> AsyncIterator[str]: ...
    def embed(self, text: str) -> list[float]: ...
    def list_available(self) -> list[ModelInfo]: ...
```

모델은 런타임에 교체 가능:
```bash
POST /api/switch-model  {"model": "llama3.2:3b"}
# 또는
export DEFAULT_MODEL=deepseek-coder:6.7b
```

---

## 포트 및 엔드포인트

| 서비스 | 포트 | 프로토콜 |
|--------|------|---------|
| Ollama | 11434 | HTTP (OpenAI 호환) |
| Open WebUI | 3000 | HTTP |
| FastAPI Agent | 8080 | HTTP |
| ChromaDB | 8000 | HTTP |
| Observability | 8090 | HTTP (SSE) |

---

## 파일 구조 요약

```
locals-only/
├── ARCHITECTURE.md    ← 이 파일 (LLM 컨텍스트용)
├── SKILL.md           ← 사용 가능한 기능 목록
├── Rules.md           ← 운영 규칙 및 제약
├── CLAUDE.md          ← Claude Code 전용 지시
├── src/               ← 핵심 소스코드
│   ├── models/        ← ModelAdapter, ModelRegistry
│   ├── agent/         ← AgentRunner, ToolRouter
│   ├── rag/           ← RAGPipeline, Indexer, Compressor
│   ├── memory/        ← MemoryManager, SlidingWindow
│   ├── context/       ← ContextBuilder, TokenBudget
│   ├── tools/         ← ToolRegistry + 구체적 도구들
│   ├── api/           ← FastAPI 라우터
│   └── observe/       ← ObservabilityBus
├── config/            ← 모든 설정 파일
│   ├── models.yaml    ← 모델 프리셋 (코드/하드코딩 금지)
│   └── tools.yaml     ← 도구 활성화 목록
├── modelfiles/        ← Ollama Modelfile 프리셋
├── data/              ← 런타임 데이터 (gitignore)
│   ├── chroma/
│   └── logs/
├── tests/
└── docs/
    └── dev-plan.md    ← 상세 개발 계획
```
