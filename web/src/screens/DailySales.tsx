import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { Keypad } from "@/components/Keypad";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { istDate } from "@/lib/format";
import { listenOnce } from "@/lib/listen";
import { useSandbox } from "@/lib/sandbox";
import { rupeesInWords, speak } from "@/lib/voice";

type Parsed = { amount_paise: number | null; sale_date: string; understood: boolean; prompt: string | null };
type Sale = { sale_date: string; amount_paise: number; method: string };

/** The owner says the day's total sales. It only counts when, month after month, it agrees with
 * what the bank shows, so this screen never asks for proof: it just listens and reads back. */
export default function DailySales() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  const sandbox = useSandbox();
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [typed, setTyped] = useState("");
  const [amount, setAmount] = useState("");
  const [misses, setMisses] = useState(0);
  const [listening, setListening] = useState(false);
  const [recent, setRecent] = useState<Sale[]>([]);
  const [saved, setSaved] = useState(false);
  const buttonsMode = misses >= 2;

  useEffect(() => {
    api<Sale[]>(`/businesses/${businessId}/daily-sales`)
      .then(setRecent)
      .catch(() => setRecent([]));
  }, [businessId, saved]);

  function miss() {
    const n = misses + 1;
    setMisses(n);
    setParsed(null);
    void speak([n >= 2 ? t("voice_entry.buttons_mode") : t("interview.not_understood")], i18n.language);
  }

  async function parse(payload: { transcript?: string; audio_b64?: string }) {
    const res = await api<Parsed>(`/businesses/${businessId}/daily-sales/parse`, {
      method: "POST",
      json: { language: i18n.language, ...payload },
    });
    if (!res.understood) return miss();
    setParsed(res);
    void speak([res.prompt ?? ""], i18n.language);
  }

  async function mic() {
    setListening(true);
    try {
      await parse(await listenOnce(i18n.language, sandbox.services.ai === false));
    } catch {
      miss();
    } finally {
      setListening(false);
    }
  }

  async function save(sale_date: string, amount_paise: number, method: "voice" | "typed" | "buttons") {
    await api(`/businesses/${businessId}/daily-sales`, { method: "POST", json: { sale_date, amount_paise, method } });
    setParsed(null);
    setTyped("");
    setAmount("");
    setSaved((s) => !s);
    void speak([t("daily_sales.saved")], i18n.language);
  }

  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

  return (
    <Screen title={t("daily_sales.title")} spoken={[t("daily_sales.intro")]}>
      <p>{t("daily_sales.intro")}</p>
      <p className="text-sm text-gray-600">{t("daily_sales.why")}</p>
      {!buttonsMode && !parsed && (
        <>
          <BigButton icon="🎤" onClick={mic} disabled={listening}>
            {listening ? t("interview.listening") : t("interview.speak")}
          </BigButton>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (typed.trim()) void parse({ transcript: typed });
            }}
          >
            <input aria-label={t("interview.or_type")} placeholder={t("interview.or_type")} className="field flex-1" value={typed} onChange={(e) => setTyped(e.target.value)} />
            <button type="submit" className="min-h-14 shrink-0 rounded-xl bg-brand px-5 font-semibold text-white shadow-sm hover:bg-brand-800">
              {t("common.next")}
            </button>
          </form>
        </>
      )}
      {parsed && (
        <Card>
          <p className="text-xl font-semibold" data-testid="sales-prompt">
            {parsed.prompt}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <BigButton onClick={() => void save(parsed.sale_date, parsed.amount_paise!, typed ? "typed" : "voice")}>{t("common.yes")}</BigButton>
            <BigButton variant="secondary" onClick={miss}>
              {t("common.no")}
            </BigButton>
          </div>
        </Card>
      )}
      {buttonsMode && (
        <div className="flex flex-col gap-3" data-testid="sales-buttons">
          <p className="rounded-2xl bg-white p-4 text-center text-3xl font-bold tabular-nums text-ink shadow-sm ring-1 ring-black/10" aria-live="polite">
            ₹ {amount || "0"}
            {amount && <span className="block text-base">{rupeesInWords(Number(amount) * 100, i18n.language)}</span>}
          </p>
          <Keypad value={amount} onChange={setAmount} max={8} />
          <BigButton disabled={!amount} onClick={() => void save(today, Number(amount) * 100, "buttons")}>
            {t("daily_sales.save_today")}
          </BigButton>
        </div>
      )}
      {recent.length > 0 && (
        <Card>
          <h2 className="font-semibold">{t("daily_sales.recent")}</h2>
          <ul data-testid="sales-recent">
            {recent.slice(0, 7).map((s) => (
              <li key={s.sale_date} className="flex justify-between">
                <span>{istDate(s.sale_date, i18n.language)}</span>
                <span>₹{(s.amount_paise / 100).toLocaleString("en-IN")}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <BigButton variant="secondary" onClick={() => nav("/home")}>
        {t("capture.done")}
      </BigButton>
    </Screen>
  );
}
