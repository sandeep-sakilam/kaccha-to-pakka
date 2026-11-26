import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { FileUpload } from "@/components/FileUpload";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";

export default function Statement() {
  const { t } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  return (
    <Screen title={t("statement.title")} spoken={[t("statement.intro")]}>
      <p>{t("statement.intro")}</p>
      <FileUpload<{ meta: { txns: number } }>
        path={`/businesses/${businessId}/statements`}
        accept="application/pdf,.pdf"
        label={t("statement.pick")}
        onDone={(r) => t("statement.done", { count: r.meta.txns })}
      />
      <BigButton variant="secondary" onClick={() => nav("/home")}>
        {t("capture.done")}
      </BigButton>
    </Screen>
  );
}
