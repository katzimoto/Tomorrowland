import { useState, useEffect, type ReactNode } from "react";
import {
  type Language,
  LanguageContext,
  getInitialLanguage,
  persistLanguage,
  applyLanguageToDocument,
  getTranslations,
} from "./index";

interface LanguageProviderProps {
  children: ReactNode;
}

export function LanguageProvider({ children }: LanguageProviderProps) {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage);

  useEffect(() => {
    applyLanguageToDocument(language);
  }, [language]);

  function setLanguage(lang: Language) {
    setLanguageState(lang);
    persistLanguage(lang);
  }

  return (
    <LanguageContext.Provider
      value={{ language, setLanguage, t: getTranslations(language) }}
    >
      {children}
    </LanguageContext.Provider>
  );
}
