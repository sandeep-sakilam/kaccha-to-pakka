import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { DisputeList, type DisputeRow } from "@/components/DisputeList";
import { ReasonInput } from "@/components/ReasonInput";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { speak } from "@/lib/voice";

type Target = "assessment" | "ledger_entry" | "attestation";
type Option = { id: string; label: string };

export default function Disputes() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const [rows, setRows] = useState<DisputeRow[]>([]);
  const [target, setTarget] = useState<Target | null>(null);
  const [options, setOptions] = useState<Option[]>([]);
  const [targetId, setTargetId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => setRows(await api<DisputeRow[]>(`/businesses/${businessId}/disputes`)), [businessId]);
  useEffect(() => {
    void load();
  }, [load]);

  async function choose(kind: Target) {
    setTarget(kind);
    setTargetId(null);
    if (kind === "assessment") {
      const a = await api<{ id: string; band: string }>(`/businesses/${businessId}/assessments/latest`);
      setOptions([{ id: a.id, label: `${t("disputes.t_assessment")}: ${a.band}` }]);
      setTargetId(a.id);
    } else if (kind === "ledger_entry") {
      const entries = await api<{ id: string; entry_date: string | null; party_text: string | null; amount_paise: number }[]>(`/businesses/${businessId}/ledger`);
      setOptions(entries.map((e) => ({ id: e.id, label: `${e.entry_date ?? ""} ${e.party_text ?? ""} ₹${e.amount_paise / 100}` })));
    } else {
      const atts = await api<{ id: string; claim: { relationship?: string; years_trading?: string }; status: string }[]>(`/businesses/${businessId}/attestations`);
      setOptions(atts.map((a) => ({ id: a.id, label: `${a.claim.relationship ?? ""} ${a.claim.years_trading ?? ""} (${a.status})` })));
    }
  }

  async function send() {
    if (!target || !targetId) return;
    try {
      await api(`/businesses/${businessId}/disputes`, { method: "POST", json: { target_type: target, target_id: targetId, reason } });
      setMessage(t("disputes.sent"));
      void speak([t("disputes.sent")], i18n.language);
      setTarget(null);
      setReason("");
      await load();
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  return (
    <Screen title={t("disputes.title")} spoken={[t("disputes.intro")]}>
      <p>{t("disputes.intro")}</p>
      <Card className="flex flex-col gap-3">
        <p className="font-semibold">{t("disputes.what")}</p>
        <div className="grid grid-cols-1 gap-2">
          {(["assessment", "ledger_entry", "attestation"] as const).map((k) => (
            <BigButton key={k} variant={target === k ? "primary" : "secondary"} aria-pressed={target === k} onClick={() => void choose(k)}>
              {t(`disputes.t_${k}`)}
            </BigButton>
          ))}
        </div>
        {target && target !== "assessment" && (
          <label className="flex flex-col gap-1">
            {t("disputes.pick")}
            <select className="field" value={targetId ?? ""} onChange={(e) => setTargetId(e.target.value || null)}>
              <option value="">—</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        )}
        {target && <ReasonInput value={reason} onChange={setReason} />}
        {target && (
          <BigButton disabled={!targetId || reason.trim().length < 3} onClick={() => void send()}>
            {t("disputes.send")}
          </BigButton>
        )}
        {message && <p role="status">{message}</p>}
      </Card>
      <h2 className="text-lg font-semibold">{t("disputes.mine")}</h2>
      <DisputeList rows={rows} />
    </Screen>
  );
}
