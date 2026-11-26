import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import "./i18n";
import { AuthProvider } from "./lib/auth";

export function renderAt(ui: ReactElement, path = "/") {
  return render(<AuthProvider><MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{ui}</MemoryRouter></AuthProvider>);
}
