import { createContext, useContext } from "react";
import { en, type Translations } from "./locales/en";
import { he } from "./locales/he";

export type { Translations };
export { en, he };

export type Language = "en" | "he";

export const LANGUAGES: { value: Language; label: string }[] = [
  { value: "en", label: "English" },
  { value: "he", label: "עברית" },
];

const STORAGE_KEY = "tomorrowland_lang";

export function getInitialLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "he") return stored;
  } catch {
    // ignore storage errors
  }
  return "en";
}

export function persistLanguage(lang: Language): void {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // ignore storage errors
  }
}

export function applyLanguageToDocument(lang: Language): void {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
}

const LOCALE_MAP: Record<Language, Translations> = { en, he };

export function getTranslations(lang: Language): Translations {
  return LOCALE_MAP[lang];
}

export interface LanguageContextValue {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: Translations;
}

export const LanguageContext = createContext<LanguageContextValue>({
  language: "en",
  setLanguage: () => undefined,
  t: en,
});

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}

export function useT(): Translations {
  return useContext(LanguageContext).t;
}
