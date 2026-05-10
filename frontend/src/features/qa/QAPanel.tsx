import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { askQuestion, type QAResponse } from "@/api/qa";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import { QuestionInput } from "./QuestionInput";
import { AnswerPanel } from "./AnswerPanel";
import styles from "./QAPanel.module.css";

interface QAPanelProps {
  returnPath?: string;
}

export function QAPanel({ returnPath }: QAPanelProps) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QAResponse | null>(null);
  const [hasError, setHasError] = useState(false);
  const { show: showToast } = useToast();

  const mutation = useMutation({
    mutationFn: () => askQuestion(question.trim()),
    onSuccess: (data) => { setHasError(false); setResult(data); },
    onError: () => { setHasError(true); showToast("error", "Q&A request failed. Check that the backend is reachable."); },
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
          Ask
        </Button>
      </div>

      {hasError && !result && (
        <EmptyState
          title="Request failed"
          body="The Q&A service is not reachable. Check the server and try again."
        />
      )}

      {!result && !hasError && !mutation.isPending && (
        <EmptyState
          title="Ask anything"
          body="Type a question and press Ask. Answers are grounded in your accessible documents."
        />
      )}

      {result && <AnswerPanel result={result} returnPath={returnPath} />}
    </div>
  );
}
