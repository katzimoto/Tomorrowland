# Model Provider Management

## Overview

The model provider system manages LLM and embedding provider connections. It
replaces the previous single-provider env-var configuration (`OLLAMA_URL`,
`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, etc.) with a flexible multi-provider
database-backed registry.

## Concepts

- **Provider**: a connection to an LLM service (Ollama, OpenAI, Anthropic,
  OpenAI-compatible, LiteLLM, llama.cpp, etc.). Each provider has a type, base URL,
  locality, credential, and enabled/disabled state.
- **Model Descriptor**: a specific model served by a provider (e.g., `llama3.2`,
  `gpt-4o`). Each descriptor records the model name, context window, capabilities,
  and enabled/disabled state.
- **Task Default**: maps a task type (`chat`, `utility`, `reranking`, `embedding`,
  etc.) to a provider + optional model descriptor. When no DB row exists, the system
  falls back to env-var configuration for zero-row backward compatibility.

## Supported Provider Types

| Type | Description | Default Port |
|------|-------------|-------------|
| `ollama` | Local Ollama instance | 11434 |
| `openai-compatible` | Any OpenAI-compatible endpoint (vLLM, LM Studio, etc.) | varies |
| `openai` | OpenAI API | — |
| `anthropic` | Anthropic Claude API | — |
| `litellm` | LiteLLM proxy | 4000 |
| `llama-cpp` | llama.cpp HTTP server | 8080 |

## Locality

Each provider has a locality label that determines SSRF validation rules:

| Locality | Meaning | SSRF Rules |
|----------|---------|------------|
| `local` | Runs on this machine (localhost) | No restrictions |
| `self_hosted` | Runs on your own infrastructure | Private IP ranges allowed |
| `external` | Third-party SaaS / cloud API | Private IP ranges rejected |

## Credential Handling

- Credentials (API keys, tokens) are encrypted at rest using the project's
  credential store (`AES-256-GCM`).
- The API **never** returns plaintext stored credentials. Responses include only
  a `credential_set: boolean` flag.
- When updating a provider's credentials, send the new value in `credential_value` or
  send an empty string to clear the stored credential.
- Locally-running providers (Ollama, llama.cpp on localhost) typically do not require
  credentials.

## Default Provider Setup (Air-Gapped / Local)

The simplest local setup requires one Ollama provider:

1. Navigate to **Admin → Model Providers**.
2. Click **Add Provider**.
3. Set name to `Local Ollama`, type to `Ollama`, locality to `Local`.
4. Leave Base URL as `http://localhost:11434` (the default).
5. Leave credential empty.
6. Save.

The system will use the default env-var configuration (`OLLAMA_URL`,
`LLM_PROVIDER`, etc.) for providers not covered by task defaults. To make a
provider the system default, create a task default mapping.

## OpenAI-Compatible Endpoint Setup

1. Add a provider with type `OpenAI Compatible`.
2. Set Base URL to the endpoint (e.g., `http://vllm:8000/v1`).
3. Set locality to `Self-hosted` or `External` as appropriate.
4. Provide an API key if required (or `not-required` for local instances).
5. Save.
6. Click **Discover** to fetch available models from the provider.
7. Add model descriptors for discovered models as needed.

## LiteLLM Setup

1. Add a provider with type `LiteLLM`.
2. Set Base URL to `http://litellm:4000` (or your proxy address).
3. Provide the proxy API key if configured.
4. Set locality appropriately.
5. Save.

## llama.cpp Setup

1. Add a provider with type `llama.cpp`.
2. Set Base URL to `http://localhost:8080` (or your server address).
3. Set locality to `Local` or `Self-hosted`.
4. Save.

## Task Defaults

Task defaults determine which provider handles which kind of task. The following
task types are available:

| Task Type | Used By |
|-----------|---------|
| `chat` | Chat sessions, RAG answer generation |
| `utility` | Simple LLM calls (classification, extraction helpers) |
| `reranking` | Cross-encoder reranking |
| `embedding` | Text embedding generation |
| `classification` | Document/folder classification |
| `extraction` | Document content extraction |

To set a task default:

1. Go to **Admin → Model Providers**.
2. In the **Task Defaults** section, click **Add Task Default**.
3. Select the task type, provider, and optionally a specific model descriptor.
4. Save.

When no task default is set for a task type, the system falls back to env-var
configuration (`LLM_PROVIDER`, `OLLAMA_URL`, `EMBEDDING_API_KEY`, etc.). This
ensures zero-row backward compatibility when migrating from env-var-only setups.

## Reloading

After creating or modifying providers, click the **Reload** button at the top of
the Model Providers page. This reloads the in-process provider registry and
task-default resolver from the database without requiring a service restart.

## Air-Gapped Deployment Expectations

- Ollama is the recommended local default provider.
- All provider connections use HTTP/HTTPS. No external connectivity is required
  when using locally-hosted providers.
- Credential store works without external dependencies.
- For fully air-gapped setups, ensure model files are downloaded and available
  to the Ollama instance before configuring the provider.

## Testing

- Use the **Test** button per provider to verify connectivity.
- Use the **Discover** button to auto-detect available models from the provider.
- Both actions require the provider to be reachable from the API service.
