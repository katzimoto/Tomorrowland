# Model-Provider Runtime (Canonical Boundary)

Status: implemented for #813A/B/E (chat, RAG, utility, reranking selection,
intelligence). Bundled local-model images (#813C) and admin-UI polish (#813D)
are tracked as follow-ups.

## Why

Model/runtime usage in Tomorrowland was fragmented: chat, RAG, utility, and
reranking each did their own `resolver.build_llm_provider(...) or
app.state.llm_provider` dance, and some paths read env values ad hoc. This made
provider precedence, credentials, and air-gap policy hard to reason about and
easy to regress.

The fix is a **single canonical boundary** — `ModelRuntime` — that product code
calls by *purpose/task*. Only the runtime knows provider details, DB/env
precedence, credentials, and air-gap policy.

## The boundary

`src/services/intelligence/runtime.py` — `ModelRuntime`, stored on
`app.state.model_runtime`.

```python
runtime = request.app.state.model_runtime
llm = runtime.get_chat_provider("chat")            # LLMProvider (DB default → env fallback)
model = runtime.effective_model_name("reranking", settings.effective_reranker_model)
res = runtime.resolve_task("source_qa")            # TaskResolution | None
source = runtime.effective_source("chat")          # "db_task_default" | "env_fallback"
runtime.reload()                                   # after admin provider changes
```

It composes the existing foundation rather than replacing it:

- `build_llm_provider(settings)` — env/bundled fallback factory.
- `TaskDefaultResolver` — DB-backed `model_task_defaults`.
- `ProviderRegistry` — runtime provider/adapter scaffold (reloaded together).
- `ModelProviderRepository` / `CredentialStore` — persistence + secrets.

There is **no** second model registry.

## Precedence

Per task/purpose:

```text
DB admin task default  >  env / bundled fallback
```

When no DB task default exists (the common zero-row case), behaviour is
identical to before — env-based deployments remain fully backward compatible.

## Air-gap policy

When `AIR_GAPPED=true`, a DB task default that resolves to an `external`
(cloud/SaaS) provider is **refused**; the task falls back to the local
env/bundled provider. Air-gapped deployments never silently egress to an
external provider. When not air-gapped, external providers configured by an
admin are honoured.

## Purposes

High-value purposes wired through the runtime today:

| Purpose | Consumer |
| --- | --- |
| `chat` | document chat answer generation |
| `utility` | query rewrite / cheap helpers |
| `reranking` | reranker model selection |
| `rag_answer` | agent/researcher RAG answer generation |
| `summarization` | intelligence summary/enrichment trigger |

Existing DB task types (`chat`, `utility`, `reranking`, `embedding`,
`classification`, `extraction`) keep working unchanged. New purposes such as
`rag_answer` / `summarization` resolve to the env fallback until an admin sets a
matching task default — no migration or DB change is required.

## Adding a new AI consumer

1. Pick a purpose string (reuse an existing one where possible).
2. Resolve through the runtime: `app.state.model_runtime.get_chat_provider("<purpose>")`
   (or `effective_model_name` / `resolve_task`).
3. **Do not** construct `OllamaClient`, `OpenAICompatibleLLMProvider`, or call
   `build_llm_provider(...)` directly. The guardrail test
   `tests/unit/test_no_direct_model_construction.py` enforces this; only the
   canonical factory/runtime/adapter modules and process bootstraps are
   allowlisted.

## Follow-ups (deferred from #813)

- **#813C** — bundle small, license-checked local models into a default/airgap
  image variant and seed providers/descriptors/task-defaults on first boot.
- **#813D** — surface effective runtime source, bundled-default badges, health,
  and missing-purpose warnings in `AdminModelProvidersPage`.
- Migrate the pipeline worker entrypoints (`slow_worker`, `enrich_worker`,
  `intelligence_consumer`) to a worker-side `ModelRuntime` (currently
  allowlisted bootstraps).
