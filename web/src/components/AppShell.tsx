import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { setLanguage, type Lang } from "@/i18n";
import { useSandbox } from "@/lib/sandbox";
import { useOnline } from "@/lib/useOnline";
import { SandboxBadge } from "./ui";

export function AppShell({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const sandbox = useSandbox();
  const online = useOnline();
  const other: Lang = i18n.language === "hi" ? "en" : "hi";
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:rounded-xl focus:bg-yellow-300 focus:p-3 focus:text-gray-900">
        {t("common.skip")}
      </a>
      <header className="sticky top-0 z-30 border-b border-black/5 bg-canvas/90 backdrop-blur">
        <div className="flex items-center justify-between gap-2 px-4 py-2.5">
          <Link to="/" className="flex min-w-0 items-center gap-2 font-extrabold tracking-tight text-brand-800">
            <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand text-xs font-black text-white shadow-sm">
              K→P
            </span>
            <span className="whitespace-nowrap text-[0.85rem]">{t("app.name")}</span>
          </Link>
          <div className="flex shrink-0 items-center gap-1.5">
            {sandbox.any_sandbox && <SandboxBadge label={t("common.sandbox")} />}
            <button
              type="button"
              onClick={() => setLanguage(other)}
              className="min-h-12 rounded-full bg-white px-3 font-semibold text-brand-800 shadow-sm ring-1 ring-gray-300 hover:bg-brand-50"
              aria-label={t("common.language")}
            >
              {other === "hi" ? "हिन्दी" : "English"}
            </button>
          </div>
        </div>
        {sandbox.any_sandbox && (
          <p className="border-t border-amber-200/70 bg-amber-50/90 px-4 py-1.5 text-sm text-amber-950">{t("common.sandbox_hint")}</p>
        )}
      </header>
      {!online && (
        <p role="status" className="mx-4 mt-3 rounded-xl bg-orange-100 px-4 py-2 text-base text-orange-950 ring-1 ring-orange-300">
          {t("common.offline")}
        </p>
      )}
      <main id="main" tabIndex={-1} className="flex-1 px-4 pb-10 pt-5 focus:outline-none">
        {children}
      </main>
    </div>
  );
}
