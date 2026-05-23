import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useT } from "@/i18n/index";
import styles from "./CommandMenu.module.css";

export function CommandMenu() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  const COMMANDS = useMemo(() => [
    { label: t.nav.search, to: "/search" },
    { label: t.nav.chat, to: "/chat" },
    { label: t.nav.subscriptions, to: "/subscriptions" },
    { label: t.nav.notifications, to: "/notifications" },
    { label: t.nav.history, to: "/history" },
    { label: t.nav.expertise, to: "/expertise" },
  ], [t]);

  const matches = useMemo(() => COMMANDS.filter((command) => command.label.toLowerCase().includes(query.toLowerCase())), [COMMANDS, query]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setOpen(true); }
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!open) return null;
  return (
    <div className={styles.overlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <div className={styles.panel} role="dialog" aria-modal="true" aria-label={t.cmd.ariaLabel}>
        <input className={styles.input} autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t.cmd.placeholder} />
        <p className={styles.hint}>{t.cmd.hint}</p>
        <ul className={styles.list}>{matches.map((command) => <li key={command.to}><button className={styles.item} onClick={() => { setOpen(false); void navigate({ to: command.to }); }}>{command.label}</button></li>)}</ul>
        {matches.length === 0 && <div className={styles.empty}>{t.cmd.empty}</div>}
      </div>
    </div>
  );
}
