import { useTranslation } from "react-i18next";

export type HistoryItem = { issued_at: string; band: string; status: string };

/** The band on each passport issued, oldest first: "12 Sep D → 14 Oct C → 27 Nov B". */
export function BandHistory({ items }: { items: HistoryItem[] }) {
  const { t, i18n } = useTranslation();
  if (!Array.isArray(items) || items.length < 2) return null;
  const day = (iso: string) =>
    new Date(iso).toLocaleDateString(i18n.language === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
  return (
    <section aria-label={t("passport.history")}>
      <h2 className="font-semibold">{t("passport.history")}</h2>
      <ol className="flex flex-wrap items-center gap-2" data-testid="band-history">
        {items.map((h, i) => (
          <li key={h.issued_at} className="flex items-center gap-2">
            {i > 0 && <span aria-hidden="true">→</span>}
            <span className="rounded-lg border-2 border-gray-300 px-2 py-1 text-sm">
              {day(h.issued_at)} <strong>{h.band}</strong>
              {h.status === "on_hold" && <span className="sr-only"> ({t("lender.status_on_hold")})</span>}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
