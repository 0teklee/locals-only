#!/bin/bash
# scripts/import-gguf.sh — GGUF 모델 직접 등록
# 사용: ./scripts/import-gguf.sh /path/to/model.gguf [model-name]

set -e

GGUF_PATH="$1"
MODEL_NAME="${2:-$(basename "$GGUF_PATH" .gguf)}"

if [ -z "$GGUF_PATH" ]; then
  echo "Usage: $0 /path/to/model.gguf [model-name]"
  exit 1
fi

if [ ! -f "$GGUF_PATH" ]; then
  echo "Error: file not found: $GGUF_PATH"
  exit 1
fi

MODELFILE=$(mktemp)
cat > "$MODELFILE" << EOF
FROM $GGUF_PATH
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
PARAMETER num_predict 2048
EOF

echo "Registering '$MODEL_NAME' from $GGUF_PATH ..."
ollama create "$MODEL_NAME" -f "$MODELFILE"
rm "$MODELFILE"

echo ""
echo "완료. 테스트: ollama run $MODEL_NAME"
echo "CLI 전환:    local-ai models switch $MODEL_NAME"
echo "config 추가: config/models.yaml 의 presets 섹션에 추가하세요."
