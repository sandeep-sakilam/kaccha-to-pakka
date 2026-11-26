import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function LinkBank() {
  const { t } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  const [monthly, setMonthly] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function link() {
    setError(null);
    try {
      const res = await api<{ consent_id: string; redirect_url: string; sandbox: boolean }>(`/businesses/${businessId}/aa/consent`, {
        method: "POST",
        json: { monthly_refresh: monthly },
      });
      const back = `business=${businessId}&consent=${res.consent_id}`;
      if (res.sandbox) nav(`${res.redirect_url}?${back}`);
      else window.location.href = res.redirect_url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  return (
    <Screen title={t("aa.title")} spoken={[t("aa.why")]}>
      <p className="text-lg">{t("aa.why")}</p>
      <label className="flex min-h-12 items-center gap-3 text-lg">
        <input type="checkbox" className="h-6 w-6" checked={monthly} onChange={(e) => setMonthly(e.target.checked)} />
        {t("aa.monthly")}
      </label>
      <BigButton icon="🏦" onClick={link}>
        {t("aa.link")}
      </BigButton>
      {error && (
        <p role="alert" className="rounded-xl bg-red-100 p-3">
          {error}
        </p>
      )}
    </Screen>
  );
}
