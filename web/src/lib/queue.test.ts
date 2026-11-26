import { enqueue, pendingCount, queueDb, syncQueue } from "./queue";

beforeEach(async () => {
  await queueDb.captures.clear();
});

const item = (key: string) => ({
  key,
  businessId: "b1",
  kind: "ledger_page",
  bytes: new Uint8Array([1, 2, 3]).buffer,
  mime: "image/jpeg",
  capturedAt: new Date().toISOString(),
  deviceId: "web-1",
  geo: null,
  quality: {},
});

test("offline: items stay queued and retry later with the same key", async () => {
  await enqueue(item("k1"));
  const offline = vi.fn(async () => {
    throw new TypeError("network down");
  });
  expect((await syncQueue("/api", offline as unknown as typeof fetch)).failed).toBe(1);
  expect(await pendingCount()).toBe(1);

  const keys: string[] = [];
  const online = vi.fn(async (_url: string, init: RequestInit) => {
    keys.push((init.headers as Record<string, string>)["Idempotency-Key"]);
    return new Response("{}", { status: 200 });
  });
  expect((await syncQueue("/api", online as unknown as typeof fetch)).sent).toBe(1);
  expect(keys).toEqual(["k1"]);
  expect(await pendingCount()).toBe(0);
});

test("a rejected photo is not retried forever", async () => {
  await enqueue(item("k2"));
  const reject = vi.fn(async () => new Response(JSON.stringify({ message: "Please retake" }), { status: 400 }));
  const res = await syncQueue("/api", reject as unknown as typeof fetch);
  expect(res.rejected).toEqual([{ key: "k2", reason: "Please retake" }]);
  expect(await pendingCount()).toBe(0);
});
