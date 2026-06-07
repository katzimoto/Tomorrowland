# Phase 03b: Translation And Chunking

## Goal

Turn extracted text into English chunks.

## Scope

- LibreTranslate `httpx` client with timeout, retry, and fallback.
- Translation state machine persistence.
- Token-based chunking (512 tokens, 50 overlap, sentence boundary aware).

## Implementation Notes

- The translation client uses a 30-second timeout and one retry.
- On any exception (timeout, 5xx, parse error) the client logs a warning and
  returns the original text untranslated. `translation_quality` stays `null`.
- On success `translation_quality` is set to `"fast"`.
- Chunking splits on sentence boundaries when possible and hard-cuts at the
  token limit otherwise. Empty text yields an empty chunk list.
- For Phase 03, token counting is approximated by whitespace splitting.

## Validation

- Unit tests for translation success and failure paths.
- Unit tests for chunking edge cases: empty text, short text, long text, and
  sentence-boundary respect.

## Acceptance Criteria

- Given a blob of text and a source language, the system returns a list of
  English chunks.
- LibreTranslate failures leave the document indexed with `translation_quality`
  set to `null`.
- Chunk overlap is exactly 50 tokens (approximated) and the last chunk is not
  padded.
