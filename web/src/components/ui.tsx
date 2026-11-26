import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const styles: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-green-800",
  secondary: "bg-white text-brand border-2 border-brand hover:bg-brand-light",
  danger: "bg-red-700 text-white hover:bg-red-800",
  ghost: "bg-transparent text-brand underline",
};

export function BigButton({
  variant = "primary",
  icon,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: ReactNode }) {
  return (
    <button
      type="button"
      className={`flex min-h-14 w-full items-center justify-center gap-3 rounded-2xl px-5 py-3 text-lg font-semibold focus:outline-none focus-visible:ring-4 focus-visible:ring-yellow-400 disabled:opacity-50 ${styles[variant]} ${className}`}
      {...rest}
    >
      {icon && <span aria-hidden="true" className="text-2xl">{icon}</span>}
      <span>{children}</span>
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-gray-300 bg-white p-4 shadow-sm ${className}`}>{children}</div>;
}

export function SandboxBadge({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-yellow-300 px-3 py-1 text-sm font-bold text-gray-900" data-testid="sandbox-badge">
      {label}
    </span>
  );
}
