import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { BandHistory, type HistoryItem } from "@/components/BandHistory";
import { bandBg } from "@/lib/bands";
import { Screen } from "@/components/Screen";
import { BigButton, Card, Pill, SandboxBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { istDate } from "@/lib/format";
import { speak } from "@/lib/voice";

type Passport = { id: string; status: string; valid_until: string; qr_png_b64: string; verify_url: string; vc: { credentialSubject: { band: string; sandbox: boolean } } };
type Explanation = {
  band: string;
  band_label: string;
  confidence_label: string;
  status: string;
  status_label: string;
  headline: string;
  positives: string[];
  gaps: string[];
  improve: string[];
};
type Assessment = { reasons: { improve: { code: string }[] } };

/** Where each coaching tip takes the owner. */
function actionFor(code: string, businessId: string): string | null {
  return (
    {
      link_bank: `/link-bank/${businessId}`,
      refresh_bank_data: `/link-bank/${businessId}`,
      ask_partners: `/partners/${businessId}`,
      add_ledger: `/capture/${businessId}/ledger_page`,
      confirm_ledger_entries: `/readback/${businessId}`,
      shop_photo: `/capture/${businessId}/shop_front`,
    }[code] ?? null
  );
}

export default function PassportScreen() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  const [passport, setPassport] = useState<Passport | null>(null);
  const [ex, setEx] = useState<Explanation | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const load = useCallback(async () => {
    try {
      setPassport(await api<Passport>(`/businesses/${businessId}/passport`));
      setEx(await api<Explanation>(`/businesses/${businessId}/explanation?language=${i18n.language}`));
      const a = await api<Assessment>(`/businesses/${businessId}/assessments/latest`);
      setCodes(a.reasons.improve.map((r) => r.code));
      setHistory(await api<HistoryItem[]>(`/businesses/${businessId}/passport/history`).catch(() => []));
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) setError(t("common.error"));
    } finally {
      setLoaded(true);
    }
  }, [businessId, i18n.language, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function make() {
    setBusy(true);
    try {
      await api(`/businesses/${businessId}/passport`, { method: "POST" });
      await load();
    } finally {
      setBusy(false);
    }
  }

  function askRevoke() {
    setConfirmRevoke(true);
    void speak([t("passport.revoke_confirm")], i18n.language);
  }

  async function revoke() {
    await api(`/businesses/${businessId}/passport/revoke`, { method: "POST" });
    setConfirmRevoke(false);
    void speak([t("passport.revoked")], i18n.language);
    await load();
  }

  async function download(lang: "hi" | "en") {
    const blob = await api<Blob>(`/businesses/${businessId}/passport.pdf?language=${lang}`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trust-passport-${lang}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const spoken = ex ? [ex.headline, ...ex.gaps, t("passport.improve"), ...ex.improve] : [t("passport.none")];
  return (
    <Screen title={t("passport.title")} spoken={spoken}>
      {!loaded && <p role="status">{t("common.loading")}</p>}
      {loaded && !passport && <p>{t("passport.none")}</p>}
      {passport && ex && (
        <>
          <Card className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-2">
              <span className="section-title">{t("passport.title")}</span>
              {passport.vc.credentialSubject.sandbox && <SandboxBadge label={t("common.sandbox")} />}
            </div>
            <div className="flex items-center gap-4">
              <div
                className={`flex h-24 w-24 shrink-0 items-center justify-center rounded-3xl text-6xl font-black text-white shadow-lift ${bandBg(ex.band)}`}
                aria-label={`${t("passport.band")} ${ex.band}`}
                data-testid="band"
              >
                {ex.band}
              </div>
              <div className="flex flex-col gap-1.5">
                <p className="text-2xl font-extrabold leading-tight">{ex.band_label}</p>
                <div className="flex flex-wrap gap-1.5">
                  <Pill tone="gray">{ex.confidence_label}</Pill>
                  <span data-testid="passport-status">
                    <Pill tone={ex.status === "final" ? "green" : "amber"}>{ex.status_label}</Pill>
                  </span>
                </div>
                <p className="text-sm text-gray-700">{t("passport.valid_until", { date: istDate(passport.valid_until, i18n.language) })}</p>
              </div>
            </div>
            <p className="border-t border-gray-100 pt-4 text-lg leading-relaxed" data-testid="headline">
              {ex.headline}
            </p>
          </Card>
          <BandHistory items={history} />
          {ex.positives.length > 0 && (
            <Card>
              <h2 className="section-title mb-3">{t("passport.why")}</h2>
              <ul className="flex flex-col gap-2.5">
                {ex.positives.map((l) => (
                  <li key={l} className="flex gap-3">
                    <span aria-hidden="true" className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-bold text-brand-800">
                      ✓
                    </span>
                    <span>{l}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {ex.gaps.length > 0 && (
            <Card>
              <h2 className="section-title mb-3">{t("passport.gaps")}</h2>
              <ul className="flex flex-col gap-2.5">
                {ex.gaps.map((l) => (
                  <li key={l} className="flex gap-3">
                    <span aria-hidden="true" className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-100 text-sm font-bold text-amber-900">
                      !
                    </span>
                    <span>{l}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {ex.improve.length > 0 && (
            <section className="flex flex-col gap-2" data-testid="coaching">
              <h2 className="section-title px-1">{t("passport.improve")}</h2>
              {ex.improve.map((line, i) => {
                const to = codes[i] ? actionFor(codes[i], businessId) : null;
                return (
                  <Card key={line} className="flex items-center justify-between gap-3 !p-4">
                    <span className="flex gap-3">
                      <span aria-hidden="true">💡</span>
                      <span>{line}</span>
                    </span>
                    {to && (
                      <button type="button" className="min-h-12 shrink-0 rounded-xl bg-brand px-4 font-semibold text-white shadow-sm hover:bg-brand-800" onClick={() => nav(to)}>
                        {t("passport.do_it")}
                      </button>
                    )}
                  </Card>
                );
              })}
            </section>
          )}
          <Card className="flex flex-col items-center gap-3">
            <img src={`data:image/png;base64,${passport.qr_png_b64}`} alt={t("passport.scan")} className="h-52 w-52 rounded-xl" />
            <p className="text-center text-sm text-gray-700">{t("passport.scan")}</p>
          </Card>
          <div className="grid grid-cols-2 gap-2">
            <BigButton variant="secondary" onClick={() => void download("hi")}>
              {t("passport.download_hi")}
            </BigButton>
            <BigButton variant="secondary" onClick={() => void download("en")}>
              {t("passport.download_en")}
            </BigButton>
          </div>
          <BigButton icon="📤" onClick={() => nav(`/shares/${businessId}`)}>
            {t("passport.share")}
          </BigButton>
          <p className="px-1 text-sm text-gray-700">{t("passport.not_credit")}</p>
          {passport.status === "revoked" ? (
            <p role="status" className="rounded-xl bg-red-100 p-3 font-semibold text-red-900" data-testid="revoked">
              {t("passport.revoked")}
            </p>
          ) : confirmRevoke ? (
            <Card className="flex flex-col gap-2">
              <p role="alert">{t("passport.revoke_confirm")}</p>
              <div className="grid grid-cols-2 gap-2">
                <BigButton variant="danger" onClick={() => void revoke()}>
                  {t("passport.revoke_yes")}
                </BigButton>
                <BigButton variant="secondary" onClick={() => setConfirmRevoke(false)}>
                  {t("common.no")}
                </BigButton>
              </div>
            </Card>
          ) : (
            <BigButton variant="ghost" onClick={askRevoke}>
              {t("passport.revoke")}
            </BigButton>
          )}
        </>
      )}
      <BigButton icon="🛂" disabled={busy} onClick={make}>
        {passport ? t("passport.refresh") : t("passport.get")}
      </BigButton>
      {error && <p role="alert">{error}</p>}
    </Screen>
  );
}
