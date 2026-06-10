# Parser Router Design (issue #668)

> Status: design / not yet implemented.
> Batch context: #668–#681 (ingestion quality, admin UX, evidence packs).
> Downstream consumers of this design: #669 (layout blocks), #670 (admin parsers UI),
> #674 (source health dashboard).

This document specifies a **parser router**: a layer that selects the best
extractor for each document based on its source and MIME type, runs it (with a
fallback chain), and records which extractor actually produced the content so the
admin UI and health dashboard can surface it.

## Decisions baked into this design

Three forks were resolved before writing (the rest of the doc assumes them):

1. **Policy storage → new `parser_policies` table.** The existing
   `source_profiles.extraction_strategy` is a single enum and there is only one
   active profile per source, so it cannot express ordered fallback chains or
   per-mimetype granularity. A dedicated table keyed by `(source_id, mime_pattern)`
   does, and gives #670 something to CRUD.
2. **Audit trail → new `document_extractions` table.** `document_payloads` is
   strictly one row per document and already overloaded; a row-per-attempt table
   supports #674 aggregation and gives #669 layout blocks a clean FK target.
3. **Naming → keep `Extractor` internally, expose "parser" at the boundary.** The
   codebase is built on `Extractor` / `ExtractorRegistry` / `*Extractor`. We do not
   rename. The DB columns, API responses, and UI use `parser_name`; internally a
   "parser" *is* an `Extractor`. This mapping is stated once and held throughout.

### Other assumptions (noted, not blocking)

- SQLAlchemy **Core** only (`sa.text(...)` + `Connection`), matching every existing
  repository. No ORM models.
- Admin endpoints require admin via `require_admin(user)` and run inside
  `request.app.state.engine.begin()`, matching `admin/source_profiles.py`.
- UUIDs cross the DB boundary via `shared.db.db_uuid` / `to_uuid` (PostgreSQL +
  SQLite test parity), as in `ProfileRepository`.
- The router must be **backward compatible**: documents already ingested have no
  `document_extractions` rows and must keep working (treated as "unknown parser").
- Parser metadata (name/version/quality tier) is *declared by the extractor*, not
  configured externally, so the registry and the policy table never drift from the
  code.

---

## 1. Current state

### 1.1 What parsers exist today and how they're called

Extractors live in `src/services/extraction/`. Each implements a tiny protocol
(`src/services/extraction/base.py`):

```python
class Extractor(Protocol):
    def extract(self, path: Path) -> ExtractionResult: ...
```

`ExtractionResult` is the uniform envelope every extractor returns:

```python
@dataclass
class ExtractionResult:
    text: str
    attachments: list[AttachmentData] = field(default_factory=list)
    location_segments: list[LocationSegment] = field(default_factory=list)
```

Concrete extractors: `PdfExtractor`, `DocxExtractor`, `PptxExtractor`,
`XlsxExtractor`, `XlsExtractor`, `Odt/Ods/OdpExtractor`, `EpubExtractor`,
`HtmlExtractor`, `XmlExtractor`, `JsonExtractor`, `RtfExtractor`, `PlainExtractor`,
`EmlExtractor`, `MsgExtractor`, `Zip/TarExtractor`, plus opt-in `OcrExtractor`,
`LegacyOfficeExtractor`, and `MarkItDownExtractor`. They are **stateless**
instances and expose **no self-describing metadata** (no name, version, or quality
tier) today.

Selection happens in `ExtractorRegistry` (`registry.py`). It is a flat
`dict[str, Extractor]` (one extractor per MIME type) plus:

- an `_ALIASES` map normalising vendor / mislabelled MIME types to a canonical one;
- opt-in registration toggled by `Settings` flags (`enable_ocr`,
  `enable_legacy_office`, `enable_markitdown`);
- a `GenericExtractor` fallback for unregistered types;
- a **sniff-and-retry** heuristic in `extract()`: for `application/zip` /
  `application/octet-stream`, or whenever the first attempt returns empty text, it
  re-sniffs the file (`sniff_office_mime`) and retries with a more specific type.

```python
def get(self, mime_type: str) -> Extractor | None:
    canonical = _ALIASES.get(mime_type, mime_type)
    return self._extractors.get(canonical)
```

So a primitive form of "fallback" already exists, but it is **hardcoded** inside
`extract()` and driven by content sniffing, not by per-source policy.

### 1.2 How extraction fits the pipeline

The parse stage is `ParseConsumer` (`src/services/pipeline/parse_worker.py`),
queue `document.parse.requested`. Its core path:

```python
result = self._extractor.extract(Path(doc.path), doc.mime_type)
content_text = result.text
location_segments = [seg.to_dict() for seg in result.location_segments]
if location_segments:
    self._job_repo.update_extraction_metadata(document_id, location_segments)
self._job_repo.update_content_text(document_id, content_text)
self._job_repo.mark_running_stage(job_id, "parsed")
self._publisher.publish_translate(job_id=..., document_id=..., content_text=content_text)
```

Then it expands email/archive attachments into child documents (cycle/depth
guarded) and enqueues them back through `publish_parse`. Downstream workers
(`translate → embed → index → intelligence → alert`) read `content_text` (and
`extraction_metadata`) from `document_payloads`; the message body itself only
carries `job_id / document_id / source_id / attempt / pipeline_version` plus
optional `content_text` (`DocumentPublisher._publish`).

### 1.3 What's missing

- **No registry of capabilities.** Extractors don't declare name, version,
  supported MIME types, quality tier, OCR requirement, or max file size.
- **No policy.** There is no per-source / per-mimetype way to say "prefer Docling,
  fall back to PyPDF." The only fallback is the global sniff-and-retry heuristic.
- **No audit trail.** Nothing records *which* extractor produced a document's text,
  how long it took, its confidence, or any warnings. `document_payloads.
  extraction_metadata` stores only location segments, not provenance. The admin UI
  (#670) and health dashboard (#674) have nothing to show.

---

## 2. Parser registry

### 2.1 How a parser declares itself

We keep the `Extractor` protocol's `extract()` and add an optional, additive
metadata surface. Existing extractors keep working; a small base mixin supplies
defaults so we don't touch all 20 classes at once.

`src/services/extraction/base.py` (additions):

```python
class QualityTier(StrEnum):
    HIGH = "high"        # layout-aware / structured (Docling, MarkItDown)
    STANDARD = "standard"  # native text extraction (pypdf, python-docx)
    BASIC = "basic"      # best-effort / lossy (striprtf, generic decode)


@dataclass(frozen=True)
class ParserCapabilities:
    """Self-declared metadata for an Extractor. 'parser_name' is the stable key
    used by policies, the audit trail, and the admin API."""

    parser_name: str
    parser_version: str
    supported_mime_types: tuple[str, ...]
    quality_tier: QualityTier = QualityTier.STANDARD
    requires_ocr: bool = False
    max_file_size: int | None = None  # bytes; None = no limit


class Extractor(Protocol):
    def extract(self, path: Path) -> ExtractionResult: ...
    def capabilities(self) -> ParserCapabilities: ...
```

A mixin gives concrete classes a one-liner declaration and keeps the protocol
satisfiable without boilerplate:

```python
class BaseExtractor:
    """Optional base providing capabilities(); concrete extractors set _CAPS."""

    _CAPS: ClassVar[ParserCapabilities]

    def capabilities(self) -> ParserCapabilities:
        return self._CAPS
```

Example on the PDF extractor (`pdf.py`):

```python
class PdfExtractor(BaseExtractor):
    _CAPS = ParserCapabilities(
        parser_name="pypdf",
        parser_version="1.0",
        supported_mime_types=("application/pdf",),
        quality_tier=QualityTier.STANDARD,
        requires_ocr=False,
    )

    def __init__(self, ocr_fallback: bool = False) -> None:
        self._ocr_fallback = ocr_fallback
    # extract() unchanged
```

> Migration note: `capabilities()` is added incrementally. The registry treats any
> extractor lacking it as a synthetic `ParserCapabilities(parser_name=<ClassName>,
> parser_version="0", ...)` so partial rollout never crashes.

### 2.2 How the registry discovers parsers

We **keep explicit, code-based registration** (no import-time auto-discovery
magic) — it matches the current `ExtractorRegistry.__init__` and keeps the
opt-in flags. The only structural change: a MIME type maps to an **ordered list**
of extractors (the fallback chain candidates) instead of a single one.

```python
class ExtractorRegistry:
    def __init__(self, *, enable_ocr=False, enable_legacy_office=False,
                 enable_markitdown=False) -> None:
        self._by_mime: dict[str, list[Extractor]] = {}
        self._by_name: dict[str, Extractor] = {}
        self._fallback = GenericExtractor()

        self._register("application/pdf", PdfExtractor(ocr_fallback=enable_ocr))
        self._register(_DOCX_MIME, DocxExtractor())
        # ... existing registrations, _ALIASES, opt-in toggles unchanged ...

    def _register(self, mime_type: str, extractor: Extractor) -> None:
        self._by_mime.setdefault(mime_type, []).append(extractor)
        self._by_name[extractor.capabilities().parser_name] = extractor
```

`enable_markitdown` already wraps OOXML extractors; under the new model it simply
inserts the higher-tier `MarkItDownExtractor` ahead of the standard one in the
list, which is exactly what a quality-ordered chain wants.

### 2.3 Registry API

```python
def register(self, mime_type: str, extractor: Extractor) -> None: ...
    # append to the chain for mime_type (and index by name)

def get(self, mime_type: str) -> Extractor | None: ...
    # FIRST extractor for the canonical mime (back-compat with today's callers)

def get_by_name(self, parser_name: str) -> Extractor | None: ...
    # used by the router to resolve a policy's named parser

def candidates(self, mime_type: str) -> list[Extractor]: ...
    # full chain for a canonical mime, quality_tier-ordered

def list(self) -> list[ParserCapabilities]: ...
    # distinct capabilities of every registered parser (for GET /admin/parsers)

def capabilities(self, parser_name: str) -> ParserCapabilities | None: ...
```

`get()`, `has_extractor()`, `_ALIASES`, and the existing `extract()` keep working
unchanged so `ParseConsumer`'s current callers are not broken during rollout.

### 2.4 Metadata each parser exposes

| Field | Type | Meaning |
|-------|------|---------|
| `parser_name` | str | Stable key used by policies, audit rows, API. Unique. |
| `parser_version` | str | Bumped when extraction behaviour changes (for re-parse decisions). |
| `supported_mime_types` | tuple[str] | Canonical MIME types this parser handles. |
| `quality_tier` | enum | `high` / `standard` / `basic` — orders the default chain. |
| `requires_ocr` | bool | True if it needs OCR deps (skipped when OCR disabled). |
| `max_file_size` | int \| None | Skip/abort threshold in bytes; None = unbounded. |

---

## 3. Strategy policies

### 3.1 Policy model

A **policy** answers: "for documents from *this source* with *this MIME type*,
which parsers do we try, in what order?" It is `(source_id, mime_pattern) → ordered
list of parser_names`, with optional per-policy options.

- `source_id` nullable: `NULL` = applies to all sources (global default).
- `mime_pattern`: an exact MIME (`application/pdf`) or a prefix glob
  (`image/*`, `*` = any). Most specific wins.
- `parser_chain`: ordered JSON array of `parser_name`s. The router tries each in
  order until one returns non-empty text (or the chain is exhausted).
- `options`: JSON for knobs (e.g. `{"max_file_size_mb": 200}`); reserved, not
  required for v1.

Worked example from the issue — "For PDFs from SharePoint, try Docling first, fall
back to PyPDF, never use striprtf":

```json
{
  "source_id": "8f3c...sharepoint",
  "mime_pattern": "application/pdf",
  "parser_chain": ["docling", "pypdf"],
  "options": {}
}
```

`striprtf` (the RTF parser) is simply absent from the chain and never selected for
PDFs, so "never use striprtf" needs no negative rule.

### 3.2 Storage — `parser_policies` table

```python
# migrations/versions/<rev>_add_parser_policies_table.py
def upgrade() -> None:
    op.create_table(
        "parser_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=True,  # NULL = global default policy
        ),
        sa.Column("mime_pattern", sa.Text(), nullable=False),
        # ordered list of parser_name strings, e.g. ["docling","pypdf"]
        sa.Column("parser_chain", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    # At most one policy per (source, mime_pattern). NULL source_id rows are the
    # global defaults; a partial unique index keeps them unique too.
    op.create_index(
        "uq_parser_policies_source_mime",
        "parser_policies",
        ["source_id", "mime_pattern"],
        unique=True,
    )
    op.create_index("ix_parser_policies_source_id", "parser_policies", ["source_id"])
```

> `sa.JSON()` is the project convention (see `source_profiles.config`). On
> PostgreSQL it maps to `json`; on the SQLite test harness it round-trips via the
> JSON serializer. The repository still `json.dumps`/`json.loads` defensively, as
> `ProfileRepository` does, because driver behaviour differs (see memory:
> `feedback_bulk_rename_migrations` era PG-only bugs).

### 3.3 Evaluation order

`ParserPolicyResolver` picks the chain for a `(source_id, mime_type)` pair:

1. Canonicalise the MIME via the registry's `_ALIASES`.
2. Look for an **exact** `(source_id, mime)` policy.
3. Else a **source-specific glob** policy (`image/*`, then `*`), most specific
   first, ties broken by `priority DESC`.
4. Else the **global** equivalents (`source_id IS NULL`), same specificity order.
5. Else the **implicit default chain**: `registry.candidates(mime)` ordered by
   `quality_tier` (high → standard → basic). This is what runs when nothing is
   configured, so the system behaves exactly like today out of the box.

```python
class ParserPolicyResolver:
    def __init__(self, repo: ParserPolicyRepository, registry: ExtractorRegistry) -> None:
        self._repo = repo
        self._registry = registry

    def resolve(self, source_id: UUID, mime_type: str) -> list[str]:
        """Return an ordered list of parser_names to attempt."""
        canonical = self._registry.canonical_mime(mime_type)
        policy = self._repo.match(source_id=source_id, mime_type=canonical)
        if policy is not None:
            return [p for p in policy["parser_chain"]
                    if self._registry.get_by_name(p) is not None]
        # Implicit default: quality-ordered registered candidates.
        return [c.capabilities().parser_name
                for c in self._registry.candidates(canonical)]
```

Unknown parser names in a stored chain are skipped (defensive — a policy may
reference a parser that was later disabled), and the implicit default still applies
if the whole chain is unusable.

---

## 4. Pipeline integration

### 4.1 Where the router sits

A new `ParserRouter` wraps the registry + resolver + audit repo. It replaces the
single `self._extractor.extract(...)` call in `ParseConsumer`. Everything else in
the parse stage (attachment expansion, `publish_translate`) is untouched.

```python
@dataclass
class RoutedExtraction:
    result: ExtractionResult
    parser_name: str
    parser_version: str
    duration_ms: int
    confidence: float | None
    warnings: list[str]
    attempts: list[str]  # parser_names tried, in order


class ParserRouter:
    def __init__(self, registry: ExtractorRegistry, resolver: ParserPolicyResolver) -> None:
        self._registry = registry
        self._resolver = resolver

    def route(self, path: Path, mime_type: str, source_id: UUID) -> RoutedExtraction:
        chain = self._resolver.resolve(source_id, mime_type)
        warnings: list[str] = []
        attempts: list[str] = []
        for parser_name in chain:
            extractor = self._registry.get_by_name(parser_name)
            if extractor is None:
                continue
            caps = extractor.capabilities()
            if caps.max_file_size and path.stat().st_size > caps.max_file_size:
                warnings.append(f"{parser_name}: file exceeds max_file_size; skipped")
                continue
            attempts.append(parser_name)
            start = time.monotonic()
            result = extractor.extract(path)
            duration_ms = int((time.monotonic() - start) * 1000)
            if result.text.strip():
                return RoutedExtraction(
                    result=result, parser_name=parser_name,
                    parser_version=caps.parser_version, duration_ms=duration_ms,
                    confidence=_confidence(result), warnings=warnings, attempts=attempts,
                )
            warnings.append(f"{parser_name}: produced empty text")
        # Whole chain failed → generic fallback, mirroring today's behaviour.
        result = self._registry.extract(path, mime_type)  # existing sniff-and-retry
        return RoutedExtraction(
            result=result, parser_name="generic", parser_version="1.0",
            duration_ms=0, confidence=0.0, warnings=warnings, attempts=attempts,
        )
```

`_confidence` is a deliberately simple v1 heuristic (e.g. ratio of printable to
total chars, or `1.0` when the parser is `high` tier and returned text). The
column exists so #674 can chart it; the scoring can improve later without a schema
change.

### 4.2 Parse worker change

```python
# parse_worker.py — inside handle_message, replacing the extract() call
if not content_text and doc.path:
    routed = self._router.route(Path(doc.path), doc.mime_type, source_id)
    content_text = routed.result.text
    location_segments = [seg.to_dict() for seg in routed.result.location_segments]
    if location_segments:
        self._job_repo.update_extraction_metadata(document_id, location_segments)
    self._extraction_repo.record(
        document_id=document_id,
        parser_name=routed.parser_name,
        parser_version=routed.parser_version,
        duration_ms=routed.duration_ms,
        confidence=routed.confidence,
        warnings=routed.warnings,
        attempts=routed.attempts,
    )
    _extraction_attachments = routed.result.attachments
    _maybe_delete_connector_temp(doc.path)
```

`ParseConsumer.__init__` gains a `router: ParserRouter | None` and an
`extraction_repo: DocumentExtractionRepository | None`, defaulting so existing
tests that pass only `extractor=` keep constructing (we build a router around the
default registry when none is supplied).

### 4.3 Message contract changes

**None required.** The selected parser is persisted to `document_extractions` and
read back by the API; it does not need to travel on the queue. Downstream workers
(`translate / embed / index`) continue to read `content_text` and
`extraction_metadata` from `document_payloads` exactly as today. `pipeline_version`
in the message body stays `"v1"`.

This is the key simplicity win: the router is a swap inside the parse stage, not a
protocol change rippling across seven consumers.

### 4.4 Flow to downstream and to the API

- **Embed/index**: unchanged. `location_segments` still flow via
  `document_payloads.extraction_metadata` into Qdrant payloads (see memory:
  `arch_qdrant_payload_schema`), so citations keep their page numbers.
- **Admin API**: reads `document_extractions` for the provenance endpoint (§5).
- **#669 layout blocks**: layout blocks (page-region metadata) will FK to the
  `document_extractions.id` that produced them (§6), so a block always knows which
  parser version generated it.

---

## 5. API surface (for #670 admin UI)

New router `src/services/api/routers/admin/parsers.py`, registered like the other
admin routers. All endpoints `require_admin(user)` and use
`request.app.state.engine.begin()`.

### 5.1 Models (Pydantic v2)

```python
class ParserCapabilitiesOut(BaseModel):
    parser_name: str
    parser_version: str
    supported_mime_types: list[str]
    quality_tier: Literal["high", "standard", "basic"]
    requires_ocr: bool
    max_file_size: int | None


class ExtractionRecordOut(BaseModel):
    document_id: UUID
    parser_name: str
    parser_version: str
    duration_ms: int
    confidence: float | None
    warnings: list[str]
    attempts: list[str]
    created_at: datetime


class ParserPolicyIn(BaseModel):
    source_id: UUID | None = None        # None = global default
    mime_pattern: str = Field(min_length=1)
    parser_chain: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 0


class ParserPolicyUpdate(BaseModel):
    mime_pattern: str | None = None
    parser_chain: list[str] | None = None
    options: dict[str, Any] | None = None
    enabled: bool | None = None
    priority: int | None = None


class ParserPolicyOut(ParserPolicyIn):
    id: UUID
    created_by: str | None
    created_at: datetime
    updated_at: datetime
```

### 5.2 Endpoints

**`GET /api/admin/parsers`** — list registered parsers with capabilities.

```python
@router.get("/admin/parsers")
def admin_list_parsers(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[ParserCapabilitiesOut]:
    require_admin(user)
    registry: ExtractorRegistry = request.app.state.extractor_registry
    return [ParserCapabilitiesOut.model_validate(c.__dict__) for c in registry.list()]
```

> Reads from the in-process registry (the source of truth for what code is
> installed), not the DB. `app.state.extractor_registry` is built at startup with
> the same `Settings` flags the parse worker uses, so the UI shows exactly the
> parsers that can actually run.

**`GET /api/admin/documents/{id}/extraction`** — which parser ran, how long, etc.

```python
@router.get("/admin/documents/{document_id}/extraction")
def admin_get_extraction(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ExtractionRecordOut:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        repo = DocumentExtractionRepository(connection)
        record = repo.get_latest(document_id)
        if record is None:
            raise HTTPException(status_code=404, detail="No extraction record")
        return ExtractionRecordOut.model_validate(record)
```

> 404 (not empty) for pre-router documents is intentional — the UI shows "parser
> unknown (ingested before tracking)" on 404, which is honest about the
> backward-compat gap rather than fabricating a parser name.

**CRUD for policies** — mirrors `admin/source_profiles.py` exactly:

```
POST   /api/admin/parser-policies          -> 201 ParserPolicyOut
GET    /api/admin/parser-policies          -> list[ParserPolicyOut]  (?source_id= filter)
GET    /api/admin/parser-policies/{id}     -> ParserPolicyOut
PATCH  /api/admin/parser-policies/{id}     -> ParserPolicyOut
DELETE /api/admin/parser-policies/{id}     -> {"deleted": true, "id": ...}
```

```python
@router.post("/admin/parser-policies", status_code=201)
def admin_create_policy(
    body: ParserPolicyIn,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ParserPolicyOut:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        if body.source_id is not None:
            exists = connection.execute(
                sa.text("SELECT id FROM ingestion_sources WHERE id = :id"),
                {"id": db_uuid(body.source_id)},
            ).scalar()
            if exists is None:
                raise HTTPException(status_code=404, detail="Source not found")
        # Validate every parser_name against the live registry.
        registry: ExtractorRegistry = request.app.state.extractor_registry
        unknown = [p for p in body.parser_chain if registry.get_by_name(p) is None]
        if unknown:
            raise HTTPException(422, detail=f"Unknown parsers: {', '.join(unknown)}")
        repo = ParserPolicyRepository(connection)
        policy_id = repo.create(**body.model_dump())
        _audit_log(connection, user.sub, "create", "parser_policy", str(policy_id),
                   details={"source_id": str(body.source_id), "mime": body.mime_pattern})
        created = repo.get(policy_id)
        if created is None:
            raise RuntimeError(f"parser_policy missing after create: {policy_id}")
        return ParserPolicyOut.model_validate(created)
```

Validating the chain against the live registry at write time is the safeguard that
keeps policies from referencing parsers that aren't installed (a frequent
operator footgun in air-gapped builds — see memory: `project_airgap_compose_parity`).

### 5.3 Repository sketch

```python
class ParserPolicyRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, *, source_id, mime_pattern, parser_chain, options,
               enabled=True, priority=0) -> UUID:
        policy_id = uuid4()
        self._connection.execute(sa.text("""
            INSERT INTO parser_policies
                (id, source_id, mime_pattern, parser_chain, options,
                 enabled, priority, created_at, updated_at)
            VALUES (:id, :source_id, :mime, :chain, :options,
                    :enabled, :priority, :now, :now)
        """), {
            "id": db_uuid(policy_id),
            "source_id": db_uuid(source_id) if source_id else None,
            "mime": mime_pattern,
            "chain": json.dumps(parser_chain),
            "options": json.dumps(options or {}),
            "enabled": enabled, "priority": priority, "now": datetime.now(UTC),
        })
        return policy_id

    def match(self, *, source_id: UUID, mime_type: str) -> dict[str, Any] | None:
        """Return the best policy for (source, mime) or None.
        Specificity: exact mime > glob > '*' ; source-specific > global;
        ties by priority DESC. Implemented as ordered SELECTs."""
        ...
```

---

## 6. Migration path (for #669 layout blocks)

### 6.1 Recording which parser produced each document

```python
# migrations/versions/<rev>_add_document_extractions_table.py
def upgrade() -> None:
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parser_name", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("attempts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_document_extractions_document_id",
                    "document_extractions", ["document_id"])
    # #674 dashboard aggregates by parser_name + recency.
    op.create_index("ix_document_extractions_parser_name",
                    "document_extractions", ["parser_name"])
```

One row per extraction attempt — re-parsing a document (e.g. after enabling
Docling) appends a new row. `get_latest(document_id)` returns the most recent by
`created_at`; the #674 dashboard can `GROUP BY parser_name` over a time window
without history loss.

### 6.2 How layout blocks reference their parser (#669)

#669 introduces page-region/layout blocks. They reference the extraction that
produced them, so a block carries its parser provenance and version:

```python
# Sketch for #669 — included here only to fix the FK target.
op.create_table(
    "document_layout_blocks",
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("document_id", sa.Uuid(),
              sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    sa.Column("extraction_id", sa.Uuid(),
              sa.ForeignKey("document_extractions.id", ondelete="CASCADE"),
              nullable=False),
    sa.Column("page_number", sa.Integer(), nullable=True),
    sa.Column("block_type", sa.Text(), nullable=False),  # heading|paragraph|table|figure
    sa.Column("bbox", sa.JSON(), nullable=True),          # [x0,y0,x1,y1]
    sa.Column("start_char", sa.Integer(), nullable=True),
    sa.Column("end_char", sa.Integer(), nullable=True),
    # ...
)
```

Because layout blocks FK to `document_extractions.id`, re-parsing a document with a
newer parser version yields a new extraction row and a new set of blocks; old
blocks remain attributable to the parser that made them.

### 6.3 Backward compatibility

- **No backfill.** Documents ingested before this change have no
  `document_extractions` row. APIs return 404 for their extraction record and the
  UI shows "parser unknown". This is acceptable and explicit.
- **Default behaviour unchanged.** With zero policies configured, the router's
  implicit default chain (quality-ordered registry candidates) plus the existing
  sniff-and-retry fallback reproduces today's extraction results.
- **Re-parse path (optional, future).** A maintenance job can re-run the parse
  stage for `mime_type IN (...)` to populate extraction rows and layout blocks for
  legacy documents; it reuses `publish_parse` and needs no new contract.
- **Registry rollout.** Extractors gain `capabilities()` incrementally; any without
  it get a synthetic capability, so the registry never crashes mid-migration.

---

## Appendix: file change inventory

| File | Change |
|------|--------|
| `src/services/extraction/base.py` | Add `QualityTier`, `ParserCapabilities`, `capabilities()` to protocol, `BaseExtractor` mixin |
| `src/services/extraction/*.py` (per extractor) | Set `_CAPS` (incremental) |
| `src/services/extraction/registry.py` | MIME→list, `get_by_name`, `candidates`, `list`, `canonical_mime` |
| `src/services/extraction/router.py` (new) | `ParserRouter`, `RoutedExtraction`, `_confidence` |
| `src/services/extraction/policy.py` (new) | `ParserPolicyResolver` |
| `src/services/extraction/policy_repository.py` (new) | `ParserPolicyRepository` |
| `src/services/extraction/extraction_repository.py` (new) | `DocumentExtractionRepository` |
| `src/services/pipeline/parse_worker.py` | Use router + record extraction; new optional ctor args |
| `src/services/api/routers/admin/parsers.py` (new) | parsers list, extraction record, policy CRUD |
| `src/services/api/main.py` | Build `app.state.extractor_registry`; register router |
| `migrations/versions/<rev>_add_parser_policies_table.py` (new) | `parser_policies` |
| `migrations/versions/<rev>_add_document_extractions_table.py` (new) | `document_extractions` |

### Verification (when implemented)

```
uv run ruff check --fix src/ tests/
uv run mypy src --strict
uv run pytest tests/unit/test_parser_router.py tests/unit/test_parser_policy.py -q
uv run pytest tests/integration/test_admin_parsers.py -q
```

### Out of scope (this design)

- Docling / new high-tier parsers themselves (the chain references them by name;
  adding the parser is separate work).
- The #670 React UI and the #674 dashboard rendering (this provides their API).
- Re-parse maintenance tooling (sketched in §6.3, not specified).
- Confidence scoring beyond the v1 heuristic.
