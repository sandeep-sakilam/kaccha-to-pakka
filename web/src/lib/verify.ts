/**
 * Offline passport verification for lenders: the QR carries a compact payload signed with our
 * Ed25519 key. The signature is checked in the browser with the public key (cached for offline
 * use); live status (valid, revoked, on hold, expired) is fetched when online.
 */
import nacl from "tweetnacl";

export type CompactPassport = { v: number; id: string; n: string; c: string; b: string; cf: string; st: string; vu: string; r: string; sb: boolean; kid: string };

/** Same bytes as Python json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False). */
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return `{${Object.keys(obj)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${canonical(obj[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function b64ToBytes(b64: string): Uint8Array {
  const norm = b64.replace(/-/g, "+").replace(/_/g, "/");
  const pad = norm + "=".repeat((4 - (norm.length % 4)) % 4);
  const bin = atob(pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function inflate(bytes: Uint8Array): Promise<string> {
  const stream = new Response(bytes).body!.pipeThrough(new DecompressionStream("deflate"));
  return new Response(stream).text();
}

export async function decodeToken(token: string): Promise<{ payload: CompactPassport; signature: string } | null> {
  try {
    const data = JSON.parse(await inflate(b64ToBytes(token))) as { p: CompactPassport; s: string };
    return { payload: data.p, signature: data.s };
  } catch {
    return null;
  }
}

export function verifySignature(payload: unknown, signatureB64url: string, publicKeyB64: string): boolean {
  try {
    const msg = Uint8Array.from(new TextEncoder().encode(canonical(payload)));
    return nacl.sign.detached.verify(msg, b64ToBytes(signatureB64url), b64ToBytes(publicKeyB64));
  } catch {
    return false;
  }
}

export async function publicKey(fetchFn: typeof fetch = fetch): Promise<string | null> {
  try {
    const res = await fetchFn("/api/.well-known/ktp-keys.json");
    const data = (await res.json()) as { keys: { public_key: string }[] };
    const key = data.keys[0].public_key;
    try {
      localStorage.setItem("ktp.pubkey", key);
    } catch {
      /* ignore */
    }
    return key;
  } catch {
    try {
      return localStorage.getItem("ktp.pubkey");
    } catch {
      return null;
    }
  }
}
