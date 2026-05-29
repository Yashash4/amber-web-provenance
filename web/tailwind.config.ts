import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Amber palette — the forensic-instrument look.
        amber: {
          DEFAULT: "#f59e0b",
          deep: "#b45309",
        },
        verified: "#16a34a",
        broken: "#dc2626",
        ink: "#0a0a0b",
        panel: "#15151a",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
