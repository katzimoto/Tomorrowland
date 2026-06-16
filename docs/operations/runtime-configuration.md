# Runtime Configuration (Admin UI)

Tomorrowland exposes a curated, admin-only surface for inspecting and overriding
selected environment-backed settings without shell access. It lives at
`/admin/config` in the UI and `/admin/runtime-config` in the API.

The goal is operability **without** weakening air-gapped safety, secret hygiene,
validation, or auditability. It deliberately does **not** expose every raw
environment variable.

## Configuration registry

The set of manageable settings is declared in
`src/services/api/config_registry.py` as a typed registry derived from
`shared.config.Settings`. Each entry carries metadata:

- `key`, `category`, `display_name`, `description`, `type`
  (`string | int | float | bool | enum | json | secret`)
- `is_secret`, `is_sensitive`, `is_runtime_editable`
- `requires_restart`, `requires_worker_restart`, `requires_reindex`,
  `requires_resync`
- validation rules (`enum_values`, `min_value`, `max_value`)

Categories include general/deployment, authentication/LDAP, extraction, preview,
search/reranker/embeddings, RAG/chat, translation/QE, worker/queue, observability,
model providers/LLM runtime, and air-gapped runtime.

## Precedence

The effective value of a setting is resolved with this explicit, tested order:

```text
deployment-locked env  >  database override  >  env value  >  application default
```

A setting that is **not** `is_runtime_editable` is treated as deployment-locked:
its effective value always comes from the process environment / application
default and cannot be overridden through the API. For runtime-editable settings,
a database override (stored in `admin_runtime_config_overrides`) takes precedence
over the env/default value.

!!! note "Restart semantics"
    Most settings are read at process startup. Each entry truthfully reports
    whether a stored override needs an API restart, worker restart, reindex, or
    resync to take effect. The UI surfaces this as a warning. Saving an override
    never silently pretends a value is live when it is not.

## API

All endpoints are admin-only.

| Method & path | Purpose |
| --- | --- |
| `GET /admin/runtime-config` | List all settings (grouped, with metadata and precedence). |
| `GET /admin/runtime-config/{key}` | Inspect a single setting. |
| `PATCH /admin/runtime-config/{key}` | Set a validated override for a runtime-editable setting. |
| `DELETE /admin/runtime-config/{key}` | Remove an override (reset to default). |
| `POST /admin/runtime-config/validate` | Validate a proposed value without saving. |
| `POST /admin/runtime-config/reload` | Invalidate cached config so DB-backed values are re-read. |
| `GET /admin/runtime-config/audit` | Recent runtime-config change audit entries. |

## Secret handling

Secrets are always read-only in this surface. The API returns only whether a
secret is configured plus a redacted placeholder — never the raw value. Secret
values are not logged, not written to audit details, and no new plaintext secrets
are stored by this feature. Provider credentials continue to use the encrypted
credential store.

## Safety

- Admin-only endpoints and UI; non-admins are denied.
- Unknown keys fail closed (`404`).
- `PATCH` rejects non-editable settings, secrets, and type/range/enum violations
  (`422`).
- Every change writes an `audit_log` event (`resource_type = runtime_config`)
  without raw values.
