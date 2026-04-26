#!/bin/bash
# scripts/setup.sh — 초기 설정
set -e

echo "=== Local AI Agent Setup (White-Box Edition) ==="

# 1. 시스템 패키지
echo "[1/6] 시스템 패키지 설치..."
brew install ollama python@3.12 git 2>/dev/null || true

# 2. Python 가상환경
echo "[2/6] Python 가상환경 생성..."
python3.12 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip -q

pip install \
  "langchain>=0.3" "langchain-ollama>=0.2" "langchain-chroma>=0.1" \
  "langchain-community>=0.3" "chromadb>=0.5" \
  "fastapi>=0.111" "uvicorn[standard]>=0.30" \
  "httpx>=0.27" "pydantic>=2.7" "pyyaml>=6.0" "psutil>=6.0" \
  "typer>=0.12" "rich>=13.7" \
  "python-dotenv>=1.0" \
  "ruff>=0.4" "pytest>=8.2" "pytest-asyncio>=0.23" \
  -q

# CLI 로컬 설치
pip install -e . -q

# 3. Ollama 서비스 시작
echo "[3/6] Ollama 서비스 시작..."
brew services start ollama 2>/dev/null || true
sleep 3

# 4. 모델 다운로드
echo "[4/6] 모델 다운로드 (시간 소요)..."
ollama pull qwen2.5-coder:7b    || echo "  skip: qwen2.5-coder:7b"
ollama pull qwen2.5-coder:3b    || echo "  skip: qwen2.5-coder:3b"
ollama pull qwen2.5-coder:1.5b  || echo "  skip: qwen2.5-coder:1.5b"
ollama pull qwen2.5:7b          || echo "  skip: qwen2.5:7b"
ollama pull gemma3:4b            || echo "  skip: gemma3:4b"
ollama pull nomic-embed-text     || echo "  skip: nomic-embed-text"

# 5. Modelfile 등록
echo "[5/6] Ollama Modelfile 등록..."
ollama create code-assist   -f modelfiles/code-assist.Modelfile   2>/dev/null || true
ollama create chat-assist   -f modelfiles/chat-assistant.Modelfile 2>/dev/null || true
ollama create agent-tools   -f modelfiles/agent-tools.Modelfile   2>/dev/null || true

# 6. 디렉토리 초기화
echo "[6/6] 디렉토리 초기화..."
mkdir -p data/{chroma,logs/context_dumps}

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "CLI 사용:"
echo "  source .venv/bin/activate"
echo "  local-ai chat '안녕하세요'"
echo "  local-ai code '버블소트 구현해줘'"
echo "  local-ai index ."
echo "  local-ai models list"
echo ""
echo "API 서버 (선택적):"
echo "  uvicorn src.api.main:app --reload --port 8080"
