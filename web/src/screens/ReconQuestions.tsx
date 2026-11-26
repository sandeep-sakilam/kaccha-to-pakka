import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { speak } from "@/lib/voice";

type Q = { party_text: string; counterparty_name: string; prompt: string };

export default function ReconQuestions() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  const [qs, setQs] = useState<Q[] | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(async () => {
    const list = await api<Q[]>(`/businesses/${businessId}/recon/questions?language=${i18n.language}`);
    setQs(list);
    if (list[0]) void speak([list[0].prompt], i18n.language);
  }, [businessId, i18n.language]);

  useEffect(() => {
    void load();
  }, [load]);

  async function answer(same: boolean) {
    const q = qs?.[0];
    if (!q) return;
    const stats = await api<{ match_rate: number }>(`/businesses/${businessId}/recon/answer`, {
      method: "POST",
      json: { party_text: q.party_text, counterparty_name: q.counterparty_name, same },
    });
    const msg = t("recon.done", { rate: Math.round(stats.match_rate * 100) });
    setDone(msg);
    await load();
  }

  const q = qs?.[0];
  return (
    <Screen title={t("recon.title")} spoken={q ? [t("recon.intro"), q.prompt] : [done ?? ""]}>
      <p>{t("recon.intro")}</p>
      {q && (
        <Card>
          <p className="text-2xl font-semibold" data-testid="recon-prompt">
            {q.prompt}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <BigButton onClick={() => void answer(true)}>{t("common.yes")}</BigButton>
            <BigButton variant="secondary" onClick={() => void answer(false)}>
              {t("common.no")}
            </BigButton>
          </div>
        </Card>
      )}
      {done && <p role="status">{done}</p>}
      {qs && !q && <BigButton onClick={() => nav("/home")}>{t("capture.done")}</BigButton>}
    </Screen>
  );
}
