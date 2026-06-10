import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import styles from "./RouteErrorFallback.module.css";

interface Props {
  error: Error;
  resetErrorBoundary: () => void;
}

export function RouteErrorFallback({ error, resetErrorBoundary }: Props) {
  return (
    <div className={styles.root} role="alert">
      <EmptyState
        icon={<AlertTriangle size={32} />}
        title="Something went wrong"
        body={error.message}
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
