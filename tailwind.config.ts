import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#070b14",
          soft: "#0b1120",
          card: "#0f1626",
          hover: "#141d31",
        },
        line: "#1e2a44",
        accent: {
          DEFAULT: "#10b981",
          soft: "rgba(16,185,129,0.12)",
        },
        danger: {
          DEFAULT: "#ef4444",
          soft: "rgba(239,68,68,0.12)",
        },
        info: {
          DEFAULT: "#38bdf8",
          soft: "rgba(56,189,248,0.12)",
        },
        warn: {
          DEFAULT: "#f59e0b",
          soft: "rgba(245,158,11,0.12)",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(16,185,129,0.25), 0 8px 32px -12px rgba(16,185,129,0.25)",
        card: "0 4px 24px -8px rgba(0,0,0,0.45)",
      },
      animation: {
        "pulse-fast": "pulse 1.2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;