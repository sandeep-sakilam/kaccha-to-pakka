/** Thin fetch wrapper. All calls go through the one API at /api. */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

let token: string | null = null;
try {
  token = localStorage.getItem("ktp.token");
} catch {
  token = null;
}

export function setToken(t: string | null): void {
  token = t;
  try {
    if (t) localStorage.setItem("ktp.token", t);
    else localStorage.removeItem("ktp.token");
  } catch {
    /* ignore */
  }
}

export function getToken(): string | null {
  return token;
}

export const API_BASE = "/api";

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(API_BASE + path, { ...init, headers, body });
  if (!res.ok) {
    let code = "error";
    let message = res.statusText;
    try {
      const data = (await res.json()) as { code?: string; message?: string; detail?: unknown };
      code = data.code ?? code;
      message = data.message ?? (typeof data.detail === "string" ? data.detail : message);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, code, message);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? await res.json() : await res.blob()) as T;
}
