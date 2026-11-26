import "@testing-library/jest-dom/vitest";
import "fake-indexeddb/auto";
import { vi } from "vitest";

vi.stubGlobal(
  "fetch",
  vi.fn(async (url: string) => {
    if (String(url).endsWith("/meta/sandbox")) {
      return new Response(JSON.stringify({ any_sandbox: true, services: { ai: true } }), {
        headers: { "content-type": "application/json" },
      });
    }
    return new Response("{}", { status: 404, headers: { "content-type": "application/json" } });
  }),
);
