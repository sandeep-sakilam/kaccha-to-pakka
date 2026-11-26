import { defineConfig } from "@playwright/test";

const backendEnv = [
  "DATABASE_URL=postgresql+psycopg://ktp:ktp@localhost:5432/ktp_e2e",
  "APP_ENV=test",
  "AI_PROVIDER=mock FALLBACK_AI_PROVIDER=mock AA_PROVIDER=mock PAYMENTS_PROVIDER=mock",
  "WHATSAPP_PROVIDER=mock KYC_PROVIDER=mock SMS_PROVIDER=mock STORAGE_PROVIDER=memory",
  "UV_SYSTEM_CERTS=1",
].join(" ");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: "http://localhost:4173", trace: "off" },
  webServer: [
    {
      command: `cd ../backend && env -u UV_NATIVE_TLS ${backendEnv} sh -c "uv run python -m scripts.reset_e2e_db && uv run uvicorn app.main:app --port 8010"`,
      url: "http://localhost:8010/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npx vite build && npx vite preview --port 4173 --strictPort",
      port: 4173,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        permissions: ["camera", "geolocation"],
        geolocation: { latitude: 22.7186, longitude: 75.8553, accuracy: 15 },
        launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
      },
    },
  ],
});
