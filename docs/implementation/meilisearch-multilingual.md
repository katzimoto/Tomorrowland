# Meilisearch Multilingual Search — Decisions

**Scope:** Language detection, query routing, Hebrew/English handling, mixed queries.
**Does not cover:** Index settings (#301), indexing pipeline (#303).
**Companion file:** `src/services/search/meili_lang.py`

---

## Same index, not per-language indexes

Separate per-language indexes would require two reindex pipelines, coordinated
alias swaps, and query routing logic that decides which index to hit before
searching. The added operational complexity gives no correctness benefit.

Meilisearch v1.4+ includes Hebrew-aware tokenization and handles Hebrew and
English content in the same index correctly. All content fields — `content`
(original language), `content_en`, `content_he` — are registered as searchable
attributes in the same index. Meilisearch searches all of them simultaneously
on every query.

---

## Flat translation fields are the right choice

Because all searchable attributes are enumerated at index configuration time,
the flat `content_en` / `content_he` / `title_en` / `title_he` approach (decided
in the data model) enables language-aware search without any query-time routing.
A Hebrew query term matches `content` (Hebrew source documents) and `content_he`
(documents translated into Hebrew). An English query term matches `content_en`.
Both happen in the same search call.

---

## Language detection

Detection serves two purposes:
1. UI hints — "Your query is in Hebrew" / "Results may include Hebrew content"
2. Future boosting — optionally apply a ranking score threshold to prefer
   results where the matched field language aligns with the query language

Detection does **not** change which Meilisearch index is queried or which
attributes are searched. It is a signal, not a router.

### Algorithm

Count Hebrew Unicode characters (U+0591–U+05FF) in the non-whitespace portion
of the query string:

```
hebrew_ratio = hebrew_char_count / non_whitespace_char_count
```

| Ratio | Detected language |
|-------|------------------|
| > 0.6 | `"he"` |
| 0.1 – 0.6 | `"mixed"` |
| < 0.1 | `"en"` |
| Empty / whitespace only | `"en"` (safe default) |

Thresholds are intentionally conservative. A query like `"Q4 דוח"` (one Hebrew
word, two English characters) hits `mixed` at ~40 %, which is correct — both
language fields should contribute equally.

### Why not a library?

`langdetect`, `langid`, and similar libraries add a dependency, require model
files, and are unreliable for short strings (< 20 chars). Short search queries
(2–5 words) are the common case. The Unicode block heuristic is deterministic,
dependency-free, and correct for the Hebrew/English use case.

---

## Mixed Hebrew/English queries

No special handling is required. A query like `"דוח quarterly"` causes
Meilisearch to:

- Match `content` on `"דוח"` in Hebrew source documents
- Match `content_en` on `"quarterly"` in English-translated content
- Match both fields in documents that contain both terms

Meilisearch unions results across all searchable attributes. Both terms
contribute to the ranking score independently. This is correct and expected
behaviour — no query rewriting or field boosting is needed.

---

## `language` query parameter behaviour

`DocumentSearchQuery.language` accepts `"auto"` (default), `"en"`, or `"he"`.

| Value | Behaviour |
|-------|-----------|
| `"auto"` | Run `detect_query_language(q)` to determine the language |
| `"en"` | Treat as English regardless of script — useful when user explicitly switches UI language |
| `"he"` | Treat as Hebrew regardless of script |

In all cases the Meilisearch query is identical — the language value is metadata
returned to the caller for UI use, not a search parameter.

---

## `detected_language` in the search response

The `DocumentSearchResponse` does not currently include a `detected_language`
field. If the frontend needs it for UI hints, it can be added as an optional
field in a future iteration. For now, the frontend can call `detect_query_language`
indirectly by interpreting the `language` field it sent.

---

## Stop words and Hebrew tokenization

Hebrew stop words are configured at the index level (index settings, issue #301).
Language detection does not interact with stop words — they are filtered by
Meilisearch's tokenizer before scoring, regardless of the detected language.

Meilisearch's built-in Hebrew tokenizer (v1.4+) handles right-to-left text,
Unicode normalization, and basic morphological splitting without extra
configuration. No custom analyzer is needed.

---

## Acceptance criteria

- [ ] `detect_query_language` returns `"he"` when > 60 % of non-whitespace chars are Hebrew Unicode
- [ ] Returns `"mixed"` when 10–60 % are Hebrew
- [ ] Returns `"en"` otherwise, including empty string and whitespace-only input
- [ ] `resolve_query_language` applies `detect_query_language` when `language="auto"`, passes through `"en"` / `"he"` otherwise
- [ ] Both functions are pure — no I/O, no side effects
- [ ] Unit tests: pure English, pure Hebrew, mixed, empty string, whitespace-only, punctuation-only, single Hebrew char
- [ ] `mypy src --strict` passes
