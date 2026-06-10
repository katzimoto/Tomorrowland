import { AlertTriangle, RotateCcw } from "lucide-react";
import type { FallbackProps } from "react-error-boundary";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import styles from "./RouteErrorFallback.module.css";

export function RouteErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  const message = error instanceof Error ? error.message : "An unexpected error occurred.";
  return (
    <div className={styles.root} role="alert">
      <EmptyState
        icon={<AlertTriangle size={32} />}
        title="Something went wrong"
        body={message}
        action={
          <Button variant="secondary" onClick={resetErrorBoundary}>
            <RotateCcw size={14} />
            Try again
          </Button>
        }
      />
    </div>
  );
}
