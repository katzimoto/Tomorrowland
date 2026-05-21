import { useT } from "@/i18n/index";
import { Button } from "@/components/primitives/Button";
import styles from "./ChatInput.module.css";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export function ChatInput({ value, onChange, onSubmit, disabled }: ChatInputProps) {
  const t = useT();

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !disabled) {
      e.preventDefault();
      if (value.trim()) onSubmit();
    }
  }

  return (
    <div className={styles.row}>
      <textarea
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
  );
}
