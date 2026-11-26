import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import hi from "./hi.json";

export const LANGUAGES = [
  { code: "hi", label: "हिन्दी", spoken: "हिन्दी के लिए यहाँ दबाएँ" },
  { code: "en", label: "English", spoken: "Tap here for English" },
] as const;

export type Lang = (typeof LANGUAGES)[number]["code"];

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("ktp.lang");
    if (saved === "hi" || saved === "en") return saved;
  } catch {
    /* storage unavailable */
  }
  return "hi";
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi } },
  lng: initialLang(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

if (typeof document !== "undefined") document.documentElement.lang = i18n.language;

export function setLanguage(lang: Lang): void {
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
  try {
    localStorage.setItem("ktp.lang", lang);
  } catch {
    /* ignore */
  }
}

export default i18n;
