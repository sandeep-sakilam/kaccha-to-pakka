import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Keypad } from "@/components/Keypad";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { rupeesInWords } from "@/lib/voice";

type Partner = {
  counterparty_id: string;
  masked_id: string;
  registered_name: string | null;
  relationship: "supplier" | "customer";
  value_paise: number;
  months_active: number;
  invite_status: string | null;
};

export default function Partners() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const [list, setList] = useState<Partner[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => setList(await api<Partner[]>(`/businesses/${businessId}/counterparties/top`)), [businessId]);
  useEffect(() => {
    void load();
  }, [load]);

  async function send(id: string) {
    setError(null);
    try {
      await api(`/businesses/${businessId}/invites`, { method: "POST", json: { counterparty_id: id, phone, language: i18n.language } });
      setOpen(null);
      setPhone("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  return (
    <Screen title={t("partners.title")} spoken={[t("partners.intro")]}>
      <p>{t("partners.intro")}</p>
      {list && list.length === 0 && <p role="status">{t("partners.none")}</p>}
      {list?.map((p) => (
        <Card key={p.counterparty_id}>
          <p className="text-lg font-semibold">{p.registered_name ?? p.masked_id}</p>
          <p className="text-sm text-gray-700">
            {t(`partners.${p.relationship}`)} · {p.masked_id} · {t("partners.months", { count: p.months_active })}
          </p>
          <p className="text-sm">{rupeesInWords(p.value_paise, i18n.language)}</p>
          {p.invite_status ? (
            <p className="mt-2 font-semibold text-brand" data-testid="invite-status">
              {t(`partners.status_${p.invite_status}`)}
            </p>
          ) : open === p.counterparty_id ? (
            <div className="mt-2 flex flex-col gap-2">
              <p>{t("partners.enter_phone")}</p>
              <p className="rounded-xl border-2 border-gray-300 p-2 text-center text-xl">+91 {phone || "__________"}</p>
              <Keypad value={phone} onChange={setPhone} max={10} />
              <BigButton disabled={phone.length !== 10} onClick={() => void send(p.counterparty_id)}>
                {t("partners.send")}
              </BigButton>
            </div>
          ) : (
            <BigButton className="mt-2" variant="secondary" onClick={() => setOpen(p.counterparty_id)}>
              {t("partners.send")}
            </BigButton>
          )}
        </Card>
      ))}
      {error && (
        <p role="alert" className="rounded-xl bg-red-100 p-3">
          {error}
        </p>
      )}
    </Screen>
  );
}
