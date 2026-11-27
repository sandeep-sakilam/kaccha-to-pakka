import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { mockApi } from "@/test-api";
import { renderAt } from "@/test-utils";
import Home from "./Home";

const show = (category: string) => {
  mockApi([
    [/GET .*\/businesses$/, () => [{ id: "b1", name: "Sethi Sev Traders", category, city: "Indore", is_sandbox: true }]],
    [/GET .*\/(readback|needs-voice|recon\/questions|presence)$/, () => []],
  ]);
  renderAt(<Routes><Route path="/home" element={<Home />} /></Routes>, "/home");
};

describe("Home business card", () => {
  it("names a partner profile in words, not as a raw key", async () => {
    await setLanguage("en");
    show("trading_partner");
    await vi.waitFor(() => screen.getByText("Trading partner"));
    expect(screen.queryByText(/categories\./)).toBeNull();
  });

  it("uses the Hindi label", async () => {
    await setLanguage("hi");
    show("trading_partner");
    await vi.waitFor(() => screen.getByText("व्यापार साझेदार"));
    await setLanguage("en");
  });
});
