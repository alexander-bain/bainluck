"use client";

import useSWR from "swr";
import { probColor, probLabel, sparkFrom, type WildCard } from "./data";
import { fetchWildCards } from "@/lib/weatherApi";
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

function WildCardSkeleton() {
  return (
    <div
      className="border border-surface-border"
      style={{ backgroundColor: "#fff", borderRadius: 14, padding: 20, minHeight: 180, display: "flex", flexDirection: "column" }}
    >
      <div className="h-2.5 w-20 bg-gray-200 rounded animate-pulse mb-2" />
      <div className="h-4 bg-gray-200 rounded animate-pulse mb-1" style={{ width: "90%" }} />
      <div className="h-4 bg-gray-200 rounded animate-pulse mb-3" style={{ width: "60%" }} />
      <div className="flex-1" />
      <div className="flex items-end justify-between mb-3">
        <div className="h-10 w-16 bg-gray-200 rounded animate-pulse" />
        <div className="h-6 w-20 bg-gray-100 rounded animate-pulse" />
      </div>
      <div className="flex items-center justify-between" style={{ borderTop: "1px dashed #E5E7EB", paddingTop: 10 }}>
        <div className="h-4 w-14 bg-gray-200 rounded-full animate-pulse" />
        <div className="h-4 w-14 bg-gray-200 rounded-full animate-pulse" />
      </div>
    </div>
  );
}

export default function WildCards() {
  const { data: liveCards } = useSWR("weather-wildcards", fetchWildCards, { refreshInterval: 21600000 });
  const cards = (liveCards as WildCard[])?.length ? (liveCards as WildCard[]) : null;

  if (!cards) {
    return (
      <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <WildCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div
      className="grid gap-3.5"
      style={{
        gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
      }}
    >
      {cards.map((card, i) => {
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
