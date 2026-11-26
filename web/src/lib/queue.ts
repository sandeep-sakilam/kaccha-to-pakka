/**
 * Offline capture queue (IndexedDB via Dexie). Photos are saved on the phone first and sent when
 * the network is back. Each item keeps its idempotency key, so a retry never makes a duplicate.
 */
import Dexie, { type Table } from "dexie";
import { getToken } from "./api";

export type QueuedCapture = {
  key: string;
  businessId: string;
  kind: string;
  bytes: ArrayBuffer; // stored as bytes: Blobs in IndexedDB are unreliable on older phones
  mime: string;
  capturedAt: string;
  deviceId: string;
  geo: { lat: number; lng: number; accuracy_m: number } | null;
  quality: Record<string, unknown>;
  attempts: number;
  lastError: string | null;
  status: "pending" | "failed";
};

class QueueDB extends Dexie {
  captures!: Table<QueuedCapture, string>;
  constructor() {
    super("ktp-queue");
    this.version(1).stores({ captures: "key, businessId, status" });
  }
}

export const queueDb = new QueueDB();

export async function enqueue(item: Omit<QueuedCapture, "attempts" | "lastError" | "status">): Promise<void> {
  await queueDb.captures.put({ ...item, attempts: 0, lastError: null, status: "pending" });
}

export async function pendingCount(): Promise<number> {
  return queueDb.captures.where("status").equals("pending").count();
}

export type SyncResult = { sent: number; failed: number; rejected: { key: string; reason: string }[] };

const RETRYABLE = new Set([0, 408, 425, 429, 500, 502, 503, 504]);

export async function syncQueue(apiBase = "/api", fetchFn: typeof fetch = fetch): Promise<SyncResult> {
  const items = await queueDb.captures.where("status").equals("pending").toArray();
  const result: SyncResult = { sent: 0, failed: 0, rejected: [] };
  for (const item of items) {
    const form = new FormData();
    form.append("file", new Blob([item.bytes], { type: item.mime }), `capture.${item.mime.split("/")[1] ?? "jpg"}`);
    form.append("kind", item.kind);
    form.append("captured_at", item.capturedAt);
    form.append("device_id", item.deviceId);
    form.append("client_quality", JSON.stringify(item.quality));
    if (item.geo) {
      form.append("lat", String(item.geo.lat));
      form.append("lng", String(item.geo.lng));
      form.append("accuracy_m", String(item.geo.accuracy_m));
    }
    let status = 0;
    let reason = "network";
    try {
      const headers: Record<string, string> = { "Idempotency-Key": item.key };
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetchFn(`${apiBase}/businesses/${item.businessId}/captures`, { method: "POST", body: form, headers });
      status = res.status;
      if (res.ok) {
        await queueDb.captures.delete(item.key);
        result.sent++;
        continue;
      }
      try {
        reason = ((await res.json()) as { message?: string }).message ?? String(status);
      } catch {
        reason = String(status);
      }
    } catch {
      status = 0;
    }
    if (RETRYABLE.has(status)) {
      await queueDb.captures.update(item.key, { attempts: item.attempts + 1, lastError: reason });
      result.failed++;
    } else {
      await queueDb.captures.update(item.key, { status: "failed", lastError: reason });
      result.rejected.push({ key: item.key, reason });
    }
  }
  return result;
}

let started = false;

/** Sync now, whenever the network returns, and every 30 seconds while the app is open. */
export function startBackgroundSync(): void {
  if (started || typeof window === "undefined") return;
  started = true;
  const run = () => void syncQueue().catch(() => undefined);
  window.addEventListener("online", run);
  setInterval(() => navigator.onLine && run(), 30_000);
  run();
}
