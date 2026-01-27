import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Custom colors for odds display
        favorite: {
          light: "#dcfce7",
          DEFAULT: "#22c55e",
          dark: "#166534",
        },
        underdog: {
          light: "#fee2e2",
          DEFAULT: "#ef4444",
          dark: "#991b1b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
