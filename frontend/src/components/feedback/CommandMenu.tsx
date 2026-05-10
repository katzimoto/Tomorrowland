import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import styles from "./CommandMenu.module.css";

const COMMANDS = [
  { label: "Search", to: "/search" },
  { label: "Q&A", to: "/qa" },
  { label: "Subscriptions", to: "/subscriptions" },
  { label: "Notifications", to: "/notifications" },
  { label: "History", to: "/history" },
  { label: "Expertise map", to: "/expertise" },
];

export function CommandMenu() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const matches = useMemo(() => COMMANDS.filter((command) => command.label.toLowerCase().includes(query.toLowerCase())), [query]);

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
      <div className={styles.panel} role="dialog" aria-modal="true" aria-label="Command menu">
        <input className={styles.input} autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Type a destination…" />
        <p className={styles.hint}>Visible navigation remains available in the rail. Use this shortcut for faster routing.</p>
        <ul className={styles.list}>{matches.map((command) => <li key={command.to}><button className={styles.item} onClick={() => { setOpen(false); void navigate({ to: command.to }); }}>{command.label}</button></li>)}</ul>
        {matches.length === 0 && <div className={styles.empty}>No matching destinations.</div>}
      </div>
    </div>
  );
}
