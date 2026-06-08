# LiteLLM Provider Gateway

Drop-in provider gateway that gives the Tomorrowland crew automatic fallback
across three LLM tiers with rate limiting and spend tracking.

## Why

All 10 crew profiles use `opencode-go/deepseek-v4-pro` via OpenRouter. When
OpenRouter hits its free-model daily cap, every Kanban worker crashes with HTTP
429 errors — losing task progress and wasting context windows.

The LiteLLM proxy sits in front of the crew's LLM calls and automatically
falls back through a chain of providers so no single outage takes down the crew.

## Architecture

```
Crew profiles (Hermes agents)
        │
        ▼
  LiteLLM Gateway  (port 4000, OpenAI-compatible)
        │
        ├── Primary:   OpenRouter (opencode-go/deepseek-v4-pro)
        ├── Secondary: OpenRouter (deepseek/deepseek-chat, paid)
        └── Tertiary:  Local Ollama (qwen3:4b, no API limits)
```

The gateway presents a single model name (`deepseek-v4-pro`) and routes
requests through the fallback chain automatically. Crew profiles don't need
to know which provider is serving their request.

## Quick Start

### 1. Set environment variables

Add these to your `.env` file:

```bash
# LiteLLM master key — generate with: openssl rand -hex 32
LITELLM_MASTER_KEY=your-generated-hex-key

# OpenRouter API key — required for primary and secondary tiers
OPENROUTER_API_KEY=sk-or-v1-your-key

# Optional: Postgres URL for spend tracking (creates a separate DB)
# LITELLM_DATABASE_URL=postgresql://postgres:changeme@postgres:5432/litellm

# Optional: Redis connection (defaults to Tomorrowland's Redis)
# LITELLM_REDIS_HOST=redis
# LITELLM_REDIS_PORT=6379

# Optional: custom port
# LITELLM_PORT=4000
```

### 2. Start the gateway

```bash
# Start alongside the existing stack
docker compose -f docker-compose.yml -f docker-compose.litellm.yml up -d litellm

# Or start the full stack including LiteLLM
docker compose -f docker-compose.yml -f docker-compose.litellm.yml up -d
```

### 3. Verify

```bash
# Health check
curl http://127.0.0.1:4000/health

# Test chat completion
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-pro",
    "messages": [{"role": "user", "content": "Hello, are you working?"}]
  }' | python3 -m json.tool
```

## Crew Profile Configuration

### Option A: Environment variables (recommended for Docker workers)

Set these env vars on each crew profile that uses the gateway:

```bash
# Point the API at the LiteLLM gateway
LLM_PROVIDER=litellm
LLM_BASE_URL=http://localhost:4000
LLM_MODEL=deepseek-v4-pro
LLM_API_KEY=<LITELLM_MASTER_KEY>
```

Add to each profile's `~/.hermes/profiles/<name>/.env`:

```bash
cat >> ~/.hermes/profiles/chief/.env <<'EOF'
HERMES_PROVIDER=openai_compatible
OPENAI_BASE_URL=http://localhost:4000/v1
OPENAI_API_KEY=<LITELLM_MASTER_KEY>
OPENAI_MODEL=deepseek-v4-pro
EOF
```

### Option B: Tomorrowland's LLM_PROVIDER env vars

The Tomorrowland backend already supports `LLM_PROVIDER=litellm` with
`LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`. Set these in `.env` to
route all Tomorrowland pipeline workers through the gateway too:

```bash
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=http://litellm:4000/v1
LLM_MODEL=deepseek-v4-pro
LLM_API_KEY=<LITELLM_MASTER_KEY>
```

### Option C: Single config change (profile config.yaml)

For each crew profile, edit `~/.hermes/profiles/<name>/config.yaml`:

```yaml
model:
  provider: openai_compatible
  model: deepseek-v4-pro
  base_url: http://localhost:4000/v1
  api_key: <LITELLM_MASTER_KEY>
```

When crew profiles share the same `LITELLM_MASTER_KEY` as their API key,
LiteLLM tracks per-key usage for budget alerts and rate limiting.

## Fallback Chain

Defined in `docker/litellm/config.yaml`:

| Tier      | Provider            | Model                          | RPM  | TPM     |
|-----------|---------------------|--------------------------------|------|---------|
| Primary   | OpenRouter          | opencode-go/deepseek-v4-pro    | 120  | 500,000 |
| Secondary | OpenRouter (paid)   | deepseek/deepseek-chat         | 60   | 300,000 |
| Tertiary  | Local Ollama        | qwen3:4b                       | 30   | 100,000 |

**How fallback works:**

1. Request arrives at the gateway for model `deepseek-v4-pro`.
2. LiteLLM's router picks the primary deployment (OpenRouter free tier).
3. If the primary returns 429 (rate limited), 5xx, or times out:
   - LiteLLM cools down the primary for 30 seconds.
   - The request retries on the secondary (OpenRouter paid tier).
4. If the secondary also fails:
   - LiteLLM cools it down.
   - The request retries on the tertiary (local Ollama, always available).
5. After the cooldown period, primary is retried first again.

The "usage-based-routing" strategy spreads load across deployments based on
current RPM/TPM usage, so the tertiary (Ollama) naturally picks up traffic
when OpenRouter is exhausted.

## Rate Limiting

- **Global:** 20 max parallel requests across all users.
- **Per-user:** 5 max parallel requests (overridable per virtual key).
- **Per-deployment RPM/TPM:** limits in `model_list` prevent any single
  deployment from being overwhelmed.
- **Redis-backed:** rate limit counters are shared across all gateway
  instances via Redis (the same Redis instance Tomorrowland uses for
  caching).

## Spend Tracking & Budget Alerts

### Enable spend tracking

Uncomment and set `daily_budget` in `docker/litellm/config.yaml`:

```yaml
litellm_settings:
  daily_budget: 10.0   # USD per day across all users
  budget_duration: 1d
```

### View spend dashboard

The LiteLLM admin UI is available at `http://127.0.0.1:4000/ui` when
`LITELLM_MASTER_KEY` is set. Log in with the master key.

### Set up Slack alerts

Add to `docker/litellm/config.yaml`:

```yaml
general_settings:
  alerting: ["slack"]
  alerting_threshold: 300
litellm_settings:
  alerting_args:
    slack_webhook_url: os.environ/SLACK_WEBHOOK_URL
```

Then set `SLACK_WEBHOOK_URL` in `.env`.

## Virtual Keys (per-crew access)

To give each crew profile its own API key with individual rate limits and
budget tracking, create virtual keys through the LiteLLM admin API:

```bash
# Create a virtual key for the chief profile
curl -s http://127.0.0.1:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "models": ["deepseek-v4-pro"],
    "rpm_limit": 20,
    "tpm_limit": 100000,
    "max_budget": 2.0,
    "budget_duration": "1d",
    "metadata": {"profile": "chief"}
  }'

# List all keys
curl -s http://127.0.0.1:4000/key/list \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

Each crew profile then uses its own virtual key as `LLM_API_KEY`.

## Troubleshooting

### Gateway won't start

```bash
# Check logs
docker compose -f docker-compose.yml -f docker-compose.litellm.yml logs litellm

# Common issues:
# - LITELLM_MASTER_KEY not set → the proxy refuses to start
# - OPENROUTER_API_KEY not set → OpenRouter deployments fail (Ollama still works)
# - Redis not healthy → rate limiting degrades to in-memory
```

### Test fallback manually

```bash
# Generate a lot of requests to trigger rate limiting on primary
for i in $(seq 1 50); do
  curl -s http://127.0.0.1:4000/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"deepseek-v4-pro","messages":[{"role":"user","content":"ping"}],"max_tokens":10}' &
done
wait

# Check which deployment served each request in the logs
docker compose -f docker-compose.yml -f docker-compose.litellm.yml logs litellm | grep "model="
```

### View current cooldown state

```bash
curl -s http://127.0.0.1:4000/health \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | python3 -m json.tool
```

## Files

| File                          | Purpose                              |
|-------------------------------|--------------------------------------|
| `docker-compose.litellm.yml`  | Docker Compose service definition    |
| `docker/litellm/config.yaml`  | Proxy config with fallback chain     |
| `docs/infra/litellm-gateway.md` | This document                      |

## References

- [LiteLLM Proxy Docs](https://docs.litellm.ai/docs/proxy/docker_quick_start)
- [Fallbacks & Load Balancing](https://docs.litellm.ai/docs/routing#fallbacks)
- [Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys)
- [Budget & Rate Limits](https://docs.litellm.ai/docs/proxy/rate_limit)
