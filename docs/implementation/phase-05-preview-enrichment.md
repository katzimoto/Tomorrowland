# Phase 05: Preview And Enrichment

## Goal

Expand document preview support and implement high-quality translation flow.

## Scope

- Preview service modes.
- View count tracking.
- Manual translation request endpoint.
- Auto-enrich threshold behavior.
- Slow worker high-quality translation and reindex pipeline.

## Decision Gates

- Resolve annotation retention and preview position shape gaps.

## Validation

- Fixture tests for supported preview modes.
- Auto-enrich threshold tests.
- Slow worker reindex tests.

## Acceptance Criteria

- Supported file types return stable preview responses.
- Manual and automatic enrichment queue work exactly once while pending.
- Re-enriched documents update both search indexes.
