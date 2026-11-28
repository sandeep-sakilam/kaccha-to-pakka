/** One colour per band, shared by the owner's passport, the lender view and the history. White text
 * on each meets WCAG AA. */
export const BAND_BG: Record<string, string> = {
  A: "bg-emerald-700",
  B: "bg-green-700",
  C: "bg-amber-600",
  D: "bg-orange-700",
  E: "bg-red-700",
  U: "bg-gray-600",
};

export const bandBg = (band: string) => BAND_BG[band] ?? "bg-gray-600";
