import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Card, SandboxBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { istDate } from "@/lib/format";

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

const BAND_COLOURS: Record<string, string> = {
  A: "bg-green-700",
  B: "bg-green-600",
  C: "bg-yellow-500",
  D: "bg-orange-500",
  E: "bg-red-600",
  U: "bg-gray-500",
};

/** Where each coaching tip takes the owner. */
function actionFor(code: string, businessId: string): string | null {
  return (
    {
      link_bank: `/link-bank/${businessId}`,
      refresh_bank_data: `/link-bank/${businessId}`,
      ask_partners: `/partners/${businessId}`,
      add_ledger: `/capture/${businessId}/ledger_page`,
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

  const load = useCallback(async () => {
    try {
      setPassport(await api<Passport>(`/businesses/${businessId}/passport`));
      setEx(await api<Explanation>(`/businesses/${businessId}/explanation?language=${i18n.language}`));
      const a = await api<Assessment>(`/businesses/${businessId}/assessments/latest`);
      setCodes(a.reasons.improve.map((r) => r.code));
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
          {passport.vc.credentialSubject.sandbox && <SandboxBadge label={t("common.sandbox")} />}
          <Card className="flex items-center gap-4">
            <div className={`flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl text-5xl font-bold text-white ${BAND_COLOURS[ex.band] ?? "bg-gray-500"}`} aria-label={`${t("passport.band")} ${ex.band}`} data-testid="band">
              {ex.band}
            </div>
            <div>
              <p className="text-xl font-bold">{ex.band_label}</p>
              <p>{ex.confidence_label}</p>
              <p className={ex.status === "final" ? "text-green-800" : "font-semibold text-orange-700"} data-testid="passport-status">
                {ex.status_label}
              </p>
              <p className="text-sm">{t("passport.valid_until", { date: istDate(passport.valid_until, i18n.language) })}</p>
            </div>
          </Card>
          <p className="text-lg" data-testid="headline">
            {ex.headline}
          </p>
          {ex.positives.length > 0 && (
            <section>
              <h2 className="font-semibold">{t("passport.why")}</h2>
              <ul className="list-inside list-disc">{ex.positives.map((l) => <li key={l}>{l}</li>)}</ul>
            </section>
          )}
          {ex.gaps.length > 0 && (
            <section>
              <h2 className="font-semibold">{t("passport.gaps")}</h2>
              <ul className="list-inside list-disc">{ex.gaps.map((l) => <li key={l}>{l}</li>)}</ul>
            </section>
          )}
          {ex.improve.length > 0 && (
            <section className="flex flex-col gap-2" data-testid="coaching">
              <h2 className="font-semibold">{t("passport.improve")}</h2>
              {ex.improve.map((line, i) => {
                const to = codes[i] ? actionFor(codes[i], businessId) : null;
                return (
                  <Card key={line} className="flex items-center justify-between gap-2">
                    <span>💡 {line}</span>
                    {to && (
                      <button type="button" className="min-h-12 shrink-0 rounded-xl bg-brand px-3 font-semibold text-white" onClick={() => nav(to)}>
                        {t("passport.do_it")}
                      </button>
                    )}
                  </Card>
                );
              })}
            </section>
          )}
          <Card className="flex flex-col items-center gap-2">
            <img src={`data:image/png;base64,${passport.qr_png_b64}`} alt={t("passport.scan")} className="h-48 w-48" />
            <p className="text-center text-sm">{t("passport.scan")}</p>
          </Card>
          <div className="grid grid-cols-2 gap-2">
            <BigButton variant="secondary" onClick={() => void download("hi")}>
              {t("passport.download_hi")}
            </BigButton>
            <BigButton variant="secondary" onClick={() => void download("en")}>
              {t("passport.download_en")}
            </BigButton>
          </div>
          <p className="text-sm text-gray-700">{t("passport.not_credit")}</p>
        </>
      )}
      <BigButton icon="🛂" disabled={busy} onClick={make}>
        {passport ? t("passport.refresh") : t("passport.get")}
      </BigButton>
      {error && <p role="alert">{error}</p>}
    </Screen>
  );
}
