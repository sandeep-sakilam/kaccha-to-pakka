import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { speak } from "@/lib/voice";

export default function ImportCsv() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await api<{ rows: number; source: string }>(`/businesses/${businessId}/imports/csv`, {
        method: "POST",
        body: form,
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
      const msg = t("import.done", { rows: res.rows, source: res.source });
      setMessage(msg);
      void speak([msg], i18n.language);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  return (
    <Screen title={t("import.title")} spoken={[t("import.intro")]}>
      <p>{t("import.intro")}</p>
      <label className="flex min-h-14 cursor-pointer items-center justify-center rounded-2xl bg-brand px-5 text-lg font-semibold text-white focus-within:ring-4 focus-within:ring-yellow-400">
        {t("import.pick")}
        <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])} />
      </label>
      {message && (
        <p role="status" className="rounded-xl bg-brand-light p-3" data-testid="import-status">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-red-100 p-3">
          {error}
        </p>
      )}
      <BigButton variant="secondary" onClick={() => nav("/home")}>
        {t("capture.done")}
      </BigButton>
    </Screen>
  );
}
