import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "@/lib/api";
import { speak } from "@/lib/voice";

/** Picker for documents (CSV exports, statement PDFs). Photos never use this: camera only. */
export function FileUpload<T>({ path, accept, label, onDone }: { path: string; accept: string; label: string; onDone: (res: T) => string }) {
  const { t, i18n } = useTranslation();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setError(null);
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await api<T>(path, { method: "POST", body: form, headers: { "Idempotency-Key": crypto.randomUUID() } });
      const msg = onDone(res);
      setMessage(msg);
      void speak([msg], i18n.language);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : t("common.error");
      setError(msg);
      void speak([msg], i18n.language);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <label className="flex min-h-14 cursor-pointer items-center justify-center rounded-2xl bg-brand px-5 text-lg font-semibold text-white focus-within:ring-4 focus-within:ring-yellow-400">
        {busy ? t("common.loading") : label}
        <input type="file" accept={accept} className="sr-only" disabled={busy} onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])} />
      </label>
      {message && (
        <p role="status" className="rounded-xl bg-brand-light p-3" data-testid="upload-status">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-red-100 p-3">
          {error}
        </p>
      )}
    </>
  );
}
