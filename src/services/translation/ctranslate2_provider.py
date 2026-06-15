"""CTranslate2 OPUS-MT high-quality translation provider (#731).

Implements :class:`TranslationProvider` for pair-specific OPUS-MT models
converted to the CTranslate2 format.  Models are loaded from a translation
model bundle (``manifest.json``) as defined in #730.

Usage (requires ``pip install tomorrowland[ctranslate2]``)::

    from services.translation.ctranslate2_provider import CTranslate2OpusProvider

    high = CTranslate2OpusProvider(
        bundle_path="/path/to/extracted/bundle",
        baseline=libretranslate_provider,  # fallback when pair is missing
        device="cpu",
    )
    result = high.translate("Hello", source_lang="en", target_lang="he")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from services.translation.model_bundle import (
    BundleValidator,
    TranslationModelManifest,
    load_manifest_from_path,
)
from services.translation.provider import TranslationProvider

logger = logging.getLogger(__name__)

_DEFAULT_NAME = "opus_mt_ctranslate2"
_DEFAULT_MODEL_FAMILY = "opus"
_DEVICE = "cpu"
_BEAM_SIZE = 4
_MAX_BATCH_SIZE = 32
_MAX_CHARS_PER_REQUEST = 5000


class CTranslate2OpusProvider(TranslationProvider):
    """High-quality translation provider backed by CTranslate2 + OPUS-MT.

    Loads pair-specific CTranslate2 model directories from a translation
    model bundle.  When a requested language pair is not covered by the
    bundle, the provider falls back to *baseline* (typically
    :class:`LibreTranslateArgosProvider`) silently — the caller does not
    need to check availability before calling :meth:`translate`.

    Requires the optional ``[ctranslate2]`` extra::

        pip install tomorrowland[ctranslate2]
    """

    def __init__(
        self,
        bundle_path: str,
        baseline: TranslationProvider | None = None,
        device: str = _DEVICE,
        beam_size: int = _BEAM_SIZE,
        max_batch_size: int = _MAX_BATCH_SIZE,
    ) -> None:
        """Initialise the provider from an extracted translation model bundle.

        Args:
            bundle_path: Path to the directory containing ``manifest.json``
                and the ``models/`` tree.
            baseline: Fallback :class:`TranslationProvider` used when the
                requested language pair is not covered by this bundle.
            device: ``"cpu"`` or ``"cuda"`` — passed to :class:`ctranslate2.Translator`.
            beam_size: Beam-search width for translation.
            max_batch_size: Maximum batch size passed to CTranslate2.
        """
        self._bundle_path = Path(bundle_path)
        self._baseline = baseline
        self._device = device
        self._beam_size = beam_size
        self._max_batch_size = max_batch_size

        # Cached per-pair translators: (source, target) → ctranslate2.Translator
        self._translators: dict[tuple[str, str], Any] = {}

        # Tokenizer cache: model_dir → (src_sp, tgt_sp) or None
        self._tokenizers: dict[Path, tuple[Any, Any] | None] = {}

        self._manifest: TranslationModelManifest | None = None
        self._bundle_valid: bool = False
        self._load_errors: list[str] = []

        self._init_bundle()

    # -- Provider identity --------------------------------------------------

    @property
    def name(self) -> str:
        if self._manifest is not None:
            return self._manifest.provider.name
        return _DEFAULT_NAME

    @property
    def version(self) -> str | None:
        if self._manifest is not None:
            return self._manifest.provider.version
        return None

    @property
    def model_family(self) -> str | None:
        if self._manifest is not None:
            return self._manifest.provider.model_family
        return _DEFAULT_MODEL_FAMILY

    # -- Capabilities -------------------------------------------------------

    @property
    def capabilities(self) -> dict[str, Any]:
        pairs = sorted(self._translators.keys())
        return {
            "max_chars_per_request": _MAX_CHARS_PER_REQUEST,
            "supports_batch": True,
            "supports_auto_detect": False,
            "model_family": self.model_family,
            "device": self._device,
            "beam_size": self._beam_size,
            "language_pairs": [{"source": s, "target": t} for s, t in pairs],
            "loaded_pair_count": len(pairs),
        }

    # -- Translation --------------------------------------------------------

    def translate(
        self,
        text: str,
        source_lang: str | None,
        target_lang: str = "en",
    ) -> str:
        """Translate *text* using the loaded OPUS-MT model, or fall back.

        When *source_lang* is ``None``, language auto-detection is not
        supported — the baseline provider is used instead.
        """
        if not text.strip():
            return text

        if source_lang is None:
            return self._fallback(text, source_lang, target_lang)

        translator = self._translators.get((source_lang, target_lang))
        if translator is None:
            return self._fallback(text, source_lang, target_lang)

        model_dir = self._bundle_path / self._manifest.models_dir / f"{source_lang}-{target_lang}"  # type: ignore[union-attr]

        try:
            return self._translate_with_ctranslate2(translator, text, model_dir)
        except Exception:
            logger.warning(
                "CTranslate2 translation failed for %s→%s, falling back",
                source_lang,
                target_lang,
                exc_info=True,
            )
            return self._fallback(text, source_lang, target_lang)

    def _translate_with_ctranslate2(
        self,
        translator: Any,
        text: str,
        model_dir: Path,
    ) -> str:
        """Run CTranslate2 translation with tokenization."""
        # Tokenize
        src_sp: Any = None
        tgt_sp: Any = None
        if model_dir in self._tokenizers:
            tok = self._tokenizers[model_dir]
            if tok is not None:
                src_sp, tgt_sp = tok

        if src_sp is not None:
            source_tokens: Any = src_sp.encode(text, out_type=str)
        else:
            source_tokens = [text]

        # Translate
        results = translator.translate_batch(
            [source_tokens],
            beam_size=self._beam_size,
            max_batch_size=self._max_batch_size,
        )
        target_tokens = results[0].hypotheses[0]

        # Detokenize
        if tgt_sp is not None:
            return str(tgt_sp.decode(target_tokens))

        # If no tokenizer available, ctranslate2 may return strings directly
        if isinstance(target_tokens, str):
            return target_tokens
        if target_tokens:
            return " ".join(str(t) for t in target_tokens)
        return text

    def _fallback(self, text: str, source_lang: str | None, target_lang: str) -> str:
        """Delegate to the baseline provider, or return unchanged."""
        if self._baseline is not None:
            return self._baseline.translate(text, source_lang=source_lang, target_lang=target_lang)
        return text

    # -- Health -------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return a health snapshot covering bundle validity and loaded pairs."""
        status = "healthy" if self._bundle_valid and self._translators else "degraded"
        if not self._bundle_valid and not self._translators:
            status = "unhealthy"
        return {
            "status": status,
            "provider": self.name,
            "version": self.version,
            "model_family": self.model_family,
            "bundle_valid": self._bundle_valid,
            "loaded_pairs": len(self._translators),
            "load_errors": self._load_errors,
            "baseline_available": self._baseline is not None,
        }

    # -- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Release CTranslate2 model memory and close the baseline provider."""
        self._translators.clear()
        self._tokenizers.clear()
        if self._baseline is not None:
            self._baseline.close()

    # -- Internal -----------------------------------------------------------

    def _init_bundle(self) -> None:
        """Load the manifest, validate the bundle, and initialise per-pair translators."""
        # 1. Load manifest
        manifest_path = self._bundle_path / "manifest.json"
        if not manifest_path.is_file():
            self._load_errors.append(f"manifest.json not found at {self._bundle_path}")
            return

        try:
            self._manifest = load_manifest_from_path(manifest_path)
        except Exception as exc:
            self._load_errors.append(f"Failed to parse manifest.json: {exc}")
            return

        # 2. Validate bundle integrity
        validator = BundleValidator(self._manifest, self._bundle_path)
        report = validator.validate()
        self._bundle_valid = report.valid
        if not report.valid:
            for issue in report.issues:
                self._load_errors.append(issue)

        # 3. Load per-pair translators
        for pair in self._manifest.language_pairs:
            model_dir_name = f"{pair.source}-{pair.target}"
            model_dir = self._bundle_path / self._manifest.models_dir / model_dir_name
            if not model_dir.is_dir():
                self._load_errors.append(f"Model directory not found: {model_dir_name}")
                continue

            try:
                self._load_pair(pair.source, pair.target, model_dir)
            except Exception as exc:
                self._load_errors.append(f"Failed to load {pair.source}→{pair.target}: {exc}")

    def _load_pair(self, source: str, target: str, model_dir: Path) -> None:
        """Load a single CTranslate2 model directory."""
        import ctranslate2

        translator = ctranslate2.Translator(
            str(model_dir),
            device=self._device,
        )
        self._translators[(source, target)] = translator

        # Try to load SentencePiece tokenizers
        self._tokenizers[model_dir] = self._load_sentencepiece(model_dir)

    @staticmethod
    def _load_sentencepiece(model_dir: Path) -> tuple[Any, Any] | None:
        """Load SentencePiece processors for source and target languages.

        OPUS-MT model directories may contain:
        - ``source.spm`` / ``target.spm``
        - ``sentencepiece.model`` (shared)
        - ``sentencepiece.source.model`` / ``sentencepiece.target.model``
        """
        try:
            import sentencepiece as spm
        except ImportError:
            return None

        src_sp = None
        tgt_sp = None

        # Try source.spm / target.spm
        src_candidate = model_dir / "source.spm"
        tgt_candidate = model_dir / "target.spm"
        if src_candidate.is_file() and tgt_candidate.is_file():
            src_sp = spm.SentencePieceProcessor(model_file=str(src_candidate))
            tgt_sp = spm.SentencePieceProcessor(model_file=str(tgt_candidate))
            return (src_sp, tgt_sp)

        # Try sentencepiece.source.model / sentencepiece.target.model
        src_candidate = model_dir / "sentencepiece.source.model"
        tgt_candidate = model_dir / "sentencepiece.target.model"
        if src_candidate.is_file() and tgt_candidate.is_file():
            src_sp = spm.SentencePieceProcessor(model_file=str(src_candidate))
            tgt_sp = spm.SentencePieceProcessor(model_file=str(tgt_candidate))
            return (src_sp, tgt_sp)

        # Try shared sentencepiece.model
        shared = model_dir / "sentencepiece.model"
        if shared.is_file():
            sp = spm.SentencePieceProcessor(model_file=str(shared))
            return (sp, sp)

        return None
