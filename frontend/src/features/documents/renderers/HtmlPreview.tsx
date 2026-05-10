import styles from "./renderers.module.css";

function sanitizeHtml(raw: string): string {
  const doc = new DOMParser().parseFromString(raw, "text/html");
  doc.querySelectorAll("script, style, iframe, object, embed").forEach((el) => el.remove());
  return doc.body.innerHTML;
}

interface HtmlPreviewProps {
  html: string;
}

export function HtmlPreview({ html }: HtmlPreviewProps) {
  return (
    <div
      className={styles.htmlContent}
      dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
    />
  );
}
