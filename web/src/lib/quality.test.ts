import { assess, type Pixels } from "./quality";

function image(w: number, h: number, fn: (x: number, y: number) => number): Pixels {
  const data = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const v = fn(x, y);
      const i = (y * w + x) * 4;
      data[i] = data[i + 1] = data[i + 2] = v;
      data[i + 3] = 255;
    }
  return { data, width: w, height: h };
}

test("sharp text-like page passes", () => {
  const q = assess(image(200, 200, (x, y) => ((x >> 2) + (y >> 3)) % 2 ? 30 : 230));
  expect(q.ok).toBe(true);
});

test("flat grey is blurry", () => {
  expect(assess(image(100, 100, () => 128)).problem).toBe("blurry");
});

test("dark and glare detected", () => {
  expect(assess(image(100, 100, (x) => (x % 2 ? 10 : 20))).problem).toBe("too_dark");
  expect(assess(image(100, 100, (x, y) => (y < 40 ? 255 : (x % 3 ? 40 : 200)))).problem).toBe("glare");
});
