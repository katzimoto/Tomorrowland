import { useLanguage, LANGUAGES } from "@/i18n/index";
import styles from "./LanguageSelector.module.css";

export function LanguageSelector() {
  const { language, setLanguage, t } = useLanguage();

  return (
    <div className={styles.wrap}>
      <label className={styles.label} htmlFor="language-select">
        {t.lang.label}
      </label>
      <select
        id="language-select"
        className={styles.select}
        value={language}
        onChange={(e) => setLanguage(e.target.value as "en" | "he")}
        aria-label={t.lang.label}
      >
        {LANGUAGES.map(({ value, label }) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );
}
