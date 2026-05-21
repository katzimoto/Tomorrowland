import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import hljs from "highlight.js/lib/core";
import json from "highlight.js/lib/languages/json";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";
import python from "highlight.js/lib/languages/python";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import bash from "highlight.js/lib/languages/bash";
import sql from "highlight.js/lib/languages/sql";
import "highlight.js/styles/github.min.css";
import { getDocumentText } from "@/api/documents";
import styles from "./CodeViewer.module.css";

hljs.registerLanguage("json", json);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("python", python);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("sql", sql);

const CODE_TRUNCATE = 50_000;

const MIME_TO_LANGUAGE: Record<string, string> = {
  "application/json": "json",
  "text/xml": "xml",
  "application/xml": "xml",
  "text/yaml": "yaml",
  "application/yaml": "yaml",
  "application/x-yaml": "yaml",
  "text/x-python": "python",
  "text/javascript": "javascript",
  "application/javascript": "javascript",
  "text/typescript": "typescript",
  "text/x-typescript": "typescript",
  "text/x-sh": "bash",
  "application/x-shellscript": "bash",
  "text/x-sql": "sql",
  "application/x-sql": "sql",
};

const EXT_TO_LANGUAGE: Record<string, string> = {
  ".json": "json",
  ".xml": "xml",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".py": "python",
  ".js": "javascript",
  ".jsx": "javascript",
  ".ts": "typescript",
  ".tsx": "typescript",
  ".sh": "bash",
  ".bash": "bash",
  ".sql": "sql",
  ".log": "plaintext",
};

function detectLanguage(mimeType: string, title?: string): string {
  const fromMime = MIME_TO_LANGUAGE[mimeType];
  if (fromMime) return fromMime;
  if (title) {
    const dotIdx = title.lastIndexOf(".");
    if (dotIdx !== -1) {
      const ext = title.slice(dotIdx).toLowerCase();
      const fromExt = EXT_TO_LANGUAGE[ext];
      if (fromExt) return fromExt;
    }
  }
  return "plaintext";
}

interface CodeViewerProps {
  docId: string;
  mimeType: string;
  title?: string;
}

export function CodeViewer({ docId, mimeType, title }: CodeViewerProps) {
  const [raw, setRaw] = useState(false);
  const [wrap, setWrap] = useState(false);
  const [copied, setCopied] = useState(false);

  const language = detectLanguage(mimeType, title);

  const { data, isLoading } = useQuery({
    queryKey: ["doc-code-text", docId],
    queryFn: () => getDocumentText(docId, { offset: 0, limit: CODE_TRUNCATE }),
    staleTime: 5 * 60_000,
  });

  const text = data?.text ?? "";
  const truncated = data?.truncated ?? false;
  const lineCount = text ? text.split("\n").length : 0;

  const highlighted = useMemo(() => {
    if (!text || raw || language === "plaintext") return null;
    try {
      return hljs.highlight(text, { language }).value;
    } catch {
      return null;
    }
  }, [text, language, raw]);

  function handleCopy() {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (isLoading) {
    return <div className={styles.loading}>Loading…</div>;
  }

  return (
    <div
      className={styles.viewer}
      role="region"
      aria-label={title ? `Code: ${title}` : "Code viewer"}
    >
      <div className={styles.toolbar}>
        <span className={styles.langLabel}>
          {language} · {lineCount.toLocaleString()} lines
        </span>
        <button
          className={`${styles.btn} ${wrap ? styles.btnActive : ""}`}
          onClick={() => setWrap((w) => !w)}
        >
          Wrap
        </button>
        <button
          className={`${styles.btn} ${raw ? styles.btnActive : ""}`}
          onClick={() => setRaw((r) => !r)}
        >
          Raw
        </button>
        <button className={styles.btn} aria-label="Copy code" onClick={handleCopy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {truncated && (
        <div className={styles.truncNotice}>
          Showing first 50,000 characters — download original for full file
        </div>
      )}

      <div className={styles.codeOuter}>
        <div className={styles.gutter} aria-hidden="true">
          {Array.from({ length: lineCount }, (_, i) => (
            <span key={i} className={styles.lineNum}>{i + 1}</span>
          ))}
        </div>
        <pre className={`${styles.pre} ${wrap ? styles.preWrap : ""}`}>
          {highlighted ? (
            <code dangerouslySetInnerHTML={{ __html: highlighted }} />
          ) : (
            <code>{text}</code>
          )}
        </pre>
      </div>
    </div>
  );
}
