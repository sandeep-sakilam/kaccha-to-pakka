import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";

type Notice = { lines: string[] };

export default function Consent() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [lines, setLines] = useState<string[]>([]);
  const [declined, setDeclined] = useState(false);

  useEffect(() => {
    api<Notice>(`/consents/notice?language=${i18n.language}`)
      .then((n) => setLines(n.lines))
      .catch(() => setLines([]));
  }, [i18n.language]);

  async function agree() {
    await api("/consents", { method: "POST", json: { purpose: "build_passport" } });
    nav("/interview");
  }

  return (
    <Screen title={t("consent.title")} spoken={lines}>
      <Card>
        <ul className="flex flex-col gap-3 text-lg">
          {lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </Card>
      <BigButton icon="✅" onClick={agree}>
        {t("consent.agree")}
      </BigButton>
      <BigButton variant="secondary" onClick={() => setDeclined(true)}>
        {t("consent.disagree")}
      </BigButton>
      {declined && <p role="status">{t("consent.no_hint")}</p>}
    </Screen>
  );
}
