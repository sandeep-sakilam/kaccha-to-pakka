import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Camera, type Shot } from "@/components/Camera";
import { Screen } from "@/components/Screen";
import { BigButton } from "@/components/ui";
import { deviceId } from "@/lib/auth";
import { currentPosition } from "@/lib/geo";
import { enqueue, pendingCount, syncQueue } from "@/lib/queue";
import { speak } from "@/lib/voice";

export default function Capture() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const { businessId = "", kind = "ledger_page" } = useParams();
  const [params] = useSearchParams();
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(0);
  const [sentOnce, setSentOnce] = useState(false);

  useEffect(() => {
    void pendingCount().then(setPending);
  }, []);

  async function onShot(shot: Shot) {
    const geo = await currentPosition();
    await enqueue({
      key: crypto.randomUUID(),
      businessId,
      kind,
      bytes: shot.bytes,
      mime: shot.mime,
      capturedAt: shot.capturedAt,
      deviceId: deviceId(),
      geo,
      quality: { blur: shot.quality.blur, brightness: shot.quality.brightness, glare: shot.quality.glare },
    });
    const res = navigator.onLine ? await syncQueue() : { sent: 0, failed: 1, rejected: [] };
    let msg = t("capture.saved");
    if (res.sent > 0) msg = t("capture.sent");
    if (res.rejected.length) msg = t("capture.rejected", { reason: res.rejected[0].reason });
    setMessage(msg);
    setSentOnce(res.sent > 0);
    void speak([msg], i18n.language);
    setPending(await pendingCount());
  }

  return (
    <Screen title={t(`capture.title_${kind}`)} spoken={[t(`capture.hint_${kind}`), t("capture.why_camera")]}>
      <p>{t(`capture.hint_${kind}`)}</p>
      <p className="text-sm text-gray-600">{t("capture.why_camera")}</p>
      <Camera onShot={onShot} />
      {message && (
        <p role="status" className="rounded-xl bg-brand-light p-3 text-lg" data-testid="capture-status">
          {message}
        </p>
      )}
      {pending > 0 && <p className="text-sm">{t("capture.pending", { count: pending })}</p>}
      {(sentOnce || message) && (
        <BigButton variant="secondary" onClick={() => nav(params.get("next") ?? "/home")}>
          {t("capture.done")}
        </BigButton>
      )}
    </Screen>
  );
}
