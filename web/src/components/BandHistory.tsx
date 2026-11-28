import { useTranslation } from "react-i18next";
import { bandBg } from "@/lib/bands";

export type HistoryItem = { issued_at: string; band: string; status: string };

/** The band on each passport issued, oldest first: "12 Sep D → 14 Oct C → 27 Nov B". */
export function BandHistory({ items }: { items: HistoryItem[] }) {
  const { t, i18n } = useTranslation();
  if (!Array.isArray(items) || items.length < 2) return null;
  const day = (iso: string) =>
    new Date(iso).toLocaleDateString(i18n.language === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
  return (
    <section aria-label={t("passport.history")}>
      <h2 className="section-title mb-2">{t("passport.history")}</h2>
      <ol className="flex flex-wrap items-center gap-2" data-testid="band-history">
        {items.map((h, i) => (
          <li key={h.issued_at} className="flex items-center gap-2">
            {i > 0 && (
              <span aria-hidden="true" className="text-gray-400">
                →
              </span>
            )}
            <span className="flex items-center gap-2 rounded-full bg-white py-1 pl-3 pr-1 text-sm shadow-sm ring-1 ring-black/10">
              <span className="text-gray-700">{day(h.issued_at)}</span>
              <strong className={`flex h-7 w-7 items-center justify-center rounded-full text-sm text-white ${bandBg(h.band)}`}>{h.band}</strong>
              {h.status === "on_hold" && <span className="sr-only"> ({t("lender.status_on_hold")})</span>}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
