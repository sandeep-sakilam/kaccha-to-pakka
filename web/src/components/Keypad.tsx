import { useTranslation } from "react-i18next";

/** Big number pad: no typing needed, works for low literacy and screen readers. */
export function Keypad({ value, onChange, max }: { value: string; onChange: (v: string) => void; max: number }) {
  const { t } = useTranslation();
  const press = (d: string) => value.length < max && onChange(value + d);
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
  const cls = "min-h-16 rounded-2xl bg-gray-100 text-2xl font-bold focus-visible:ring-4 focus-visible:ring-yellow-400";
  return (
    <div className="grid grid-cols-3 gap-2" role="group" aria-label="keypad">
      {keys.map((k) => (
        <button key={k} type="button" className={cls} onClick={() => press(k)}>
          {k}
        </button>
      ))}
      <button type="button" className={`${cls} text-base`} onClick={() => onChange("")}>
        {t("login.clear")}
      </button>
      <button type="button" className={cls} onClick={() => press("0")}>
        0
      </button>
      <button type="button" className={`${cls} text-base`} onClick={() => onChange(value.slice(0, -1))} aria-label={t("login.delete")}>
        ⌫
      </button>
    </div>
  );
}

export function Dots({ value, length, label }: { value: string; length: number; label: string }) {
  return (
    <div className="flex justify-center gap-3" aria-label={label} role="status">
      {Array.from({ length }).map((_, i) => (
        <span key={i} className={`h-5 w-5 rounded-full border-2 border-brand ${i < value.length ? "bg-brand" : ""}`} />
      ))}
    </div>
  );
}
