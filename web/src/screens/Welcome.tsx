import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";
import { LANGUAGES, setLanguage } from "@/i18n";
import { speak } from "@/lib/voice";

export default function Welcome() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  return (
    <Screen title={t("welcome.title")} spoken={[t("welcome.intro"), t("welcome.pick_language")]}>
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-700 to-brand-900 p-6 text-white shadow-lift">
        <div aria-hidden="true" className="absolute -right-8 -top-8 h-36 w-36 rounded-full bg-white/10" />
        <p aria-hidden="true" className="relative text-4xl">
          🏪 → 🛂
        </p>
        <p className="relative mt-3 text-xl font-semibold leading-snug">{t("welcome.intro")}</p>
      </div>
      <p className="section-title px-1">{t("welcome.pick_language")}</p>
      <div className="grid grid-cols-2 gap-3" role="group" aria-label={t("welcome.pick_language")}>
        {LANGUAGES.map((l) => (
          <BigButton
            key={l.code}
            variant={i18n.language === l.code ? "primary" : "secondary"}
            aria-pressed={i18n.language === l.code}
            onClick={() => {
              setLanguage(l.code);
              void speak([l.spoken], l.code);
            }}
          >
            {l.label}
          </BigButton>
        ))}
      </div>
      <BigButton icon="→" onClick={() => nav("/start")}>
        {t("welcome.start")}
      </BigButton>
      <BigButton variant="ghost" onClick={() => nav("/never")}>
        {t("welcome.never")}
      </BigButton>
    </Screen>
  );
}
