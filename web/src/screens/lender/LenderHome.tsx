import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";

type Detector = { detect: (src: HTMLVideoElement) => Promise<{ rawValue: string }[]> };

export default function LenderHome() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [link, setLink] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const BD = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => Detector }).BarcodeDetector;

  function open(value: string) {
    try {
      const u = new URL(value.trim(), window.location.origin);
      nav(u.pathname + u.hash);
    } catch {
      /* not a link */
    }
  }

  async function scan() {
    if (!BD || !video.current) return;
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    video.current.srcObject = stream;
    await video.current.play();
    const detector = new BD({ formats: ["qr_code"] });
    for (let i = 0; i < 100; i++) {
      const codes = await detector.detect(video.current);
      if (codes[0]) {
        stream.getTracks().forEach((tr) => tr.stop());
        return open(codes[0].rawValue);
      }
      await new Promise((r) => setTimeout(r, 300));
    }
    stream.getTracks().forEach((tr) => tr.stop());
  }

  return (
    <Screen title={t("lender.title")} spoken={[t("lender.intro")]}>
      <p>{t("lender.intro")}</p>
      {BD && (
        <>
          <video ref={video} playsInline muted className="w-full rounded-xl bg-black" />
          <BigButton icon="📷" onClick={() => void scan()}>
            {t("lender.scan")}
          </BigButton>
        </>
      )}
      <input aria-label={t("lender.paste")} placeholder={t("lender.paste")} className="min-h-12 rounded-xl border-2 border-gray-300 px-3" value={link} onChange={(e) => setLink(e.target.value)} />
      <BigButton disabled={!link} onClick={() => open(link)}>
        {t("lender.open")}
      </BigButton>
    </Screen>
  );
}
