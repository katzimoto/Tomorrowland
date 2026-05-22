import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useT } from "@/i18n/index";
import type { ChatScopeType, ChatSession } from "@/api/chat";
import { ScopeBadge } from "./ScopeBadge";
import styles from "./ScopeSelector.module.css";

interface ScopeSelectorProps {
  session: ChatSession;
  onNewScope: (scopeType: ChatScopeType, scopeIds: string[]) => void;
  isCreating?: boolean;
}

export function ScopeSelector({
  session,
  onNewScope,
  isCreating = false,
}: ScopeSelectorProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLUListElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onOutsideClick(e: MouseEvent) {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [open]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") setOpen(false);
  }

  const isCurrentlyAll = session.scope_type === "all_accessible_documents";

  return (
    <div className={styles.container} onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        className={styles.trigger}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={t.chat.scopeSwitchLabel}
        disabled={isCreating}
      >
        <ScopeBadge
          scopeType={session.scope_type}
          scopeIds={session.scope_ids}
        />
        <ChevronDown
          size={14}
          className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <ul
          ref={menuRef}
          className={styles.menu}
          role="listbox"
          aria-label={t.chat.scopeSwitchLabel}
        >
          <li role="option" aria-selected={isCurrentlyAll}>
            <button
              className={`${styles.option} ${isCurrentlyAll ? styles.optionActive : ""}`}
              onClick={() => {
                onNewScope("all_accessible_documents", []);
                setOpen(false);
              }}
              disabled={isCurrentlyAll}
            >
              {t.chat.scopeAll}
            </button>
          </li>
          <li
            role="option"
            aria-selected={false}
            aria-disabled="true"
            className={styles.optionDisabled}
          >
            <span className={styles.optionDisabledLabel}>
              {t.chat.scopeSource}
            </span>
            <span className={styles.optionDisabledNote}>(coming soon)</span>
          </li>
          <li
            role="option"
            aria-selected={false}
            aria-disabled="true"
            className={styles.optionDisabled}
          >
            <span className={styles.optionDisabledLabel}>
              {t.chat.scopeFolder}
            </span>
            <span className={styles.optionDisabledNote}>(coming soon)</span>
          </li>
        </ul>
      )}
    </div>
  );
}
