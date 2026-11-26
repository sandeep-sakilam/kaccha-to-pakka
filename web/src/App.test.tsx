import { act, fireEvent, screen } from "@testing-library/react";
import { AppRoutes } from "./App";
import i18n, { setLanguage } from "./i18n";
import { renderAt } from "./test-utils";

test("welcome screen in Hindi by default, switches to English", async () => {
  setLanguage("hi");
  renderAt(<AppRoutes />);
  expect(screen.getByRole("heading", { name: "नमस्ते! स्वागत है" })).toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "English" })));
  expect(i18n.language).toBe("en");
  expect(screen.getByRole("heading", { name: /welcome/i })).toBeInTheDocument();
});

test("every screen has a Listen button", () => {
  setLanguage("en");
  renderAt(<AppRoutes />);
  expect(screen.getByRole("button", { name: /listen/i })).toBeInTheDocument();
});

test("sandbox badge is shown", () => {
  setLanguage("en");
  renderAt(<AppRoutes />);
  expect(screen.getAllByTestId("sandbox-badge").length).toBeGreaterThan(0);
});
