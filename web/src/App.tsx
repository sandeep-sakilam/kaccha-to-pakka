import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { SandboxProvider } from "@/lib/sandbox";
import Welcome from "@/screens/Welcome";

const Never = lazy(() => import("@/screens/Never"));

function Loading() {
  const { t } = useTranslation();
  return <p role="status">{t("common.loading")}</p>;
}

export function AppRoutes() {
  return (
    <AppShell>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Welcome />} />
          <Route path="/never" element={<Never />} />
          <Route path="*" element={<Welcome />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

export default function App() {
  return (
    <SandboxProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
      </BrowserRouter>
    </SandboxProvider>
  );
}
