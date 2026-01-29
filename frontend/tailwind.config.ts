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
        // Core palette from design brief
        snow: "#FAFAFA",
        graphite: "#1A1A1A",
        slate: "#6B7280",
        silver: "#9CA3AF",
        mist: "#E5E7EB",
        ink: "#0F172A",
        // Semantic colors
        charcoal: "#374151",
        fog: "#D1D5DB",
        forest: "#059669",
        rust: "#DC2626",
        emerald: "#10B981",
        amber: "#F59E0B",
      },
      fontFamily: {
        sans: ["Inter", ...defaultTheme.fontFamily.sans],
        mono: ["JetBrains Mono", "SF Mono", ...defaultTheme.fontFamily.mono],
      },
      fontSize: {
        // Custom type scale from design brief
        display: ["48px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "700" }],
        "title-1": ["28px", { lineHeight: "1.2", letterSpacing: "-0.01em", fontWeight: "600" }],
        "title-2": ["22px", { lineHeight: "1.25", letterSpacing: "-0.01em", fontWeight: "600" }],
        "title-3": ["18px", { lineHeight: "1.3", letterSpacing: "0", fontWeight: "600" }],
        body: ["16px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "400" }],
        "body-strong": ["16px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "600" }],
        caption: ["14px", { lineHeight: "1.4", letterSpacing: "0.01em", fontWeight: "400" }],
        "caption-strong": ["14px", { lineHeight: "1.4", letterSpacing: "0.01em", fontWeight: "600" }],
        micro: ["12px", { lineHeight: "1.3", letterSpacing: "0.02em", fontWeight: "500" }],
        probability: ["32px", { lineHeight: "1", letterSpacing: "-0.02em", fontWeight: "700" }],
      },
      spacing: {
        // Design system spacing
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
        card: "0 1px 3px rgba(0,0,0,0.08)",
        "card-hover": "0 4px 12px rgba(0,0,0,0.08)",
      },
      borderRadius: {
        card: "12px",
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
