import { Search, X } from "lucide-react";
import { IconButton } from "./IconButton";
import styles from "./SearchInput.module.css";

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  autoFocus?: boolean;
}

export function SearchInput({
  value,
  onChange,
  onSubmit,
  placeholder = "Search documents, issues, pages, and emails",
  autoFocus,
}: SearchInputProps) {
  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") onSubmit?.();
    if (e.key === "Escape" && value) onChange("");
  }

  return (
    <div className={styles.wrapper} role="search">
      <span className={styles.icon} aria-hidden>
        <Search size={18} />
      </span>
      <input
        className={styles.input}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        placeholder={placeholder}
        aria-label="Search"
        autoFocus={autoFocus}
        autoComplete="off"
      />
      {value && (
        <IconButton
          label="Clear search"
          size="sm"
          className={styles.clearBtn}
          onClick={() => onChange("")}
        >
          <X size={16} />
        </IconButton>
      )}
    </div>
  );
}
