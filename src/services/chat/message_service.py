"""Conversation-aware query rewrite for Document Chat."""

from __future__ import annotations

import logging

from services.chat.models import ChatMessage
from services.intelligence.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """\
Given the conversation below, rewrite the last user message as a standalone search query.
Do not add facts. Only resolve references from earlier messages.
Return only the rewritten query. No explanation.

Conversation:
{history}

Last message: {user_message}

Standalone query:"""

MAX_HISTORY_PAIRS = 4


def _build_history_text(messages: list[ChatMessage]) -> str:
    """Format the last *MAX_HISTORY_PAIRS* user+assistant pairs as text."""
    relevant = messages[-(MAX_HISTORY_PAIRS * 2) :]
    lines: list[str] = []
    for m in relevant:
        prefix = "User: " if m.role == "user" else "Assistant: "
        lines.append(f"{prefix}{m.content}")
    return "\n".join(lines)


def rewrite_query(
    question: str,
    existing_messages: list[ChatMessage],
    ollama_client: LLMProvider,
    model: str | None = None,
) -> str:
    """Rewrite *question* as a standalone search query using conversation history.

    Returns the rewritten query, or the original *question* if the session
    has fewer than one prior user+assistant turn or if the LLM call fails.

    Args:
        model: Override the client's default model. Pass the utility model
               here so query rewrite uses the smaller/faster model.
    """
    prior_turns = len(existing_messages) // 2
    if prior_turns < 1:
        return question

    history_text = _build_history_text(existing_messages)
    prompt = REWRITE_PROMPT.format(
        history=history_text,
        user_message=question,
    )
    try:
        rewritten = ollama_client.generate(prompt, model=model).strip()
        if rewritten:
            return rewritten
    except Exception:
        logger.warning("Query rewrite failed, falling back to raw message", exc_info=True)
    return question
