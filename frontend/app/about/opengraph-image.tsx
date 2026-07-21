import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "What is Bain Luck? Probability, not betting.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: "#f8fafc",
          color: "#111827",
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ fontSize: 44 }}>🍀</div>
          <div style={{ fontSize: 34, fontWeight: 800 }}>Bain Luck</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <div style={{ fontSize: 66, fontWeight: 900, lineHeight: 1.05, maxWidth: 940 }}>
            Probability, not betting.
          </div>
          <div style={{ fontSize: 30, color: "#475569", lineHeight: 1.3, maxWidth: 900 }}>
            Every game, election, and premiere has a number. We find it, blend six sources into one,
            and show it clean.
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              border: "2px solid #d1d5db",
              borderRadius: 999,
              padding: "12px 22px",
              fontSize: 24,
              fontWeight: 700,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            <span style={{ color: "#111827" }}>60%</span>
            <span style={{ color: "#94a3b8", fontWeight: 500 }}>vs</span>
            <span style={{ color: "#64748b" }}>40%</span>
          </div>
          <div style={{ fontSize: 24, color: "#64748b" }}>bainluck.com</div>
        </div>
      </div>
    ),
    size
  );
}
