import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Keypad } from "@/components/Keypad";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { listenOnce } from "@/lib/listen";
import { useSandbox } from "@/lib/sandbox";
import { rupeesInWords, speak } from "@/lib/voice";

type Parsed = {
  amount_paise: number | null;
  party_text: string | null;
  direction: "in" | "out" | null;
  entry_date: string | null;
  understood: boolean;
  prompt: string | null;
  stt_confidence: number;
};
type Entry = { amount_paise: number; direction: "in" | "out"; party_text: string | null; entry_date: string | null; method: "voice" | "buttons"; stt_confidence: number };

export default function VoiceEntry() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const sandbox = useSandbox();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [misses, setMisses] = useState(0);
  const [typed, setTyped] = useState("");
  const [amount, setAmount] = useState("");
  const [party, setParty] = useState("");
  const [direction, setDirection] = useState<"in" | "out">("in");
  const [listening, setListening] = useState(false);
  const [done, setDone] = useState(false);
  const buttonsMode = misses >= 2;

  function miss() {
    const n = misses + 1;
    setMisses(n);
    setParsed(null);
    void speak([n >= 2 ? t("voice_entry.buttons_mode") : t("interview.not_understood")], i18n.language);
  }

  async function parse(payload: { transcript?: string; audio_b64?: string }) {
    const res = await api<Parsed>(`/businesses/${businessId}/voice-entries/parse`, {
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

  function accept() {
    if (!parsed?.amount_paise || !parsed.direction) return;
    setEntries((e) => [
      ...e,
      { amount_paise: parsed.amount_paise!, direction: parsed.direction!, party_text: parsed.party_text, entry_date: parsed.entry_date, method: "voice", stt_confidence: parsed.stt_confidence },
    ]);
    setParsed(null);
    setTyped("");
  }

  function addButtons() {
    setEntries((e) => [
      ...e,
      { amount_paise: Number(amount) * 100, direction, party_text: party || null, entry_date: null, method: "buttons", stt_confidence: 1 },
    ]);
    setAmount("");
    setParty("");
  }

  async function saveAll() {
    await api(`/businesses/${businessId}/voice-entries`, {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      json: { entries, source_evidence_id: params.get("source") },
    });
    setDone(true);
    void speak([t("voice_entry.saved")], i18n.language);
  }

  if (done) {
    return (
      <Screen title={t("voice_entry.title")} spoken={[t("voice_entry.saved")]}>
        <p role="status" className="text-lg">
          {t("voice_entry.saved")}
        </p>
        <BigButton onClick={() => nav("/home")}>{t("capture.done")}</BigButton>
      </Screen>
    );
  }

  return (
    <Screen title={t("voice_entry.title")} spoken={[t("voice_entry.intro")]}>
      <p>{t("voice_entry.intro")}</p>
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
            <input aria-label={t("interview.or_type")} placeholder={t("interview.or_type")} className="min-h-12 flex-1 rounded-xl border-2 border-gray-300 px-3 text-lg" value={typed} onChange={(e) => setTyped(e.target.value)} />
            <button type="submit" className="min-h-12 rounded-xl bg-brand px-4 font-semibold text-white">
              {t("common.next")}
            </button>
          </form>
        </>
      )}
      {parsed && (
        <Card>
          <p className="text-xl font-semibold" data-testid="voice-prompt">
            {parsed.prompt}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <BigButton onClick={accept}>{t("common.yes")}</BigButton>
            <BigButton variant="secondary" onClick={miss}>
              {t("common.no")}
            </BigButton>
          </div>
        </Card>
      )}
      {buttonsMode && (
        <div className="flex flex-col gap-3" data-testid="buttons-mode">
          <p className="rounded-xl bg-brand-light p-2">{t("voice_entry.buttons_mode")}</p>
          <p className="rounded-xl border-2 border-gray-300 p-3 text-center text-2xl" aria-live="polite">
            ₹ {amount || "0"}
            {amount && <span className="block text-base">{rupeesInWords(Number(amount) * 100, i18n.language)}</span>}
          </p>
          <Keypad value={amount} onChange={setAmount} max={9} />
          <div className="grid grid-cols-2 gap-2">
            {(["in", "out"] as const).map((d) => (
              <BigButton key={d} variant={direction === d ? "primary" : "secondary"} aria-pressed={direction === d} onClick={() => setDirection(d)}>
                {t(d === "in" ? "readback.received" : "readback.paid")}
              </BigButton>
            ))}
          </div>
          <input aria-label={t("voice_entry.party")} placeholder={t("voice_entry.party")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3 text-lg" value={party} onChange={(e) => setParty(e.target.value)} />
          <BigButton disabled={!amount} onClick={addButtons}>
            {t("voice_entry.add")}
          </BigButton>
        </div>
      )}
      {entries.length > 0 && (
        <>
          <p role="status">{t("voice_entry.added", { count: entries.length })}</p>
          <BigButton icon="💾" onClick={saveAll}>
            {t("voice_entry.save_all")}
          </BigButton>
        </>
      )}
    </Screen>
  );
}
