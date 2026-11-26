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
      <header className="flex items-center justify-between gap-2 border-b border-gray-200 px-4 py-3">
        <Link to="/" className="text-lg font-bold text-brand">
          {t("app.name")}
        </Link>
        <div className="flex items-center gap-2">
          {sandbox.any_sandbox && <SandboxBadge label={t("common.sandbox")} />}
          <button
            type="button"
            onClick={() => setLanguage(other)}
            className="min-h-12 rounded-full border-2 border-brand px-3 font-semibold text-brand"
            aria-label={t("common.language")}
          >
            {other === "hi" ? "हिन्दी" : "English"}
          </button>
        </div>
      </header>
      {sandbox.any_sandbox && <p className="bg-yellow-50 px-4 py-1 text-sm text-gray-700">{t("common.sandbox_hint")}</p>}
      {!online && (
        <p role="status" className="bg-orange-100 px-4 py-2 text-base text-orange-900">
          {t("common.offline")}
        </p>
      )}
      <main id="main" tabIndex={-1} className="flex-1 p-4 focus:outline-none">
        {children}
      </main>
    </div>
  );
}
