/**
 * Voice playback. Uses the server voice (Sarvam Bulbul) when it is real; in Sandbox, or when the
 * network is down, falls back to the phone's own speech engine so every screen can still be heard.
 */
import { API_BASE } from "./api";

let serverVoice = false;
let current: HTMLAudioElement | null = null;

export function setServerVoice(enabled: boolean): void {
  serverVoice = enabled;
}

export function stopSpeaking(): void {
  current?.pause();
  current = null;
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
}

function speakLocally(text: string, lang: string): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === "hi" ? "hi-IN" : "en-IN";
    u.rate = 0.9;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

export async function speak(lines: string[], lang: string): Promise<void> {
  stopSpeaking();
  const text = lines.filter(Boolean).join(". ");
  if (!text) return;
  if (serverVoice && navigator.onLine) {
    try {
      const res = await fetch(`${API_BASE}/voice/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language: lang }),
      });
      if (res.ok) {
        const url = URL.createObjectURL(await res.blob());
        current = new Audio(url);
        await current.play();
        return;
      }
    } catch {
      /* fall through to local voice */
    }
  }
  await speakLocally(text, lang);
}

/** Amounts are read in words, because digits are where errors hide. */
export function rupeesInWords(paise: number, lang: string): string {
  const rupees = Math.round(paise / 100);
  if (lang === "hi") return hindiNumber(rupees) + " रुपये";
  return englishNumber(rupees) + " rupees";
}

const HI_0_99 = (
  "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस " +
  "इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस " +
  "सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास " +
  "इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ " +
  "अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी " +
  "बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानबे बानवे तिरानवे चौरानवे पचानवे छियानवे " +
  "सत्तानवे अट्ठानवे निन्यानवे"
).split(" ");

export function hindiNumber(n: number): string {
  if (n < 100) return HI_0_99[n];
  const parts: string[] = [];
  const units: [number, string][] = [
    [10_000_000, "करोड़"],
    [100_000, "लाख"],
    [1000, "हज़ार"],
    [100, "सौ"],
  ];
  let rest = n;
  for (const [size, word] of units) {
    if (rest >= size) {
      parts.push(`${hindiNumber(Math.floor(rest / size))} ${word}`);
      rest %= size;
    }
  }
  if (rest > 0) parts.push(HI_0_99[rest]);
  return parts.join(" ");
}

const EN_ONES =
  "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(
    " ",
  );
const EN_TENS = "  twenty thirty forty fifty sixty seventy eighty ninety".split(" ");

export function englishNumber(n: number): string {
  if (n < 20) return EN_ONES[n];
  if (n < 100) return EN_TENS[Math.floor(n / 10)] + (n % 10 ? "-" + EN_ONES[n % 10] : "");
  const units: [number, string][] = [
    [10_000_000, "crore"],
    [100_000, "lakh"],
    [1000, "thousand"],
    [100, "hundred"],
  ];
  const parts: string[] = [];
  let rest = n;
  for (const [size, word] of units) {
    if (rest >= size) {
      parts.push(`${englishNumber(Math.floor(rest / size))} ${word}`);
      rest %= size;
    }
  }
  if (rest > 0) parts.push(englishNumber(rest));
  return parts.join(" ");
}
