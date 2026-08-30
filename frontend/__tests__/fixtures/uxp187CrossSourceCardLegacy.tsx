/**
 * UX-P187 — the VERBATIM pre-fix `CrossSourceCard`, as it shipped inside
 * `app/politics/page.tsx`.
 *
 * Extracted with `git show e6719c91:frontend/app/politics/page.tsx`. The ONLY
 * edits are this header, the renamed export, and its two page-local
 * dependencies (`BORDER_COLOR`, `SourceBadge`) copied in beside it so the file
 * stands alone — every line that decides what a reader sees is untouched,
 * including the two bare `market.kalshi` / `market.poly` numerals with nothing
 * to say which outcome either one prices.
 *
 * It exists so `politicsCrossSourceOutcomeCapture.test.tsx` can prove its
 * probe DISCRIMINATES: the same probe, run against this file, must come back
 * broken. A discriminator nobody has watched discriminate is a decoration.
 *
 * Precedents: `uxp177RelatedByTagLegacy.tsx`, `playerPropsGroupingLegacy.ts`.
 *
 * DO NOT "fix" this file. It is evidence.
 */
/* eslint-disable */

import type { CrossSourceMatch } from "@/lib/api";
import s from "@/app/politics/politics.module.css";

const BORDER_COLOR: Record<string, string> = {
  presidential: "#3B82F6",
  congressional: "#8B5CF6",
  gubernatorial: "#10B981",
  policy: "#F59E0B",
  scotus: "#EF4444",
  international: "#0EA5E9",
  other: "#9CA3AF",
};

function SourceBadge({ source, compact = false }: { source: string; compact?: boolean }) {
  if (source === "both" || source === "Both") {
    return (
      <span className={s.srcBoth} title="Both Kalshi and Polymarket">
        <span className={s.srcDot} style={{ background: "#22C55E" }} />
        <span className={s.srcDot} style={{ background: "#3B82F6" }} />
        {!compact && "Both"}
      </span>
    );
  }
  if (source === "kalshi") {
    return (
      <span className={s.srcKalshi}>
        <span className={s.srcDot} style={{ background: "#22C55E" }} />
        Kalshi
      </span>
    );
  }
  return (
    <span className={s.srcPolymarket}>
      <span className={s.srcDot} style={{ background: "#3B82F6" }} />
      Polymarket
    </span>
  );
}

export default function CrossSourceCard({ market }: { market: CrossSourceMatch }) {
  const delta = market.delta;
  const merged = (market.kalshi + market.poly) / 2;
  const arbitrage = delta > 5;
  const disagree = delta > 2;
  const borderColor = BORDER_COLOR[market.category] || "#9CA3AF";

  return (
    <div className={s.crossCard} style={{ borderTop: `2px solid ${borderColor}` }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        <SourceBadge source="both" />
        {arbitrage && (
          <span className={s.spreadBadge}>⚠ {delta.toFixed(1)}pt spread</span>
        )}
      </div>

      <h3
        style={{
          margin: 0,
          fontSize: 14,
          fontWeight: 500,
          lineHeight: 1.35,
          color: "var(--text-primary)",
        }}
      >
        {market.q}
      </h3>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 8,
          marginTop: 2,
        }}
      >
        <div className={s.sourceCellKalshi}>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: "#22C55E",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            Kalshi
          </span>
          <span
            className={s.probNum}
            style={{
              fontSize: 22,
              color: market.kalshi >= market.poly ? "#111827" : "#6B7280",
            }}
          >
            {market.kalshi.toFixed(1)}%
          </span>
        </div>
        <div className={s.sourceCellPoly}>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: "#3B82F6",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            Polymarket
          </span>
          <span
            className={s.probNum}
            style={{
              fontSize: 22,
              color: market.poly >= market.kalshi ? "#111827" : "#6B7280",
            }}
          >
            {market.poly.toFixed(1)}%
          </span>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 11,
          color: "var(--text-muted)",
          marginTop: 2,
        }}
      >
        <span>
          Merged:{" "}
          <b className={s.probNum} style={{ color: "var(--text-primary)" }}>
            {merged.toFixed(1)}%
          </b>
        </span>
        {disagree && (
          <span>
            Disagree by{" "}
            <b className={s.probNum} style={{ color: "#B45309" }}>
              {delta.toFixed(1)}pp
            </b>
          </span>
        )}
      </div>
    </div>
  );
}
