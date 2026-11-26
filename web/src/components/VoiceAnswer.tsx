import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { listenOnce } from "@/lib/listen";
import { useSandbox } from "@/lib/sandbox";
import { speak } from "@/lib/voice";
import { BigButton } from "./ui";

export type Interpretation = { field: string; value: string | number | null; transcript: string; confirm: string; understood: boolean };

/** Ask one question by voice; the owner hears what we understood and says yes or no. */
export function VoiceAnswer({
  question,
  onConfirmed,
}: {
  question: "name" | "category" | "since" | "place";
  onConfirmed: (value: string | number | null) => void;
}) {
  const { t, i18n } = useTranslation();
  const sandbox = useSandbox();
  const [listening, setListening] = useState(false);
  const [typed, setTyped] = useState("");
  const [result, setResult] = useState<Interpretation | null>(null);
  const [failed, setFailed] = useState(false);

  async function interpret(payload: { transcript?: string; audio_b64?: string }) {
    const res = await api<Interpretation>("/onboarding/interpret", {
      method: "POST",
      json: { question, language: i18n.language, ...payload },
    });
    setResult(res);
    setFailed(!res.understood);
    if (res.understood) void speak([res.confirm], i18n.language);
    else void speak([t("interview.not_understood")], i18n.language);
  }

  async function mic() {
    setListening(true);
    try {
      await interpret(await listenOnce(i18n.language, sandbox.services.ai === false));
    } catch {
      setFailed(true);
    } finally {
      setListening(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <BigButton icon="🎤" onClick={mic} disabled={listening} aria-live="polite">
        {listening ? t("interview.listening") : t("interview.speak")}
      </BigButton>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (typed.trim()) void interpret({ transcript: typed });
        }}
      >
        <input
          aria-label={t("interview.or_type")}
          placeholder={t("interview.or_type")}
          className="min-h-12 flex-1 rounded-xl border-2 border-gray-300 px-3 text-lg"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <button type="submit" className="min-h-12 rounded-xl bg-brand px-4 font-semibold text-white">
          {t("common.next")}
        </button>
      </form>
      {failed && <p role="alert">{t("interview.not_understood")}</p>}
      {result && result.understood && (
        <div className="flex flex-col gap-2 rounded-2xl bg-brand-light p-3" data-testid="confirm-box">
          <p className="text-sm">{t("interview.heard", { text: result.transcript })}</p>
          <p className="text-lg font-semibold">{result.confirm}</p>
          <div className="grid grid-cols-2 gap-2">
            <BigButton onClick={() => onConfirmed(result.value)}>{t("common.yes")}</BigButton>
            <BigButton variant="secondary" onClick={() => setResult(null)}>
              {t("common.no")}
            </BigButton>
          </div>
        </div>
      )}
    </div>
  );
}
