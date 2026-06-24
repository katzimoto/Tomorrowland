"""Tests for source-language detection in the translate worker.

Guards the fix for translations that silently no-op when a document's source
language is unknown: LibreTranslate's ``auto`` mode mis-detects CJK text as
English and returns it unchanged. We detect the source language ourselves and
normalise it to a base code LibreTranslate accepts.
"""

from __future__ import annotations

from services.pipeline.translate_worker import _detect_source_language

# ~120+ chars each so langdetect clears its minimum-length / confidence gates.
_CHINESE = (
    "中文向量搜索简报。本文档用于测试中文文本抽取、CJK 字符渲染和搜索召回。"
    "关键词包括向量索引、语义搜索、混合检索、元数据加权以及翻译版本管理。"
    "场景一：查询中文分词与向量索引应当命中本文档。场景二：混合检索应当融合"
    "BM25、向量相似度以及元数据权重。我们希望确保中文内容能够被正确地翻译成英文。"
)
_ENGLISH = (
    "This document describes the vector search pipeline used for indexing and "
    "retrieval. It covers hybrid search, metadata weighting, and translation "
    "versions, and exists purely to exercise English language detection."
)


def test_detects_chinese() -> None:
    assert _detect_source_language(_CHINESE) == "zh"


def test_detects_chinese_mixed_with_ascii_keywords() -> None:
    # Regression: a Chinese doc peppered with English terms (BM25, blue bicycle,
    # reciprocal rank fusion) makes statistical detectors mis-fire (langdetect
    # labelled this "vi"). The Han-script shortcut must still resolve it to zh
    # so it is not sent to LibreTranslate as an unsupported language.
    mixed = (
        "中文向量搜索简报。场景二: 查询 blue bicycle 蓝色自行车 应通过翻译字段"
        "召回多语言样本。场景三: reciprocal rank fusion 可融合 BM25、向量相似度"
        "和元数据权重。测试建议: 对 title、tags、translated_text 设置独立 boost。"
    )
    assert _detect_source_language(mixed) == "zh"


def test_detects_english() -> None:
    assert _detect_source_language(_ENGLISH) == "en"


def test_returns_none_for_inconclusive_text() -> None:
    # Too short / no linguistic content -> detector declines, leaving the
    # caller's existing ``auto`` fallback untouched.
    assert _detect_source_language("") is None
    assert _detect_source_language("123 456 789") is None
