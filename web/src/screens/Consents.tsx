import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Dots, Keypad } from "@/components/Keypad";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { parseConsentCommand } from "@/lib/consentVoice";
import { istDate } from "@/lib/format";
import { listenOnce } from "@/lib/listen";
import { speak } from "@/lib/voice";

type ConsentRow = { id: string; purpose: string; why: string; granted_at: string; expires_at: string | null; revoked_at: string | null; active: boolean };

/** Every consent the owner gave, each withdrawable with one tap or by voice. */
export default function Consents() {
  const { t, i18n } = useTranslation();
  const [rows, setRows] = useState<ConsentRow[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [listening, setListening] = useState(false);
  const [erasing, setErasing] = useState(false);
  const [pin, setPin] = useState("");
  const { signOut } = useAuth();
  const nav = useNavigate();

  async function erase() {
    try {
      await api("/auth/erase", { method: "POST", json: { pin, confirm: "DELETE" } });
      void speak([t("consents.erased")], i18n.language);
      await signOut();
      nav("/");
    } catch (e) {
      setPin("");
      setMessage(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  const load = useCallback(async () => setRows(await api<ConsentRow[]>(`/consents?language=${i18n.language}`)), [i18n.language]);
  useEffect(() => {
    void load();
  }, [load]);

  const active = rows.filter((r) => r.active);

  async function withdraw(row: ConsentRow) {
    await api(`/consents/${row.id}/revoke`, { method: "POST" });
    const msg = t("consents.withdrew", { what: row.why });
    setMessage(msg);
    void speak([msg], i18n.language);
    await load();
  }

  async function command(text: string) {
    const cmd = parseConsentCommand(text);
    if (!active.length) {
      setMessage(t("consents.none"));
      return void speak([t("consents.none")], i18n.language);
    }
    if (cmd.index && cmd.index >= 1 && cmd.index <= active.length) return withdraw(active[cmd.index - 1]);
    if (!cmd.withdraw) {
      setMessage(t("consents.not_understood"));
      return void speak([t("consents.not_understood")], i18n.language);
    }
    const matches = cmd.purposes ? active.filter((r) => cmd.purposes!.includes(r.purpose)) : active;
    if (matches.length === 1 || (cmd.purposes && matches.length > 0)) {
      for (const m of matches) await withdraw(m);
      return;
    }
    const list = active.map((r, i) => `${i + 1}: ${r.why}`);
    setMessage([t("consents.which"), ...list].join(" "));
    void speak([t("consents.which"), ...list], i18n.language);
  }

  async function mic() {
    setListening(true);
    try {
      const heard = await listenOnce(i18n.language, false);
      if (heard.transcript) await command(heard.transcript);
    } catch {
      setMessage(t("consents.not_understood"));
    } finally {
      setListening(false);
    }
  }

  return (
    <Screen title={t("consents.title")} spoken={[t("consents.intro"), ...active.map((r, i) => `${i + 1}: ${r.why}`)]}>
      <p>{t("consents.intro")}</p>
      <BigButton icon="🎤" disabled={listening} onClick={() => void mic()}>
        {t("consents.voice")}
      </BigButton>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (typed.trim()) void command(typed);
          setTyped("");
        }}
      >
        <input aria-label={t("interview.or_type")} placeholder={t("interview.or_type")} className="field flex-1" value={typed} onChange={(e) => setTyped(e.target.value)} />
        <button type="submit" className="min-h-14 shrink-0 rounded-xl bg-brand px-5 font-semibold text-white shadow-sm hover:bg-brand-800">
          {t("common.next")}
        </button>
      </form>
      {message && (
        <p role="status" className="rounded-xl bg-brand-light p-3" data-testid="consent-message">
          {message}
        </p>
      )}
      <ol className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.id}>
            <Card className="flex items-center justify-between gap-3">
              <div>
                <p className="font-semibold">
                  {r.active ? `${active.indexOf(r) + 1}. ` : ""}
                  {r.why}
                </p>
                <p className="text-sm">
                  {r.active ? t("consents.active") : r.revoked_at ? t("consents.withdrawn") : t("consents.expired")} · {t("consents.since", { date: istDate(r.granted_at, i18n.language) })}
                  {r.expires_at && ` · ${t("consents.until", { date: istDate(r.expires_at, i18n.language) })}`}
                </p>
              </div>
              {r.active && (
                <button type="button" className="min-h-12 shrink-0 rounded-xl bg-red-700 px-3 font-semibold text-white" onClick={() => void withdraw(r)}>
                  {t("consents.withdraw")}
                </button>
              )}
            </Card>
          </li>
        ))}
      </ol>
      {!erasing ? (
        <BigButton
          variant="ghost"
          onClick={() => {
            setErasing(true);
            void speak([t("consents.erase_warning")], i18n.language);
          }}
        >
          {t("consents.erase")}
        </BigButton>
      ) : (
        <Card className="flex flex-col gap-3">
          <p role="alert">{t("consents.erase_warning")}</p>
          <Dots value={pin} length={4} label="PIN" />
          <Keypad value={pin} onChange={setPin} max={4} />
          <BigButton variant="danger" disabled={pin.length !== 4} onClick={() => void erase()}>
            {t("consents.erase_yes")}
          </BigButton>
          <BigButton variant="secondary" onClick={() => setErasing(false)}>
            {t("common.no")}
          </BigButton>
        </Card>
      )}
    </Screen>
  );
}
