import { useI18n } from "../lib/i18n";

type Props = {
  compact?: boolean;
};

export default function LanguageToggle({ compact = false }: Props) {
  const { language, setLanguage, pick } = useI18n();

  return (
    <div
      className={`languageSwitch ${compact ? "languageSwitchCompact" : ""}`}
      role="group"
      aria-label={pick("Language switcher", "ენის შეცვლა")}
    >
      <button
        className={`languageButton ${language === "en" ? "languageButtonActive" : ""}`}
        type="button"
        onClick={() => setLanguage("en")}
      >
        EN
      </button>
      <button
        className={`languageButton ${language === "ka" ? "languageButtonActive" : ""}`}
        type="button"
        onClick={() => setLanguage("ka")}
      >
        ქა
      </button>
    </div>
  );
}
