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
  /**
   * #3769. How this rung actually finished, when the page knows. `probability`
   * is read live and collapses to ~0/~100 the moment the market resolves, so a
   * settled rung must be graded against the final rather than quoted — see
   * `ladderHeading`.
   */
  outcome?: "cleared" | "missed";
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
  /**
   * #3210. Whether `density` describes a shape at all — `densityDrawsShape`,
   * decided once by the section that built the density so the subtitle and the
   * rail cannot come to different answers about the same band.
   *
   * When it is false the rail paints NO segments (an empty track under the
   * markers, which is a number line and claims nothing) and the ladder this
   * card already builds is drawn inline instead of hidden behind a hover.
   */
  bandDrawsShape: boolean;
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
  variant,
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
  bandDrawsShape,
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
      className="relative border border-surface-border rounded-[22px] bg-surface-card transition-shadow hover:shadow-lg hover:border-text-muted cursor-pointer group"
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
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 1 }}>{subtitle}</div>
        </div>
        <div style={{ fontSize: 14, fontWeight: 950, color: "var(--text-primary)", whiteSpace: "nowrap" }}>
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
          {/* #3210: a band with no shape is not painted. Every segment would
              take the same colour, so what the reader gets is a solid block
              under a subtitle promising a distribution — the whole complaint.
              The bare `#eef2f7` track underneath is a number line, which is
              exactly what the markers on it need and all this card can honestly
              claim. The rungs go inline below instead. */}
          {bandDrawsShape && (
            <div style={{ display: "flex", height: "100%" }}>
              {density.map((d, i) => (
                <div
                  key={i}
                  data-density-segment={i}
                  style={{
                    height: "100%",
                    width: `${100 / density.length}%`,
                    background: rgbaFromIntensity(d, accentRgb),
                  }}
                />
              ))}
            </div>
          )}
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
                  <span style={{ fontSize: 8, fontWeight: 950, color: "var(--text-primary)" }}>
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

      {/* #3210: THE RUNGS, DRAWN — the card already held them.
          A band with no shape is replaced by the lines it actually has, in the
          card itself rather than behind a hover a phone cannot perform. The
          popover below is suppressed in the same breath: one card must not
          print the same ladder twice. */}
      {!bandDrawsShape && ladder.length > 0 && (
        // 18, and it is measured rather than chosen. The rail block above is
        // `height: 76` when it has no tiles, but its axis labels are absolutely
        // positioned at `top: 68` and stand ~15px tall, so they finish ~7px
        // BELOW the block that contains them. At the popover's old `marginTop:
        // 4` the first LOOK of this change photographed "32 38 44+" sitting on
        // top of "CHANCE OF GOING OVER" on the pre-game card.
        <div style={{ marginTop: 18, position: "relative", zIndex: 6 }} data-inline-ladder="1">
          <LadderRows
            ladder={ladder}
            accentRgb={accentRgb}
            heading={ladderHeading(status, variant, ladderGraded(ladder))}
          />
        </div>
      )}

      {/* Hover/tap popover — detail ladder, NOT constrained to card width */}
      {bandDrawsShape && ladder.length > 0 && (
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
          <LadderRows
            ladder={ladder}
            accentRgb={accentRgb}
            heading={ladderHeading(status, variant, ladderGraded(ladder))}
          />
        </div>
      )}
    </section>
  );
}

/**
 * L2-131 Item 4: name what the bars mean — the chance of reaching each margin
 * (or clearing each total).
 *
 * #2442: this said "covering", which is the betting verb — a side covers THE
 * SPREAD. The bars mean the same thing either way, and "winning by" states it
 * in the sport's own terms rather than the slip's.
 *
 * #3769: the `done` arm used to read "Pregame chance of going over", and it was
 * the ONE branch where the word "pregame" appeared — over numbers that are not
 * pregame. `probability` comes from the live payload, so on a settled match it
 * is the resolved price: measured on production 2026-09-06, `/events/15304847`
 * (Paul–Alcaraz, 6-4 6-3 6-4) served `over_probability: 0.0005` for both 36.5
 * and 40.5, and the card printed "PREGAME CHANCE OF GOING OVER — Over 36.5: 0%"
 * two rows under its own "PRE-GAME 33" tile. A book had hung a 36.5 line; no
 * book hangs a line at 0%. The scheduled control (`/events/15305580`) served
 * 0.445, so the collapse is settlement, not a genuinely tiny pregame chance.
 * `PlayerPropsDashboard` already refuses to "fall through to `pre`, which
 * renders the resolved over_probability" — this is that defense, applied to the
 * ladder next to it.
 *
 * So there are three headings, not two, and none of them claims to be pregame:
 * a graded ladder says how each line finished, an ungraded settled ladder says
 * the numbers are last quotes, and anything else asks about a live chance.
 */
/**
 * #3769. A ladder is graded only when EVERY rung knows how it finished. A
 * partially graded ladder would put "cleared" beside "0%" and invite the reader
 * to compare them, so the mixed case falls back to quoting — one ladder, one
 * tense.
 */
export function ladderGraded(ladder: MarketMapLadderRow[]): boolean {
  return ladder.length > 0 && ladder.every((row) => row.outcome != null);
}

function ladderHeading(
  status: MarketMapProps["status"],
  variant: MarketMapProps["variant"],
  graded: boolean
): string {
  const what = variant === "total" ? "going over" : "winning by";
  if (graded) return "Each line vs the final";
  if (status === "done") return "Last quote for " + what;
  return "Chance of " + what;
}

/**
 * The rungs and their bars. ONE renderer, because #3210 gave this ladder a
 * second home inside the card and two copies of it is how the hover version
 * and the inline version come to disagree about what a bar means.
 */
function LadderRows({
  ladder,
  accentRgb,
  heading,
}: {
  ladder: MarketMapLadderRow[];
  accentRgb: string;
  heading: string;
}) {
  const barColor = `rgba(${accentRgb},0.65)`;
  // #3769: all-or-nothing, decided by the same `ladderGraded` the heading used,
  // so one ladder can never print a graded row beside a quoted one.
  const graded = ladderGraded(ladder);
  return (
    <>
      <div
        style={{
          fontSize: 10,
          fontWeight: 950,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          color: "#94a3b8",
          margin: "0 0 6px 2px",
        }}
      >
        {heading}
      </div>
      {ladder.map((row, i) => (
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
          <div style={{ fontSize: 10, color: "var(--text-secondary)", fontWeight: 850 }}>{row.label}</div>
          {graded ? (
            // #3769: a settled rung has a result, not a chance. No bar, because
            // there is no longer a quantity to draw — the line either came in or
            // it did not, and the emphasis carries which.
            <div
              style={{
                gridColumn: "2 / span 2",
                textAlign: "right",
                fontSize: 10,
                fontWeight: row.outcome === "cleared" ? 950 : 850,
                color: row.outcome === "cleared" ? "#0f172a" : "var(--text-secondary)",
              }}
            >
              {row.outcome === "cleared" ? "cleared" : "not cleared"}
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>
      ))}
    </>
  );
}
