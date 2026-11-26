/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { brand: { DEFAULT: "#14532d", light: "#dcfce7" } } } },
  plugins: [],
};
