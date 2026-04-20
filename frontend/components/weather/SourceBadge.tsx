"use client";

import { SOURCES, type Source } from "./data";

interface SourceBadgeProps {
  src: Source;
}

export function SourceBadge({ src }: SourceBadgeProps) {
  const s = SOURCES[src] ?? SOURCES.kalshi;

  return (
    <span
      className="inline-flex items-center rounded-full"
      style={{
        backgroundColor: s.bg,
        color: s.fg,
        fontSize: 11,
        fontWeight: 500,
        padding: "3px 8px",
        gap: 6,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          backgroundColor: s.color,
          flexShrink: 0,
        }}
      />
      {s.label}
    </span>
  );
}

export function CrossSourceBadge() {
  return (
    <span
      className="inline-flex items-center rounded-full"
      style={{
        background: `linear-gradient(90deg, ${SOURCES.kalshi.bg} 50%, ${SOURCES.polymarket.bg} 50%)`,
        border: "1px solid var(--surface-border)",
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: "0.2px",
        padding: "3px 8px",
        gap: 6,
        color: "#374151",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          backgroundColor: SOURCES.kalshi.color,
          flexShrink: 0,
        }}
      />
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          backgroundColor: SOURCES.polymarket.color,
          flexShrink: 0,
        }}
      />
      CROSS-SOURCE
    </span>
  );
}
