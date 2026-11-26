/**
 * Capture a spoken answer. With real server speech-to-text we record audio and send it; in
 * Sandbox we use the phone's speech recogniser when present. Typing is always a fallback,
 * never a requirement.
 */

type Recogniser = {
  lang: string;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

export type Heard = { transcript?: string; audio_b64?: string };

export function canListen(): boolean {
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition || navigator.mediaDevices?.getUserMedia);
}

export async function listenOnce(lang: string, serverStt: boolean, maxMs = 8000): Promise<Heard> {
  const w = window as unknown as Record<string, new () => Recogniser>;
  const Rec = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!serverStt && Rec) {
    return new Promise((resolve, reject) => {
      const r = new Rec();
      r.lang = lang === "hi" ? "hi-IN" : "en-IN";
      r.interimResults = false;
      let done = false;
      r.onresult = (e) => {
        done = true;
        resolve({ transcript: e.results[0][0].transcript });
      };
      r.onerror = () => reject(new Error("no speech"));
      r.onend = () => !done && reject(new Error("no speech"));
      r.start();
      setTimeout(() => r.stop(), maxMs);
    });
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const rec = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  const stopped = new Promise<void>((res) => (rec.onstop = () => res()));
  rec.start();
  setTimeout(() => rec.state !== "inactive" && rec.stop(), maxMs);
  await stopped;
  stream.getTracks().forEach((t) => t.stop());
  const buf = await new Blob(chunks).arrayBuffer();
  let bin = "";
  new Uint8Array(buf).forEach((b) => (bin += String.fromCharCode(b)));
  return { audio_b64: btoa(bin) };
}
