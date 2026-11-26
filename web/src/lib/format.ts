/** Timestamps are stored in UTC and shown in IST. */
export function istDate(iso: string, lang: string): string {
  return new Date(iso).toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "long", year: "numeric" });
}

export function istDateTime(iso: string, lang: string): string {
  return new Date(iso).toLocaleString(lang === "hi" ? "hi-IN" : "en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}
