"use client";

import { WILDCARDS, probColor, probLabel, sparkFrom, SOURCES } from "./data";
import Sparkline from "./Sparkline";
import { SourceBadge } from "./SourceBadge";
import ProbabilityNumber from "./ProbabilityNumber";

function pillBg(label: string): string {
  if (label === "Likely") return "#ECFDF5";
  if (label === "Toss-up") return "#FFFBEB";
  return "#FEF2F2";
}

function pillFg(label: string): string {
  if (label === "Likely") return "#047857";
  if (label === "Toss-up") return "#B45309";
  return "#B91C1C";
}

export default function WildCards() {
  return (
    <div
      className="grid gap-3.5"
      style={{
        gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
      }}
    >
      {WILDCARDS.map((card, i) => {
        const color = probColor(card.prob);
        const label = probLabel(card.prob);
        const spark = sparkFrom(i * 137 + 42, card.prob);

        return (
          <div
            key={i}
            className="border border-surface-border"
            style={{
              backgroundColor: "#fff",
              borderRadius: 14,
              padding: 20,
              minHeight: 180,
              display: "flex",
              flexDirection: "column",
              transition: "transform 160ms ease, box-shadow 160ms ease",
              cursor: "default",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)";
              (e.currentTarget as HTMLElement).style.boxShadow =
                "0 4px 12px rgba(0,0,0,0.08)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
              (e.currentTarget as HTMLElement).style.boxShadow = "none";
            }}
          >
            {/* Tag */}
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                color: "#9CA3AF",
                marginBottom: 6,
              }}
            >
              {card.tag}
            </span>

            {/* Question */}
            <div
              style={{
                fontSize: 15,
                fontWeight: 500,
                color: "#111827",
                lineHeight: 1.35,
                marginBottom: 12,
                flex: 1,
              }}
            >
              {card.q}
            </div>

            {/* Probability + Sparkline */}
            <div
              className="flex items-end justify-between"
              style={{ marginBottom: 12 }}
            >
              <ProbabilityNumber value={card.prob} size={42} />
              <Sparkline data={spark} color={color} width={80} height={24} />
            </div>

            {/* Footer */}
            <div
              className="flex items-center justify-between"
              style={{
                borderTop: "1px dashed #E5E7EB",
                paddingTop: 10,
              }}
            >
              <SourceBadge src={card.src} />
              <span
                style={{
                  fontSize: 10.5,
                  fontWeight: 600,
                  color: pillFg(label),
                  backgroundColor: pillBg(label),
                  padding: "3px 8px",
                  borderRadius: 9999,
                }}
              >
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
