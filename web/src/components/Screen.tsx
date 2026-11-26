import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { speak, stopSpeaking } from "@/lib/voice";

/**
 * Every screen can be heard: `spoken` lists the lines read aloud by the Listen button.
 */
export function Screen({ title, spoken, children }: { title: string; spoken: string[]; children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const [playing, setPlaying] = useState(false);

  useEffect(() => () => stopSpeaking(), []);

  async function toggle() {
    if (playing) {
      stopSpeaking();
      setPlaying(false);
      return;
    }
    setPlaying(true);
    await speak([title, ...spoken], i18n.language);
    setPlaying(false);
  }

  return (
    <section className="flex flex-col gap-4" aria-labelledby="screen-title">
      <div className="flex items-start justify-between gap-3">
        <h1 id="screen-title" className="text-2xl font-bold text-brand">
          {title}
        </h1>
        <button
          type="button"
          onClick={toggle}
          aria-pressed={playing}
          className="flex min-h-12 min-w-12 shrink-0 items-center gap-2 rounded-full bg-brand-light px-4 text-brand focus-visible:ring-4 focus-visible:ring-yellow-400"
        >
          <span aria-hidden="true" className="text-xl">
            {playing ? "⏹" : "🔊"}
          </span>
          <span className="font-semibold">{playing ? t("common.stop") : t("common.listen")}</span>
        </button>
      </div>
      {children}
    </section>
  );
}
