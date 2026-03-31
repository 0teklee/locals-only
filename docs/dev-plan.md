# 🖥️ M1 Mac Mini 로컬 AI 에이전트 시스템 설계서

> **버전**: 1.0.0 | **대상 환경**: Apple Silicon M1 (Mac Mini) | **네트워크**: 완전 오프라인(Air-gap)

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [하드웨어 제약 및 최적화 전략](#2-하드웨어-제약-및-최적화-전략)
3. [모델 선택 전략](#3-모델-선택-전략)
4. [시스템 아키텍처](#4-시스템-아키텍처)
5. [컴포넌트별 설계](#5-컴포넌트별-설계)
6. [토큰 효율화 전략](#6-토큰-효율화-전략)
7. [오픈소스 연동 매트릭스](#7-오픈소스-연동-매트릭스)
8. [디렉토리 구조](#8-디렉토리-구조)
9. [설치 및 구성 가이드](#9-설치-및-구성-가이드)
10. [에이전트 워크플로우](#10-에이전트-워크플로우)
11. [성능 튜닝 파라미터](#11-성능-튜닝-파라미터)
12. [확장 로드맵](#12-확장-로드맵)

---

## 1. 프로젝트 개요

### 목적

외부 API 없이 M1 Mac Mini에서 완전 로컬로 동작하는 AI 코딩 에이전트 + 범용 AI 어시스턴트 시스템 구축.

### 핵심 요구사항

| 요구사항                | 세부 내용                                            |
| ----------------------- | ---------------------------------------------------- |
| **오프라인 완전 동작**  | 인터넷 없이 모든 기능 작동 (모델/임베딩/벡터DB 로컬) |
| **코드 에디터 연동**    | Cline, Continue, Aider 등 LSP/API 방식 통합          |
| **최대 토큰 효율**      | 컨텍스트 압축, 청킹, 캐싱 전략 적용                  |
| **다중 인터페이스**     | TUI(터미널), GUI(브라우저), API(OpenAI 호환)         |
| **에이전트 프레임워크** | 도구 호출, RAG, 멀티스텝 추론 지원                   |

---

## 2. 하드웨어 제약 및 최적화 전략

### M1 Mac Mini 스펙 기준

```
CPU  : Apple M1 (8-core, 4E+4P)
GPU  : 8-core GPU (통합)
RAM  : 8GB ~ 16GB Unified Memory
SSD  : NVMe (고속 스왑 활용 가능)
```

### Unified Memory 활용 원칙

```
┌─────────────────────────────────────────────────────┐
│              Unified Memory (16GB 기준)              │
├──────────────┬──────────────┬────────────────────────┤
│  모델 가중치  │   KV Cache   │   OS + 앱 오버헤드     │
│   ~8-10GB    │   ~2-3GB     │      ~3-4GB            │
└──────────────┴──────────────┴────────────────────────┘
```

### 메모리 절감 원칙

- **Q4_K_M 양자화**를 기본 사용 (Q8 대비 2배 절약, 품질 손실 최소)
- **컨텍스트 길이 제한**: 기본 4096, 코드 특화 시 8192
- **Metal GPU 가속** 필수 (`-ngl 99` 플래그로 모든 레이어 GPU 오프로드)
- 동시 모델 2개 이상 로드 금지 (스왑 발생 시 성능 급락)

---

## 3. 모델 선택 전략

### 3.1 메인 LLM — 용도별 추천

| 용도                   | 모델               | 크기(Q4_K_M) | 컨텍스트 | 특이사항                  |
| ---------------------- | ------------------ | ------------ | -------- | ------------------------- |
| **코드 생성 (메인)**   | `qwen2.5-coder:7b` | ~4.7GB       | 32K      | 코드 특화, 함수 호출 지원 |
| **코드 생성 (경량)**   | `qwen2.5-coder:3b` | ~2.0GB       | 32K      | RAM 8GB 환경 추천         |
| **범용 대화**          | `gemma3:4b`        | ~3.3GB       | 128K     | 긴 컨텍스트, 다국어 강점  |
| **범용 대화 (고품질)** | `mistral:7b`       | ~4.1GB       | 32K      | 지시 따르기 우수          |
| **에이전트/추론**      | `qwen2.5:7b`       | ~4.7GB       | 128K     | 도구 호출, JSON 출력 안정 |
| **임베딩**             | `nomic-embed-text` | ~270MB       | 8K       | RAG 전용, 분리 운용       |

> **RAM 8GB 권장 스택**: `qwen2.5-coder:3b` (코드) + `gemma3:4b` (대화), 번갈아 사용

> **RAM 16GB 권장 스택**: `qwen2.5-coder:7b` (기본 상주) + 필요시 전환

### 3.2 모델 파일 위치

```bash
# Ollama 기본 저장 경로 (변경 권장)
~/.ollama/models/

# 외장 SSD 사용 시 심볼릭 링크
ln -s /Volumes/ExternalSSD/ollama-models ~/.ollama/models
```

### 3.3 GGUF 파일 직접 다운로드 (오프라인 이전 준비)

```bash
# Hugging Face에서 오프라인 이전 전에 미리 다운로드
# 추천: bartowski 또는 lmstudio-community 업로더의 Q4_K_M 파일

# 예: qwen2.5-coder 7B
huggingface-cli download bartowski/Qwen2.5-Coder-7B-Instruct-GGUF \
  --include "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf" \
  --local-dir ~/models/qwen2.5-coder-7b
```

---

## 4. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    클라이언트 레이어                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │  VS Code │  │  Neovim  │  │ Browser  │  │  Terminal     │   │
│  │ (Cline/  │  │(Continue/│  │(Open     │  │  (Aider/      │   │
│  │ Continue)│  │ Avante)  │  │ WebUI)   │  │   TUI)        │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬────────┘   │
└───────┼─────────────┼─────────────┼────────────────┼────────────┘
        │             │             │                │
        └─────────────┴─────────────┴────────────────┘
                              │ OpenAI Compatible API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    서비스 레이어                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Ollama Server  (port: 11434)                │   │
│  │  • /api/chat  • /api/generate  • /v1/* (OpenAI compat)  │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │  Open WebUI          │  │  Agent Orchestrator              │ │
│  │  (port: 3000)        │  │  (LangChain / LlamaIndex)        │ │
│  │  • 대화 UI            │  │  • RAG 파이프라인                 │ │
│  │  • 파일 업로드         │  │  • 도구 호출                     │ │
│  │  • 모델 전환           │  │  • 멀티 에이전트                 │ │
│  └──────────────────────┘  └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
        │                              │
        ▼                              ▼
┌───────────────────┐    ┌─────────────────────────────────────┐
│   Vector DB       │    │         도구 레이어                   │
│  ChromaDB         │    │  • 파일시스템 읽기/쓰기               │
│  (port: 8000)     │    │  • 쉘 실행                           │
│  • 코드 인덱스     │    │  • Git 연동                          │
│  • 문서 임베딩     │    │  • LSP 연동                          │
└───────────────────┘    └─────────────────────────────────────┘
```

---

## 5. 컴포넌트별 설계

### 5.1 Ollama — 모델 서버

**역할**: 단일 진입점 LLM 서버. OpenAI 호환 API 제공.

```bash
# 설치
brew install ollama

# 서비스 등록 (부팅 시 자동 시작)
brew services start ollama

# 핵심 환경변수 (~/.zshrc 또는 launchd plist)
export OLLAMA_HOST=0.0.0.0:11434       # 로컬 네트워크 공개
export OLLAMA_MAX_LOADED_MODELS=1      # 메모리 보호: 동시 로드 1개
export OLLAMA_NUM_PARALLEL=2           # 병렬 요청 수
export OLLAMA_FLASH_ATTENTION=1        # Flash Attention 활성화
export OLLAMA_KV_CACHE_TYPE=q8_0      # KV 캐시 양자화 (메모리 절감)
```

**Modelfile 예시 — 코드 특화 프리셋**

```dockerfile
# ~/.ollama/Modelfile.code
FROM qwen2.5-coder:7b

SYSTEM """
You are an expert coding assistant. When writing code:
- Always output complete, runnable code
- Prefer explicit over implicit
- Add brief inline comments for non-obvious logic
- For file edits, use SEARCH/REPLACE blocks
"""

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_ctx 8192
PARAMETER num_predict 2048
PARAMETER repeat_penalty 1.1
```

```bash
ollama create code-assist -f ~/.ollama/Modelfile.code
```

### 5.2 Open WebUI — 브라우저 GUI

```bash
# Docker 없이 pip 설치 (권장)
pip install open-webui

# 실행 (오프라인 전용 설정)
WEBUI_AUTH=false \
OLLAMA_BASE_URL=http://localhost:11434 \
ENABLE_RAG_WEB_SEARCH=false \
ENABLE_IMAGE_GENERATION=false \
open-webui serve --port 3000
```

**주요 설정 (`~/.config/open-webui/config.json`)**

```json
{
  "default_models": "qwen2.5-coder:7b",
  "rag_embedding_model": "nomic-embed-text",
  "chunk_size": 1000,
  "chunk_overlap": 100,
  "rag_top_k": 5,
  "enable_web_search": false,
  "enable_community_sharing": false
}
```

### 5.3 TUI — 터미널 인터페이스

**옵션 A: Ollama CLI (기본)**

```bash
ollama run qwen2.5-coder:7b
```

**옵션 B: Aider (코드 특화 TUI)**

```bash
pip install aider-chat

# 오프라인 Ollama 연결
aider \
  --model ollama/qwen2.5-coder:7b \
  --openai-api-base http://localhost:11434/v1 \
  --openai-api-key ollama \
  --no-auto-commits \
  --map-tokens 2048
```

**옵션 C: Shell-GPT (범용 TUI)**

```bash
pip install shell-gpt

# 설정 (~/.config/shell_gpt/.sgptrc)
OPENAI_API_HOST=http://localhost:11434
DEFAULT_MODEL=qwen2.5-coder:7b
```

### 5.4 에이전트 오케스트레이터

**LangChain + Ollama 기반 에이전트 (Python)**

```python
# agent/core.py
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from tools import file_tools, shell_tools, git_tools

llm = ChatOllama(
    model="qwen2.5:7b",
    base_url="http://localhost:11434",
    temperature=0.1,
    num_ctx=8192,
    # 스트리밍 활성화
    streaming=True,
)

tools = [
    *file_tools,   # read_file, write_file, list_dir
    *shell_tools,  # run_command (sandboxed)
    *git_tools,    # git_status, git_diff, git_commit
]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a local coding agent. Use tools to complete tasks."),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=10,
    handle_parsing_errors=True,
)
```

### 5.5 RAG 파이프라인

```python
# rag/pipeline.py
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader

# 임베딩 모델 (오프라인)
embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://localhost:11434",
)

# 코드베이스 인덱싱
def index_codebase(path: str, collection: str = "codebase"):
    loader = DirectoryLoader(
        path,
        glob="**/*.{py,ts,js,go,rs,md}",
        recursive=True,
        exclude=["**/node_modules/**", "**/.git/**", "**/dist/**"],
    )
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        # 코드용 구분자 우선순위
        separators=["\nclass ", "\ndef ", "\n\n", "\n", " "],
    )
    chunks = splitter.split_documents(docs)

    vectordb = Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory="./data/chroma",
    )
    vectordb.add_documents(chunks)
    return vectordb

# 검색 (MMR: 다양성 + 관련성 균형)
def search(query: str, vectordb: Chroma, k: int = 5):
    return vectordb.max_marginal_relevance_search(
        query, k=k, fetch_k=20, lambda_mult=0.7
    )
```

---

## 6. 토큰 효율화 전략

### 6.1 컨텍스트 압축 (핵심)

```python
# token/compressor.py
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain.retrievers import ContextualCompressionRetriever

# 검색 결과를 LLM으로 압축 (불필요한 내용 제거)
compressor = LLMChainExtractor.from_llm(llm)
compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=vectordb.as_retriever(search_kwargs={"k": 10}),
)
```

### 6.2 프롬프트 토큰 최적화 원칙

```
❌ 비효율 패턴:
  "Please carefully analyze the following code and provide a comprehensive
   and detailed explanation of what it does, including all edge cases..."

✅ 효율 패턴:
  "Explain this code. Focus: purpose, inputs/outputs, edge cases."
```

**시스템 프롬프트 최소화 템플릿**

```
[ROLE] Coding agent on M1 Mac, offline.
[FORMAT] Be concise. Code blocks for code. No preamble.
[TOOLS] Use tools for file/shell ops. Confirm before destructive actions.
```

### 6.3 대화 히스토리 관리

```python
# memory/sliding_window.py
from langchain.memory import ConversationSummaryBufferMemory

memory = ConversationSummaryBufferMemory(
    llm=llm,
    max_token_limit=2048,     # 초과 시 요약으로 압축
    return_messages=True,
    memory_key="chat_history",
)
```

### 6.4 토큰 예산 할당 (8192 컨텍스트 기준)

```
┌─────────────────────────────────────────────┐
│         토큰 예산 (8192 총합)                 │
├──────────────────┬──────────────────────────┤
│ 시스템 프롬프트   │  ~200 토큰  (2.4%)       │
│ 대화 히스토리     │  ~1500 토큰 (18.3%)      │
│ RAG 컨텍스트     │  ~2000 토큰 (24.4%)      │
│ 현재 입력        │  ~500 토큰  (6.1%)       │
│ 출력 예약        │  ~2048 토큰 (25.0%)      │
│ 여유분           │  ~1944 토큰 (23.7%)      │
└──────────────────┴──────────────────────────┘
```

### 6.5 스트리밍 + 조기 종료

````python
# 불필요한 반복 감지 시 조기 종료
from langchain.callbacks import StreamingStdOutCallbackHandler

class EarlyStopHandler(StreamingStdOutCallbackHandler):
    def __init__(self, stop_sequences=["```\n\n```", "...\n\n..."]):
        self.stop_sequences = stop_sequences
        self.buffer = ""

    def on_llm_new_token(self, token: str, **kwargs):
        self.buffer += token
        for seq in self.stop_sequences:
            if seq in self.buffer:
                raise StopIteration("반복 패턴 감지")
````

---

## 7. 오픈소스 연동 매트릭스

### 7.1 코드 에디터 연동

| 도구                       | 연동 방식                | 설정 파일                     | 비고                |
| -------------------------- | ------------------------ | ----------------------------- | ------------------- |
| **VS Code + Cline**        | OpenAI API (Ollama 호환) | `.vscode/settings.json`       | 자동완성 + 에이전트 |
| **VS Code + Continue**     | Ollama 직접              | `~/.continue/config.json`     | 인라인 완성 강점    |
| **Neovim + Avante**        | OpenAI API               | `init.lua`                    | Lazy.nvim 플러그인  |
| **Neovim + CodeCompanion** | Ollama 직접              | `init.lua`                    | 채팅 UI 포함        |
| **Cursor**                 | OpenAI API (로컬 프록시) | `.cursor/settings.json`       | 프록시 필요         |
| **Zed**                    | Ollama 내장 지원         | `~/.config/zed/settings.json` | 네이티브 지원       |

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
  "models": [
    {
      "title": "Qwen Coder 7B",
      "provider": "ollama",
      "model": "qwen2.5-coder:7b",
      "contextLength": 8192,
      "completionOptions": {
        "temperature": 0.1,
        "topP": 0.9
      }
    }
  ],
  "tabAutocompleteModel": {
    "title": "Qwen Coder 3B (fast)",
    "provider": "ollama",
    "model": "qwen2.5-coder:3b"
  },
  "embeddingsProvider": {
    "provider": "ollama",
    "model": "nomic-embed-text"
  },
  "contextProviders": [
    { "name": "code" },
    { "name": "docs" },
    { "name": "diff" },
    { "name": "terminal" },
    { "name": "open" }
  ]
}
```

**Neovim + Avante (`init.lua`)**

```lua
require("avante").setup({
  provider = "openai",
  openai = {
    endpoint = "http://localhost:11434/v1",
    model = "qwen2.5-coder:7b",
    api_key = "ollama",
    max_tokens = 4096,
    temperature = 0.1,
  },
  behaviour = {
    auto_suggestions = false, -- 성능 절약
    auto_apply_diff_after_generation = false,
  },
})
```

### 7.2 기타 도구 연동

| 도구            | API 엔드포인트              | 용도                 |
| --------------- | --------------------------- | -------------------- |
| **Aider**       | `http://localhost:11434/v1` | 터미널 코드 에이전트 |
| **Open WebUI**  | Ollama 네이티브             | 문서/파일 기반 대화  |
| **LM Studio**   | GGUF 직접 로드              | 백업 모델 서버       |
| **AnythingLLM** | `http://localhost:11434`    | 지식베이스 구축      |
| **Hollama**     | `http://localhost:11434`    | 경량 WebUI           |
| **Msty**        | Ollama 연결                 | 멀티모델 비교        |

---

## 8. 디렉토리 구조

```
~/ai-local/
├── README.md
├── .env.local                    # 환경변수 (gitignore)
│
├── models/                       # GGUF 파일 직접 관리
│   ├── qwen2.5-coder-7b-q4_k_m.gguf
│   └── nomic-embed-text-v1.5.f16.gguf
│
├── modelfiles/                   # Ollama Modelfile 프리셋
│   ├── code-assist.Modelfile
│   ├── chat-assistant.Modelfile
│   └── agent-tools.Modelfile
│
├── agent/                        # 에이전트 코어
│   ├── __init__.py
│   ├── core.py                   # AgentExecutor 설정
│   ├── tools/
│   │   ├── file_tools.py
│   │   ├── shell_tools.py
│   │   ├── git_tools.py
│   │   └── search_tools.py       # 로컬 검색
│   └── prompts/
│       ├── system.md
│       └── templates/
│
├── rag/                          # RAG 파이프라인
│   ├── pipeline.py
│   ├── indexer.py                # 코드베이스 인덱싱
│   └── compressor.py             # 컨텍스트 압축
│
├── memory/                       # 메모리 관리
│   ├── sliding_window.py
│   └── summary.py
│
├── api/                          # FastAPI 래퍼 (선택)
│   ├── main.py                   # OpenAI 호환 엔드포인트
│   ├── routes/
│   │   ├── chat.py
│   │   ├── completions.py
│   │   └── embeddings.py
│   └── middleware/
│       └── token_counter.py
│
├── tui/                          # TUI 스크립트
│   ├── chat.py                   # Rich 기반 채팅 TUI
│   └── agent.py                  # 에이전트 TUI
│
├── data/                         # 로컬 데이터 (gitignore)
│   ├── chroma/                   # 벡터 DB
│   └── logs/
│
├── config/                       # 설정 파일들
│   ├── open-webui.json
│   └── aider.conf.yml
│
├── scripts/                      # 유틸리티 스크립트
│   ├── setup.sh                  # 초기 설정
│   ├── index-codebase.sh         # RAG 인덱싱
│   └── switch-model.sh           # 모델 전환 헬퍼
│
└── tests/
    ├── test_agent.py
    └── test_rag.py
```

---

## 9. 설치 및 구성 가이드

### 9.1 초기 설정 스크립트

```bash
#!/bin/bash
# scripts/setup.sh

set -e

echo "=== M1 Local AI Agent Setup ==="

# 1. Homebrew 패키지
brew install ollama python@3.12 git

# 2. Python 환경
python3 -m venv ~/ai-local/.venv
source ~/ai-local/.venv/bin/activate

pip install \
  langchain langchain-ollama langchain-chroma \
  chromadb fastapi uvicorn \
  open-webui \
  rich typer \
  aider-chat shell-gpt

# 3. Ollama 서비스 시작
brew services start ollama
sleep 3

# 4. 모델 다운로드 (오프라인 이전에 실행)
echo "모델 다운로드 중..."
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
ollama pull gemma3:4b

# 5. 커스텀 Modelfile 등록
ollama create code-assist -f ~/ai-local/modelfiles/code-assist.Modelfile

echo "=== 설치 완료 ==="
echo "Open WebUI: http://localhost:3000"
echo "Ollama API: http://localhost:11434"
```

### 9.2 환경변수 `.env.local`

```bash
# Ollama
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_PARALLEL=2

# Open WebUI
WEBUI_AUTH=false
OLLAMA_BASE_URL=http://localhost:11434

# Agent
DEFAULT_MODEL=qwen2.5-coder:7b
EMBED_MODEL=nomic-embed-text
CHROMA_PATH=./data/chroma
MAX_CONTEXT_TOKENS=8192
MAX_OUTPUT_TOKENS=2048

# API (OpenAI 호환)
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama
```

### 9.3 launchd 서비스 등록 (자동 시작)

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
    <string>/bin/bash</string>
    <string>/Users/USERNAME/ai-local/scripts/start-services.sh</string>
  </array>
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

## 10. 에이전트 워크플로우

### 10.1 코드 에이전트 플로우

```
사용자 요청
     │
     ▼
[의도 분류]
  • 코드 생성?  → code-assist 모델
  • 파일 수정?  → 에이전트 + 도구
  • 질문/설명?  → 대화 모델
     │
     ▼
[RAG 검색] (관련 코드/문서 검색)
     │
     ▼
[컨텍스트 압축] (2000 토큰 이내로 압축)
     │
     ▼
[LLM 추론]
     │
     ├── 도구 호출 필요? → [도구 실행] → 결과 반환 → 재추론
     │
     └── 최종 응답 생성
           │
           ▼
     [스트리밍 출력]
           │
           ▼
     [메모리 업데이트] (요약 또는 슬라이딩 윈도우)
```

### 10.2 에이전트 도구 정의

```python
# agent/tools/file_tools.py
from langchain.tools import tool
from pathlib import Path

@tool
def read_file(path: str) -> str:
    """Read file content. Args: path (relative or absolute)"""
    p = Path(path).expanduser()
    if not p.exists():
        return f"Error: {path} not found"
    if p.stat().st_size > 100_000:  # 100KB 제한
        return p.read_text()[:50_000] + "\n...(truncated)"
    return p.read_text()

@tool
def write_file(path: str, content: str) -> str:
    """Write content to file. Creates parent dirs if needed."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written: {path} ({len(content)} chars)"

@tool
def list_directory(path: str = ".", pattern: str = "*") -> str:
    """List directory contents. Args: path, pattern (glob)"""
    p = Path(path).expanduser()
    items = sorted(p.glob(pattern))
    return "\n".join(
        f"{'[DIR]' if i.is_dir() else '[FILE]'} {i.name}"
        for i in items[:50]  # 최대 50개
    )
```

---

## 11. 성능 튜닝 파라미터

### 11.1 Ollama 서버 튜닝

```bash
# 메모리 8GB 환경
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1

# 메모리 16GB 환경
OLLAMA_MAX_LOADED_MODELS=2
OLLAMA_NUM_PARALLEL=2
```

### 11.2 모델 파라미터 (용도별)

| 파라미터         | 코드 생성 | 대화 | 에이전트 |
| ---------------- | --------- | ---- | -------- |
| `temperature`    | 0.1       | 0.7  | 0.2      |
| `top_p`          | 0.9       | 0.95 | 0.9      |
| `top_k`          | 20        | 40   | 30       |
| `repeat_penalty` | 1.1       | 1.05 | 1.1      |
| `num_ctx`        | 8192      | 4096 | 8192     |
| `num_predict`    | 2048      | 1024 | 1024     |

### 11.3 벤치마크 기준 (M1 8GB)

| 모델                | 토큰/초 (생성) | 첫 토큰 지연 | 메모리 사용 |
| ------------------- | -------------- | ------------ | ----------- |
| qwen2.5-coder:3b Q4 | ~45 t/s        | ~0.8s        | ~2.5GB      |
| qwen2.5-coder:7b Q4 | ~22 t/s        | ~1.5s        | ~5.2GB      |
| gemma3:4b Q4        | ~38 t/s        | ~1.0s        | ~3.1GB      |
| mistral:7b Q4       | ~20 t/s        | ~1.6s        | ~4.5GB      |

---

## 12. 확장 로드맵

### Phase 1 — 기반 구축 (현재)

- [x] Ollama 서버 + 모델 설치
- [x] Open WebUI 연동
- [x] VS Code Cline/Continue 연동
- [x] 기본 TUI (Aider) 설정

### Phase 2 — RAG + 에이전트

- [ ] 코드베이스 벡터 인덱싱
- [ ] LangChain 에이전트 구현
- [ ] 도구 호출 (파일, 쉘, Git)
- [ ] 대화 메모리 관리

### Phase 3 — 고도화

- [ ] FastAPI 커스텀 라우터 (멀티 모델 라우팅)
- [ ] 프로젝트별 컨텍스트 격리
- [ ] 함수 호출 스키마 표준화
- [ ] 평가 파이프라인 (코드 테스트 자동 실행)

### Phase 4 — 멀티 에이전트 (선택)

- [ ] Planner + Executor 분리
- [ ] 병렬 서브태스크 처리
- [ ] 에이전트 간 메시지 패싱

---

## 부록: 빠른 참조

### 자주 쓰는 명령어

```bash
# 모델 전환
ollama run qwen2.5-coder:7b       # 코드
ollama run gemma3:4b               # 대화

# Open WebUI 시작/중지
open-webui serve --port 3000 &
pkill -f "open-webui"

# Aider 실행
aider --model ollama/qwen2.5-coder:7b \
      --openai-api-base http://localhost:11434/v1 \
      --openai-api-key ollama

# 모델 사용량 확인
ollama ps

# 로그 확인
tail -f /tmp/ai-agent.log
```

### 트러블슈팅

| 증상                | 원인                  | 해결                           |
| ------------------- | --------------------- | ------------------------------ |
| 응답 느림 (< 5 t/s) | GPU 오프로드 안됨     | `num_gpu: -1` 확인             |
| OOM 에러            | 메모리 초과           | 모델 크기↓ 또는 `num_ctx`↓     |
| 연결 거부           | Ollama 미실행         | `brew services restart ollama` |
| 반복 출력           | `repeat_penalty` 낮음 | 1.1~1.15로 조정                |
| 느린 첫 응답        | Cold start            | 워밍업 요청 선행               |

---

_최종 수정: 2026-03-31 | 대상: M1 Mac Mini (8GB/16GB) | 완전 오프라인 환경_
