import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { BandHistory, type HistoryItem } from "@/components/BandHistory";
import { Screen } from "@/components/Screen";
import { Card, SandboxBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { istDate } from "@/lib/format";

type View = {
  lender_org: string;
  scope: string;
  passport: { id: string; status: string; valid_until: string; vc: { credentialSubject: { band: string; confidence: string; sandbox: boolean } } };
  explanation: { headline: string; band_label: string; positives: string[]; gaps: string[] };
  business: { name: string; category: string; city: string | null; since: number | null };
  history?: HistoryItem[];
  evidence?: {
    monthly_totals_paise: Record<string, { in: number; out: number }>;
    confirmations: { label: string; status: string }[];
    presence: { done: number; failed: number; missed: number };
    records: {
      match_rate?: number;
      cash_entries?: number;
      credit_entries?: number;
      credit_customers?: number;
      repeat_credit_customers?: number;
      credit_given_paise?: number;
      credit_repaid_bank_paise?: number;
      credit_repaid_cash_paise?: number;
      credit_outstanding_paise?: number;
      median_days_to_repay?: number | null;
      owner_confirmed_share?: number;
      supplier_credit_entries?: number;
      supplier_credit_suppliers?: number;
      supplier_credit_taken_paise?: number;
      supplier_paid_bank_paise?: number;
      supplier_paid_cash_paise?: number;
      supplier_outstanding_paise?: number;
      median_days_to_pay_suppliers?: number | null;
      daily_sales_months_checked?: number;
      daily_sales_months_agree?: number;
    };
    registration?: { status: string; source: string | null; registered_on: string | null };
    age?: { claimed_years: number | null; proven_years: number | null; proof: string };
    address_proofs?: string[];
    cash_deposit_paise?: number;
    cash_deposit_months?: number;
    avg_monthly_inflow_paise?: number;
    evidence_items: { type: string; status: string; file_hash: string | null }[];
    flags: { code: string; detail: string }[];
  };
};

const rupees = (p: number) => `₹${(p / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

/** Lender view of a share link: only the shared scope, watermarked with the lender's name. */
export default function LenderView() {
  const { t, i18n } = useTranslation();
  const { token = "" } = useParams();
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<View>(`/l/${token}`)
      .then(setView)
      .catch((e) => setError(e instanceof ApiError ? e.message : t("common.error")));
  }, [token, t]);

  if (error)
    return (
      <p role="alert" className="p-4 text-lg">
        {error}
      </p>
    );
  if (!view) return <p role="status">{t("common.loading")}</p>;
  const s = view.passport.vc.credentialSubject;
  const mark = t("lender.watermark", { lender: view.lender_org, date: istDate(new Date().toISOString(), i18n.language) });
  const ev = view.evidence;
  return (
    <div className="relative">
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-10 flex flex-col justify-around overflow-hidden opacity-[0.12]" data-testid="watermark">
        {Array.from({ length: 6 }).map((_, i) => (
          <p key={i} className="-rotate-[30deg] whitespace-nowrap text-2xl font-bold text-red-800">
            {mark} · {mark}
          </p>
        ))}
      </div>
      <Screen title={view.business.name} spoken={[view.explanation.headline]}>
        {s.sandbox && <SandboxBadge label={t("common.sandbox")} />}
        <Card className="flex items-center gap-4">
          <span className="text-5xl font-bold text-brand" data-testid="band">
            {s.band}
          </span>
          <div>
            <p className="font-semibold">{view.explanation.band_label}</p>
            <p>{s.confidence}</p>
            <p data-testid="live-status">
              {t("lender.live")}: {t(`lender.status_${view.passport.status}`)}
            </p>
            <p className="text-sm">
              {t("lender.valid_until")}: {istDate(view.passport.valid_until, i18n.language)}
            </p>
          </div>
        </Card>
        <p>{view.explanation.headline}</p>
        <BandHistory items={view.history ?? []} />
        <ul className="list-inside list-disc">
          {[...view.explanation.positives, ...view.explanation.gaps].map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        {ev && (
          <section className="flex flex-col gap-3" data-testid="evidence">
            <h2 className="text-lg font-semibold">{t("lender.evidence")}</h2>
            <Card>
              <h3 className="font-semibold">{t("lender.monthly")}</h3>
              <table className="w-full text-sm">
                <tbody>
                  {Object.entries(ev.monthly_totals_paise)
                    .slice(-12)
                    .map(([m, v]) => (
                      <tr key={m}>
                        <td>{m}</td>
                        <td className="text-right text-green-800">{rupees(v.in)}</td>
                        <td className="text-right text-red-800">{rupees(v.out)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </Card>
            {ev.age && (ev.age.claimed_years != null || ev.age.proven_years != null) && (
              <Card>
                <h3 className="font-semibold">{t("lender.age_title")}</h3>
                <p className="text-sm" data-testid="business-age">
                  {t("lender.age_line", {
                    claimed: ev.age.claimed_years != null ? Math.floor(ev.age.claimed_years) : "?",
                    proven: ev.age.proven_years != null ? Math.floor(ev.age.proven_years) : 0,
                    proof: t(`lender.age_proof_${ev.age.proof}`),
                  })}
                </p>
              </Card>
            )}
            {(ev.address_proofs ?? []).length > 0 && (
              <Card>
                <h3 className="font-semibold">{t("lender.address_title")}</h3>
                <p className="text-sm" data-testid="address-proofs">
                  {t("lender.address_line", { docs: (ev.address_proofs ?? []).map((d) => t(`lender.doc_${d}`)).join(", ") })}
                </p>
              </Card>
            )}
            {ev.registration && ev.registration.status !== "none" && (
              <Card>
                <h3 className="font-semibold">{t("lender.registration_title")}</h3>
                <p className="text-sm" data-testid="registration">
                  {t(`lender.registration_${ev.registration.status}`, {
                    source: ev.registration.source === "gstin" ? "GST" : "Udyam",
                    date: ev.registration.registered_on ? istDate(ev.registration.registered_on, i18n.language) : "?",
                  })}
                </p>
              </Card>
            )}
            {(ev.cash_deposit_months ?? 0) > 0 && (
              <Card>
                <h3 className="font-semibold">{t("lender.cash_title")}</h3>
                <p className="text-sm" data-testid="cash-deposits">
                  {t("lender.cash_deposits", { amount: rupees(ev.cash_deposit_paise ?? 0), months: ev.cash_deposit_months })}
                </p>
              </Card>
            )}
            <Card>
              <h3 className="font-semibold">{t("lender.records")}</h3>
              <p>{Math.round((ev.records.match_rate ?? 0) * 100)}%</p>
              {(ev.records.cash_entries ?? 0) > 0 && <p className="text-sm">{t("lender.cash_entries", { count: ev.records.cash_entries })}</p>}
              {(ev.records.daily_sales_months_checked ?? 0) > 0 && (
                <p className="text-sm" data-testid="daily-sales-check">
                  {t("lender.daily_sales", { agree: ev.records.daily_sales_months_agree ?? 0, checked: ev.records.daily_sales_months_checked })}
                </p>
              )}
              {(ev.records.owner_confirmed_share ?? 0) > 0 && (
                <p className="text-sm">{t("lender.owner_confirmed", { percent: Math.round((ev.records.owner_confirmed_share ?? 0) * 100) })}</p>
              )}
            </Card>
            {(ev.records.credit_entries ?? 0) > 0 && <CreditBook r={ev.records} monthly={ev.avg_monthly_inflow_paise ?? 0} />}
            {(ev.records.supplier_credit_entries ?? 0) > 0 && <SupplierBook r={ev.records} />}
            <Card>
              <h3 className="font-semibold">{t("lender.confirmations")}</h3>
              <ul>
                {ev.confirmations.map((c, i) => (
                  <li key={i}>
                    ✓ {c.label} ({c.status})
                  </li>
                ))}
              </ul>
            </Card>
            <Card>
              <h3 className="font-semibold">{t("lender.presence")}</h3>
              <p>{t("lender.presence_counts", ev.presence)}</p>
            </Card>
            {ev.flags.length > 0 && (
              <Card>
                <h3 className="font-semibold text-orange-800">{t("lender.flags")}</h3>
                <ul>
                  {ev.flags.map((f) => (
                    <li key={f.code}>{f.detail}</li>
                  ))}
                </ul>
              </Card>
            )}
            <Card>
              <h3 className="font-semibold">{t("lender.files")}</h3>
              <ul className="text-xs">
                {ev.evidence_items.map((e, i) => (
                  <li key={i}>
                    {e.type} · {e.status} · {e.file_hash?.slice(0, 16) ?? "—"}
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        )}
        <a className="flex min-h-12 items-center justify-center rounded-xl border-2 border-brand font-semibold text-brand" href={`/api/l/${token}/passport.pdf`}>
          {t("lender.pdf")}
        </a>
        <p className="text-sm text-gray-700">{t("lender.disclaimer")}</p>
      </Screen>
    </div>
  );
}

/** Plain facts about the owner's credit book (udhaar). Not a score: the lender decides. */
function CreditBook({ r, monthly }: { r: NonNullable<View["evidence"]>["records"]; monthly: number }) {
  const { t } = useTranslation();
  const given = r.credit_given_paise ?? 0;
  const pct = (p: number) => (given ? Math.round((p / given) * 100) : 0);
  const unpaid = r.credit_outstanding_paise ?? 0;
  return (
    <Card>
      <h3 className="font-semibold">{t("lender.credit_title")}</h3>
      <ul className="text-sm" data-testid="credit-book">
        <li>{t("lender.credit_given", { amount: rupees(given), customers: r.credit_customers ?? 0 })}</li>
        <li>{t("lender.credit_bank", { percent: pct(r.credit_repaid_bank_paise ?? 0) })}</li>
        <li>{t("lender.credit_cash", { percent: pct(r.credit_repaid_cash_paise ?? 0) })}</li>
        {r.median_days_to_repay != null && <li>{t("lender.credit_days", { days: r.median_days_to_repay })}</li>}
        <li>{t("lender.credit_regular", { count: r.repeat_credit_customers ?? 0 })}</li>
        <li>
          {t("lender.credit_unpaid", { amount: rupees(unpaid) })}
          {monthly > 0 && ` (${t("lender.credit_vs_sales", { percent: Math.round((unpaid / monthly) * 100) })})`}
        </li>
      </ul>
    </Card>
  );
}

/** Goods bought on credit and how they were paid for: plain facts for the lender. */
function SupplierBook({ r }: { r: NonNullable<View["evidence"]>["records"] }) {
  const { t } = useTranslation();
  const taken = r.supplier_credit_taken_paise ?? 0;
  const pct = (p: number) => (taken ? Math.round((p / taken) * 100) : 0);
  return (
    <Card>
      <h3 className="font-semibold">{t("lender.supplier_title")}</h3>
      <ul className="text-sm" data-testid="supplier-book">
        <li>{t("lender.supplier_taken", { amount: rupees(taken), suppliers: r.supplier_credit_suppliers ?? 0 })}</li>
        <li>{t("lender.supplier_bank", { percent: pct(r.supplier_paid_bank_paise ?? 0) })}</li>
        <li>{t("lender.supplier_cash", { percent: pct(r.supplier_paid_cash_paise ?? 0) })}</li>
        {r.median_days_to_pay_suppliers != null && <li>{t("lender.supplier_days", { days: r.median_days_to_pay_suppliers })}</li>}
        <li>{t("lender.supplier_unpaid", { amount: rupees(r.supplier_outstanding_paise ?? 0) })}</li>
      </ul>
    </Card>
  );
}

