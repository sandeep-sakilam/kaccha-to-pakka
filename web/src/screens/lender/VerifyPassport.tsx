import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { Card, SandboxBadge } from "@/components/ui";
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
        <p role="alert" className="rounded-xl bg-red-100 p-4 text-lg font-bold text-red-900" data-testid="signature">
          ✗ {t("lender.signature_bad")}
        </p>
      )}
      {valid && payload && (
        <>
          <p className="rounded-xl bg-green-100 p-4 text-lg font-bold text-green-900" data-testid="signature">
            ✓ {t("lender.signature_ok")}
          </p>
          {payload.sb && <SandboxBadge label={t("common.sandbox")} />}
          <Card>
            <p className="text-xl font-bold">{payload.n}</p>
            <p>{payload.c}</p>
            <p className="text-4xl font-bold text-brand" data-testid="band">
              {payload.b}
            </p>
            <p>{payload.cf}</p>
            <p>
              {t("lender.valid_until")}: {payload.vu}
            </p>
          </Card>
          <p className="text-lg" data-testid="live-status">
            {live ? `${t("lender.live")}: ${t(`lender.status_${live}`)}` : t("lender.offline")}
          </p>
          <p className="text-sm text-gray-700">{t("lender.disclaimer")}</p>
        </>
      )}
    </Screen>
  );
}
