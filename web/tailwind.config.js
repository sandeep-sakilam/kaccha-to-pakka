/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Deep "trust" green. DEFAULT keeps white text at >= 7:1 contrast.
        brand: {
          DEFAULT: "#15603a",
          light: "#e7f5ec",
          50: "#f1f9f3",
          100: "#e7f5ec",
          200: "#c6e8d2",
          300: "#93d0aa",
          400: "#57b07a",
          500: "#2f8f57",
          600: "#1f7546",
          700: "#15603a",
          800: "#124d30",
          900: "#0f3d27",
        },
        ink: "#16211b",
        canvas: "#f4f6f2",
      },
      fontFamily: {
        // System fonts only: nothing to download on a weak network. Devanagari falls back to the
        // phone's Noto Sans Devanagari.
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Noto Sans",
          "Noto Sans Devanagari",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16, 33, 24, 0.06), 0 4px 14px -6px rgba(16, 33, 24, 0.10)",
        lift: "0 2px 4px rgba(16, 33, 24, 0.08), 0 10px 24px -10px rgba(16, 33, 24, 0.25)",
      },
    },
  },
  plugins: [],
};
