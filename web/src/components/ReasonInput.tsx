import { useState } from "react";
import { useTranslation } from "react-i18next";
import { listenOnce } from "@/lib/listen";

/** Free-text reason that can also be spoken (the phone's speech recogniser fills the box). */
export function ReasonInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t, i18n } = useTranslation();
  const [listening, setListening] = useState(false);
  const hasRecogniser = typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
  return (
    <div className="flex gap-2">
      <input aria-label={t("disputes.reason")} placeholder={t("disputes.reason")} className="field flex-1" value={value} onChange={(e) => onChange(e.target.value)} />
      {hasRecogniser && (
        <button
          type="button"
          className="min-h-12 rounded-xl bg-brand-light px-3 text-brand"
          disabled={listening}
          onClick={async () => {
            setListening(true);
            try {
              const heard = await listenOnce(i18n.language, false);
              if (heard.transcript) onChange(heard.transcript);
            } catch {
              /* nothing heard: typing still works */
            } finally {
              setListening(false);
            }
          }}
        >
          🎤 {t("disputes.speak")}
        </button>
      )}
    </div>
  );
}
