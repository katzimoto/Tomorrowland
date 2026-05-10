import { useCallback, useState } from "react";
import { CheckCircle, AlertCircle, Info, X } from "lucide-react";
import { IconButton } from "./IconButton";
import { ToastContext, type ToastKind } from "./ToastContext";
import styles from "./Toast.module.css";

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

let _nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback((kind: ToastKind, message: string) => {
    const id = ++_nextId;
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => dismiss(id), 4000);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div className={styles.region} role="region" aria-live="polite" aria-label="Notifications">
        {toasts.map((toast) => (
          <div key={toast.id} className={`${styles.toast} ${styles[toast.kind]}`} role="status">
            <span className={styles.icon} aria-hidden>
              {toast.kind === "success" && <CheckCircle size={16} />}
              {toast.kind === "error" && <AlertCircle size={16} />}
              {toast.kind === "info" && <Info size={16} />}
            </span>
            <span className={styles.message}>{toast.message}</span>
            <IconButton label="Dismiss" size="sm" onClick={() => dismiss(toast.id)}>
              <X size={14} />
            </IconButton>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
