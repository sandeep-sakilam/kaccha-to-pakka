/**
 * On-phone photo quality check, run before upload so no AI cost is wasted on a bad photo.
 * Blur: variance of the Laplacian on a downscaled grey image. Light: mean brightness.
 * Glare: share of near-white pixels.
 */

export type Pixels = { data: Uint8ClampedArray; width: number; height: number };
export type Quality = { blur: number; brightness: number; glare: number; ok: boolean; problem: Problem | null };
export type Problem = "blurry" | "too_dark" | "too_bright" | "glare";

export const THRESHOLDS = { blurMin: 60, darkMax: 40, brightMin: 250, glareMax: 0.25 };

export function grey(px: Pixels): Float32Array {
  const out = new Float32Array(px.width * px.height);
  for (let i = 0, j = 0; i < px.data.length; i += 4, j++) {
    out[j] = 0.299 * px.data[i] + 0.587 * px.data[i + 1] + 0.114 * px.data[i + 2];
  }
  return out;
}

export function laplacianVariance(g: Float32Array, w: number, h: number): number {
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const v = 4 * g[i] - g[i - 1] - g[i + 1] - g[i - w] - g[i + w];
      sum += v;
      sumSq += v * v;
      n++;
    }
  }
  if (n === 0) return 0;
  const mean = sum / n;
  return sumSq / n - mean * mean;
}

export function assess(px: Pixels): Quality {
  const g = grey(px);
  let total = 0;
  let white = 0;
  for (const v of g) {
    total += v;
    if (v > 250) white++;
  }
  const brightness = total / g.length;
  const glare = white / g.length;
  const blur = laplacianVariance(g, px.width, px.height);
  let problem: Problem | null = null;
  if (brightness < THRESHOLDS.darkMax) problem = "too_dark";
  else if (brightness > THRESHOLDS.brightMin) problem = "too_bright";
  else if (glare > THRESHOLDS.glareMax) problem = "glare";
  else if (blur < THRESHOLDS.blurMin) problem = "blurry";
  return { blur: Math.round(blur), brightness: Math.round(brightness), glare: Math.round(glare * 100) / 100, ok: problem === null, problem };
}
