import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export type Business = { id: string; name: string; category: string; address: string | null; started_on: string | null };

export default function Home() {
  const { t } = useTranslation();
  const { signOut } = useAuth();
  const nav = useNavigate();
  const [businesses, setBusinesses] = useState<Business[] | null>(null);

  const [toCheck, setToCheck] = useState(0);
  const [reconQs, setReconQs] = useState(0);
  const [presence, setPresence] = useState<{ status: string }[] | null>(null);
  const [needsVoice, setNeedsVoice] = useState<{ evidence_id: string }[]>([]);

  useEffect(() => {
    api<Business[]>("/businesses")
      .then(async (list) => {
        setBusinesses(list);
        if (list[0]) {
          setToCheck((await api<unknown[]>(`/businesses/${list[0].id}/readback`)).length);
          setNeedsVoice(await api<{ evidence_id: string }[]>(`/businesses/${list[0].id}/needs-voice`));
          await api(`/businesses/${list[0].id}/reconcile`, { method: "POST" });
          setReconQs((await api<unknown[]>(`/businesses/${list[0].id}/recon/questions`)).length);
          setPresence(await api<{ status: string }[]>(`/businesses/${list[0].id}/presence`));
        }
      })
      .catch(() => setBusinesses([]));
  }, []);

  const biz = businesses?.[0];
  const todo =
    biz &&
    (toCheck > 0 || reconQs > 0 || needsVoice.length > 0 || presence?.some((p) => p.status === "sent"));
  return (
    <Screen title={t("home.title")} spoken={biz ? [biz.name, t(`categories.${biz.category}`)] : [t("home.no_business")]}>
      {businesses === null && <p role="status">{t("common.loading")}</p>}
      {businesses && !biz && (
        <>
          <p className="hint">{t("home.no_business")}</p>
          <BigButton onClick={() => nav("/consent")}>{t("home.setup")}</BigButton>
        </>
      )}
      {biz && (
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-700 to-brand-900 p-5 text-white shadow-lift">
          <div aria-hidden="true" className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
          <div aria-hidden="true" className="absolute -bottom-14 right-10 h-32 w-32 rounded-full bg-white/5" />
          <p className="relative text-2xl font-extrabold leading-tight" data-testid="business-name">
            {biz.name}
          </p>
          <p className="relative mt-1 text-brand-100">
            {[t(`categories.${biz.category}`), biz.address, biz.started_on?.slice(0, 4)].filter(Boolean).join(" · ")}
          </p>
          <BigButton icon="🛂" variant="secondary" className="relative mt-5 !text-brand-900" onClick={() => nav(`/passport/${biz.id}`)}>
            {t("home.passport")}
          </BigButton>
        </div>
      )}
      {biz && todo && (
        <Section title={t("home.section_now")}>
          {toCheck > 0 && (
            <BigButton variant="alert" icon="🔎" onClick={() => nav(`/readback/${biz.id}`)}>
              {t("home.to_check", { count: toCheck })}
            </BigButton>
          )}
          {presence?.some((p) => p.status === "sent") && (
            <BigButton variant="alert" icon="📍" onClick={() => nav(`/capture/${biz.id}/presence`)}>
              {t("home.presence_today")}
            </BigButton>
          )}
          {reconQs > 0 && (
            <BigButton variant="alert" icon="🤔" onClick={() => nav(`/recon/${biz.id}`)}>
              {t("home.recon_questions", { count: reconQs })}
            </BigButton>
          )}
          {needsVoice.length > 0 && (
            <BigButton variant="alert" icon="🗣️" onClick={() => nav(`/voice-entry/${biz.id}?source=${needsVoice[0].evidence_id}`)}>
              {t("home.needs_voice", { count: needsVoice.length })}
            </BigButton>
          )}
        </Section>
      )}
      {biz && (
        <Section title={t("home.section_money")}>
          <BigButton variant="tile" icon="🏦" onClick={() => nav(`/link-bank/${biz.id}`)}>
            {t("home.link_bank")}
          </BigButton>
          <BigButton variant="tile" icon="📒" onClick={() => nav(`/capture/${biz.id}/ledger_page`)}>
            {t("home.add_ledger")}
          </BigButton>
          <BigButton variant="tile" icon="🎤" onClick={() => nav(`/voice-entry/${biz.id}`)}>
            {t("home.read_aloud")}
          </BigButton>
          <BigButton variant="tile" icon="🪙" onClick={() => nav(`/daily-sales/${biz.id}`)}>
            {t("home.daily_sales")}
          </BigButton>
          <BigButton variant="tile" icon="🧾" onClick={() => nav(`/statement/${biz.id}`)}>
            {t("home.add_statement")}
          </BigButton>
          <BigButton variant="tile" icon="📄" onClick={() => nav(`/import/${biz.id}`)}>
            {t("home.import_csv")}
          </BigButton>
        </Section>
      )}
      {biz && (
        <Section title={t("home.section_shop")}>
          <BigButton variant="tile" icon="🏪" onClick={() => nav(`/capture/${biz.id}/shop_front`)}>
            {t("home.add_shop")}
          </BigButton>
          <BigButton variant="tile" icon="💡" onClick={() => nav(`/capture/${biz.id}/address_proof`)}>
            {t("home.address_proof")}
          </BigButton>
          {presence && presence.length === 0 && (
            <BigButton
              variant="tile"
              icon="📍"
              onClick={async () => {
                await api("/consents", { method: "POST", json: { purpose: "presence_location", business_id: biz.id } });
                setPresence(await api(`/businesses/${biz.id}/presence/start`, { method: "POST" }));
              }}
            >
              {t("home.start_presence")}
            </BigButton>
          )}
        </Section>
      )}
      {biz && (
        <Section title={t("home.section_people")}>
          <BigButton variant="tile" icon="🤝" onClick={() => nav(`/partners/${biz.id}`)}>
            {t("home.partners")}
          </BigButton>
          <BigButton variant="tile" icon="🧑‍🤝‍🧑" onClick={() => nav(`/helpers/${biz.id}`)}>
            {t("home.helpers")}
          </BigButton>
        </Section>
      )}
      <nav aria-label={t("home.section_more")} className="card flex flex-col gap-1 !p-2">
        {biz && (
          <BigButton variant="ghost" onClick={() => nav(`/disputes/${biz.id}`)}>
            {t("home.disputes")}
          </BigButton>
        )}
        <BigButton variant="ghost" onClick={() => nav("/consents")}>
          {t("home.consents")}
        </BigButton>
        <BigButton variant="ghost" onClick={() => nav("/sahayak")}>
          {t("home.sahayak_mode")}
        </BigButton>
        <BigButton variant="ghost" onClick={() => void signOut().then(() => nav("/"))}>
          {t("home.logout")}
        </BigButton>
      </nav>
    </Screen>
  );
}
