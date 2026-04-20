"use client";

import { probColor, type EventMarket } from "./data";
import { SourceBadge } from "./SourceBadge";
import ProbabilityNumber from "./ProbabilityNumber";

const months = [
  { m: "May", p: 21 },
  { m: "Jun", p: 34 },
  { m: "Jul", p: 58 },
  { m: "Aug", p: 78 },
  { m: "Sep", p: 88 },
  { m: "Oct", p: 60 },
  { m: "Nov", p: 24 },
];

export default function HurricaneTracker({ items }: { items: EventMarket[] }) {
  const marketRows = items.slice(0, 4);

  return (
    <div
      style={{
        backgroundColor: "#fff",
        borderRadius: 16,
        padding: 22,
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between" style={{ marginBottom: 20 }}>
        <div>
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
              Hurricane Season &middot; 2026
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
            Atlantic season tracker
          </h3>
        </div>

        <div className="flex flex-col items-end" style={{ gap: 2 }}>
          <ProbabilityNumber value={80} size={32} forceColor="#22C55E" />
          <span
            style={{
              fontSize: 11,
              color: "#6B7280",
              textAlign: "right",
              maxWidth: 130,
              lineHeight: 1.3,
            }}
          >
            &ge;1 major hurricane in 2026
          </span>
        </div>
      </div>

      {/* Monthly bars */}
      <div style={{ marginBottom: 20 }}>
        <div className="flex items-end" style={{ gap: 8, height: 120 }}>
          {months.map((mo) => {
            const isPeak = mo.p >= 70;
            const opacity = 0.28 + (mo.p / 100) * 0.72;
            const barHeight = (mo.p / 100) * 100;

            return (
              <div
                key={mo.m}
                className="flex flex-col items-center flex-1"
                style={{ height: "100%", justifyContent: "flex-end" }}
              >
                <span
                  className="font-mono"
                  style={{
                    fontSize: 11,
                    fontWeight: isPeak ? 700 : 400,
                    color: isPeak ? "#B91C1C" : "#9CA3AF",
                    marginBottom: 4,
                  }}
                >
                  {mo.p}%
                </span>
                <div
                  style={{
                    width: "100%",
                    height: barHeight,
                    borderRadius: 4,
                    background: "linear-gradient(180deg, #EF4444, #F87171)",
                    opacity,
                  }}
                />
              </div>
            );
          })}
        </div>

        <div
          className="flex"
          style={{
            gap: 8,
            borderTop: "1px solid #E5E7EB",
            paddingTop: 6,
            marginTop: 6,
          }}
        >
          {months.map((mo) => (
            <div
              key={mo.m}
              className="flex-1 text-center"
              style={{
                fontSize: 11,
                color: "#6B7280",
              }}
            >
              {mo.m}
            </div>
          ))}
        </div>
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
              borderTop: i > 0 ? "1px solid #F3F4F6" : undefined,
            }}
          >
            <div className="flex items-center" style={{ gap: 8 }}>
              <span style={{ fontSize: 13, color: "#374151" }}>{item.q}</span>
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
