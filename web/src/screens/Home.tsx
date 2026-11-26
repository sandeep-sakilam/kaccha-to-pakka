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

  useEffect(() => {
    api<Business[]>("/businesses")
      .then(setBusinesses)
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
      <BigButton variant="ghost" onClick={() => void signOut().then(() => nav("/"))}>
        {t("home.logout")}
      </BigButton>
    </Screen>
  );
}
