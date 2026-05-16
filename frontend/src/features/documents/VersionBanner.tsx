import { Link } from "@tanstack/react-router";
import { useT } from "@/i18n/index";
import styles from "./VersionBanner.module.css";

interface VersionBannerProps {
  latestDocumentId: string;
}

export function VersionBanner({ latestDocumentId }: VersionBannerProps) {
  const t = useT();
  return (
    <div className={styles.banner} role="alert">
      <span className={styles.text}>{t.insight.versionBannerTitle}</span>
      <Link to="/doc/$docId" params={{ docId: latestDocumentId }} className={styles.link}>
        {t.insight.versionBannerLink}
      </Link>
    </div>
  );
}
