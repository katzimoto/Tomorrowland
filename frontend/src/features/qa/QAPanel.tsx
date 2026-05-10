import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { askQuestion, type QAResponse } from "@/api/qa";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import { measurePerformance } from "@/lib/performanceTelemetry";
import { QuestionInput } from "./QuestionInput";
import { AnswerPanel } from "./AnswerPanel";
import styles from "./QAPanel.module.css";

interface QAPanelProps {
  returnPath?: string;
}

export function QAPanel({ returnPath }: QAPanelProps) {
  const t = useT();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QAResponse | null>(null);
  const [hasError, setHasError] = useState(false);
  const { show: showToast } = useToast();

  const mutation = useMutation({
    mutationFn: () =>
      measurePerformance("qa.answer", () => askQuestion(question.trim())),
    onSuccess: (data) => {
      setHasError(false);
      setResult(data);
    },
    onError: () => {
      setHasError(true);
      showToast("error", t.qa.toastError);
    },
  });

  function handleSubmit() {
    if (question.trim()) mutation.mutate();
  }

  return (
    <div className={styles.panel}>
      <div className={styles.inputRow}>
        <QuestionInput
          value={question}
          onChange={setQuestion}
          onSubmit={handleSubmit}
          disabled={mutation.isPending}
        />
        <Button
          onClick={handleSubmit}
          disabled={!question.trim() || mutation.isPending}
          loading={mutation.isPending}
        >
          {t.qa.ask}
        </Button>
      </div>

      {hasError && !result && (
        <EmptyState title={t.qa.failedTitle} body={t.qa.failedBody} />
      )}

      {!result && !hasError && !mutation.isPending && (
        <EmptyState title={t.qa.emptyTitle} body={t.qa.emptyBody} />
      )}

      {result && <AnswerPanel result={result} returnPath={returnPath} />}
    </div>
  );
}
