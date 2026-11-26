import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import "./i18n";

export function renderAt(ui: ReactElement, path = "/") {
  return render(<MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{ui}</MemoryRouter>);
}
