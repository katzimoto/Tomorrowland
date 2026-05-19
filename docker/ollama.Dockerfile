FROM ollama/ollama:latest

ARG OLLAMA_MODEL=mistral
ARG EMBEDDING_MODEL=nomic-embed-text

RUN /bin/ollama serve & \
    pid=$! && \
    timeout=60 && \
    until ollama list >/dev/null 2>&1; do \
        sleep 1; timeout=$((timeout - 1)); \
        [ $timeout -gt 0 ] || { kill $pid; exit 1; }; \
    done && \
    ollama pull "$OLLAMA_MODEL" && \
    ollama pull "$EMBEDDING_MODEL" && \
    kill $pid && \
    wait $pid 2>/dev/null || true
