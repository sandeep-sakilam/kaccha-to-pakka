import { act, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { mockApi } from "@/test-api";
import { renderAt } from "@/test-utils";
import Capture from "@/screens/Capture";
import { currentPosition } from "./geo";
import { canListen, listenOnce } from "./listen";

test("GPS position, and null when refused", async () => {
  const geo = {
    getCurrentPosition: (ok: PositionCallback) => ok({ coords: { latitude: 22.7, longitude: 75.8, accuracy: 12.4 } } as GeolocationPosition),
  };
  Object.defineProperty(navigator, "geolocation", { value: geo, configurable: true });
  expect(await currentPosition()).toEqual({ lat: 22.7, lng: 75.8, accuracy_m: 12 });
  geo.getCurrentPosition = (_ok: PositionCallback, err?: PositionErrorCallback | null) => err?.({} as GeolocationPositionError);
  expect(await currentPosition()).toBeNull();
});

test("speech recogniser gives a transcript", async () => {
  class Rec {
    lang = "";
    interimResults = false;
    onresult: ((e: unknown) => void) | null = null;
    onerror: (() => void) | null = null;
    onend: (() => void) | null = null;
    start() {
      setTimeout(() => this.onresult?.({ results: [[{ transcript: "chaar hazaar" }]] }), 0);
    }
    stop() {}
  }
  (window as unknown as Record<string, unknown>).webkitSpeechRecognition = Rec;
  expect(canListen()).toBe(true);
  expect(await listenOnce("hi", false)).toEqual({ transcript: "chaar hazaar" });
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
});

test("capture screen explains when the camera is not available", async () => {
  setLanguage("en");
  mockApi([]);
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: () => Promise.reject(new Error("denied")) }, configurable: true });
  renderAt(
    <Routes>
      <Route path="/capture/:businessId/:kind" element={<Capture />} />
    </Routes>,
    "/capture/b1/shop_front",
  );
  await act(async () => {});
  expect(await vi.waitFor(() => screen.getByRole("alert"))).toHaveTextContent("Camera is not available");
  expect(screen.getByText(/live camera only, not old photos/)).toBeInTheDocument();
});
