import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#07111f",
          900: "#0c1b33",
          800: "#163056",
          700: "#1d4474",
        },
        paper: "#f3efe6",
        card: "#fffcf8",
        ink: "#142033",
        mist: "#5c6b7c",
        line: "#e4dccf",
        gold: "#a67c2d",
        clay: "#8d3b3b",
        pine: "#1d6b4a",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Segoe UI", "sans-serif"],
        display: ["var(--font-display)", "Georgia", "serif"],
      },
      boxShadow: {
        soft: "0 18px 50px -28px rgba(12, 27, 51, 0.55)",
      },
    },
  },
  plugins: [],
};

export default config;
