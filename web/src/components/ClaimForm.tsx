import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "@/lib/api";
import { speak } from "@/lib/voice";
import { BigButton } from "./ui";

const VALUES = ["0-10k", "10k-25k", "25k-50k", "50k-1L", "1L-5L", "5L+"];
const YEARS: [string, string][] = [
  ["<1", "years_lt1"],
  ["1-3", "years_1_3"],
  ["3-5", "years_3_5"],
  ["5+", "years_5p"],
];

function Choice({ label, options, value, onPick }: { label: string; options: [string, string][]; value: string | null; onPick: (v: string) => void }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 font-semibold">{label}</legend>
      <div className="grid grid-cols-2 gap-2">
        {options.map(([v, text]) => (
          <BigButton key={v} variant={value === v ? "primary" : "secondary"} aria-pressed={value === v} onClick={() => onPick(v)}>
            {text}
          </BigButton>
        ))}
      </div>
    </fieldset>
  );
}

export function ClaimForm({ token, defaultRelationship }: { token: string; defaultRelationship: string }) {
  const { t, i18n } = useTranslation();
  const [rel, setRel] = useState<string | null>(defaultRelationship);
  const [years, setYears] = useState<string | null>(null);
  const [value, setValue] = useState<string | null>(null);
  const [behaviour, setBehaviour] = useState<string | null>(null);
  const [gstin, setGstin] = useState("");
  const [name, setName] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      const id = gstin.trim().toUpperCase();
      const res = await api<{ status: string }>(`/invites/${token}/claim`, {
        method: "POST",
        json: {
          relationship: rel,
          years_trading: years,
          monthly_value: value,
          payment_behaviour: behaviour,
          gstin: id.startsWith("UDYAM") ? null : id || null,
          udyam: id.startsWith("UDYAM") ? id : null,
          business_name: name || null,
        },
      });
      const msg = t(res.status === "confirmed" ? "claim.done" : "claim.discrepancy");
      setDone(msg);
      void speak([msg], i18n.language);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  if (done)
    return (
      <p role="status" className="rounded-xl bg-brand-light p-3 text-lg" data-testid="claim-status">
        {done}
      </p>
    );
  return (
    <div className="flex flex-col gap-4">
      <p>{t("claim.intro")}</p>
      <Choice label={t("claim.q_relationship")} value={rel} onPick={setRel} options={[["supplier", t("partners.supplier")], ["customer", t("partners.customer")]]} />
      <Choice label={t("claim.q_years")} value={years} onPick={setYears} options={YEARS.map(([v, k]) => [v, t(`claim.${k}`)])} />
      <Choice label={t("claim.q_value")} value={value} onPick={setValue} options={VALUES.map((v) => [v, `₹${v}`])} />
      <Choice label={t("claim.q_behaviour")} value={behaviour} onPick={setBehaviour} options={["on_time", "sometimes_late", "often_late"].map((v) => [v, t(`claim.${v}`)])} />
      <input aria-label={t("claim.business_name")} placeholder={t("claim.business_name")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3" value={name} onChange={(e) => setName(e.target.value)} />
      <input aria-label={t("claim.id_optional")} placeholder={t("claim.id_optional")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3 uppercase" value={gstin} onChange={(e) => setGstin(e.target.value)} />
      <p className="text-sm text-gray-700">{t("claim.not_guarantor")}</p>
      <BigButton disabled={!rel || !years || !value || !behaviour} onClick={submit}>
        {t("claim.submit")}
      </BigButton>
      {error && (
        <p role="alert" className="rounded-xl bg-red-100 p-3">
          {error}
        </p>
      )}
    </div>
  );
}
