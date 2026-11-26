import { lazy, Suspense, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { AuthProvider, useAuth } from "@/lib/auth";
import { startBackgroundSync } from "@/lib/queue";
import { SandboxProvider } from "@/lib/sandbox";
import Welcome from "@/screens/Welcome";

const Never = lazy(() => import("@/screens/Never"));
const Login = lazy(() => import("@/screens/Login"));
const Consent = lazy(() => import("@/screens/Consent"));
const Interview = lazy(() => import("@/screens/Interview"));
const Home = lazy(() => import("@/screens/Home"));
const Capture = lazy(() => import("@/screens/Capture"));
const ReadBack = lazy(() => import("@/screens/ReadBack"));
const VoiceEntry = lazy(() => import("@/screens/VoiceEntry"));
const ImportCsv = lazy(() => import("@/screens/ImportCsv"));
const Statement = lazy(() => import("@/screens/Statement"));
const LinkBank = lazy(() => import("@/screens/LinkBank"));
const ReconQuestions = lazy(() => import("@/screens/ReconQuestions"));
const Partners = lazy(() => import("@/screens/Partners"));
const Confirm = lazy(() => import("@/screens/Confirm"));
const PassportScreen = lazy(() => import("@/screens/PassportScreen"));
const Shares = lazy(() => import("@/screens/Shares"));
const SahayakHome = lazy(() => import("@/screens/SahayakHome"));
const Helpers = lazy(() => import("@/screens/Helpers"));
const Review = lazy(() => import("@/screens/Review"));
const VerifyPassport = lazy(() => import("@/screens/lender/VerifyPassport"));
const LenderView = lazy(() => import("@/screens/lender/LenderView"));
const LenderHome = lazy(() => import("@/screens/lender/LenderHome"));
const SandboxAA = lazy(() => import("@/screens/SandboxAA"));

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  return me ? <>{children}</> : <Navigate to="/start" replace />;
}

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
          <Route path="/start" element={<Login />} />
          <Route path="/consent" element={<RequireAuth><Consent /></RequireAuth>} />
          <Route path="/interview" element={<RequireAuth><Interview /></RequireAuth>} />
          <Route path="/home" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="/v/:passportId" element={<VerifyPassport />} />
          <Route path="/l/:token" element={<LenderView />} />
          <Route path="/lender" element={<LenderHome />} />
          <Route path="/review" element={<RequireAuth><Review /></RequireAuth>} />
          <Route path="/sahayak" element={<RequireAuth><SahayakHome /></RequireAuth>} />
          <Route path="/helpers/:businessId" element={<RequireAuth><Helpers /></RequireAuth>} />
          <Route path="/shares/:businessId" element={<RequireAuth><Shares /></RequireAuth>} />
          <Route path="/passport/:businessId" element={<RequireAuth><PassportScreen /></RequireAuth>} />
          <Route path="/confirm/:token" element={<Confirm />} />
          <Route path="/partners/:businessId" element={<RequireAuth><Partners /></RequireAuth>} />
          <Route path="/recon/:businessId" element={<RequireAuth><ReconQuestions /></RequireAuth>} />
          <Route path="/link-bank/:businessId" element={<RequireAuth><LinkBank /></RequireAuth>} />
          <Route path="/sandbox/aa/approve/:handle" element={<RequireAuth><SandboxAA /></RequireAuth>} />
          <Route path="/statement/:businessId" element={<RequireAuth><Statement /></RequireAuth>} />
          <Route path="/import/:businessId" element={<RequireAuth><ImportCsv /></RequireAuth>} />
          <Route path="/voice-entry/:businessId" element={<RequireAuth><VoiceEntry /></RequireAuth>} />
          <Route path="/readback/:businessId" element={<RequireAuth><ReadBack /></RequireAuth>} />
          <Route path="/capture/:businessId/:kind" element={<RequireAuth><Capture /></RequireAuth>} />
          <Route path="*" element={<Welcome />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

export default function App() {
  startBackgroundSync();
  return (
    <SandboxProvider>
      <AuthProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
      </BrowserRouter>
      </AuthProvider>
    </SandboxProvider>
  );
}
