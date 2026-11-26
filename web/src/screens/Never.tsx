import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";

const KEYS = ["lend", "sell", "share", "train", "delete"] as const;

export default function Never() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const lines = KEYS.map((k) => t(`never.${k}`));
  return (
    <Screen title={t("never.title")} spoken={lines}>
      <Card>
        <ul className="flex flex-col gap-3 text-lg">
          {lines.map((line) => (
            <li key={line} className="flex gap-3">
              <span aria-hidden="true">🚫</span>
              {line}
            </li>
          ))}
        </ul>
      </Card>
      <BigButton variant="secondary" onClick={() => nav(-1)}>
        {t("common.back")}
      </BigButton>
    </Screen>
  );
}
