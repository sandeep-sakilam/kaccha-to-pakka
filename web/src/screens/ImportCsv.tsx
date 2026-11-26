import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { FileUpload } from "@/components/FileUpload";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";

export default function ImportCsv() {
  const { t } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  return (
    <Screen title={t("import.title")} spoken={[t("import.intro")]}>
      <p>{t("import.intro")}</p>
      <FileUpload<{ rows: number; source: string }>
        path={`/businesses/${businessId}/imports/csv`}
        accept=".csv,text/csv"
        label={t("import.pick")}
        onDone={(r) => t("import.done", { rows: r.rows, source: r.source })}
      />
      <BigButton variant="secondary" onClick={() => nav("/home")}>
        {t("capture.done")}
      </BigButton>
    </Screen>
  );
}
