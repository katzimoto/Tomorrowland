"""Offline eval fixture cases.

Each fixture is a dict with:
    id: str           — unique case identifier
    category: str     — eval category (see CATEGORIES)
    question: str     — the question to ask
    gold_ids: list[str]    — expected document IDs in the answer (empty = no-answer case)
    expected_no_answer: bool — True if the system should say "I don't know"
    notes: str        — human-readable description for diagnosis reports
    language: str     — question language (ISO 639-1)
    tags: list[str]   — optional tags for filtering runs

Add new cases by appending to EVAL_CASES.  Each case must have a unique `id`.
"""

from __future__ import annotations

CATEGORIES = [
    "simple_factual",
    "citation_required",
    "no_answer",
    "hebrew_english_translation",
    "permission_boundary",
    "multi_document",
    "follow_up",
    "table_heavy",
]

EVAL_CASES: list[dict] = [
    # ------------------------------------------------------------------
    # simple_factual
    # ------------------------------------------------------------------
    {
        "id": "sf-001",
        "category": "simple_factual",
        "question": "What is the main topic of the indexed documents?",
        "gold_ids": [],
        "expected_no_answer": False,
        "notes": "Baseline factual retrieval; verifies the system returns at least one result.",
        "language": "en",
        "tags": ["baseline"],
    },
    # ------------------------------------------------------------------
    # citation_required
    # ------------------------------------------------------------------
    {
        "id": "cr-001",
        "category": "citation_required",
        "question": "Which document mentions a specific date or deadline?",
        "gold_ids": [],
        "expected_no_answer": False,
        "notes": "Citation accuracy case; answer must include at least one cited document.",
        "language": "en",
        "tags": ["citations"],
    },
    # ------------------------------------------------------------------
    # no_answer / out-of-scope
    # ------------------------------------------------------------------
    {
        "id": "na-001",
        "category": "no_answer",
        "question": "What is the current price of crude oil on the London Stock Exchange?",
        "gold_ids": [],
        "expected_no_answer": True,
        "notes": "Out-of-scope question; system must not fabricate an answer.",
        "language": "en",
        "tags": ["no-answer"],
    },
    {
        "id": "na-002",
        "category": "no_answer",
        "question": "Who won the last FIFA World Cup?",
        "gold_ids": [],
        "expected_no_answer": True,
        "notes": "Real-world knowledge outside indexed corpus; should decline.",
        "language": "en",
        "tags": ["no-answer"],
    },
    # ------------------------------------------------------------------
    # Hebrew / English translation
    # ------------------------------------------------------------------
    {
        "id": "he-001",
        "category": "hebrew_english_translation",
        "question": "מה הנושא המרכזי של המסמכים?",
        "gold_ids": [],
        "expected_no_answer": False,
        "notes": "Hebrew question; verifies cross-lingual retrieval via LibreTranslate.",
        "language": "he",
        "tags": ["multilingual", "hebrew"],
    },
    # ------------------------------------------------------------------
    # permission_boundary
    # ------------------------------------------------------------------
    {
        "id": "pb-001",
        "category": "permission_boundary",
        "question": "Summarise all restricted documents.",
        "gold_ids": [],
        "expected_no_answer": True,
        "notes": "No-permission case; system must not leak restricted document content.",
        "language": "en",
        "tags": ["permissions", "security"],
    },
    # ------------------------------------------------------------------
    # multi_document
    # ------------------------------------------------------------------
    {
        "id": "md-001",
        "category": "multi_document",
        "question": "Compare the conclusions of the different reports in the corpus.",
        "gold_ids": [],
        "expected_no_answer": False,
        "notes": "Requires synthesis across multiple documents.",
        "language": "en",
        "tags": ["multi-doc"],
    },
    # ------------------------------------------------------------------
    # follow_up
    # ------------------------------------------------------------------
    {
        "id": "fu-001",
        "category": "follow_up",
        "question": "Can you give me more details about that?",
        "gold_ids": [],
        "expected_no_answer": False,
        "notes": "Follow-up question stub; real test requires a conversation fixture.",
        "language": "en",
        "tags": ["follow-up"],
    },
    # ------------------------------------------------------------------
    # table_heavy
    # ------------------------------------------------------------------
    {
        "id": "th-001",
        "category": "table_heavy",
        "question": "What are the values in the first table of the document?",
        "gold_ids": [],
        "expected_no_answer": False,
        "notes": "Table extraction; verifies chunk content includes table rows.",
        "language": "en",
        "tags": ["tables"],
    },
]
