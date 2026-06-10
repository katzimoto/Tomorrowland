"""Parser policy resolver — selects the parser chain for a source+MIME pair.

See docs/design/parser-router.md §3.3 for the resolution algorithm.
"""

from __future__ import annotations

from uuid import UUID

from services.extraction.policy_repository import ParserPolicyRepository
from services.extraction.registry import ExtractorRegistry, _caps


class ParserPolicyResolver:
    """Select the parser chain for a (source_id, mime_type) pair.

    Resolution order (from most specific to least):
      1. Exact (source_id, mime) policy
      2. Source-specific glob policy (image/* → text/* → *)
      3. Global (source_id IS NULL) equivalents
      4. Implicit default: quality-tier-ordered registry candidates
    """

    def __init__(
        self,
        repo: ParserPolicyRepository,
        registry: ExtractorRegistry,
    ) -> None:
        self._repo = repo
        self._registry = registry

    def resolve(self, source_id: UUID, mime_type: str) -> list[str]:
        """Return an ordered list of parser_names to attempt.

        Unknown parser names in a stored chain are silently skipped.
        If no policy matches (or the matched policy's chain is empty or
        all-unknown), falls back to the implicit default chain from the
        registry.
        """
        canonical = self._registry.canonical_mime(mime_type)
        policy = self._repo.match(source_id=source_id, mime_type=canonical)

        if policy is not None:
            chain = [p for p in policy["parser_chain"] if self._registry.get_by_name(p) is not None]
            if chain:
                return chain

        # Implicit default: quality-ordered registered candidates.
        return [_caps(c).parser_name for c in self._registry.candidates(canonical)]
