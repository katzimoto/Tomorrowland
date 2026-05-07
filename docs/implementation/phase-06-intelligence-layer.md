# Phase 06: Intelligence Layer

## Goal

Add best-effort local LLM intelligence without blocking ingestion.

## Scope

- Ollama service integration.
- Worker-intelligence service.
- Summarization.
- Entity extraction.
- Auto-tagging.
- Alert matching.
- Best-effort failure behavior.

## Validation

- Mocked Ollama tests.
- Database upsert tests for summaries, entities, tags, and notifications.
- Failure tests prove ingestion is not blocked and DLQ is not used.

## Acceptance Criteria

- Enabled intelligence tasks update Postgres and indexes.
- Disabled tasks are skipped.
- Ollama failures are logged and do not block document ingestion.
