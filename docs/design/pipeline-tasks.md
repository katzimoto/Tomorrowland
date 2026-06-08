# Pipeline Tasks: Event-Driven DAGs on Kanban

## Goal

Extend Hermes Kanban with a first-class pipeline task type so the Tomorrowland
crew can express multi-stage workflows — document ingestion, code review
pipelines, research synthesis — as durable, resumable DAGs on the board instead
of ad-hoc `kanban_create` chains or external orchestrators.

## Motivation

### What exists today

**Hermes Kanban** (the Tomorrowland crew's coordination layer) already has the
AND-gate dependency primitive needed for DAG edges:

- `kanban_link(parent_id, child_id)` — a child stays in `todo` until ALL its
  parents reach `done`, then auto-promotes to `ready`.
- `kanban_create(..., parents=[...])` creates a child gated on multiple parents.
- The dispatcher evaluates these gates every tick and promotes when satisfied.

This is sufficient for expressing any DAG — sequential chains, fan-out, fan-in,
and parallel branches — but the ergonomics are entirely manual. An orchestrator
agent must create each stage task individually, wire all the `parents` edges by
hand, and track pipeline-level state in comments or external memory.

**Tomorrowland's document ingestion pipeline** (the motivating use case) is a
7-stage RabbitMQ workflow:

```
ingest → parse → translate → embed → index → intelligence (parallel)
                                               → alert (parallel)
                                               → enrich (on-demand)
```

Each stage runs as a long-lived Docker Compose worker consuming from RabbitMQ
queues. The pipeline is robust (retry tiers, DLQ, metrics) but opaque — an
agent orchestrating document ingestion cannot see which stage a document is in
or recover a stalled pipeline without querying the `pipeline_jobs` DB table
directly, an ops-only surface.

**CrewAI Flows** (the reference pattern from `t_ed5d965a`) provides event-driven
DAGs with `@start()` / `@listen()` decorators, shared state via Pydantic models,
conditional routing, and checkpointing. The pattern is clean; we need the
pattern, not the tool.

### What we need

A pipeline task type that:

1. **Defines a DAG once, instantiates many times.** A pipeline template is
   written once (YAML, JSON, or Python DSL) and instantiated with specific
   inputs (document ID, source ID, etc.).

2. **Uses existing Kanban primitives.** Pipeline stages are regular kanban
   tasks with parent→child links. No new storage engine, no new dispatcher.

3. **Carries pipeline-level state.** The pipeline parent task aggregates
   per-stage status so agents and humans can see pipeline health at a glance.

4. **Handles failure gracefully.** Per-stage retry (existing `failure_limit`),
   stage skip (new `skipped` status), pipeline abort (cascade abort to
   downstream stages), and timeout (per-stage `max_runtime_seconds`).

5. **Supports conditional routing.** Some pipelines branch: if extraction
   succeeds, proceed to chunking; if it detects a non-text file, skip to index
   with metadata only.

6. **Surfaces through the Kanban CLI/tools.** `hermes kanban pipeline create`,
   `kanban_pipeline_create(...)`, `kanban_pipeline_show(...)` — discoverable,
   self-documenting.

## Design

### 1. Pipeline template (definition)

A pipeline template is a YAML file in `.hermes/pipelines/<name>.yaml` (or a
JSON blob in the task body for ad-hoc pipelines). It defines stages, their
dependencies, and optional guards.

```yaml
# .hermes/pipelines/document-ingestion.yaml
name: document-ingestion
description: "Ingest a document: extract text, translate, embed, index, enrich intelligence"
version: 1

# Shared state schema (passed to every stage's context)
state_schema:
  document_id: string       # required at instantiation
  source_id: string         # required at instantiation
  content_text: string?     # populated by parse stage
  translated_text: string?  # populated by translate stage

stages:
  - name: parse
    worker: parser-coder     # kanban profile that executes this stage
    entrypoint: true         # fires when the pipeline starts
    description: "Extract text, detect language, chunk"
    max_attempts: 3
    max_runtime_seconds: 600

  - name: translate
    worker: translator
    after: [parse]           # fires when parse succeeds
    description: "Translate content to target language"
    max_attempts: 2
    max_runtime_seconds: 300
    condition: "metadata.requires_translation == true"  # optional guard

  - name: embed
    worker: embedder
    after: [translate]
    description: "Generate vector embeddings for chunks"
    max_attempts: 2
    max_runtime_seconds: 600

  - name: index
    worker: indexer
    after: [embed]
    description: "Index in Meilisearch and Qdrant"
    max_attempts: 2

  - name: intelligence
    worker: intelligence-worker
    after: [index]
    optional: true           # best-effort: pipeline proceeds even if this fails
    description: "Generate summary, entities, tags"

  - name: alert
    worker: alert-matcher
    after: [index]
    optional: true
    description: "Match against alert rules"

  - name: enrich
    worker: enricher
    after: [intelligence, alert]  # fan-in: fires when BOTH are done (or skipped)
    description: "Re-translate or enrich based on usage patterns"
    condition: "metadata.enrich_requested == true"

pipeline_policy:
  on_stage_failure: retry    # retry | skip | abort
  on_stage_timeout: retry    # retry | skip | abort
  max_pipeline_attempts: 2   # whole-pipeline retry budget
  notify_on_complete: true
  notify_on_failure: true
```

### 2. Pipeline instance (runtime)

When a pipeline is instantiated, the system creates:

1. **A parent kanban task** with `task_type: pipeline` and metadata field
   `pipeline_name: document-ingestion`. This task carries aggregate status.

2. **One child kanban task per stage**, each linked via `kanban_link` to its
   predecessors. The parent→child links form the DAG edges:

   ```
   pipeline_instance (parent, type=pipeline)
     ├── parse (entrypoint, parents=[])
     │   └── translate (after=[parse])
   ```
   
   Actually, the edges are stage→stage using the existing parent→child
   links, not pipeline→stage. The pipeline parent is a separate tracking task
   that every stage links to as an additional parent, so the pipeline can
   observe all stage completions.

**Revised link topology:**

```
pipeline_tracker (type=pipeline, aggregates status)
     │
     ├── stage:parse    (parents=[pipeline_tracker])  ← pipeline_tracker done = all args ready
     ├── stage:translate (parents=[parse])
     ├── stage:embed     (parents=[translate])
     ├── stage:index     (parents=[embed])
     ├── stage:intelligence (parents=[index], optional)
     ├── stage:alert       (parents=[index], optional)
     └── stage:enrich      (parents=[intelligence, alert], optional)
```

Wait — this doesn't work with the current AND-gate semantics. If `parse` and
`translate` are both children of `pipeline_tracker`, they'd both fire at once.
The existing parent→child link is an AND-gate on ALL parents being done.

**Correct approach: stage-to-stage edges are parent→child links.**

```
pipeline_tracker (type=pipeline)   ← holds pipeline state, args, status
     ↑ (each stage also links to tracker as a "pipeline_parent" — metadata, not gate)

stage:parse       parents=[pipeline_tracker]        ← entry: fires when tracker ready
stage:translate   parents=[parse]                   ← sequential
stage:embed       parents=[translate]               ← sequential
stage:index       parents=[embed]                   ← sequential
stage:intelligence parents=[index]                  ← parallel after index
stage:alert       parents=[index]                   ← parallel after index
stage:enrich      parents=[intelligence, alert]     ← fan-in
```

This uses the existing AND-gate exactly as designed:
- `translate` fires when `parse` is done (its only parent)
- `intelligence` and `alert` both fire when `index` is done (they share a parent)
- `enrich` fires when BOTH `intelligence` AND `alert` are done

The `pipeline_tracker` is a special parent: it carries pipeline-level state but
its `done` status is the gate for the entrypoint stage. It transitions to
`done` immediately after creating all child stages (it's a lightweight
bookkeeping task).

### 3. Task shape extension

Existing kanban task fields (from `t_ed5d965a` research and Kanban docs):

| Field | Purpose |
|-------|---------|
| `id` | Task UUID (`t_<hex>`) |
| `title` | Human-readable one-liner |
| `body` | Full task spec — the worker reads this |
| `assignee` | Profile name |
| `status` | triage `/` todo `/` ready `/` running `/` blocked `/` done `/` archived |
| `parents` | IDs — child stays todo until all are done |
| `workspace_kind` | scratch `/` dir:/path `/` worktree |
| `workspace_path` | Absolute path for dir/worktree |
| `tenant` | Optional namespace |
| `priority` | Dispatcher tiebreaker |
| `metadata` | Free-form JSON — **this is where pipeline fields go** |

**New fields in `metadata` for pipeline stages:**

```json
{
  "pipeline_name": "document-ingestion",
  "pipeline_instance_id": "t_a1b2c3d4",
  "stage_name": "parse",
  "stage_index": 0,
  "optional": false,
  "pipeline_args": {
    "document_id": "uuid-here",
    "source_id": "uuid-here"
  }
}
```

**New fields in `metadata` for the pipeline tracker:**

```json
{
  "task_type": "pipeline",
  "pipeline_name": "document-ingestion",
  "pipeline_version": 1,
  "pipeline_status": "running",
  "stages": {
    "parse":        {"task_id": "t_1", "status": "done",     "worker": "parser-coder"},
    "translate":    {"task_id": "t_2", "status": "running",  "worker": "translator"},
    "embed":        {"task_id": "t_3", "status": "ready",    "worker": "embedder"},
    "index":        {"task_id": "t_4", "status": "todo",     "worker": "indexer"},
    "intelligence": {"task_id": "t_5", "status": "todo",     "worker": "intelligence-worker"},
    "alert":        {"task_id": "t_6", "status": "todo",     "worker": "alert-matcher"},
    "enrich":       {"task_id": "t_7", "status": "todo",     "worker": "enricher"}
  },
  "pipeline_args": {
    "document_id": "uuid-here",
    "source_id": "uuid-here"
  }
}
```

**New status value: `skipped`**

When `optional: true` and a stage fails, or when a `condition` evaluates to
false, the stage task is marked `skipped` instead of `done`. The dispatcher
treats `skipped` identically to `done` for parent-gate evaluation — downstream
stages that depend on a skipped stage still fire.

### 4. Trigger mechanism

The trigger mechanism is **the existing Kanban dispatcher's parent-gate
evaluation, extended with condition checking.**

Current behavior:
1. Dispatcher sweeps all `todo` tasks.
2. For each, checks: are ALL parents `done`?
3. If yes → promote to `ready`.
4. If no → stay in `todo`.

Extended behavior for pipeline tasks:
1. Dispatcher sweeps all `todo` tasks.
2. For each, checks: are ALL parents `done` or `skipped`?
3. If yes and task has `condition` in metadata → evaluate condition against
   parent's `metadata` field.
   - If condition passes → promote to `ready`.
   - If condition fails → mark `skipped` (optional stages) or `blocked`
     (required stages, needs human decision).
4. If yes and no condition → promote to `ready`.

**Condition evaluation:**

Conditions are simple boolean expressions referencing the parent task's
`metadata` field. For the initial implementation, support:

```
# Field existence
"metadata.requires_translation == true"
"metadata.content_text != null"

# Numeric comparison
"metadata.chunk_count > 0"
"metadata.confidence >= 0.8"
```

The condition is evaluated against the **union of all parent metadata**
(deduplicated by key, last-write-wins for conflicts). This lets a fan-in stage
like `enrich` access state from both `intelligence` and `alert`.

**What the worker sees:**

When a pipeline stage worker is spawned, its `kanban_show()` context includes:

```
## Pipeline context
Pipeline: document-ingestion (t_pipeline_id)
Stage: embed (3/7)
Args: document_id=uuid, source_id=uuid
Upstream outputs:
  - parse: {content_text: "...", language: "en", chunk_count: 5}
  - translate: {translated_text: "...", target_lang: "es"}
```

This is assembled from the parent tasks' `metadata` fields, so the downstream
worker has full context without querying external systems.

### 5. Failure handling

Three policies, configured per-stage and at the pipeline level:

#### 5a. Retry (default)

The stage task fails, the dispatcher re-spawns it. Governed by:
- `max_attempts` on the stage (default: 3)
- `kanban.failure_limit` on the board (auto-blocks after N consecutive spawn
  failures)
- `max_runtime_seconds` for timeout

This is **entirely the existing Kanban retry mechanism** — no new code paths.

#### 5b. Skip

For `optional: true` stages (intelligence, alert, enrich):
- On failure or condition-false → mark stage `skipped`.
- Downstream stages treat `skipped` as `done` for gate evaluation.
- The pipeline tracker records `status: skipped` for that stage.
- Pipeline continues as if the stage succeeded.

For required stages, skip requires explicit human action (`hermes kanban skip
<t_id> "reason"`). This prevents accidental data loss — you don't want to skip
`parse` without knowing why.

#### 5c. Abort

When a required stage fails fatally (exhausted retries + `on_stage_failure:
abort`) or the operator explicitly aborts the pipeline:
1. Mark the failed stage `dead_letter` (or `blocked` with error).
2. Mark ALL downstream stages (transitive closure of children) as `aborted`.
3. Mark the pipeline tracker `pipeline_status: failed`.
4. Emit a notification (if `notify_on_failure: true`).

New status: `aborted` — final, like `done` but with an error reason. The
dispatcher never promotes aborted tasks.

#### 5d. Pipeline-level retry

The `max_pipeline_attempts` field (default: 1) allows the entire pipeline to be
re-run. When all stages are `done` or `skipped` and at least one failed with
`aborted`, the pipeline tracker can be manually reset:

```bash
hermes kanban pipeline retry t_pipeline_id
```

This resets all `aborted` and `failed` stages back to `todo` (with cleared
attempts), increments the pipeline attempt counter, and re-triggers the
entrypoint.

### 6. Conditional routing

Two mechanisms:

**Condition gates** (described above): A stage fires only if a boolean
condition on upstream metadata evaluates to true. Example:

```yaml
- name: translate
  after: [parse]
  condition: "metadata.requires_translation == true"
```

If the parse stage sets `metadata.requires_translation = false`, the translate
stage is marked `skipped` and the pipeline proceeds to `embed` (which depends
on `translate` — it sees `skipped` as satisfied).

**Router stages**: A stage that explicitly decides which downstream path to
take:

```yaml
- name: classify
  after: [parse]
  worker: classifier
  routes:
    - condition: "metadata.file_type == 'pdf'"
      next: extract-pdf
    - condition: "metadata.file_type == 'image'"
      next: ocr-image
    - default: extract-text
```

The router stage's worker evaluates conditions and sets
`metadata.route_next: "extract-pdf"` in its completion. The dispatcher then
skips non-matching children and promotes only the matching one. Router stages
are an advanced feature for the second phase.

### 7. CLI and tool changes

#### New CLI verbs

```bash
# Pipeline lifecycle
hermes kanban pipeline create <template-name> [--arg key=value ...]
  → Creates pipeline_instance tracker + all stage tasks
  → Returns pipeline instance ID

hermes kanban pipeline show <pipeline_id>
  → Pretty-prints pipeline DAG with stage statuses
  → Like kanban show but pipeline-aware

hermes kanban pipeline retry <pipeline_id>
  → Resets aborted/failed stages to todo

hermes kanban pipeline abort <pipeline_id> [--reason "..."]
  → Aborts all running/todo stages, marks pipeline failed

hermes kanban pipeline list [--status running|failed|done]
  → Lists pipeline instances

# Template management
hermes kanban pipeline template list
  → Lists available pipeline templates

hermes kanban pipeline template show <name>
  → Shows template YAML with description
```

#### New kanban tool calls (for agents)

```python
# Create a pipeline instance from a template
kanban_pipeline_create(
    template_name="document-ingestion",
    args={"document_id": "...", "source_id": "..."},
    board="tomorrowland"
)
# → Returns pipeline instance task ID + stage task IDs

# Show pipeline status (aggregated view)
kanban_pipeline_show(task_id="t_pipeline_instance")
# → Returns the pipeline tracker metadata with all stage statuses

# Abort a pipeline
kanban_pipeline_abort(task_id="t_pipeline_instance", reason="Source deleted")
```

#### New status values

| Status | Meaning | Effect on downstream |
|--------|---------|---------------------|
| `skipped` | Stage intentionally bypassed (optional, condition-false) | Treated as `done` for parent-gate |
| `aborted` | Pipeline aborted — stage will never run | Blocker — downstream stages also aborted |

### 8. Example: document ingestion pipeline end-to-end

**Template:** `.hermes/pipelines/document-ingestion.yaml` (as defined above).

**Instantiation (by an orchestrator agent):**

```python
# Agent calls:
pipeline = kanban_pipeline_create(
    template_name="document-ingestion",
    args={"document_id": "550e8400-e29b-41d4-a716-446655440000",
          "source_id": "660e8400-e29b-41d4-a716-446655440001"},
    board="tomorrowland"
)
# pipeline = {
#   "pipeline_id": "t_pipe_001",
#   "stages": {
#     "parse": "t_stage_001",
#     "translate": "t_stage_002",
#     ...
#   }
# }
```

**What happens on the board:**

```
t_pipe_001  [pipeline] document-ingestion  | status: running
  ├── t_001 [parse]        Extract text     | status: running (assignee: parser-coder)
  ├── t_002 [translate]    Translate        | status: todo    (assignee: translator)
  ├── t_003 [embed]        Embed chunks     | status: todo    (assignee: embedder)
  ├── t_004 [index]        Index document   | status: todo    (assignee: indexer)
  ├── t_005 [intelligence] Gen summary      | status: todo    (assignee: intel-worker) [optional]
  ├── t_006 [alert]        Match alerts     | status: todo    (assignee: alert-matcher) [optional]
  └── t_007 [enrich]       Enrich content   | status: todo    (assignee: enricher)
```

**Execution trace:**

1. `t_001` (parse) is `ready` → dispatcher spawns `parser-coder`.
2. Worker extracts text, sets `metadata.content_text`, `metadata.language`,
   `metadata.requires_translation`, `metadata.chunk_count`.
3. Worker calls `kanban_complete(metadata={...})`.
4. `t_001` → `done`.
5. Dispatcher sweep: `t_002` (translate) parent `t_001` is `done`. Condition
   `metadata.requires_translation == true`? Yes → promote to `ready`.
6. `t_002` dispatched, translator worker translates.
7. `t_002` → `done`.
8. Dispatcher: `t_003` (embed) parent `t_002` is `done` → promote to `ready`.
9. And so on through `t_004` (index).

At step 10, after `t_004` (index) is done:
- `t_005` (intelligence) parent `t_004` done → `ready`. **Optional**: if
  Ollama is down, it exhausts retries → `skipped`.
- `t_006` (alert) parent `t_004` done → `ready`.
- Both run in parallel (dispatcher claims them independently).

At step 11, `t_006` (alert) finishes → `done`. `t_005` exhausted retries →
`skipped`. Both parents of `t_007` (enrich) are now `done` or `skipped`.
Condition check: `metadata.enrich_requested == true`? If the pipeline was
instantiated without enrich → `skipped`. Pipeline completes with `enrich`
bypassed.

**Pipeline tracker updates after each stage:**

The pipeline tracker is a lightweight task that updates its `metadata.stages`
map whenever a child stage transitions. This is done by:

- **Monitor mode**: A separate lightweight watcher process (or the dispatcher
  itself, extended) observes stage completions and updates the tracker.
  
- **Self-reporting mode** (simpler, Phase 1): Each stage worker, upon
  completion, calls `kanban_comment` on the pipeline tracker task with its
  status. The pipeline tracker's body is a running status log. This doesn't
  require dispatcher changes — stages just comment on the tracker.

The pipeline tracker's `pipeline_status` is derived:

```
If all required stages are done → pipeline_status: done
If any required stage is running/todo/ready → pipeline_status: running
If any required stage is aborted → pipeline_status: failed
If all stages are done or skipped → pipeline_status: done
```

### 9. Relationship to existing RabbitMQ pipeline

The Kanban pipeline task type does NOT replace the RabbitMQ pipeline. They
serve different purposes:

| Aspect | RabbitMQ Pipeline | Kanban Pipeline |
|--------|-------------------|-----------------|
| **Engine** | Long-lived worker processes consuming queues | Dispatcher-spawned agent profiles |
| **Purpose** | Production document ingestion at scale | Agent-orchestrated workflows with human-in-the-loop |
| **Latency** | Sub-second for queued jobs | 60s+ (dispatcher tick interval) |
| **Durability** | Message persistence + DLQ | SQLite rows, forever |
| **Human intervention** | Ops-only (dead-letter queue) | First-class (block/unblock/comment) |
| **Use cases** | Ingest 10k documents, continuous sync | Code review pipeline, research synthesis, one-off document processing with decisions |

They can interoperate: a Kanban pipeline stage worker could publish to the
RabbitMQ pipeline via the API (`POST /documents/{id}/sync`), or the RabbitMQ
pipeline could spawn a Kanban pipeline for exception handling (dead-letter →
human review → retry).

### 10. Implementation phases

#### Phase 1: Pipeline templates + manual instantiation (this design)

- [ ] YAML template schema and validation
- [ ] `hermes kanban pipeline create <template>` — creates tracker + stage tasks
- [ ] `hermes kanban pipeline show <id>` — pretty-prints pipeline status
- [ ] `hermes kanban pipeline abort <id>` — cascade abort
- [ ] `skipped` status — treated as done for parent-gate
- [ ] Pipeline tracker self-updating via stage-worker comments
- [ ] `kanban_pipeline_create` / `kanban_pipeline_show` tools for agents

**Files to touch:**
- Kanban CLI: new `pipeline` subcommand group
- Kanban dispatcher: `skipped` as done-equivalent for gate eval
- Pipeline template loader: reads `.hermes/pipelines/*.yaml`
- Kanban tools: add `kanban_pipeline_*` to the toolset

**Does NOT require:**
- New database tables (everything in existing task metadata + links)
- New dispatcher process (existing dispatcher, extended gate eval)
- New worker lifecycle (stages are regular kanban workers)

#### Phase 2: Conditional routing + router stages

- [ ] Condition evaluation in dispatcher gate check
- [ ] `condition` field on pipeline stages
- [ ] Router stages with `routes` definitions
- [ ] Parent metadata union for condition context

#### Phase 3: Pipeline monitoring + retry

- [ ] `max_pipeline_attempts` enforcement
- [ ] `hermes kanban pipeline retry <id>` — reset and rerun
- [ ] Pipeline status aggregation in the Kanban dashboard
- [ ] Pipeline-aware notifications (gateway notifier sends pipeline summaries)

### 11. Design decisions

1. **No new storage.** Pipeline state lives in kanban task metadata and
   parent→child links. This avoids schema migrations and keeps the board as the
   single source of truth.

2. **Stages are regular kanban workers.** A pipeline stage worker is a normal
   Hermes profile dispatched with `kanban_show()` just like any other task. The
   only difference is what's in `metadata`.

3. **Pipeline tracker is a lightweight task, not a worker.** It's a
   bookkeeping row that aggregates stage statuses. It transitions to `done`
   immediately after creating children — its `done` status is the gate for the
   entrypoint stage.

4. **`skipped` is done-equivalent, not a third state.** The dispatcher's
   parent-gate check becomes: "all parents in {done, skipped}" instead of "all
   parents done". This is the smallest possible change to the existing gate
   logic.

5. **Condition evaluation is string-based, not a full expression language.**
   Simple field-existence and equality checks cover 90% of routing needs.
   Complex logic belongs in the worker, not the dispatcher.

6. **Phase 1 does not touch the dispatcher's claim/spawn loop.** Pipeline
   creation is a one-time fan-out of `kanban_create` calls; after that, the
   existing dispatcher handles everything. The only dispatcher change needed is
   `skipped` gate semantics.

### 12. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Pipeline fan-out creates 20+ tasks at once — dispatcher tick delay on large pipelines | Pipeline creation is O(stages) `kanban_create` calls, batched. Future: transaction-aware creation. |
| Stage workers forget to update pipeline tracker | Tracker can be reconstructed from child statuses via `kanban_list`. The `pipeline show` command queries children, not the tracker body. |
| Race condition: stage completes and downstream fires same tick | The dispatcher processes completions and promotions in order within a tick — no race possible. |
| Condition evaluation is too simplistic for real workflows | Phase 2 adds router stages; complex routing moves to the worker, not the dispatcher. |
| Pipeline template drift (template changes while instances are running) | Templates are versioned (`version: 1`). Running instances pin their template version. |

## Acceptance criteria

- [ ] Design doc covers document ingestion pipeline end-to-end as kanban tasks
- [ ] Task shape defined (parent tracker + child stages with metadata)
- [ ] Trigger mechanism uses existing parent→child AND-gate + `skipped` extension
- [ ] Failure handling: retry (existing), skip (new status), abort (new status + cascade)
- [ ] Identifies all CLI changes needed (new `pipeline` subcommand group)
- [ ] Identifies all `kanban_*` tool changes needed (3 new tool calls)
- [ ] Uses existing Hermes primitives (no external tools, no new DB tables)
- [ ] Phase 1 implementation is scoped to <200 lines of new code
- [ ] Concrete enough for backend-coder to implement directly

## References

- [CrewAI Flows — event-driven DAGs](https://docs.crewai.com/concepts/flows)
- [CrewAI Checkpointing](https://docs.crewai.com/concepts/checkpointing)
- [Hermes Kanban — Multi-Agent Board](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)
- [Hermes Kanban Tutorial](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-tutorial)
- [Tomorrowland Pipeline Workers](../operations/pipeline-workers.md)
- Parent research: `t_ed5d965a` — CrewAI/AutoGen/Hermes Kanban comparison
