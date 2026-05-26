#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export OLLAMA_MODELS="${OLLAMA_MODELS:-${WORKSPACE_DIR}/tools/ollama/models}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

if [[ ! -d "${OLLAMA_MODELS}/manifests" ]]; then
  echo "Ollama model directory not found: ${OLLAMA_MODELS}" >&2
  exit 1
fi

echo "Starting Ollama with:"
echo "  OLLAMA_MODELS=${OLLAMA_MODELS}"
echo "  OLLAMA_HOST=${OLLAMA_HOST}"
exec ollama serve
