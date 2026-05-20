import styles from "./renderers.module.css";

interface HtmlPreviewProps {
  html: string;
}

export function HtmlPreview({ html }: HtmlPreviewProps) {
  return (
    <iframe
      srcDoc={html}
      sandbox="allow-same-origin"
      title="HTML document preview"
      className={styles.htmlFrame}
    />
  );
}
