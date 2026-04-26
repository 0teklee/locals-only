# SKILL — 에이전트 기능 카탈로그

> 이 문서는 시스템이 제공하는 모든 기능(스킬)의 명세입니다.
> LLM이 어떤 도구를 사용할 수 있는지 파악하기 위한 레퍼런스입니다.

---

## 도구 분류 체계

```
SKILL
├── FILE    — 파일시스템 읽기/쓰기
├── SHELL   — 쉘 명령 실행
├── GIT     — Git 연산
├── RAG     — 코드베이스 검색
├── MODEL   — 모델 전환/관리
└── SYS     — 시스템 유틸리티
```

---

## FILE 도구

### `read_file`
```
목적  : 파일 내용 읽기
입력  : path (str) — 상대 또는 절대 경로
출력  : 파일 내용 (str), 100KB 초과 시 앞 50KB + 잘림 표시
제약  : 바이너리 파일 지원 안 함
```

### `write_file`
```
목적  : 파일 내용 쓰기 (생성 또는 덮어쓰기)
입력  : path (str), content (str)
출력  : 쓰기 결과 확인 메시지
제약  : 파괴적 작업 — 실행 전 확인 권장
```

### `patch_file`
```
목적  : SEARCH/REPLACE 블록 방식으로 파일 일부 수정
입력  : path (str), search (str), replace (str)
출력  : 변경된 줄 수
제약  : search 문자열이 정확히 1회 존재해야 함
```

### `list_directory`
```
목적  : 디렉토리 내용 열람
입력  : path (str, 기본값="."), pattern (str, glob)
출력  : 파일/디렉토리 목록 (최대 50개)
```

### `find_files`
```
목적  : 패턴으로 파일 탐색
입력  : pattern (str, glob), root (str, 기본값=".")
출력  : 매칭 경로 목록 (최대 100개)
```

---

## SHELL 도구

### `run_command`
```
목적  : 쉘 명령 실행
입력  : command (str), cwd (str, 선택), timeout (int, 초, 기본값=30)
출력  : stdout + stderr, 반환코드
제약  : 허용 명령만 실행 (Rules.md > SHELL_ALLOWLIST 참조)
       대화형 명령(vim, less 등) 사용 불가
       파괴적 명령(rm -rf 등)은 확인 후 실행
```

### `run_python`
```
목적  : Python 스크립트 인라인 실행
입력  : code (str), timeout (int, 초, 기본값=60)
출력  : 실행 결과 (stdout)
제약  : .venv 환경에서 실행, 네트워크 요청 불가
```

---

## GIT 도구

### `git_status`
```
목적  : 현재 git 상태 확인
입력  : repo_path (str, 기본값=".")
출력  : 변경 파일 목록, 브랜치 정보
```

### `git_diff`
```
목적  : 변경사항 diff 조회
입력  : repo_path (str), target (str, 기본값="HEAD")
출력  : unified diff 형식
```

### `git_log`
```
목적  : 커밋 히스토리 조회
입력  : repo_path (str), n (int, 기본값=10)
출력  : 최근 n개 커밋 (hash, author, message)
```

### `git_commit`
```
목적  : 변경사항 커밋
입력  : message (str), files (list[str], 기본값=all staged)
출력  : 커밋 해시
제약  : 파괴적 작업 — 사용자 확인 필요
       --no-verify 사용 금지
```

---

## RAG 도구

### `search_codebase`
```
목적  : 벡터 검색으로 관련 코드 탐색
입력  : query (str), k (int, 기본값=5), collection (str, 기본값="codebase")
출력  : 관련 코드 청크 목록 (파일경로, 내용, 유사도)
```

### `search_docs`
```
목적  : 문서 벡터 검색
입력  : query (str), k (int, 기본값=3), collection (str, 기본값="docs")
출력  : 관련 문서 청크 목록
```

### `index_path`
```
목적  : 경로를 벡터 DB에 인덱싱
입력  : path (str), collection (str), file_patterns (list[str])
출력  : 인덱싱된 청크 수
제약  : 시간 소요 (대용량 코드베이스의 경우 수 분)
```

---

## MODEL 도구

### `list_models`
```
목적  : 로컬에 설치된 Ollama 모델 목록 조회
입력  : 없음
출력  : 모델명, 크기, 수정일 목록
```

### `switch_model`
```
목적  : 활성 모델 전환
입력  : model_name (str) — ollama pull된 모델명
출력  : 전환 완료 메시지, 예상 메모리 사용량
제약  : 모델이 로컬에 존재해야 함 (오프라인 환경)
```

### `get_model_info`
```
목적  : 모델 상세 정보 조회 (컨텍스트 길이, 파라미터 등)
입력  : model_name (str)
출력  : ModelInfo 객체
```

---

## SYS 도구

### `get_token_usage`
```
목적  : 현재 대화의 토큰 사용량 조회
입력  : 없음
출력  : {system, history, rag, input, output, remaining} 토큰 수
```

### `clear_memory`
```
목적  : 대화 히스토리 초기화
입력  : confirm (bool)
출력  : 초기화 완료 메시지
```

### `health_check`
```
목적  : 서비스 상태 확인
입력  : 없음
출력  : Ollama, ChromaDB, WebUI 각 서비스 상태
```

---

## 도구 사용 우선순위

```
1. 먼저 read_file / search_codebase로 현황 파악
2. 수정 전 항상 git_status 확인
3. 파괴적 작업(write, commit, run_command) 전 사용자 확인
4. 검색은 find_files(빠름) → search_codebase(의미 검색) 순으로
5. 쉘 실행은 최후 수단 — run_python 우선 고려
```

---

## 스킬 활성화 설정

`config/tools.yaml`에서 스킬을 선택적으로 활성화:

```yaml
tools:
  file: true
  shell:
    enabled: true
    allowlist: [git, python3, pip, make, npm, cargo]
  git: true
  rag: true
  model: true
  sys: true
```
