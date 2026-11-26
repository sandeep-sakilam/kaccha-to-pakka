import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, SandboxBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { speak } from "@/lib/voice";

type Fetched = { accounts: { bank: string; txns: number }[] };

/** Stands in for the owner's AA app while Account Aggregator is the Sandbox mock. */
export default function SandboxAA() {
  const { t, i18n } = useTranslation();
  const { handle = "" } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(approve: boolean) {
    setBusy(true);
    try {
      await api(`/sandbox/aa/${handle}/decide`, { method: "POST", json: { approve } });
      if (!approve) {
        setStatus(t("aa.rejected"));
        return;
      }
      setStatus(t("aa.fetching"));
      const res = await api<Fetched>(`/businesses/${params.get("business")}/aa/${params.get("consent")}/fetch`, { method: "POST" });
      const total = res.accounts.reduce((n, a) => n + a.txns, 0);
      const msg = t("aa.done", { count: total, bank: res.accounts[0]?.bank ?? "" });
      setStatus(msg);
      void speak([msg], i18n.language);
    } catch (e) {
      setStatus(e instanceof ApiError ? e.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen title={t("aa.sandbox_title")} spoken={[t("aa.sandbox_hint")]}>
      <SandboxBadge label={t("common.sandbox")} />
      <p>{t("aa.sandbox_hint")}</p>
      {!status && (
        <div className="grid grid-cols-2 gap-3">
          <BigButton disabled={busy} onClick={() => void decide(true)}>
            {t("aa.approve")}
          </BigButton>
          <BigButton variant="secondary" disabled={busy} onClick={() => void decide(false)}>
            {t("aa.reject")}
          </BigButton>
        </div>
      )}
      {status && (
        <>
          <p role="status" className="rounded-xl bg-brand-light p-3 text-lg" data-testid="aa-status">
            {status}
          </p>
          <BigButton onClick={() => nav("/home")}>{t("capture.done")}</BigButton>
        </>
      )}
    </Screen>
  );
}
