# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.
<!-- Compaction cutoff: 2026-06-01. Older Done entries archived to docs/memory/archive/current-state.md. -->

## 2026-06-12 — #539 preview architecture re-planned mail+Office-first (plan ready for implementation)

Status: Active
Source: Claude planning session; `docs/planning/preview-mail-office-first-2026-06.md` (also posted to #539)

New architecture plan for #539 **supersedes the 2026-05-29 PDF-first plan comment** on the issue. Priority correction from owner: Mail (EML/MSG) and Office (DOCX/PPTX/XLSX) are P0; PDF is shared infrastructure delivered last. Key shape: `document_preview_artifacts` table keyed `(document_id, content_sha256)`; manifest API (`GET /preview/{id}/manifest`, opaque-ID artifact endpoint, admin rerender); email rendered synchronously (stdlib parse → sanitized HTML + cid artifacts), Office async via new `preview_render` pipeline job + `preview-worker` (LibreOffice→PDF for DOCX/PPTX into existing pdf.js viewer; XLSX gets per-sheet grid artifacts + SheetViewer, NOT PDF). Attachments reuse existing `document_relationships` child-doc model. Feature branch: `feature/preview-rendering`, 7 slices, S1–S2 = demoable mail wedge.

**Owner decisions resolved 2026-06-12** (recorded in `decisions.md`): (1) `nh3` adopted for preview sanitization; (2) separate `docker/preview-worker.Dockerfile` image carries LibreOffice; (3) all artifact-writing renders (email included) go through the preview worker — API keeps read-only `files_data`. Plan updated accordingly; preview-worker + `preview_render` job type move into S1. **Plan is approved and ready for implementation.**

Gap noted for implementers: tests/fixtures has **zero** mail fixtures (#671 corpus is Office/PDF only) — S1 adds `tests/fixtures/mail/`.

**S1 IMPLEMENTED (2026-06-13, branch `feat/539-s1-preview-manifest` → `feature/preview-rendering`).** Backend EML preview + manifest pipeline:
- Migration `f2a4c6e8b0d2` adds `document_preview_artifacts` (UNIQUE `document_id+content_sha256`); single linear head, downgrade verified.
- New `src/services/preview/`: `manifest.py` (kind/renderer classification), `sanitizer.py` (nh3 allowlist; `*`-key empty-set override needed to drop nh3's default title/lang attrs — the #623 breakout vector), `email_renderer.py` (stdlib `email` MIME-tree parse — NOT the text-flattening `EmlExtractor`; cid→data: embedding, remote-image blocking+count, quoted-range heuristics), `artifact_store.py` (files_root/previews, traversal-guarded), `artifact_repository.py`, `render.py` (orchestrator — render failures are terminal artifact states, never raised; infra errors raise).
- `preview_worker.py` (queue `document.preview.requested`, health 8088) + `publish_preview` + topology in `shared/rabbit.py`. API never writes artifacts (read-only mount honored); manifest endpoint enqueues the job, worker renders.
- Router `preview_manifest.py`: `GET /preview/{id}/manifest` (pending→ready lifecycle; pdf/image/text ready-immediate, Office text-fallback), `GET …/artifact/{artifact_id}` (opaque-ID, CSP+nosniff on HTML), `POST /admin/preview/{id}/rerender`.
- **Reusable discovery**: `DocumentRelationshipRepository.get_child_relationships()` is NEW — `get_relationships()` hardcodes `path_in_parent=None` (and even the existing `PreviewResponse.relationships` always carries null path). Use the new method when you need attachment→child filename matching.
- Config: `ENABLE_PREVIEW_RENDER` + `PREVIEW_MAX_*`. Dep: `nh3`. Compose: `preview-worker` in both files + airgap validator. Fixtures: `tests/fixtures/mail/*.eml` (incl. `malicious.eml` XSS corpus).
- Verified: ruff, mypy --strict (194 files), 32 unit + 13 integration preview tests, pipeline/relationship/rabbit regressions, migration round-trip, mkdocs --strict.
- **S1 merged to `feature/preview-rendering`** (PR #737, squash `bb9910a`).

**S2 IMPLEMENTED (2026-06-13, branch `feat/539-s2-email-viewer`).** Frontend EML viewer + manifest dispatch:
- `frontend/src/api/preview.ts`: `PreviewManifest` types, `getPreviewManifest`, `getPreviewArtifactText` (raw-text fetch), `usePreviewManifest` (polls while pending/running using `retry_after_ms`). Added `api.getText` to `client.ts` (refactored shared `buildHeaders`) — needed because iframes can't send the Bearer header, so HTML artifacts load via fetch→`srcdoc`.
- `renderers/EmailViewer.tsx`: header card, HTML body in `sandbox=""` iframe (srcdoc), Formatted/Text toggle, collapsible quoted ranges, blocked-images notice, attachment links to child docs. Search forces text view + highlights text body (HTML iframe is unreachable). `renderers/EmailManifestPreview.tsx`: dispatch wrapper — ready/partial→EmailViewer, pending/running→"Preparing…", failed/error/disabled→legacy EmailPreview fallback.
- `ParentContextBanner.tsx` in DocumentPage (above PreviewPane) — links attachment docs back to parent email via existing `preview.relationships`.
- PreviewPane email branch: default/original mode→EmailManifestPreview; extracted/translation already handled by the top text block (so the email branch is default-mode only). `EmailPreview` now only used as the fallback inside EmailManifestPreview.
- i18n `preview.*` in en + he. Verified: typecheck, lint (0 errors; 4 pre-existing TextPreview warnings), 310 frontend tests pass (15 new across EmailViewer/EmailManifestPreview/ParentContextBanner).
- **S2 merged to `feature/preview-rendering`** (PR #739, squash `563113c`).

**S3 IMPLEMENTED (2026-06-13, branch `feat/539-s3-msg`).** Outlook MSG preview, backend-only:
- `preview/email_common.py` NEW: shared `RenderedEmail`, `detect_quoted_ranges`, `cid_to_data_uri`, `assemble_email_manifest` — factored out of `email_renderer.py` so EML and MSG emit identical manifest shapes. `email_renderer` re-exports `detect_quoted_ranges`/`RenderedEmail` for back-compat (its tests import them).
- `preview/msg_renderer.py` NEW: `render_msg(path)` via `extract_msg` (core dep). Partitions attachments into cid inline-images (embedded as data URIs) vs regular; htmlBody→nh3 sanitize; RTF-only→plain-text fallback. `render.py` dispatches MSG vs EML by mime; `manifest.RENDERED_EMAIL_MIMES` now includes `application/vnd.ms-outlook`.
- **No frontend change**: MSG manifests are `kind:"email"`; PreviewPane already routes `application/vnd.ms-outlook` to EmailManifestPreview/EmailViewer.
- **No `.msg` binary fixture** (can't generate offline) — MSG tested by mocking `extract_msg.Message`, the repo's established pattern (see `test_extraction_msg.py`). 5 unit + 1 integration test.
- RTF-only-body → HTML conversion is tracked in **#740**. Verified: ruff, mypy --strict (196 files), preview suite (48 tests) + EML tests survive the refactor.
- **S3 merged to `feature/preview-rendering`** (PR #741, squash `3e0c483`).

**S4 IMPLEMENTED (2026-06-13, branch `feat/539-s4-office-pdf`). Owner approved the airgap image packaging.** Office DOCX/PPTX visual preview:
- `preview/office_pdf.py` NEW: `render_office_pdf(path)` → `soffice --headless --norestore --convert-to pdf` (isolated per-job UserInstallation + HOME, subprocess timeout, page-count via pypdf, cap→partial). `OfficeRenderError(category)` maps to manifest error category (renderer_unavailable / render_timeout / render).
- `manifest.py`: `RENDERED_OFFICE_PDF_MIMES` (= doc+slides mimes, NOT sheets), `worker_renderer(mime)→"email"|"libreoffice_pdf"|None`, `WORKER_RENDERERS`. `render.py` refactored into `_render_email`/`_render_office`/`_persist_render_failure`; dispatches by renderer. Manifest endpoint + `_kind_for_renderer` generalized off hardcoded "email".
- Config: `preview_render_timeout_seconds`, `preview_max_pages`.
- **Image/packaging**: `docker/preview-worker.Dockerfile` (FROM backend image + libreoffice-{writer,impress,calc}-nogui + fonts-liberation/dejavu). Compose `preview-worker` now builds from it (`TOMORROWLAND_PREVIEW_WORKER_IMAGE`, 2cpu/1g). `build-release-artifact.sh` builds+bundles the image; `.env.airgap.example` rewrite + validator already assert the service.
- **Frontend**: `PdfViewer` gains optional `src` prop (defaults to `/api/download/{id}`; office passes `/api/preview/{id}/artifact/converted-pdf` — same auth mechanism as download). `OfficeManifestPreview` NEW dispatch wrapper (ready→PdfViewer, pending→preparing, failed/disabled/non-pdf→fallback). PreviewPane DOCX/PPTX branches (default/original mode) route through it with TextPreview/SlidesPreview as fallback; extracted/translation modes still hit the top text block.
- XLSX/sheets still report ready-immediate text fallback (renderer "text") — sheet grids are S5.
- Verified: ruff, mypy --strict (197 files), backend preview suite (unit+integration incl. office success/timeout-missing-binary/partial paths), 316 frontend tests (11 new: OfficeManifestPreview ×6, updated PreviewPane dispatch), typecheck, lint 0 errors, airgap compose renders. **Next: S5 (XLSX sheet grids + SheetViewer) then S6 (admin diagnostics/rerender UI).**

## 2026-06-08 — docs: documentation overhaul — MkDocs wiki, archives, documentation policy

Status: Active
Source: feature/documentation-wiki branch, PR #647

Complete documentation modernization. MkDocs Material wiki with 7-section nav, 6 auto-generated API Reference pages (mkdocstrings), and CI enforcement via `mkdocs build --strict` job in `.github/workflows/docs.yml`. 65+ historical docs archived to `archive/` (implementation plans, agent missions, superseded designs). `docs/` reduced from 121 to 56 curated files.

**Documentation policy:** Every new feature must be documented. Change-type → docs mapping in `docs/agents/documenting-features.md`. Enforced via coding-behavior.md rule #6, AGENTS.md Pre-PR checklist item #6, and issue template Documentation section.

**README:** Modernized with badges, emoji feature grid, architecture diagram.

**New deps:** `mkdocs-material>=9.7` + `mkdocstrings[python]>=1.0` in optional-dependencies.dev. `site/` added to `.gitignore`.

**Branch:** PR #647 open targeting `main`. After merge, update this entry to Done.

> Full file list and key invariants in `handoffs.md` 2026-06-08. Durable decisions in `decisions.md` 2026-06-08.

---

## 2026-06-02 — airgap RC deployment-impact audit: health-port bug fixed; NiFi/Kafka drain NOT wired; rest verified

Status: Active
Source: Claude Code session 2026-06-02; worker health-port fix committed + audit + rc6 local packaging build

Deployment-impact audit of the air-gapped RC (no AI bundle / LiteLLM). One real bug fixed, one functional gap found (NiFi ingestion not wired), rest verified good.

**FIXED (committed):** worker health-check port mismatch. `parse/translate/embed/index` worker classes defaulted `health_port=8080` while `docker-compose(.airgap).yml` probes `curl :8081/8082/8083/8084` (intelligence/alert/enrich were already correct at 8085-8087). `main()` never overrides → those 4 workers were permanently **unhealthy** in `docker compose ps` despite running. Set defaults to 8081-8084. ruff+mypy+py_compile clean; no tests pinned the port.

**CORRECTION — Kafka is NOT vestigial (an earlier "remove it" call was WRONG): it is the NiFi ingestion bus. DO NOT remove the `kafka` service.** `kafka_consumer.py` = "Bounded Kafka drain for NiFi event ingestion"; it imports `services.connectors.nifi`; `nifi` is a real `ingestion_sources.type` (and a `SourceType` in `schemas.py`); README + `production-compose.md` describe NiFi→Kafka ingestion.

**REAL GAP (functional; a blocker if this deployment uses NiFi):** the drain is implemented + unit/integration-tested but **never wired into any running process**. `NiFiKafkaDrain` is instantiated nowhere in `src/` (only tests, with a fake `KafkaConsumer` Protocol); there is **no Kafka client dependency** in `pyproject.toml`; the api lifespan starts no drain; no worker `command:` runs it; `settings.kafka_broker` is never read. So a configured `nifi` source lands events in Kafka that **nothing consumes** (silent non-ingestion), while `production-compose.md` falsely claims NiFi ingestion is "release-usable" and "runs in the API container." Wiring it (api background task OR new worker service + add a Kafka client dep + read `kafka_broker` + periodic `drain()` loop + offset commit) is a feature-completion task, not a surgical fix — needs design + user go-ahead. If NiFi is unused here, at minimum correct the production-compose.md claim.

**VERIFIED GOOD (no action — so future agents skip re-checking):** single alembic head (`e5f7g9h1i2j3`, 41 revs) → migrate safe; frontend `client.ts` uses relative `BASE="/api"` and `frontend-nginx.conf` proxies `/api/→api:8000` → remote access works, NO CORS trap (same-origin), and api binding to 127.0.0.1:8000 is fine; backend image has NO USER → runs root → named-volume writes OK (no upload perm bug); backend image installs curl (worker probes) and is debian-slim (bash for mcp probe); operator wrapper `tomorrowland-airgap.sh` up/down/status use `docker compose --env-file .env -f docker-compose.airgap.yml`; validator required_files == build-script packaged files.

**rc6 local build:** full image-inclusive build can't run in this offline env (no network egress; `ollama/ollama:0.5.13` not cached; first-party rebuild needs PyPI/npm). Ran the packaging stage only — `RELEASE_DIST_DIR=dist SKIP_DOCKER_BUILD=1 SPLIT_IMAGE_BUNDLE=0 bash scripts/build-release-artifact.sh v1.0-rc6` → `dist/tomorrowland-release-v1.0-rc6/` (git_commit 1303104; packaged compose carries LLM passthrough + .env LiteLLM block; no model bundle; checksums OK; compose renders). **Image tar is a PLACEHOLDER.** Real build must run on a connected host / CI: `SPLIT_IMAGE_BUNDLE=1 IMAGE_PART_SIZE=1900m bash scripts/build-release-artifact.sh v1.0-rc6` (or the release-artifact workflow), which produces no model bundle by default.

**RESIDUAL LOW RISK:** container health-checks were never exercised in CI (`validate --load-images` loads images but does not boot the stack); qdrant uses a `bash /dev/tcp` probe, meili uses `wget` — fine on their debian/alpine bases but recommend a real first-boot smoke test. See [[project_airgap_compose_parity]].

---

## 2026-06-02 — verified: tag-cut RC ships no Ollama model bundle (workflow + build-script + static proof)

Status: Active
Source: Claude Code session 2026-06-02; commits cc6e203 + static build proof

**Verified the next tag-cut RC excludes the Ollama model-weights bundle** (user goal: ship RC without the local-LLM bundle, run on LiteLLM). Three independent confirmations:
1. `.github/workflows/release-artifact.yml`: the `build-ollama-model-bundle` job is `if: inputs.build_ollama_bundle` (default false); on a `push: tags` event `inputs.*` is empty → job skipped. The `build-artifact` job attaches ONLY `tomorrowland-release-*.tar.gz` + `tomorrowland-images-*.tar.part-*` — never a bundle.
2. `scripts/build-release-artifact.sh`: archive is an explicit allow-list (no `*ollama-bundle*` copied in); model weights live in the `ollama_data` Docker VOLUME, never in an image, so `docker save` of the runtime images cannot capture them. The `ollama/ollama:0.5.13` RUNTIME image stays bundled so the service still starts.
3. Static proof: `RELEASE_DIST_DIR=/tmp SKIP_DOCKER_BUILD=1 SPLIT_IMAGE_BUNDLE=0 bash scripts/build-release-artifact.sh v1.0-rc6` → archive file list clean of bundle/weights/blobs/.gguf; ollama runtime present in manifest.

**Doc follow-up (committed cc6e203):** README-airgap.md + generated README-airgap.txt now state the no-bundle path — external LLM (LiteLLM/openai-compatible via LLM_PROVIDER) OR optional bundle; keyword search + ingest work with no model at all.

**Note:** `validate-airgap-artifact.sh` auto-discovers any stray `tomorrowland-ollama-bundle-*.tar.gz` in the artifact dir or its parent `dist/` and validates it (warning-only, never attached). CI runs on a clean checkout so this is a no-op there; only matters for LOCAL builds where old bundles sit in `dist/`. See [[project_airgap_compose_parity]].

---

## 2026-06-02 — air-gapped LiteLLM / external-LLM enabled (compose passthrough) + RC state

Status: Active
Source: Claude Code session 2026-06-02; working tree (uncommitted)

**Found + fixed (uncommitted working tree):** the air-gapped stack could not be switched to an external local LLM (LiteLLM / OpenAI-compatible) even though the code fully supports it. `Settings` defines `LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` (factory.py → OpenAICompatibleLLMProvider; `litellm`/`openai-compatible`/`openai`/`llama-cpp`) and the embedding factory supports `EMBEDDING_PROVIDER=openai-compatible` + `EMBEDDING_API_KEY`, but **none of those vars were in the `x-app-environment` anchor** of either compose file, so they never reached the containers (proven via `docker compose config`). Default provider stayed hard-pinned to Ollama.

**Fix:** added `LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`/`EMBEDDING_API_KEY` (empty defaults → no behavior change) to BOTH `docker-compose.airgap.yml` and `docker-compose.yml`; documented the LiteLLM path in `.env.airgap.example` + `docs/operations/air-gapped-deployment.md`; softened the "must use EMBEDDING_PROVIDER=ollama" line; CHANGELOG Added entry. Because the pipeline workers (intelligence/enrich/slow) build via `build_llm_provider(settings)` (env factory), setting `LLM_PROVIDER=litellm` now routes api AND all workers. Verified: override flows into every service; compose still renders; validator assertions (meili + 7 workers, no build steps) hold.

**Also fixed:** untracked `scripts/bundle-from-running-ollama.sh` defaulted `COMPOSE_SERVICE=ollama-llm` (a main-compose name) while its default `COMPOSE_FILE=docker-compose.airgap.yml` only has `ollama` → realigned to `ollama`. Script still untracked.

**Release state:** tag `v1.0-rc5` = `8f1b98e` (#621 airgap fix IS included). `[Unreleased]` now holds #622–#625 + this LiteLLM passthrough → a fresh tag (rc6) is needed to ship them. Did NOT tag/build (outward-facing).

**Watch (not changed):** (1) compose defaults vs `.env.airgap.example` drift — `OLLAMA_MODEL` qwen3:4b vs mistral, `EMBEDDING_MODEL`/`EMBEDDING_DIMENSION` qwen3-embedding:8b/4096 vs nomic-embed-text/768 (harmless when operator copies the .env, dangerous dim mismatch only if relying on compose defaults). (2) `embed-worker`/`intelligence-worker` still `depends_on ollama:healthy`; bundled ollama idles (empty=healthy) under LiteLLM so workers still start — acceptable, no profile added (memory warns against touching the ollama service).

See [[project_airgap_compose_parity]].

---

## 2026-06-02 — #625 merged (rebase preserved #624); stale-base pattern now spans 2 author branches

Status: Watch
Source: PR #625 (6b1719c), Claude Code session

**#625** (`fix/pipeline-bugs-15`) was force-pushed onto stale **#623**, re-doing #624's pipeline work *without* its review fixes and conflicting in `parse_worker`/`scheduler`/`slow_worker`. Rebased onto current main and resolved to keep #624 (attachment cycle guard) + only the net-new work (tombstone wiring in `sync_now`, `build_index_cleanup`, scheduler reconnect guard, bare-`except` logging). Also fixed a **no-op intelligence timeout** — `as_completed()` only yields finished futures, so `future.result(timeout=120)` never fired; moved the budget onto `as_completed(futures, timeout=120)` + non-blocking `pool.shutdown(cancel_futures=True)`.

**Broadened Watch:** the *stale-base → force-push → re-do-already-merged-work* pattern (with PR descriptions that undercount files) now spans **both** of this author's branches — `fix/bug-bounty-rounds-1-3` (#622, #623; airgap revert) and `fix/pipeline-bugs-15` (#624 → #625). For any PR from **katzimoto**: diff against current `main` (not the description), confirm it isn't based on a pre-merge commit, and check it doesn't revert prior merged fixes. Airgap specifics in the #622–#624 entry below.

Still open (unverified): ~~the `translate*`/`embed` double-index question — untouched by #625~~ — **resolved 2026-06-12**: confirmed real and unintentional (see Watch resolution in the #622–#624 entry below); fix tracked in #693/#694.

---

## 2026-06-01 — bug-bounty + pipeline hardening merged (#622, #623, #624)

Status: Done — all three squash-merged to main; 2 Watch items below
Source: PRs #622 (d3abd92), #623 (49d7470), #624 (cec926d) — Claude Code review+fix sessions

Three review-and-fix passes merged the same day:
- **#622** bug-bounty rounds 1-3. Review fixes: chat SSE keeps the user message on client disconnect (own txn), `/notifications` pagination wired through the endpoint, SSRF rejects private IPs on *both* DNS resolutions, vault deterministic `ORDER BY`, search seeds URL state once.
- **#623** SQL-safety + sanitizer. `profile_repository._ALLOWED_COLUMNS` whitelist before `UPDATE ... SET` interpolation. Review fix: `preview/service.py` HTML sanitizer now `html.escape`s attribute values + text — the rewrite had attribute-breakout + entity-smuggle XSS; kept dependency-free (no nh3/bleach) for air-gap. Removed orphaned legacy QA UI.
- **#624** 15 ingest→embed pipeline bugs (claim_next double-claim race, consumer_base retry rewrite, attachments as child docs, embed citation metadata). Review fix: async attachment processing has a cycle/depth guard + `has_extractor()` filter.

**Watch:**
- **Recurring airgap revert (branch `fix/bug-bounty-rounds-1-3`, author katzimoto):** re-introduced the Ollama removal in `docker-compose.airgap.yml` (reverting #621) in BOTH #622 and #623 — never in the PR description. Both PRs also omitted their largest changes (#623 silently deleted the QA UI). On any PR from this branch, reset `docker-compose.airgap.yml` + `scripts/{build-release,validate}-airgap*.sh` to main and don't trust its "validation passed" claims against the diff.
- **Double-index — RESOLVED 2026-06-12 (was: unverified):** confirmed real and unintentional. `translation_worker` is dead code (no entrypoint/callers — deletion tracked in #695). The live duplication is `translate_worker.py:102` (early index) + `embed_worker.py:137` (post-embed index), and since `index_worker.py:76,86` publishes intelligence + alert on every index message, enrichment fires **twice** per document with content. Owner decision: enrichment fires once, on the **final** index pass (post-translation), via an `enrich: bool` message flag — translate publishes `enrich=False` (early BM25 availability preserved), embed publishes `enrich=True`. Tracked in #693 (tracker) / #694 (fix), branch `feature/pipeline-correctness`. Plan: `docs/planning/project-review-remediation-2026-06.md`.

---
