import { useTranslation } from "react-i18next";

/** Big number pad: no typing needed, works for low literacy and screen readers. */
export function Keypad({ value, onChange, max }: { value: string; onChange: (v: string) => void; max: number }) {
  const { t } = useTranslation();
  const press = (d: string) => value.length < max && onChange(value + d);
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
  const cls =
    "min-h-16 rounded-2xl bg-white text-2xl font-bold text-ink shadow-sm ring-1 ring-black/10 transition-transform active:scale-95 active:bg-brand-50";
  return (
    <div className="grid grid-cols-3 gap-2" role="group" aria-label="keypad">
      {keys.map((k) => (
        <button key={k} type="button" className={cls} onClick={() => press(k)}>
          {k}
        </button>
      ))}
      <button type="button" className={`${cls} !bg-gray-100 text-base text-gray-700`} onClick={() => onChange("")}>
        {t("login.clear")}
      </button>
      <button type="button" className={cls} onClick={() => press("0")}>
        0
      </button>
      <button type="button" className={`${cls} !bg-gray-100 text-xl text-gray-700`} onClick={() => onChange(value.slice(0, -1))} aria-label={t("login.delete")}>
        ⌫
      </button>
    </div>
  );
}

export function Dots({ value, length, label }: { value: string; length: number; label: string }) {
  return (
    <div className="flex justify-center gap-3" aria-label={label} role="status">
      {Array.from({ length }).map((_, i) => (
        <span key={i} className={`h-4 w-4 rounded-full transition ${i < value.length ? "scale-110 bg-brand" : "bg-gray-300"}`} />
      ))}
    </div>
  );
}
