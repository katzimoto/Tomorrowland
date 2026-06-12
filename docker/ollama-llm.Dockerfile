FROM ollama/ollama:0.5.13

ARG OLLAMA_MODEL=qwen3:4b
ARG OLLAMA_UTILITY_MODEL=qwen3:1.7b
ARG OLLAMA_RERANKER_MODEL=

RUN /bin/ollama serve & \
    pid=$! && \
    timeout=60 && \
    until ollama list >/dev/null 2>&1; do \
        sleep 1; timeout=$((timeout - 1)); \
        [ $timeout -gt 0 ] || { kill $pid; exit 1; }; \
    done && \
    ollama pull "$OLLAMA_MODEL" && \
    { [ -z "$OLLAMA_UTILITY_MODEL" ] || ollama pull "$OLLAMA_UTILITY_MODEL"; } && \
    { [ -z "$OLLAMA_RERANKER_MODEL" ] || ollama pull "$OLLAMA_RERANKER_MODEL"; } && \
    kill $pid && \
    wait $pid 2>/dev/null || true
