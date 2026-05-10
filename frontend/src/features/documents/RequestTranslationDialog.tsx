import { useMutation } from "@tanstack/react-query";
import { Languages } from "lucide-react";
import { requestTranslation } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./RequestTranslationDialog.module.css";

interface RequestTranslationDialogProps {
  docId: string;
  open: boolean;
  onClose: () => void;
}

export function RequestTranslationDialog({ docId, open, onClose }: RequestTranslationDialogProps) {
  const { show: showToast } = useToast();

  const mutation = useMutation({
    mutationFn: () => requestTranslation(docId),
    onSuccess: () => {
      showToast("success", "High-quality translation queued.");
      onClose();
    },
    onError: () => showToast("error", "Failed to queue translation request."),
  });

  return (
    <Dialog open={open} onClose={onClose} title="Request high-quality translation">
      <div className={styles.body}>
        <p className={styles.description}>
          Request a high-quality translation of this document. The translation will be
          processed in the background and available shortly.
        </p>
        {mutation.isSuccess && (
          <p className={styles.pendingNote} role="status">
            Translation queued successfully. This tab will update when ready.
          </p>
        )}
        <div className={styles.actions}>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={mutation.isPending || mutation.isSuccess}
          >
            <Languages size={14} />
            Request translation
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
