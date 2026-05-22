import { useT } from "@/i18n/index";
import type { ChatScopeType } from "@/api/chat";
import styles from "./StarterQuestions.module.css";

interface StarterQuestionsProps {
  scopeType: ChatScopeType;
  onSelect: (question: string) => void;
  disabled?: boolean;
}

const SCOPE_QUESTIONS: Record<ChatScopeType, string[]> = {
  all_accessible_documents: [
    "Summarize my documents",
    "What are the key topics?",
    "Find documents about contracts",
    "What recent updates are there?",
  ],
  single_document: [
    "Summarize this document",
    "What are the key points?",
    "List all dates mentioned",
    "Who are the parties involved?",
  ],
  selected_documents: [
    "Compare these documents",
    "Find common themes",
    "What are the key differences?",
  ],
  source: [
    "What's in this source?",
    "Find recent documents",
    "Summarize the latest updates",
  ],
  folder: [
    "What's in this folder?",
    "Summarize all documents",
    "Find the most recent file",
  ],
  current_search_results: [
    "Summarize these results",
    "What do these documents have in common?",
    "Extract key data points",
  ],
};

export function StarterQuestions({ scopeType, onSelect, disabled }: StarterQuestionsProps) {
  const t = useT();
  const questions = SCOPE_QUESTIONS[scopeType] ?? SCOPE_QUESTIONS.all_accessible_documents;

  return (
    <div className={styles.container} role="group" aria-label="Suggested questions">
      <p className={styles.heading}>{t.chat.starterHeading}</p>
      <div className={styles.grid}>
        {questions.map((q) => (
          <button
            key={q}
            className={styles.pill}
            onClick={() => onSelect(q)}
            disabled={disabled}
            type="button"
            aria-label={`Ask: ${q}`}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
