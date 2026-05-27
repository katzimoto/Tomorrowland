FROM ollama/ollama:latest

ARG EMBEDDING_MODEL=qwen3-embedding:8b

RUN /bin/ollama serve & \
    pid=$! && \
    timeout=60 && \
    until ollama list >/dev/null 2>&1; do \
        sleep 1; timeout=$((timeout - 1)); \
        [ $timeout -gt 0 ] || { kill $pid; exit 1; }; \
    done && \
    ollama pull "$EMBEDDING_MODEL" && \
    kill $pid && \
    wait $pid 2>/dev/null || true
