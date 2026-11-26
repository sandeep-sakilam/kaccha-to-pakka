import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";
import { VoiceAnswer } from "@/components/VoiceAnswer";
import { api, ApiError } from "@/lib/api";
import { speak } from "@/lib/voice";

const CATEGORY_ICONS: Record<string, string> = {
  kirana: "🛒",
  namkeen: "🥨",
  tailor: "🧵",
  vegetables: "🥕",
  dairy: "🥛",
  food_stall: "🍵",
  salon: "💈",
  mobile_repair: "📱",
  hardware: "🔧",
  manufacturing: "🏭",
  other: "🏪",
};

type Step = "name" | "category" | "since" | "place" | "ids";
const ORDER: Step[] = ["name", "category", "since", "place", "ids"];

export default function Interview() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [step, setStep] = useState<Step>("name");
  const [profile, setProfile] = useState<Record<string, unknown>>({ city: "Indore", women_owned: false });
  const [udyam, setUdyam] = useState("");
  const [gstin, setGstin] = useState("");
  const [error, setError] = useState<string | null>(null);

  const next = (field: string, value: unknown) => {
    setProfile((p) => ({ ...p, [field]: value }));
    setStep(ORDER[ORDER.indexOf(step) + 1]);
  };

  async function save() {
    setError(null);
    try {
      const body = { ...profile, udyam: udyam || null, gstin: gstin || null };
      await api("/businesses", { method: "POST", json: body });
      void speak([t("interview.done")], i18n.language);
      nav("/home");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  const questions: Record<Step, string> = {
    name: t("interview.q_name"),
    category: t("interview.q_category"),
    since: t("interview.q_since"),
    place: t("interview.q_place"),
    ids: t("interview.ids_title"),
  };

  return (
    <Screen title={t("interview.title")} spoken={[questions[step]]}>
      <p className="text-sm text-gray-600" aria-live="polite">
        {ORDER.indexOf(step) + 1} / {ORDER.length}
      </p>
      <h2 className="text-xl font-semibold">{questions[step]}</h2>
      {step === "name" && <VoiceAnswer key="name" question="name" onConfirmed={(v) => next("name", v)} />}
      {step === "category" && (
        <>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(CATEGORY_ICONS).map(([key, icon]) => (
              <BigButton
                key={key}
                variant="secondary"
                icon={icon}
                onClick={() => next("category", key)}
                onFocus={() => void speak([t(`categories.${key}`)], i18n.language)}
              >
                {t(`categories.${key}`)}
              </BigButton>
            ))}
          </div>
          <VoiceAnswer key="category" question="category" onConfirmed={(v) => next("category", v)} />
        </>
      )}
      {step === "since" && <VoiceAnswer key="since" question="since" onConfirmed={(v) => next("started_year", v)} />}
      {step === "place" && <VoiceAnswer key="place" question="place" onConfirmed={(v) => next("address", v)} />}
      {step === "ids" && (
        <div className="flex flex-col gap-3">
          <p>{t("interview.ids_hint")}</p>
          <input
            aria-label="Udyam"
            placeholder="UDYAM-MP-23-0000000"
            className="min-h-12 rounded-xl border-2 border-gray-300 px-3 text-lg uppercase"
            value={udyam}
            onChange={(e) => setUdyam(e.target.value)}
          />
          <input
            aria-label="GSTIN"
            placeholder="GSTIN"
            className="min-h-12 rounded-xl border-2 border-gray-300 px-3 text-lg uppercase"
            value={gstin}
            onChange={(e) => setGstin(e.target.value)}
          />
          <label className="flex min-h-12 items-center gap-3 text-lg">
            <input
              type="checkbox"
              className="h-6 w-6"
              checked={Boolean(profile.women_owned)}
              onChange={(e) => setProfile((p) => ({ ...p, women_owned: e.target.checked }))}
            />
            {t("interview.women_owned")}
          </label>
          <BigButton icon="💾" onClick={save}>
            {udyam || gstin ? t("interview.save") : t("interview.skip")}
          </BigButton>
          {error && (
            <p role="alert" className="rounded-xl bg-red-100 p-3 text-red-900">
              {error}
            </p>
          )}
        </div>
      )}
    </Screen>
  );
}
