import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { ClaimForm } from "@/components/ClaimForm";
import { Screen } from "@/components/Screen";
import { BigButton, Card, SandboxBadge } from "@/components/ui";
import { setLanguage } from "@/i18n";
import { api, ApiError } from "@/lib/api";
import { speak } from "@/lib/voice";

type Invite = { business_name: string; city: string | null; relationship: "supplier" | "customer"; masked_id: string; status: string; language: "hi" | "en"; sandbox: boolean };
type Penny = { ref: string; upi_link: string; sandbox: boolean; pay_to_vpa: string };

/** Public page for a confirmer: no login, sees only the claim they are asked to confirm. */
export default function Confirm({ children }: { children?: (token: string) => React.ReactNode }) {
  const { t, i18n } = useTranslation();
  const { token = "" } = useParams();
  const [inv, setInv] = useState<Invite | null>(null);
  const [penny, setPenny] = useState<Penny | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vpa, setVpa] = useState("");
  const [name, setName] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api<Invite>(`/invites/${token}`);
      setInv(data);
      setStatus(data.status);
      if (data.language !== i18n.language) setLanguage(data.language);
    } catch {
      setError(t("confirm.not_valid"));
    }
  }, [token, i18n.language, t]);

  useEffect(() => {
    void load();
    // load once per token
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function startPay() {
    try {
      setPenny(await api<Penny>(`/invites/${token}/penny-drop`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  async function check() {
    const res = await api<{ status: string; reason: string | null }>(`/invites/${token}/penny-drop/check`, { method: "POST" });
    setStatus(res.status);
    const msg = t(`confirm.${res.status === "pending" ? "pending" : res.status}`);
    void speak([msg], i18n.language);
  }

  async function sandboxPay() {
    if (!penny) return;
    await api(`/sandbox/payments/${penny.ref}/pay`, { method: "POST", json: { payer_vpa: vpa, payer_name: name } });
    await check();
  }

  if (error) return <p role="alert">{error}</p>;
  if (!inv) return <p role="status">{t("common.loading")}</p>;
  const role = t(`partners.${inv.relationship}`);
  const asked = t("confirm.asked", { business: inv.business_name, city: inv.city ?? "", role });

  return (
    <Screen title={t("confirm.title")} spoken={[asked, t("confirm.step_pay", { masked: inv.masked_id })]}>
      <Card>
        <p className="text-lg">{asked}</p>
      </Card>
      {(status === "sent" || status === "opened" || status === "pending") && (
        <>
          <p>{t("confirm.step_pay", { masked: inv.masked_id })}</p>
          {!penny ? (
            <BigButton icon="💸" onClick={startPay}>
              {t("confirm.pay")}
            </BigButton>
          ) : penny.sandbox ? (
            <Card className="flex flex-col gap-2">
              <SandboxBadge label={t("common.sandbox")} />
              <p className="font-semibold">{t("confirm.sandbox_pay")}</p>
              <input aria-label={t("confirm.your_vpa")} placeholder={t("confirm.your_vpa")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3" value={vpa} onChange={(e) => setVpa(e.target.value)} />
              <input aria-label={t("confirm.your_name")} placeholder={t("confirm.your_name")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3" value={name} onChange={(e) => setName(e.target.value)} />
              <BigButton disabled={!vpa || !name} onClick={sandboxPay}>
                {t("confirm.pay")}
              </BigButton>
            </Card>
          ) : (
            <>
              <a className="flex min-h-14 items-center justify-center rounded-2xl bg-brand text-lg font-semibold text-white" href={penny.upi_link}>
                {t("confirm.pay")}
              </a>
              <BigButton variant="secondary" onClick={check}>
                {t("confirm.check")}
              </BigButton>
            </>
          )}
          {status === "pending" && <p role="status">{t("confirm.pending")}</p>}
        </>
      )}
      {status === "rejected" && (
        <p role="alert" className="rounded-xl bg-red-100 p-3 text-lg" data-testid="confirm-status">
          {t("confirm.rejected")}
        </p>
      )}
      {status === "proven" && (
        <>
          <p role="status" className="rounded-xl bg-brand-light p-3 text-lg" data-testid="confirm-status">
            {t("confirm.proven")}
          </p>
          {children ? children(token) : <ClaimForm token={token} defaultRelationship={inv.relationship} />}
        </>
      )}
    </Screen>
  );
}
