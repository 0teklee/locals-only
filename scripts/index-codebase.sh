#!/bin/bash
# scripts/index-codebase.sh — 코드베이스 RAG 인덱싱
# 사용: ./scripts/index-codebase.sh /path/to/project

set -e

PROJECT_PATH="${1:-.}"

if [ ! -d "$PROJECT_PATH" ]; then
  echo "Error: directory not found: $PROJECT_PATH"
  exit 1
fi

source .venv/bin/activate 2>/dev/null || true

echo "인덱싱 시작: $PROJECT_PATH"
local-ai index "$PROJECT_PATH"
