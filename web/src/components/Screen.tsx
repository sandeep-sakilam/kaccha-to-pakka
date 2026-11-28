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
    <section className="flex flex-col gap-5" aria-labelledby="screen-title">
      <div className="flex items-start justify-between gap-3 pt-1">
        <h1 id="screen-title" className="text-[1.7rem] font-extrabold leading-tight text-ink">
          {title}
        </h1>
        <button
          type="button"
          onClick={toggle}
          aria-pressed={playing}
          className={`flex min-h-12 min-w-12 shrink-0 items-center gap-2 rounded-full px-4 font-semibold shadow-sm ring-1 ${
            playing ? "bg-brand text-white ring-brand" : "bg-white text-brand-800 ring-brand-200 hover:bg-brand-50"
          }`}
        >
          <span aria-hidden="true" className="text-xl">
            {playing ? "⏹" : "🔊"}
          </span>
          <span>{playing ? t("common.stop") : t("common.listen")}</span>
        </button>
      </div>
      {children}
    </section>
  );
}
