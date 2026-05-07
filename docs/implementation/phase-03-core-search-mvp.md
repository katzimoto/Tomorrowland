# Phase 03: Core Search MVP

## Goal

Deliver a working permission-filtered search system for ingested documents.

## Scope

- Folder ingestion.
- Document persistence.
- Fast worker pipeline.
- Text extraction abstraction.
- LibreTranslate fast translation and fallback.
- Chunking and embeddings abstraction.
- Elasticsearch and Qdrant indexing.
- Search, preview, and download APIs.

## Decision Gates

- Resolve chunk text storage, delete source of truth, and translation state gaps.

## Validation

- Integration test ingests a fixture document, indexes it, searches it, previews
  it, and downloads it.
- Permission-filtered search tests.
- Translation failure fallback tests.

## Acceptance Criteria

- A user can find only documents their groups allow.
- Indexed documents include enough metadata for search results and previews.
- Translation failure still leaves the document searchable with fallback state.
