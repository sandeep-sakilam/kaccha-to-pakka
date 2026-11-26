import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function SahayakHome() {
  const { t } = useTranslation();
  const { me, refresh } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [woman, setWoman] = useState(false);
  const [owners, setOwners] = useState<{ id: string; name: string }[]>([]);
  const isSahayak = me?.roles.includes("sahayak");

  const load = useCallback(async () => {
    if (isSahayak) setOwners(await api(`/sahayak/businesses`));
  }, [isSahayak]);
  useEffect(() => {
    void load();
  }, [load]);

  async function register() {
    await api("/sahayak/register", { method: "POST", json: { name, gender: woman ? "female" : null } });
    await refresh();
  }

  return (
    <Screen title={t("sahayak.title")} spoken={[t("sahayak.register_intro")]}>
      <p>{t("sahayak.register_intro")}</p>
      {!isSahayak && (
        <Card className="flex flex-col gap-3">
          <input aria-label={t("sahayak.name")} placeholder={t("sahayak.name")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3" value={name} onChange={(e) => setName(e.target.value)} />
          <label className="flex min-h-12 items-center gap-3">
            <input type="checkbox" className="h-6 w-6" checked={woman} onChange={(e) => setWoman(e.target.checked)} />
            {t("sahayak.woman")}
          </label>
          <BigButton disabled={name.trim().length < 2} onClick={register}>
            {t("sahayak.register")}
          </BigButton>
        </Card>
      )}
      {isSahayak && (
        <>
          <h2 className="text-lg font-semibold">{t("sahayak.owners")}</h2>
          {owners.length === 0 && <p>{t("sahayak.none")}</p>}
          {owners.map((o) => (
            <Card key={o.id} className="flex flex-col gap-2">
              <p className="font-semibold">{o.name}</p>
              <div className="grid grid-cols-3 gap-2">
                <BigButton onClick={() => nav(`/capture/${o.id}/ledger_page`)}>{t("sahayak.photo")}</BigButton>
                <BigButton variant="secondary" onClick={() => nav(`/voice-entry/${o.id}`)}>
                  {t("sahayak.voice")}
                </BigButton>
                <BigButton variant="secondary" onClick={() => nav(`/readback/${o.id}`)}>
                  {t("sahayak.check")}
                </BigButton>
              </div>
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}
