import styles from "./renderers.module.css";

interface TextPreviewProps {
  text: string;
}

export function TextPreview({ text }: TextPreviewProps) {
  return <pre className={styles.textContent}>{text || "No text content available."}</pre>;
}
