import { createContext, PropsWithChildren, useContext, useEffect, useMemo, useState } from "react";

export type Language = "en" | "ka";

const LANGUAGE_STORAGE_KEY = "expertpay_language";

type I18nContextValue = {
  language: Language;
  locale: string;
  isGeorgian: boolean;
  setLanguage: (language: Language) => void;
  pick: (english: string, georgian: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

function readStoredLanguage(): Language {
  if (typeof window === "undefined") return "ka";
  const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (stored === "en") return "en";
  return "ka";
}

export function I18nProvider({ children }: PropsWithChildren) {
  const [language, setLanguage] = useState<Language>(readStoredLanguage);

  useEffect(() => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    document.documentElement.lang = language === "ka" ? "ka" : "en";
  }, [language]);

  const value = useMemo<I18nContextValue>(() => {
    return {
      language,
      locale: language === "ka" ? "ka-GE" : "en-US",
      isGeorgian: language === "ka",
      setLanguage,
      pick: (english, georgian) => (language === "ka" ? georgian : english)
    };
  }, [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used inside I18nProvider.");
  }
  return context;
}
