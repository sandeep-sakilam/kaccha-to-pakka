import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { setServerVoice } from "./voice";

type SandboxInfo = { any_sandbox: boolean; services: Record<string, boolean> };

const SandboxContext = createContext<SandboxInfo>({ any_sandbox: true, services: {} });

export function SandboxProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<SandboxInfo>({ any_sandbox: true, services: {} });
  useEffect(() => {
    api<SandboxInfo>("/meta/sandbox")
      .then((data) => {
        setInfo(data);
        setServerVoice(data.services.ai === false);
      })
      .catch(() => setInfo({ any_sandbox: true, services: {} }));
  }, []);
  return <SandboxContext.Provider value={info}>{children}</SandboxContext.Provider>;
}

export function useSandbox(): SandboxInfo {
  return useContext(SandboxContext);
}
