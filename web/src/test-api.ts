/** Route fetch calls in tests: the first matching rule answers; calls are recorded. */
export type Call = { url: string; method: string; body: unknown };
type Rule = [RegExp, (call: Call) => unknown];

export function mockApi(rules: Rule[]): Call[] {
  const calls: Call[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    let body: unknown = undefined;
    if (typeof init?.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    } else if (init?.body) body = init.body;
    const call = { url: u, method: init?.method ?? "GET", body };
    calls.push(call);
    for (const [re, fn] of rules) {
      if (re.test(`${call.method} ${u}`)) {
        const out = fn(call);
        if (out instanceof Response) return out;
        return new Response(JSON.stringify(out ?? {}), { headers: { "content-type": "application/json" } });
      }
    }
    return new Response(JSON.stringify({ any_sandbox: true, services: { ai: true } }), { headers: { "content-type": "application/json" } });
  });
  return calls;
}

export const posted = (calls: Call[], re: RegExp) => calls.filter((c) => c.method === "POST" && re.test(c.url));
