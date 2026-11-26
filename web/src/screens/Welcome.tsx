import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";
import { LANGUAGES, setLanguage } from "@/i18n";
import { speak } from "@/lib/voice";

export default function Welcome() {
  const { t } = useTranslation();
  const nav = useNavigate();
  return (
    <Screen title={t("welcome.title")} spoken={[t("welcome.intro"), t("welcome.pick_language")]}>
      <p className="text-lg">{t("welcome.intro")}</p>
      <p className="font-semibold">{t("welcome.pick_language")}</p>
      <div className="grid grid-cols-2 gap-3" role="group" aria-label={t("welcome.pick_language")}>
        {LANGUAGES.map((l) => (
          <BigButton
            key={l.code}
            variant="secondary"
            onClick={() => {
              setLanguage(l.code);
              void speak([l.spoken], l.code);
            }}
          >
            {l.label}
          </BigButton>
        ))}
      </div>
      <BigButton icon="➡️" onClick={() => nav("/start")}>
        {t("welcome.start")}
      </BigButton>
      <BigButton variant="ghost" onClick={() => nav("/never")}>
        {t("welcome.never")}
      </BigButton>
    </Screen>
  );
}
