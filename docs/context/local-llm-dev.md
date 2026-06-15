# Local LLM Dev — Hardware & Model Guide

Gated behind `FEATURE_LOCAL_LLM_DEV=false` in `.env`. When enabled, use this
guide to pick Ollama models that run well on the dev machine.

## Reference hardware

| Component | Spec |
|---|---|
| CPU | 13th Gen Intel i7-13620H (10C/16T, x86_64) |
| RAM | 15 GB total (~10-12 GB available after OS + apps) |
| GPU | Intel UHD Graphics (integrated, no discrete NVIDIA/AMD) |
| Disk | 938 GB NVMe (317 GB free) |

**Key constraint:** CPU-only inference. The integrated Intel GPU is not used by
Ollama for LLM inference without extra SYCL/oneAPI setup. All model inference
hits the CPU.

## Recommended models (CPU-only, ~10 GB usable RAM)

### Tier 1 — Fast & comfortable (1-5 tok/s, low RAM pressure)

| Model | Pull command | Disk | RAM | Best for |
|---|---|---|---|---|
| Llama 3.2 3B | `ollama pull llama3.2:3b` | ~2 GB | ~6 GB | General chat, instruction |
| Gemma 3 4B | `ollama pull gemma3:4b` | ~2.5 GB | ~6 GB | Chat, tool use |
| Phi-3 Mini | `ollama pull phi3:mini` | ~2.5 GB | ~6 GB | Microsoft efficient model |
| Qwen 2.5-Coder 1.5B | `ollama pull qwen2.5-coder:1.5b` | ~1 GB | ~3 GB | Quick code tasks |

### Tier 2 — Good quality, usable speed (3-8 tok/s)

| Model | Pull command | Disk | RAM | Notes |
|---|---|---|---|---|
| Llama 3.2 8B (Q4) | `ollama pull llama3.2:8b` | ~5.5 GB | ~8 GB | Best smart option, fills most RAM |
| Mistral 7B (Q4) | `ollama pull mistral:7b` | ~4.5 GB | ~7 GB | Solid general purpose |
| Qwen 2.5 7B (Q4) | `ollama pull qwen2.5:7b` | ~4.5 GB | ~7 GB | Good coding + chat |

### Tier 3 — Too large for this machine

- `phi4:14b` / `mistral-nemo:12b` — need >12 GB RAM free for acceptable speed

## Integration with Docker Compose

The bundled Ollama containers (`ollama-llm`, `ollama-embed`) are gated behind
the `--profile local-llm` Compose profile:

```bash
docker compose --profile local-llm up -d
```

To pull a recommended model into the container:

```bash
docker exec -it tomorrowland-ollama-llm-1 ollama pull llama3.2:3b
```

## Tips

- Ollama defaults to all CPU cores — your 10C/16T i7 helps
- Monitor RAM with `ollama ps` or `docker stats`
- Start with `llama3.2:3b` — genuinely useful, runs instantly
- For embedding use `qwen3-embedding:8b` (already the project default)
- See `docs/context/search.md` for search/embedding configuration
