import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";

type Dispute = { id: string; target_type: string; reason: string | null; raised_by: string; created_at: string };
type Case = { id: string; business: { name: string } | null; target: Record<string, unknown>; reason: string | null };
type SahayakStat = { sahayak_user_id: string; actions_30d: number; businesses: number; failure_rate: number; reasons: string[] };

/** Operations reviewer queue: case data only, every access logged by the API. */
export default function Review() {
  const { t } = useTranslation();
  const [queue, setQueue] = useState<Dispute[]>([]);
  const [open, setOpen] = useState<Case | null>(null);
  const [note, setNote] = useState("");
  const [stats, setStats] = useState<SahayakStat[]>([]);

  const load = useCallback(async () => {
    setQueue(await api<Dispute[]>("/review/disputes"));
    setStats(await api<SahayakStat[]>("/review/sahayaks"));
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function decide(decision: "cleared" | "upheld") {
    if (!open) return;
    await api(`/review/disputes/${open.id}/resolve`, { method: "POST", json: { decision, note } });
    setOpen(null);
    setNote("");
    await load();
  }

  return (
    <Screen title={t("review.title")} spoken={[t("review.logged")]}>
      <p className="text-sm">{t("review.logged")}</p>
      {queue.length === 0 && <p>{t("review.none")}</p>}
      {queue.map((d) => (
        <Card key={d.id} className="flex items-center justify-between gap-2">
          <span>
            <b>{d.target_type}</b> · {d.reason} · {d.raised_by}
          </span>
          <button type="button" className="min-h-12 rounded-xl bg-brand px-3 text-white" onClick={() => void api<Case>(`/review/disputes/${d.id}`).then(setOpen)}>
            {t("review.open")}
          </button>
        </Card>
      ))}
      {open && (
        <Card className="flex flex-col gap-2" data-testid="case">
          <p className="font-semibold">{open.business?.name}</p>
          <p>{open.reason}</p>
          <pre className="overflow-x-auto rounded bg-gray-100 p-2 text-xs">{JSON.stringify(open.target, null, 2)}</pre>
          <input aria-label={t("review.note")} placeholder={t("review.note")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <BigButton onClick={() => void decide("cleared")}>{t("review.cleared")}</BigButton>
            <BigButton variant="danger" onClick={() => void decide("upheld")}>
              {t("review.upheld")}
            </BigButton>
          </div>
        </Card>
      )}
      <h2 className="text-lg font-semibold">{t("review.sahayaks")}</h2>
      <BigButton variant="secondary" onClick={() => void api("/review/monitor", { method: "POST" }).then(load)}>
        {t("review.run")}
      </BigButton>
      <table className="w-full text-sm">
        <tbody>
          {stats.map((s) => (
            <tr key={s.sahayak_user_id} className={s.reasons.length ? "bg-orange-50" : ""}>
              <td>{s.sahayak_user_id.slice(0, 8)}</td>
              <td>{s.actions_30d}</td>
              <td>{s.businesses}</td>
              <td>{Math.round(s.failure_rate * 100)}%</td>
              <td>{s.reasons.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Screen>
  );
}
