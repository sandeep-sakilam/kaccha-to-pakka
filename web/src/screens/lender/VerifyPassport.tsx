import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { Card, Pill, SandboxBadge } from "@/components/ui";
import { bandBg } from "@/lib/bands";
import { decodeToken, publicKey, verifySignature, type CompactPassport } from "@/lib/verify";

export default function VerifyPassport() {
  const { t } = useTranslation();
  const { passportId = "" } = useParams();
  const { hash } = useLocation();
  const [payload, setPayload] = useState<CompactPassport | null>(null);
  const [valid, setValid] = useState<boolean | null>(null);
  const [live, setLive] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const decoded = await decodeToken(hash.replace(/^#/, ""));
      const key = await publicKey();
      const ok = Boolean(decoded && key && decoded.payload.id === passportId && verifySignature(decoded.payload, decoded.signature, key));
      setPayload(decoded?.payload ?? null);
      setValid(ok);
      if (ok) {
        try {
          const res = await fetch(`/api/passports/${passportId}/status`);
          setLive(((await res.json()) as { status: string }).status);
        } catch {
          setLive(null);
        }
      }
    })();
  }, [hash, passportId]);

  return (
    <Screen title={t("lender.title")} spoken={[valid ? t("lender.signature_ok") : t("lender.signature_bad")]}>
      {valid === null && <p role="status">{t("common.loading")}</p>}
      {valid === false && (
        <p role="alert" className="rounded-2xl bg-red-100 p-4 text-lg font-bold text-red-900 ring-1 ring-red-200" data-testid="signature">
          ✗ {t("lender.signature_bad")}
        </p>
      )}
      {valid && payload && (
        <>
          <p className="rounded-2xl bg-brand-100 p-4 text-lg font-bold text-brand-900 ring-1 ring-brand-200" data-testid="signature">
            ✓ {t("lender.signature_ok")}
          </p>
          <Card className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-2">
              <span className="section-title">{t("lender.passport_label")}</span>
              {payload.sb && <SandboxBadge label={t("common.sandbox")} />}
            </div>
            <div className="flex items-center gap-4">
              <span
                className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-3xl text-5xl font-black text-white shadow-lift ${bandBg(payload.b)}`}
                data-testid="band"
              >
                {payload.b}
              </span>
              <div className="flex min-w-0 flex-col gap-1">
                <p className="text-xl font-extrabold leading-tight">{payload.n}</p>
                <p className="text-gray-700">{payload.c}</p>
                <div>
                  <Pill tone="gray">{payload.cf}</Pill>
                </div>
              </div>
            </div>
            <p className="text-sm text-gray-700">
              {t("lender.valid_until")}: {payload.vu}
            </p>
          </Card>
          <p className="text-lg" data-testid="live-status">
            <Pill tone={live === "valid" ? "green" : live ? "amber" : "gray"}>
              {live ? `${t("lender.live")}: ${t(`lender.status_${live}`)}` : t("lender.offline")}
            </Pill>
          </p>
          <p className="text-sm text-gray-700">{t("lender.disclaimer")}</p>
        </>
      )}
    </Screen>
  );
}
