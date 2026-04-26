# CLAUDE.md — 이 프로젝트 작업 시 Claude Code 지시사항

> 이 파일은 Claude Code가 이 프로젝트에서 작업할 때 항상 따르는 지시사항입니다.

---

## 필수 참조 문서

코드 작성 전 반드시 확인:
1. `ARCHITECTURE.md` — 컴포넌트 구조, 데이터 흐름, 파일 위치
2. `SKILL.md` — 사용 가능한 도구 목록
3. `Rules.md` — 운영 규칙 및 제약 (코드보다 우선)
4. `config/models.yaml` — 모델 파라미터 단일 진실 소스

---

## 핵심 제약 (절대 불변)

### 모델명 하드코딩 금지
```python
# ❌ 절대 금지
ChatOllama(model="qwen2.5-coder:7b")

# ✅ 항상 설정에서 읽기
from src.config import settings
ChatOllama(model=settings.DEFAULT_MODEL)
```

### 모든 LLM 호출에 로깅 필수
- `OllamaAdapter.chat()`을 거쳐야 함 (직접 HTTP 호출 금지)
- 로깅 없는 LLM 호출은 white-box 원칙 위반

### 파괴적 작업 전 확인 필수
- `write_file`, `git_commit`, 쉘 명령 실행 전 사용자 확인
- `--no-verify`, `--force` 플래그 사용 금지

---

## 코드 작성 규칙

- Python 3.12+, 타입 힌트 필수 (공개 함수)
- 포매터: `ruff format`, 린터: `ruff check`
- 새 파일 전 `ARCHITECTURE.md`의 파일 위치 확인
- 단위 테스트는 `MockAdapter` 사용 (실제 Ollama 불필요)
- 새 도구 추가 시 `SKILL.md`에 명세 추가

---

## 프로젝트 구조 요약

```
src/models/   → ModelAdapter (인터페이스) + OllamaAdapter (구현)
src/agent/    → AgentRunner + IntentClassifier
src/rag/      → RAGPipeline (임베딩+검색+압축)
src/memory/   → MemoryManager (슬라이딩윈도우+SQLite)
src/context/  → ContextBuilder (토큰 예산)
src/tools/    → ToolRegistry + 도구들
src/api/      → FastAPI 라우터
src/observe/  → ObservabilityBus
config/       → models.yaml (모델 파라미터 단일 진실 소스)
data/logs/    → 감사 로그 (gitignore)
```

---

## 자주 사용하는 명령어

```bash
# 개발 서버
source .venv/bin/activate
uvicorn src.api.main:app --reload --port 8080

# 린트/포맷
ruff check src/ && ruff format src/

# 테스트
pytest tests/unit/ -v
pytest tests/integration/ -v  # Ollama 실행 중이어야 함

# 모델 목록
ollama list

# 관측 스트림
curl -N http://localhost:8080/api/observe
```
