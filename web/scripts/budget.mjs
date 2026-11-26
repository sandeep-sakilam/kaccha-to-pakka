// Low-end phone budget: what the first screen downloads must stay under 300 KB gzipped.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join } from "node:path";

const BUDGET = 300 * 1024;
const dist = new URL("../dist/", import.meta.url).pathname;
const html = readFileSync(join(dist, "index.html"), "utf8");
const refs = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1]);
let total = gzipSync(html).length;
for (const r of refs) total += gzipSync(readFileSync(join(dist, r))).length;
const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
const lazy = readdirSync(join(dist, "assets")).filter((f) => !refs.includes(`assets/${f}`));
console.log(`first load: ${kb(total)} gzipped (${refs.length} files); ${lazy.length} lazy chunks; budget ${kb(BUDGET)}`);
for (const f of lazy.filter((f) => f.endsWith(".js"))) {
  const size = gzipSync(readFileSync(join(dist, "assets", f))).length;
  if (size > 100 * 1024) console.log(`  large lazy chunk ${f}: ${kb(size)}`);
}
if (total > BUDGET) {
  console.error("over budget");
  process.exit(1);
}
void statSync;
