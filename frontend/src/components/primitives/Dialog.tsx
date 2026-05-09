import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { IconButton } from "./IconButton";
import styles from "./Dialog.module.css";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  width?: string;
}

export function Dialog({ open, onClose, title, children, width = "480px" }: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open) {
      el.showModal();
    } else {
      el.close();
    }
  }, [open]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    const handler = () => onClose();
    el.addEventListener("close", handler);
    return () => el.removeEventListener("close", handler);
  }, [onClose]);

  if (!open) return null;

  return (
    <dialog ref={dialogRef} className={styles.dialog} style={{ width }} onClick={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <div className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
        <IconButton label="Close dialog" size="sm" onClick={onClose}>
          <X size={16} />
        </IconButton>
      </div>
      <div className={styles.body}>{children}</div>
    </dialog>
  );
}
