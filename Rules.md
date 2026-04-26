# Rules — 운영 규칙 및 제약 조건

> 에이전트와 개발자 모두가 따라야 할 규칙입니다.
> 이 문서의 규칙은 코드 구현보다 우선합니다.

---

## 1. 안전 규칙 (Safety Rules) — 절대 불변

### 1.1 파괴적 작업 규칙
```
❌ 금지 — 확인 없이 절대 실행 불가:
  - rm -rf, rmdir (비어있지 않은 디렉토리)
  - git reset --hard, git clean -f
  - git push --force
  - DROP TABLE, DELETE FROM (조건 없음)
  - 시스템 설정 파일 덮어쓰기 (/etc/*, ~/.ssh/*)

✅ 허용 — 확인 후 실행:
  - 파일 쓰기 (write_file)
  - git commit, git push (일반)
  - 패키지 설치 (pip, brew)
```

### 1.2 쉘 실행 허용 목록 (SHELL_ALLOWLIST)
```yaml
# 이 목록에 없는 명령은 에이전트가 직접 실행 불가
allowlist:
  - git
  - python3, pip, uv
  - brew
  - make, cmake
  - npm, npx, node
  - cargo, rustc
  - ollama
  - ls, cat, head, tail, grep, find, wc
  - curl (localhost만 허용)
```

### 1.3 네트워크 규칙
```
- 기본: 모든 외부 네트워크 요청 금지
- localhost (127.0.0.1) 및 LAN (192.168.x.x) 만 허용
- curl/requests 사용 시 URL 화이트리스트 확인 필수
  허용: http://localhost:11434, http://localhost:8000
```

---

## 2. 모델 사용 규칙 (Model Rules)

### 2.1 모델 선택 기준
```
용도별 우선 모델 (config/models.yaml에서 재정의 가능):

CODE_GENERATION:  qwen2.5-coder:7b  (RAM 16GB)
                  qwen2.5-coder:3b  (RAM 8GB)
CHAT:             gemma3:4b
AGENT_REASONING:  qwen2.5:7b
EMBEDDING:        nomic-embed-text  (전용, 다른 용도 사용 금지)
FALLBACK:         mistral:7b
```

### 2.2 동시 로드 제한
```
- 동시 로드 모델: 최대 1개 (RAM 8GB) / 최대 2개 (RAM 16GB)
- 임베딩 모델은 별도 슬롯으로 항상 로드 유지
- 모델 전환 시 이전 모델 언로드 후 신규 로드
```

### 2.3 컨텍스트 길이 규칙
```
- 기본 컨텍스트: 8192 토큰
- 최대 컨텍스트: 모델별 상한 (models.yaml 참조)
- 입력이 컨텍스트 80% 초과 시 → 압축 단계 강제 실행
- 출력 예약: 항상 2048 토큰 확보
```

---

## 3. 토큰 효율 규칙 (Token Rules)

### 3.1 토큰 예산 (8192 기준)
```
시스템 프롬프트 : 최대 300 토큰
대화 히스토리  : 최대 1500 토큰 (초과 시 요약 압축)
RAG 컨텍스트  : 최대 2000 토큰 (압축 후)
현재 입력     : 최대 500 토큰
출력 예약     : 2048 토큰
여유분        : 나머지
```

### 3.2 프롬프트 작성 규칙
```
✅ 해야 할 것:
  - 역할, 형식, 도구를 각 1줄로 명시
  - 구체적 지시 (예: "JSON으로 출력", "파일명 포함")
  - 예시는 1개만 (few-shot 남용 금지)

❌ 하지 말 것:
  - "carefully", "comprehensive", "detailed" 같은 수식어 남용
  - 같은 지시 반복
  - 불필요한 예의 표현 ("Please", "Thank you")
  - 이미 컨텍스트에 있는 내용 재설명
```

### 3.3 RAG 청크 규칙
```
- 청크 크기: 1000 토큰 (코드), 800 토큰 (문서)
- 오버랩: 100 토큰
- 검색 결과: k=5 (기본), k=3 (토큰 부족 시)
- 검색 후 압축 필수 (LLMChainExtractor 사용)
- 중복 청크 필터링 (cosine similarity > 0.95 → 하나만 사용)
```

---

## 4. 코드 작성 규칙 (Code Rules)

### 4.1 언어 및 스타일
```
Python 버전: 3.12+
타입 힌트: 모든 공개 함수에 필수
포매터: ruff (black 호환 모드)
린터: ruff
임포트: isort 정렬
```

### 4.2 모델 의존성 분리
```
❌ 금지 — 코드 내 모델명 하드코딩:
  model = ChatOllama(model="qwen2.5-coder:7b")  # 금지

✅ 허용 — 설정에서 읽기:
  model = ChatOllama(model=settings.DEFAULT_MODEL)
```

### 4.3 에러 처리
```
- Ollama 연결 실패: 재시도 3회 (exponential backoff)
- 모델 타임아웃: 기본 120초, 코드 생성 시 180초
- 도구 실행 실패: 에러 메시지를 LLM에게 반환하여 재시도 유도
- 치명적 오류: 로그 기록 후 사용자에게 명확히 보고
```

### 4.4 White-Box 구현 요구사항
```
모든 LLM 호출 전후 반드시:
  1. 호출 전: 입력 토큰 수, 모델명, 타임스탬프 로그
  2. 호출 후: 출력 토큰 수, 지연 시간, 완료 여부 로그
  3. 형식: JSONL → data/logs/llm_calls.jsonl

모든 도구 호출 전후 반드시:
  1. 호출 전: 도구명, 인자 로그
  2. 호출 후: 결과 크기, 실행 시간 로그
  3. 형식: JSONL → data/logs/tool_calls.jsonl
```

---

## 5. 개발 프로세스 규칙

### 5.1 변경 전 확인 사항
```
체크리스트 (코드 수정 전):
  [ ] ARCHITECTURE.md의 컴포넌트 위치 확인
  [ ] 해당 모듈의 기존 테스트 실행
  [ ] 모델명/파라미터가 config/models.yaml 참조인지 확인
  [ ] 로깅 훅이 추가되어 있는지 확인
```

### 5.2 테스트 규칙
```
- 단위 테스트: Ollama 실제 호출 대신 MockAdapter 사용
- 통합 테스트: 실제 Ollama 서버 필요 (로컬에서만 실행)
- 성능 테스트: 토큰/초, 첫 토큰 지연 기준값 유지 필수
```

### 5.3 설정 관리
```
환경별 설정:
  .env.local       — 개발 (gitignore)
  .env.production  — 실서비스 (gitignore)
  config/*.yaml    — 기본값 (git 추적)

우선순위: 환경변수 > .env.local > config/*.yaml 기본값
```

---

## 6. 금지 패턴 목록

```python
# ❌ 외부 API 호출
import openai  # 금지
requests.get("https://api.openai.com/...")  # 금지

# ❌ 모델명 하드코딩
ChatOllama(model="qwen2.5-coder:7b")  # 금지

# ❌ 컨텍스트 무제한 성장
messages.append(new_message)  # 압축 없이 계속 추가 금지

# ❌ 관찰 불가능한 LLM 호출
response = llm.invoke(prompt)  # 로깅 없는 직접 호출 금지

# ✅ 올바른 패턴
from src.models.adapter import ModelAdapter
adapter = ModelAdapter.from_config()  # 설정에서 로드
response = await adapter.chat(messages)  # 자동 로깅 포함
```

---

## 7. 버전 관리 규칙

```
브랜치 전략: main (안정) / feat/* / fix/* / exp/*
커밋 메시지: Conventional Commits 형식
  feat: 새 기능
  fix: 버그 수정
  refactor: 리팩토링
  docs: 문서
  test: 테스트
  chore: 빌드/설정

PR 기준:
  - 1개 PR = 1개 논리적 변경
  - 모든 테스트 통과 필수
  - ARCHITECTURE.md 변경 시 별도 PR
```
