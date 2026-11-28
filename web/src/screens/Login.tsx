import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Dots, Keypad } from "@/components/Keypad";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";
import { api, ApiError, setToken } from "@/lib/api";
import { deviceId, useAuth } from "@/lib/auth";

type Step = "phone" | "otp" | "pin";
type LoginOut = { token: string; stage: string; has_pin: boolean; new_device: boolean };

export default function Login() {
  const { t, i18n } = useTranslation();
  const { signIn } = useAuth();
  const nav = useNavigate();
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");
  const [hasPin, setHasPin] = useState(false);
  const [sandboxCode, setSandboxCode] = useState<string | null>(null);
  const [newDevice, setNewDevice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newProfile, setNewProfile] = useState(false);
  const [profileName, setProfileName] = useState("");

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  const sendOtp = () =>
    run(async () => {
      const res = await api<{ sandbox_code: string | null }>("/auth/otp/request", {
        method: "POST",
        json: { phone, language: i18n.language },
      });
      setSandboxCode(res.sandbox_code);
      setStep("otp");
    });

  const verifyOtp = () =>
    run(async () => {
      const res = await api<LoginOut>("/auth/otp/verify", {
        method: "POST",
        json: { phone, code, device_id: deviceId(), language: i18n.language },
      });
      setToken(res.token);
      setHasPin(res.has_pin);
      setNewDevice(res.new_device);
      setStep("pin");
    });

  const submitPin = () =>
    run(async () => {
      if (newProfile) {
        await api("/auth/profile/new", { method: "POST", json: { name: profileName, pin } });
        const token = localStorage.getItem("ktp.token");
        if (token) await signIn(token);
        nav("/consent");
        return;
      }
      await api(hasPin ? "/auth/pin/verify" : "/auth/pin/set", { method: "POST", json: { pin } });
      const token = localStorage.getItem("ktp.token");
      if (token) await signIn(token);
      nav(hasPin ? "/home" : "/consent");
    });

  const spoken =
    step === "phone" ? [t("login.phone")] : step === "otp" ? [t("login.otp")] : hasPin ? [t("login.enter_pin")] : [t("login.set_pin"), t("login.set_pin_why")];

  return (
    <Screen title={t("login.title")} spoken={spoken}>
      {step === "phone" && (
        <>
          <label className="font-semibold">{t("login.phone")}</label>
          <p className="rounded-2xl bg-white p-4 text-center text-3xl font-bold tabular-nums text-ink shadow-sm ring-1 ring-black/10 tracking-widest" data-testid="phone-display">
            +91 {phone || "__________"}
          </p>
          <Keypad value={phone} onChange={setPhone} max={10} />
          <BigButton disabled={phone.length !== 10 || busy} onClick={sendOtp}>
            {t("login.send_otp")}
          </BigButton>
        </>
      )}
      {step === "otp" && (
        <>
          <p>{t("login.otp")}</p>
          {sandboxCode && (
            <p className="rounded-xl bg-yellow-100 p-2 text-center font-mono" data-testid="sandbox-otp">
              {t("login.sandbox_otp", { code: sandboxCode })}
            </p>
          )}
          <Dots value={code} length={6} label={t("login.otp")} />
          <Keypad value={code} onChange={setCode} max={6} />
          <BigButton disabled={code.length !== 6 || busy} onClick={verifyOtp}>
            {t("login.verify")}
          </BigButton>
        </>
      )}
      {step === "pin" && (
        <>
          {newDevice && <p className="rounded-xl bg-orange-100 p-3">{t("login.new_device")}</p>}
          {newProfile ? (
            <>
              <input aria-label={t("login.profile_name")} placeholder={t("login.profile_name")} className="field" value={profileName} onChange={(e) => setProfileName(e.target.value)} />
              <p className="font-semibold">{t("login.new_profile_pin")}</p>
            </>
          ) : (
            <p className="font-semibold">{hasPin ? t("login.enter_pin") : t("login.set_pin")}</p>
          )}
          {(!hasPin || newProfile) && (
            <p>
              {t("login.set_pin_why")} {t("login.pin_hint")}
            </p>
          )}
          <Dots value={pin} length={4} label="PIN" />
          <Keypad value={pin} onChange={setPin} max={4} />
          <BigButton disabled={pin.length !== 4 || busy || (newProfile && profileName.trim().length < 2)} onClick={submitPin}>
            {newProfile ? t("login.create_profile") : t("common.next")}
          </BigButton>
          {hasPin && !newProfile && (
            <BigButton
              variant="ghost"
              onClick={() => {
                setNewProfile(true);
                setPin("");
              }}
            >
              {t("login.new_profile")}
            </BigButton>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-red-100 p-3 text-red-900">
          {error}
        </p>
      )}
    </Screen>
  );
}
