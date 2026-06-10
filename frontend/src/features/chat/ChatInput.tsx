import { useEffect, useRef } from "react";
import { useT } from "@/i18n/index";
import { Button } from "@/components/primitives/Button";
import type { ChatStreamPhase } from "@/api/chat";
import styles from "./ChatInput.module.css";
import phaseStyles from "./ChatPhase.module.css";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  phase?: ChatStreamPhase | null;
  autoFocus?: boolean;
}

export function ChatInput({ value, onChange, onSubmit, disabled, phase, autoFocus }: ChatInputProps) {
  const t = useT();

  const phaseLabels: Record<ChatStreamPhase, string> = {
    searching: t.chat.phaseSearching,
    reading_sources: t.chat.phaseReadingSources,
    generating: t.chat.phaseGenerating,
  };
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [autoFocus]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !disabled) {
      e.preventDefault();
      if (value.trim()) onSubmit();
    }
  }

  return (
    <div className={styles.wrapper}>
      {phase && (
        <div className={phaseStyles.indicator} role="status" aria-live="polite">
          <span className={phaseStyles.spinner} aria-hidden="true" />
          {phaseLabels[phase]}
        </div>
      )}
      <div className={styles.row}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t.chat.inputPlaceholder}
          disabled={disabled}
          rows={2}
          aria-label={t.chat.inputPlaceholder}
        />
        <Button
          onClick={onSubmit}
          disabled={!value.trim() || disabled}
          loading={disabled}
          aria-label={t.chat.send}
        >
          {t.chat.send}
        </Button>
      </div>
    </div>
  );
}
