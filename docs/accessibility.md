# Accessibility (WCAG 2.2 AA) and low-end phones

The test for every screen: a 55-year-old kirana owner who reads little, with a ₹6,000 phone on a weak network, can finish it alone or with a Sahayak.

## Automated checks (run in `make e2e`)

- `e2e/a11y.spec.ts`: axe-core with WCAG 2.0/2.1/2.2 A and AA rules on welcome (Hindi and English), what-we-never-do, login, home, passport and lender screens: no violations.
- `e2e/low-end.spec.ts`: Moto G4 profile, slow 3G (400 kbps, 400 ms) and 4× CPU throttling; the first screen is usable in under 15 s (measured ~3.7 s); tap targets are at least 48 px; keyboard users can skip to content.
- `npm run budget` (part of `make check`): first-load HTML+JS+CSS must stay under 300 KB gzipped (currently ~120 KB); every other screen is a lazy chunk.

## Design rules in the code

- Every screen has a Listen button (`<Screen spoken=[…]>`); amounts are read in words.
- No typing required: keypads, big yes/no buttons, icon choices with spoken labels; typing is only a fallback.
- Large tap targets (`min-h-12`/`min-h-14`, i.e. 48–56 px), 18 px base font, high-contrast brand colours.
- Visible focus on every control (3 px outline), "Skip to main content" link, `lang` attribute follows the chosen language, live regions (`role="status"`/`role="alert"`) for results and errors.
- Reduced motion respected; no information conveyed by colour alone (bands always show the letter and a label).
- Offline: captures queue in IndexedDB and sync later; the app shell is cached by the service worker.

## Manual checks still to do with real users

- TalkBack walkthrough on a low-end Android phone in Hindi.
- Unaided task completion with 5 shopkeepers (see SPEC Evaluation).
