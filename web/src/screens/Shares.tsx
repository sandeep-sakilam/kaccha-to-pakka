import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { istDateTime } from "@/lib/format";

type Share = { id: string; lender_org: string; scope: string; expires_at: string; state: string; link: string; views: number };
type Access = { lender_org: string; viewer: string; viewed_at: string };

export default function Shares() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const [shares, setShares] = useState<Share[]>([]);
  const [logs, setLogs] = useState<Access[]>([]);
  const [lender, setLender] = useState("");
  const [scope, setScope] = useState<"summary" | "evidence">("summary");
  const [days, setDays] = useState(30);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setShares(await api<Share[]>(`/businesses/${businessId}/shares`));
    setLogs(await api<Access[]>(`/businesses/${businessId}/access-logs`));
  }, [businessId]);
  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    setError(null);
    try {
      await api(`/businesses/${businessId}/shares`, { method: "POST", json: { lender_org: lender, scope, days } });
      setLender("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  return (
    <Screen title={t("shares.title")} spoken={[t("shares.intro")]}>
      <p>{t("shares.intro")}</p>
      <Card className="flex flex-col gap-3">
        <input aria-label={t("shares.lender")} placeholder={t("shares.lender")} className="field" value={lender} onChange={(e) => setLender(e.target.value)} />
        <div className="grid grid-cols-2 gap-2">
          {(["summary", "evidence"] as const).map((s) => (
            <BigButton key={s} variant={scope === s ? "primary" : "secondary"} aria-pressed={scope === s} onClick={() => setScope(s)}>
              {t(`shares.scope_${s}`)}
            </BigButton>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {[7, 30, 90].map((d) => (
            <BigButton key={d} variant={days === d ? "primary" : "secondary"} aria-pressed={days === d} onClick={() => setDays(d)}>
              {t("shares.days", { count: d })}
            </BigButton>
          ))}
        </div>
        <BigButton disabled={lender.trim().length < 2} onClick={create}>
          {t("shares.create")}
        </BigButton>
        {error && <p role="alert">{error}</p>}
      </Card>
      {shares.map((s) => (
        <Card key={s.id} className="flex flex-col gap-2">
          <p className="font-semibold">{s.lender_org}</p>
          <p className="text-sm">
            {t(`shares.${s.state}`)} · {t(`shares.scope_${s.scope}`)} · {t("shares.views", { count: s.views })}
          </p>
          {s.state === "active" && (
            <>
              <p className="break-all text-sm" data-testid="share-link">
                {s.link}
              </p>
              <a className="flex min-h-12 items-center justify-center rounded-xl bg-green-700 font-semibold text-white" href={`https://wa.me/?text=${encodeURIComponent(s.link)}`} target="_blank" rel="noreferrer">
                {t("shares.send")}
              </a>
              <BigButton variant="danger" onClick={() => void api(`/shares/${s.id}/revoke`, { method: "POST" }).then(load)}>
                {t("shares.revoke")}
              </BigButton>
            </>
          )}
        </Card>
      ))}
      <h2 className="text-lg font-semibold">{t("shares.log_title")}</h2>
      {logs.length === 0 && <p>{t("shares.none")}</p>}
      <ul data-testid="access-log">
        {logs.map((l) => (
          <li key={l.viewed_at + l.viewer}>{t("shares.viewed", { who: l.viewer, when: istDateTime(l.viewed_at, i18n.language) })}</li>
        ))}
      </ul>
    </Screen>
  );
}
