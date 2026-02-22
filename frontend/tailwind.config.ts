import type { Config } from "tailwindcss";
import defaultTheme from "tailwindcss/defaultTheme";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // === Scoreboard Dark Design System ===
        // Surfaces (layered dark)
        surface: {
          deep: "#0C0F14",    // Page background
          card: "#141820",    // Card background
          elevated: "#1C2028", // Hover / raised elements
          border: "#242830",   // Borders between elements
        },
        // Text hierarchy
        text: {
          primary: "#F8FAFC",   // Headlines, numbers
          secondary: "#94A3B8", // Labels, descriptions
          muted: "#475569",     // Metadata, timestamps
          inverse: "#0C0F14",   // Text on light backgrounds
        },
        // Accents
        accent: {
          live: "#22C55E",      // Live games, positive
          brand: "#10B981",     // Primary brand / CTA
          futures: "#8B5CF6",   // Futures/predictions
          warning: "#F59E0B",   // Warnings, starting soon
          danger: "#EF4444",    // Negative movement
        },

        // Legacy aliases (keep existing code working during migration)
        snow: "#0C0F14",       // Now maps to dark background
        graphite: "#F8FAFC",   // Now maps to light text
        slate: "#94A3B8",      // Now maps to secondary text
        silver: "#475569",     // Now maps to muted text
        mist: "#242830",       // Now maps to border color
        ink: "#F8FAFC",
        charcoal: "#94A3B8",
        fog: "#1C2028",
        forest: "#22C55E",
        rust: "#EF4444",
        emerald: "#10B981",
        amber: "#F59E0B",
      },
      fontFamily: {
        sans: ["Inter", ...defaultTheme.fontFamily.sans],
        mono: ["var(--font-jetbrains-mono)", "SF Mono", ...defaultTheme.fontFamily.mono],
      },
      fontSize: {
        // Hero probability numbers
        "prob-hero": ["36px", { lineHeight: "1", letterSpacing: "-0.03em", fontWeight: "700" }],
        "prob-lg": ["28px", { lineHeight: "1", letterSpacing: "-0.02em", fontWeight: "700" }],
        "prob-md": ["20px", { lineHeight: "1", letterSpacing: "-0.02em", fontWeight: "700" }],
        "prob-sm": ["16px", { lineHeight: "1", letterSpacing: "-0.01em", fontWeight: "700" }],
        // UI type scale
        display: ["48px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "700" }],
        "title-1": ["28px", { lineHeight: "1.2", letterSpacing: "-0.01em", fontWeight: "600" }],
        "title-2": ["22px", { lineHeight: "1.25", letterSpacing: "-0.01em", fontWeight: "600" }],
        "title-3": ["18px", { lineHeight: "1.3", letterSpacing: "0", fontWeight: "600" }],
        body: ["16px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "400" }],
        "body-strong": ["16px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "600" }],
        caption: ["14px", { lineHeight: "1.4", letterSpacing: "0.01em", fontWeight: "400" }],
        "caption-strong": ["14px", { lineHeight: "1.4", letterSpacing: "0.01em", fontWeight: "600" }],
        micro: ["12px", { lineHeight: "1.3", letterSpacing: "0.02em", fontWeight: "500" }],
        "micro-xs": ["10px", { lineHeight: "1.2", letterSpacing: "0.04em", fontWeight: "600" }],
      },
      spacing: {
        "space-1": "4px",
        "space-2": "8px",
        "space-3": "12px",
        "space-4": "16px",
        "space-5": "20px",
        "space-6": "24px",
        "space-8": "32px",
        "space-10": "40px",
        "space-12": "48px",
        "space-16": "64px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.03)",
        "card-hover": "0 4px 16px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.06)",
        glow: "0 0 20px rgba(16, 185, 129, 0.15)",
      },
      borderRadius: {
        card: "10px",
      },
      transitionDuration: {
        fast: "150ms",
        base: "200ms",
        slow: "300ms",
        probability: "400ms",
      },
      maxWidth: {
        content: "1200px",
      },
    },
  },
  plugins: [],
};

export default config;
