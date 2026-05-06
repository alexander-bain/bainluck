"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { posOnRail, rgbaFromIntensity } from "@/lib/marketMapUtils";

export interface MarketMapMarker {
  key: string;
  value: number;
  type: "actual" | "pre" | "proj" | "final";
  label: string;
  displayValue: string;
  logoUrl?: string;
  logoFallback?: string;
  hideTile?: boolean;
}

export interface MarketMapLadderRow {
  label: string;
  probability: number;
  side: "left" | "mid" | "right";
}

interface MarketMapProps {
  variant: "margin" | "total";
  title: string;
  subtitle: string;
  headline: string;
  rangeMin: number;
  rangeMax: number;
  density: number[];
  accentRgb: string;
  axisLabels: { left: string; mid: string; right: string };
  zeroPosition?: number;
  markers: MarketMapMarker[];
  ladder: MarketMapLadderRow[];
  status: "pre" | "live" | "done";
}

const DOT_COLORS: Record<string, string> = {
  actual: "#16a34a",
  final: "#0f172a",
  pre: "#94a3b8",
  proj: "#0f172a",
};

const LANE_TOP: Record<string, number> = {
  pre: 32,
  proj: 47,
  actual: 57,
  final: 57,
};

export default function MarketMap({
  title,
  subtitle,
  headline,
  rangeMin,
  rangeMax,
  density,
  accentRgb,
  axisLabels,
  zeroPosition,
  markers,
  ladder,
  status,
}: MarketMapProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [popOpen, setPopOpen] = useState(false);
  const [leaderLines, setLeaderLines] = useState<
    Array<{ x1: number; y1: number; x2: number; y2: number; color: string }>
  >([]);

  const visibleTiles = markers.filter((m) => !m.hideTile);
  const orderedTiles = [...visibleTiles].sort(
    (a, b) => posOnRail(a.value, rangeMin, rangeMax) - posOnRail(b.value, rangeMin, rangeMax)
  );
  const noTiles = orderedTiles.length === 0;

  const computeLeaders = useCallback(() => {
    const card = cardRef.current;
    if (!card) return;
    const cr = card.getBoundingClientRect();
    const newLines: typeof leaderLines = [];

    for (const m of orderedTiles) {
      const tile = card.querySelector(`[data-tile="${m.key}"]`) as HTMLElement | null;
      const dot = card.querySelector(`[data-dot="${m.key}"]`) as HTMLElement | null;
      if (!tile || !dot) continue;

      const tr = tile.getBoundingClientRect();
      const dr = dot.getBoundingClientRect();
      newLines.push({
        x1: tr.left + tr.width / 2 - cr.left,
        y1: tr.top + tr.height - cr.top + 1,
        x2: dr.left + dr.width / 2 - cr.left,
        y2: dr.top + dr.height / 2 - cr.top,
        color: DOT_COLORS[m.type] || "#94a3b8",
      });
    }
    setLeaderLines(newLines);
  }, [orderedTiles, rangeMin, rangeMax]);

  useEffect(() => {
    const card = cardRef.current;
    if (!card) return;
    const frame = requestAnimationFrame(computeLeaders);
    const ro = new ResizeObserver(() => requestAnimationFrame(computeLeaders));
    ro.observe(card);
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
    };
  }, [computeLeaders]);

  const zeroPct = zeroPosition != null ? posOnRail(zeroPosition, rangeMin, rangeMax) : null;

  return (
    <section
      ref={cardRef}
      className="relative border border-[#dbe4ef] rounded-[22px] bg-surface-card transition-shadow hover:shadow-lg hover:border-[#cbd5e1] cursor-pointer group"
      style={{ padding: 14, overflow: "visible" }}
      onClick={() => setPopOpen((p) => !p)}
      onMouseLeave={() => setPopOpen(false)}
    >
      {/* Leader lines SVG — BEHIND dots (z-index 5), clipped to card via overflow:hidden on inner wrapper */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        style={{ zIndex: 5 }}
      >
        {leaderLines.map((l, i) => (
          <line
            key={i}
            x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
            stroke={l.color}
            strokeWidth={2}
            strokeLinecap="round"
            opacity={0.35}
          />
        ))}
      </svg>

      {/* Header */}
      <div className="flex justify-between gap-3 items-start relative" style={{ zIndex: 6 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 950, letterSpacing: "-0.035em", lineHeight: 1.1 }}>
            {title}
          </div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 1 }}>{subtitle}</div>
        </div>
        <div style={{ fontSize: 14, fontWeight: 950, color: "#334155", whiteSpace: "nowrap" }}>
          {headline}
        </div>
      </div>

      {/* Summary tiles — with colored left border matching the dot */}
      {!noTiles && (
        <div
          className="relative"
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${orderedTiles.length}, 1fr)`,
            gap: 8,
            marginTop: 10,
            zIndex: 6,
          }}
        >
          {orderedTiles.map((m) => {
            const borderColor = DOT_COLORS[m.type] || "#94a3b8";
            return (
              <div
                key={m.key}
                data-tile={m.key}
                style={{
                  background: "#f8fafc",
                  borderRadius: 14,
                  padding: "8px 10px",
                  minHeight: 50,
                  borderBottom: `3px solid ${borderColor}`,
                }}
              >
                <div style={{
                  fontSize: 10,
                  fontWeight: 950,
                  color: "#94a3b8",
                  letterSpacing: "0.055em",
                  textTransform: "uppercase" as const,
                  whiteSpace: "nowrap" as const,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}>
                  {m.label}
                </div>
                <div style={{ fontSize: 14, fontWeight: 950, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {m.displayValue}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Distribution rail + markers */}
      <div
        className="relative"
        style={{
          height: noTiles ? 76 : 86,
          marginTop: 6,
          zIndex: 3,
          overflow: "visible",
        }}
      >
        {/* Rail */}
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 32,
            height: 30,
            borderRadius: 999,
            overflow: "hidden",
            border: "1px solid #cbd5e1",
            background: "#eef2f7",
          }}
        >
          <div style={{ display: "flex", height: "100%" }}>
            {density.map((d, i) => (
              <div
                key={i}
                style={{
                  height: "100%",
                  width: `${100 / density.length}%`,
                  background: rgbaFromIntensity(d, accentRgb),
                }}
              />
            ))}
          </div>
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "linear-gradient(to bottom, rgba(255,255,255,0.25), rgba(0,0,0,0.04))",
            }}
          />
        </div>

        {/* Zero / tie line */}
        {zeroPct != null && (
          <div
            style={{
              position: "absolute",
              left: `${zeroPct}%`,
              top: 25,
              height: 48,
              width: 2,
              background: "rgba(71,85,105,0.28)",
              zIndex: 2,
            }}
          />
        )}

        {/* Marker dots — z-index 8, above leader lines */}
        {markers
          .filter((m) => m.value != null)
          .map((m) => {
            const left = posOnRail(m.value, rangeMin, rangeMax);
            const top = LANE_TOP[m.type] || 47;
            const isProj = m.type === "proj";
            const dotSize = isProj ? 26 : 22;
            const bgColor = isProj ? "#fff" : (DOT_COLORS[m.type] || "#94a3b8");
            const borderColor = isProj ? "#0f172a" : "#fff";

            return (
              <div
                key={m.key}
                data-dot={m.key}
                style={{
                  position: "absolute",
                  left: `${left}%`,
                  top,
                  transform: "translate(-50%, -50%)",
                  width: dotSize,
                  height: dotSize,
                  borderRadius: 999,
                  border: `2px solid ${borderColor}`,
                  background: bgColor,
                  boxShadow: "0 1px 7px rgba(15,23,42,0.25)",
                  zIndex: 8,
                  display: "grid",
                  placeItems: "center",
                }}
              >
                {isProj && m.logoUrl ? (
                  <img src={m.logoUrl} alt="" style={{ width: 16, height: 16, objectFit: "contain" }} />
                ) : isProj ? (
                  <span style={{ fontSize: 8, fontWeight: 950, color: "#0f172a" }}>
                    {m.logoFallback || ""}
                  </span>
                ) : null}
              </div>
            );
          })}

        {/* Axis labels */}
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 68,
            display: "flex",
            justifyContent: "space-between",
            fontSize: 12,
            fontWeight: 950,
            color: "#94a3b8",
          }}
        >
          <span>{axisLabels.left}</span>
          <span>{axisLabels.mid}</span>
          <span>{axisLabels.right}</span>
        </div>
        {/* Zero label positioned at actual zero on the rail */}
        {zeroPct != null && zeroPct > 5 && zeroPct < 95 && Math.abs(zeroPct - 50) > 3 && (
          <span
            style={{
              position: "absolute",
              left: `${zeroPct}%`,
              top: 68,
              transform: "translateX(-50%)",
              fontSize: 11,
              fontWeight: 950,
              color: "#64748b",
            }}
          >
            0
          </span>
        )}
      </div>

      {/* Hover/tap popover — detail ladder, NOT constrained to card width */}
      {ladder.length > 0 && (
        <div
          className={`transition-all duration-150 ${
            popOpen
              ? "opacity-100 pointer-events-auto"
              : "opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto"
          }`}
          style={{
            position: "absolute",
            left: -1,
            right: -1,
            top: "calc(100% - 8px)",
            zIndex: 20,
            background: "#fff",
            border: "1px solid #cbd5e1",
            borderRadius: 16,
            padding: 10,
            boxShadow: "0 20px 50px rgba(15,23,42,0.18)",
            minWidth: 320,
          }}
        >
          {ladder.map((row, i) => {
            const barColor = `rgba(${accentRgb},0.65)`;
            return (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "94px 1fr 38px",
                  alignItems: "center",
                  gap: 8,
                  margin: "5px 0",
                }}
              >
                <div style={{ fontSize: 10, color: "#475569", fontWeight: 850 }}>{row.label}</div>
                <div
                  style={{
                    height: 16,
                    background: "#f1f5f9",
                    border: "1px solid #e2e8f0",
                    borderRadius: 999,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      borderRadius: 999,
                      width: `${Math.max(2, row.probability)}%`,
                      background: barColor,
                      minWidth: 2,
                    }}
                  />
                </div>
                <div style={{ textAlign: "right", fontSize: 10, fontWeight: 950 }}>
                  {row.probability}%
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
