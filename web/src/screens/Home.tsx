import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export type Business = { id: string; name: string; category: string; address: string | null; started_on: string | null };

export default function Home() {
  const { t } = useTranslation();
  const { signOut } = useAuth();
  const nav = useNavigate();
  const [businesses, setBusinesses] = useState<Business[] | null>(null);

  const [toCheck, setToCheck] = useState(0);
  const [needsVoice, setNeedsVoice] = useState<{ evidence_id: string }[]>([]);

  useEffect(() => {
    api<Business[]>("/businesses")
      .then(async (list) => {
        setBusinesses(list);
        if (list[0]) {
          setToCheck((await api<unknown[]>(`/businesses/${list[0].id}/readback`)).length);
          setNeedsVoice(await api<{ evidence_id: string }[]>(`/businesses/${list[0].id}/needs-voice`));
        }
      })
      .catch(() => setBusinesses([]));
  }, []);

  const biz = businesses?.[0];
  return (
    <Screen title={t("home.title")} spoken={biz ? [biz.name, t(`categories.${biz.category}`)] : [t("home.no_business")]}>
      {businesses === null && <p role="status">{t("common.loading")}</p>}
      {businesses && !biz && (
        <>
          <p>{t("home.no_business")}</p>
          <BigButton onClick={() => nav("/consent")}>{t("home.setup")}</BigButton>
        </>
      )}
      {biz && (
        <Card>
          <p className="text-xl font-bold" data-testid="business-name">
            {biz.name}
          </p>
          <p>{t(`categories.${biz.category}`)}</p>
          {biz.address && <p className="text-gray-700">{biz.address}</p>}
          {biz.started_on && <p className="text-gray-700">{biz.started_on.slice(0, 4)}</p>}
        </Card>
      )}
      {biz && (
        <>
          <h2 className="text-xl font-semibold">{t("home.next_steps")}</h2>
          {toCheck > 0 && (
            <BigButton icon="🔎" onClick={() => nav(`/readback/${biz.id}`)}>
              {t("home.to_check", { count: toCheck })}
            </BigButton>
          )}
          <BigButton icon="📒" onClick={() => nav(`/capture/${biz.id}/ledger_page`)}>
            {t("home.add_ledger")}
          </BigButton>
          {needsVoice.length > 0 && (
            <BigButton icon="🗣️" onClick={() => nav(`/voice-entry/${biz.id}?source=${needsVoice[0].evidence_id}`)}>
              {t("home.needs_voice", { count: needsVoice.length })}
            </BigButton>
          )}
          <BigButton variant="secondary" icon="🎤" onClick={() => nav(`/voice-entry/${biz.id}`)}>
            {t("home.read_aloud")}
          </BigButton>
          <BigButton icon="🏦" onClick={() => nav(`/link-bank/${biz.id}`)}>
            {t("home.link_bank")}
          </BigButton>
          <BigButton variant="secondary" icon="🧾" onClick={() => nav(`/statement/${biz.id}`)}>
            {t("home.add_statement")}
          </BigButton>
          <BigButton variant="secondary" icon="📄" onClick={() => nav(`/import/${biz.id}`)}>
            {t("home.import_csv")}
          </BigButton>
          <BigButton variant="secondary" icon="🏪" onClick={() => nav(`/capture/${biz.id}/shop_front`)}>
            {t("home.add_shop")}
          </BigButton>
        </>
      )}
      <BigButton variant="ghost" onClick={() => void signOut().then(() => nav("/"))}>
        {t("home.logout")}
      </BigButton>
    </Screen>
  );
}
