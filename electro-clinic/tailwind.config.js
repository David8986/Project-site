/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        clinic: {
          bg: "#050B12",
          panel: "#0B1220",
          panelSoft: "#101A2B",
          line: "rgba(148, 163, 184, 0.22)",
          cyan: "#22D3EE",
          blue: "#3B82F6",
          green: "#34D399",
          text: "#F8FAFC",
          muted: "#A7B3C8",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 36px rgba(34, 211, 238, 0.22)",
        card: "0 18px 60px rgba(0, 0, 0, 0.28)",
      },
      backgroundImage: {
        "circuit-grid":
          "linear-gradient(rgba(148, 163, 184, 0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(148, 163, 184, 0.05) 1px, transparent 1px)",
      },
    },
  },
  plugins: [],
};
