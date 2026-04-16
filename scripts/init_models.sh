#!/bin/sh
# Downloads Ollama models on first startup. Runs once then exits.
set -e

export OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"

echo ">>> Pulling LLM model: ${LLM_MODEL:-mistral}"
ollama pull "${LLM_MODEL:-mistral}"

echo ">>> Pulling embedding model: ${EMBED_MODEL:-nomic-embed-text}"
ollama pull "${EMBED_MODEL:-nomic-embed-text}"

echo ">>> Models ready."
