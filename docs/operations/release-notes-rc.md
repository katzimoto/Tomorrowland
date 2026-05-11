# Tomorrowland Release Candidate Notes

## Release identity

- Version/tag: `1.0-rc2`.
- Commit SHA: `5685bcc58775e65052bce03c877c1b51855a22a3`.
- Artifacts: platform archive plus default Ollama model bundle from the release workflow or release-manager build.
- Validation: #91 accepted as **Ready with limitations**.
- Branding: technical identifiers still use `tomorrowland`; Tomorrowland visible branding/logo remains optional unless #103/#104 are merged before tagging.

## Included capabilities

This RC includes:

- Air-gapped release artifact support with bundled images and local image loading.
- Air-gapped upgrade flow from #75 with preflight, backup, restore, and upgrade helpers.
- Hebrew/English UI localization from #83. English is default; Hebrew switches the page to RTL.
- NiFi event ingestion from #65 with typed events and DLQ routing semantics.
- Privacy-safe local frontend performance telemetry from #88.
- Large list and lazy panel performance improvements from #86.
- Optional monitoring Compose profile from #64. Prometheus/Grafana are opt-in and not started by default.
- Air-gapped translation language pack from #107 using `tomorrowland/libretranslate:airgap`.
- Default Ollama model bundle delivery path from #115, shipped as a separate release asset for offline Q&A/RAG support.

## Air-gapped install and upgrade

After the release artifacts are copied to the target environment, the target host should not need internet access to start the packaged stack. Images are loaded locally from the platform artifact. The RC2 release ships with a default Ollama model bundle as a separate release asset. Operators should transfer and load this bundle for offline Q&A/RAG support. The main platform can still start without the model, but the default RC2 release package includes the model bundle artifact and validation path.

Upgrade notes:

- Preserve persistent volumes.
- Preserve operator-managed `.env` values.
- Run preflight before upgrade.
- Create a backup before upgrade.
- Load images from the local artifact bundle.
- Verify and load `tomorrowland-ollama-bundle-mistral-<version>.tar.gz` when offline Q&A/RAG/local intelligence is required.
- Run migrations through the documented upgrade flow.
- Validate health/readiness after startup.
- Validate Ollama model availability with `scripts/validate-ollama-model.sh`; use `--smoke-test` for a tiny local generation check.

Warning: never run `docker compose down -v` during upgrade.

Relevant guides:

- `docs/operations/air-gapped-deployment.md`
- `docs/operations/air-gapped-upgrade.md`
- `docs/operations/production-compose.md`


## RC2 Ollama model bundle

Default RC2 release distribution means two release assets by default:

- `tomorrowland-release-<version>.tar.gz` and `.sha256` for the platform, runtime
  images, Compose files, scripts, and docs.
- `tomorrowland-ollama-bundle-mistral-<version>.tar.gz` and `.sha256` for the
  default `OLLAMA_MODEL=mistral` model weights.

The model bundle remains separate from the platform artifact to keep platform
updates smaller and to allow customer-approved replacement models. The bundle
contains Ollama `models/` storage, `model-manifest.json`, `checksums.txt`, and a
bundle README. Release managers must review the manifest fields for requested and
resolved model identity, digest, runtime image/version, blob checksums, model
source, and license/source/attribution metadata. If license verification is
marked `operator_required`, approval is still a release/operator step and the
release should not imply verified redistribution rights.

Missing model bundle behavior is degraded rather than fatal: platform startup,
login, ingestion, search, preview/download, permissions, and translation can
still work, while Q&A/RAG/summaries that call Ollama may fail until the bundle is
loaded and validated.

## Supported translation languages

The bundled offline translation image supports:

```text
en, he, zh, ko, th, ar, fr, ru, es
```

| Code | Language |
|---|---|
| `en` | English |
| `he` | Hebrew |
| `zh` | Chinese Simplified |
| `ko` | Korean |
| `th` | Thai |
| `ar` | Arabic |
| `fr` | French |
| `ru` | Russian |
| `es` | Spanish |

Chinese support means Chinese Simplified (`zh`) only. Chinese Traditional (`zt`) is out of scope for this RC.

Every required non-English language is intended to translate to and from English. Direct non-English-to-non-English translation may use an English pivot.

Unsupported languages may still be indexed, searched, previewed, and downloaded as original text, but they are not officially translated by this RC.

## Connector support matrix

| Connector | Support level | Permission model | Air-gapped notes | Limitations |
|---|---|---|---|---|
| Folder | Supported | Source-level permissions | Uses local files or mounted paths | Operator must provide stable paths. |
| Native SMB | Supported | Source-level permissions | SMB server must be reachable from the deployment network | NTFS ACL sync is deferred. Kerberos/DFS remain limited unless separately configured. |
| Host-mounted SMB via folder | Supported | Source-level permissions | Operator mounts the SMB share on the Docker host | Stable mount paths are required. |
| Confluence/Jira Server/Data Center | Supported/limited | Stored connector configuration plus source grants | Target services must be reachable inside the environment | Native Atlassian permission sync is not claimed in this RC. |
| NiFi event ingestion | Supported with validation caveats | Source-level permissions after normalized ingestion | Kafka/NiFi deployment is operator-owned | Live NiFi/Kafka validation depends on operator environment. |

## Monitoring and telemetry

The monitoring stack is optional. `docker compose up` should not start Prometheus/Grafana by default. Operators can enable the `monitoring` profile explicitly.

Frontend performance telemetry is local-only and intended for release validation of user-perceived performance.

## Validation summary

#91 was completed and accepted for release-flow purposes as **Ready with limitations**.

Carry-forward validation facts:

- Base commit: `5685bcc58775e65052bce03c877c1b51855a22a3`.
- #79/#100 NTFS ACL sync is deferred.
- #107 translation matrix excludes `zt` and includes only `en, he, zh, ko, th, ar, fr, ru, es`.
- Environment-limited checks from #91 remain release caveats and should be reviewed before cutting the RC tag/artifact.

## Known limitations

- #91 is **Ready with limitations**; final artifact validation should still be performed on a Docker-enabled build host and representative target host.
- The bundled translation image/model pack should be verified in a connected build environment and then validated against a running service with `scripts/validate-translation-languages.sh`.
- The default Ollama model bundle should be built on a connected release host with `OLLAMA_MODEL=mistral bash scripts/build-ollama-model-bundle.sh 1.0-rc2`, checksum-verified, and validated after loading with `scripts/validate-ollama-model.sh --smoke-test`.
- Chinese Traditional (`zt`) is not supported in this RC.
- Direct non-English translation pairs may pivot through English, which can reduce translation quality.
- Translation worker architecture remains a follow-up area tracked by #110.
- NTFS ACL sync for SMB is deferred; SMB access uses source-level permissions.
- Elasticsearch/Qdrant backup/restore may remain operator-guided where full snapshots are not automated.
- Live NiFi/Kafka validation depends on the operator environment.
- Native Hebrew copy review is recommended if not already completed before tagging.
- Optional open polish PRs are not part of the RC unless deliberately merged before tagging.

## Deferred follow-ups

- #79 — NTFS ACL permission sync for SMB sources.
- #110 — Improve translation worker architecture.
- #111 — Evaluate SQLModel for bounded backend models and agent guidance.
- #103/#104 — Tomorrowland visible branding and logo follow-up if not merged.
- #84/#97 — Frontend perceived performance polish if not merged.
- #85/#98 — Search keyboard workflow / quick preview if not merged.
- #87/#99 — Admin source sync usability polish if not merged.
- #58 — Legacy Office format extraction if still deferred.
- #63 — Structured logs and tracing hooks.

## Remaining human release decisions

Before cutting the RC tag, decide:

- platform artifact name/checksum and model bundle artifact name/checksum after release workflow output
- whether optional open PRs #104, #97, #98, and #99 are excluded or promoted
- whether the generated Tomorrowland logo is included now or left as a post-RC nice-to-have
- final approval to cut the RC tag
