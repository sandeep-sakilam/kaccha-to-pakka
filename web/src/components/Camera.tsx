import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { assess, type Quality } from "@/lib/quality";
import { speak } from "@/lib/voice";
import { BigButton } from "./ui";

export type Shot = { bytes: ArrayBuffer; mime: string; quality: Quality; capturedAt: string };

const MAX_SIDE = 1600;

/** Live camera only: there is deliberately no gallery picker. */
export function Camera({ onShot }: { onShot: (s: Shot) => void }) {
  const { t, i18n } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1600 } }, audio: false })
      .then((s) => {
        stream = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play();
        }
      })
      .catch(() => setError(t("capture.no_camera")));
    if (!navigator.mediaDevices) setError(t("capture.no_camera"));
    return () => stream?.getTracks().forEach((tr) => tr.stop());
  }, [t]);

  async function take() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const scale = Math.min(1, MAX_SIDE / Math.max(v.videoWidth, v.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(v.videoWidth * scale);
    canvas.height = Math.round(v.videoHeight * scale);
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
    const small = document.createElement("canvas");
    const s2 = 320 / Math.max(canvas.width, canvas.height);
    small.width = Math.round(canvas.width * s2);
    small.height = Math.round(canvas.height * s2);
    small.getContext("2d")!.drawImage(canvas, 0, 0, small.width, small.height);
    const px = small.getContext("2d")!.getImageData(0, 0, small.width, small.height);
    const quality = assess(px);
    if (!quality.ok && quality.problem) {
      setProblem(t(`capture.${quality.problem}`));
      void speak([t(`capture.${quality.problem}`)], i18n.language);
      return;
    }
    setProblem(null);
    const blob = await new Promise<Blob>((res) => canvas.toBlob((b) => res(b!), "image/jpeg", 0.75));
    onShot({ bytes: await blob.arrayBuffer(), mime: "image/jpeg", quality, capturedAt: new Date().toISOString() });
  }

  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <p role="alert" className="rounded-xl bg-red-100 p-3">
          {error}
        </p>
      ) : (
        <video ref={video} playsInline muted className="aspect-[3/4] w-full rounded-2xl bg-black object-cover" aria-label="camera" />
      )}
      {problem && (
        <p role="alert" className="rounded-xl bg-orange-100 p-3 text-lg" data-testid="quality-problem">
          {problem}
        </p>
      )}
      <BigButton icon="📸" onClick={take} disabled={Boolean(error)}>
        {t("capture.take")}
      </BigButton>
    </div>
  );
}
