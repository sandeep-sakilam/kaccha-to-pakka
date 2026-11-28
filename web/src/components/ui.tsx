import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "tile" | "alert";

const base =
  "flex min-h-14 w-full items-center gap-3 rounded-2xl px-5 py-3 text-lg font-semibold transition-transform duration-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100";

const styles: Record<Variant, string> = {
  primary: "justify-center bg-brand text-white shadow-lift hover:bg-brand-800",
  secondary: "justify-center bg-white text-brand-800 shadow-sm ring-1 ring-gray-300 hover:bg-brand-50 hover:ring-brand-300",
  danger: "justify-center bg-red-700 text-white shadow-sm hover:bg-red-800",
  ghost: "justify-center bg-transparent text-brand underline decoration-brand/40 underline-offset-4 hover:decoration-brand",
  // A row in a list of actions: icon chip on the left, label, arrow on the right.
  tile: "justify-start bg-white text-left text-ink shadow-card ring-1 ring-black/5 hover:ring-brand-300",
  // Something the owner should do now.
  alert: "justify-start bg-amber-50 text-left text-amber-950 ring-1 ring-amber-300 hover:bg-amber-100",
};

export function BigButton({
  variant = "primary",
  icon,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: ReactNode }) {
  const listRow = variant === "tile" || variant === "alert";
  return (
    <button type="button" className={`${base} ${styles[variant]} ${className}`} {...rest}>
      {icon &&
        (listRow ? (
          <span
            aria-hidden="true"
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-2xl ${variant === "alert" ? "bg-amber-100" : "bg-brand-50"}`}
          >
            {icon}
          </span>
        ) : (
          <span aria-hidden="true" className="text-2xl">
            {icon}
          </span>
        ))}
      <span className={listRow ? "flex-1" : ""}>{children}</span>
      {listRow && (
        <span aria-hidden="true" className="text-2xl text-gray-400">
          ›
        </span>
      )}
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function SandboxBadge({ label }: { label: string }) {
  return (
    <span className="pill bg-amber-300 px-2.5 py-0.5 text-xs text-amber-950" data-testid="sandbox-badge">
      {label}
    </span>
  );
}

const tones = {
  green: "bg-brand-100 text-brand-900",
  amber: "bg-amber-100 text-amber-900",
  red: "bg-red-100 text-red-900",
  gray: "bg-gray-100 text-gray-800",
} as const;

export function Pill({ tone = "gray", children }: { tone?: keyof typeof tones; children: ReactNode }) {
  return <span className={`pill ${tones[tone]}`}>{children}</span>;
}

/** A titled group of actions or facts. */
export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3" aria-label={title}>
      <h2 className="section-title px-1">{title}</h2>
      {children}
    </section>
  );
}
