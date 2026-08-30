"use client";

import { probColor, type EventMarket } from "./data";
import { SourceBadge } from "./SourceBadge";

export default function HurricaneTracker({ items }: { items: EventMarket[] }) {
  // Every number this card prints is a market price out of `items`. It used to
  // print eight that were not: a hard-coded 80% hero and a seven-bar monthly
  // climatology chart, both survivors of the fabricated-data purge (567e22b4,
  // 8484c3ce) that emptied `data.ts` but never opened this file. Measured
  // against the real payload on 2026-08-30, the card rendered twelve
  // percentages and only four of them came from a market.
  const marketRows = items.slice(0, 8);

  return (
    <div
      style={{
        backgroundColor: "#fff",
        borderRadius: 16,
        padding: 22,
      }}
    >
      {/* Header. The basin is deliberately not named: the rail behind this card
          is `FuturesMarket.name ILIKE '%hurricane%'` (routes/weather.py) with no
          basin filter at all, so "Atlantic" was a claim the data could not back —
          the live payload carries Pacific-named storms alongside Atlantic ones. */}
      <div style={{ marginBottom: 20 }}>
        <div
          className="flex items-center"
          style={{ gap: 6, marginBottom: 6 }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              backgroundColor: "#B91C1C",
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: 11.5,
              fontWeight: 600,
              letterSpacing: "0.5px",
              textTransform: "uppercase",
              color: "#B91C1C",
            }}
          >
            Hurricane Season
          </span>
        </div>
        <h3
          style={{
            fontSize: 20,
            fontWeight: 600,
            color: "#111827",
            margin: 0,
          }}
        >
          Hurricane markets
        </h3>
      </div>

      {/* Market rows */}
      <div className="flex flex-col" style={{ gap: 0 }}>
        {marketRows.map((item: EventMarket, i: number) => (
          <div
            key={i}
            className="grid items-center"
            style={{
              gridTemplateColumns: "1fr auto auto",
              gap: 10,
              padding: "10px 0",
              borderTop: i > 0 ? "1px solid var(--surface-border)" : undefined,
            }}
          >
            <div className="flex items-center" style={{ gap: 8 }}>
              <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{item.q}</span>
              <SourceBadge src={item.src} />
            </div>

            <div
              style={{
                width: 72,
                height: 5,
                backgroundColor: "#F3F4F6",
                borderRadius: 3,
                overflow: "hidden",
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  width: `${item.prob}%`,
                  height: "100%",
                  backgroundColor: probColor(item.prob),
                  borderRadius: 3,
                }}
              />
            </div>

            <span
              className="font-mono"
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: probColor(item.prob),
                minWidth: 36,
                textAlign: "right",
              }}
            >
              {item.prob}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
