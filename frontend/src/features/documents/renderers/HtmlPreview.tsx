import styles from "./renderers.module.css";

interface HtmlPreviewProps {
  html: string;
}

/** Dark-mode override injected into the iframe so HTML previews
 *  match the workspace surface instead of showing a white sheet. */
const DARK_OVERRIDE = `
<style>
  :root { color-scheme: dark; }
  html, body {
    background: #0d1117 !important;
    color: #e6edf3 !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
    font-size: 14px;
    line-height: 1.65;
  }
  a { color: #58a6ff; }
  h1, h2, h3, h4, h5, h6 { color: #e6edf3; }
  p { color: #8b949e; }
  p strong, b { color: #e6edf3; }
  code, pre {
    background: #161b22;
    color: #e6edf3;
    border-radius: 4px;
    font-family: "JetBrains Mono", ui-monospace, monospace;
  }
  table { border-collapse: collapse; }
  th, td {
    border: 1px solid #30363d;
    padding: 6px 12px;
  }
  th { background: #161b22; }
  blockquote {
    border-left: 3px solid #30363d;
    margin: 0;
    padding-left: 12px;
    color: #8b949e;
  }
  hr { border-color: #30363d; }
  mark {
    background: rgba(210, 153, 34, 0.22);
    color: #e6edf3;
  }
</style>
`;

function prependDarkOverride(html: string): string {
  const headMatch = html.match(/<head[^>]*>/i);
  if (headMatch && headMatch.index !== undefined) {
    const insertAt = headMatch.index + headMatch[0].length;
    return html.slice(0, insertAt) + DARK_OVERRIDE + html.slice(insertAt);
  }
  // No <head> — prepend before everything
  return DARK_OVERRIDE + html;
}

export function HtmlPreview({ html }: HtmlPreviewProps) {
  return (
    <iframe
      srcDoc={prependDarkOverride(html)}
      sandbox="allow-same-origin"
      title="HTML document preview"
      className={styles.htmlFrame}
    />
  );
}
