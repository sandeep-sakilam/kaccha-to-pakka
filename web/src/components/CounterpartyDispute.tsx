import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "@/lib/api";
import { DisputeList, type DisputeRow } from "./DisputeList";
import { ReasonInput } from "./ReasonInput";
import { BigButton, Card } from "./ui";

/** A confirmer can contest the claim from their invite link and follow the answer there. */
export function CounterpartyDispute({ token }: { token: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [rows, setRows] = useState<DisputeRow[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await api<DisputeRow[]>(`/invites/${token}/disputes`));
    } catch {
      setRows([]);
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);

  async function send() {
    try {
      await api(`/invites/${token}/dispute`, { method: "POST", json: { reason } });
      setMessage(t("disputes.sent"));
      setReason("");
      setOpen(false);
      await load();
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  return (
    <Card className="flex flex-col gap-2">
      {!open ? (
        <BigButton variant="ghost" onClick={() => setOpen(true)}>
          {t("disputes.cp_link")}
        </BigButton>
      ) : (
        <>
          <p>{t("disputes.cp_intro")}</p>
          <ReasonInput value={reason} onChange={setReason} />
          <BigButton disabled={reason.trim().length < 3} onClick={() => void send()}>
            {t("disputes.send")}
          </BigButton>
        </>
      )}
      {message && <p role="status">{message}</p>}
      {rows.length > 0 && <DisputeList rows={rows} />}
    </Card>
  );
}
