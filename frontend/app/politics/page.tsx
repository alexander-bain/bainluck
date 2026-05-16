"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchPolitics } from "@/lib/api";
import type {
  PoliticsData,
  PoliticsMarketRow,
  PoliticsCandidate,
  PoliticsThemePresidential,
  PoliticsThemeCongressional,
  PoliticsThemeSimple,
  ChamberControl,
  CrossSourceMatch,
} from "@/lib/api";
import ErrorState from "@/components/ErrorState";
import s from "./politics.module.css";

// ─────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────

type SourceMode = "merged" | "kalshi" | "poly";

const THEMES = [
  { key: "presidential", emoji: "🏛", label: "Presidential 2028" },
  { key: "congressional", emoji: "🏤", label: "Congressional" },
  { key: "gubernatorial", emoji: "🗺", label: "Gubernatorial" },
  { key: "policy", emoji: "📜", label: "Policy & Legislation" },
  { key: "scotus", emoji: "⚖", label: "Supreme Court" },
  { key: "international", emoji: "🌍", label: "International" },
  { key: "other", emoji: "📊", label: "Other" },
] as const;

const BORDER_COLOR: Record<string, string> = {
  presidential: "#3B82F6",
  congressional: "#8B5CF6",
  gubernatorial: "#10B981",
  policy: "#F59E0B",
  scotus: "#EF4444",
  international: "#0EA5E9",
  other: "#9CA3AF",
};

const PARTY_COLOR: Record<string, string> = {
  R: "#DC2626",
  D: "#2563EB",
  I: "#9CA3AF",
};

// ─────────────────────────────────────────────────────────
// Atoms
// ─────────────────────────────────────────────────────────

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

function SourceToggle({
  mode,
  onChange,
}: {
  mode: SourceMode;
  onChange: (m: SourceMode) => void;
}) {
  const items: { k: SourceMode; l: string }[] = [
    { k: "merged", l: "Merged" },
    { k: "kalshi", l: "Kalshi" },
    { k: "poly", l: "Polymarket" },
  ];
  return (
    <div className={s.sourceToggle}>
      {items.map((it) => (
        <button
          key={it.k}
          className={mode === it.k ? s.sourceToggleBtnActive : s.sourceToggleBtn}
          onClick={() => onChange(it.k)}
        >
          {it.l}
        </button>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Sub-theme navigation
// ─────────────────────────────────────────────────────────

function SubNav({
  themes,
  counts,
  active,
  onJump,
}: {
  themes: typeof THEMES;
  counts: Record<string, number>;
  active: string | null;
  onJump: (k: string | null) => void;
}) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  return (
    <div className={s.subnav}>
      <div className={s.subnavInner}>
        <button
          className={!active ? s.subnavChipActive : s.subnavChip}
          onClick={() => onJump(null)}
        >
          <span>All</span>
          <span className={s.subnavCount}>{total.toLocaleString()}</span>
        </button>
        {themes.map((t) => (
          <button
            key={t.key}
            className={active === t.key ? s.subnavChipActive : s.subnavChip}
            onClick={() => onJump(t.key)}
          >
            <span style={{ fontSize: 13 }}>{t.emoji}</span>
            <span>{t.label}</span>
            <span className={s.subnavCount}>{counts[t.key] || 0}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Sparkline + MoveChip atoms
// ─────────────────────────────────────────────────────────

function Sparkline({ history, width = 60, height = 18 }: {
  history?: { t: string; p: number }[];
  width?: number;
  height?: number;
}) {
  if (!history || history.length < 2) return <span style={{ width, height, display: "inline-block" }} />;
  const probs = history.map((h) => h.p);
  const min = Math.min(...probs);
  const max = Math.max(...probs);
  const range = max - min || 1;
  const d = probs
    .map((p, i) => {
      const x = (i / (probs.length - 1)) * width;
      const y = height - ((p - min) / range) * (height - 2) - 1;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const change = probs[probs.length - 1] - probs[0];
  const color = change > 0.5 ? "#16A34A" : change < -0.5 ? "#EF4444" : "#6B7280";
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MoveChip({ change }: { change: number | null | undefined }) {
  if (change == null || Math.abs(change) < 0.1)
    return <span className={s.moveFlat}>—</span>;
  const cls = change > 0 ? s.moveUp : s.moveDown;
  return (
    <span className={cls}>
      {change > 0 ? "↑" : "↓"}{Math.abs(change).toFixed(1)}%
    </span>
  );
}

// ─────────────────────────────────────────────────────────
// Presidential hero — bar race + evolution chart
// ─────────────────────────────────────────────────────────

type HeroVariant = "bar-race" | "evolution";

const CANDIDATE_COLORS = [
  "#DC2626", "#2563EB", "#F59E0B", "#10B981", "#8B5CF6", "#EC4899",
  "#0891B2", "#65A30D", "#C026D3", "#EA580C", "#4F46E5", "#059669",
];

function getCandidateProb(c: PoliticsCandidate, mode: SourceMode): number {
  if (mode === "kalshi") return c.kalshi ?? c.merged;
  if (mode === "poly") return c.poly ?? c.merged;
  return c.merged;
}

function PresHero({ data }: { data: PoliticsThemePresidential }) {
  const [sourceMode, setSourceMode] = useState<SourceMode>("merged");
  const [variant, setVariant] = useState<HeroVariant>("bar-race");
  const candidates = data.candidates;

  const sorted = useMemo(
    () =>
      candidates
        ? [...candidates].sort(
            (a, b) =>
              getCandidateProb(b, sourceMode) -
              getCandidateProb(a, sourceMode)
          )
        : [],
    [candidates, sourceMode]
  );

  const hasHistory = useMemo(
    () => candidates?.some((c) => c.history && c.history.length >= 2) ?? false,
    [candidates]
  );

  if (!candidates || candidates.length === 0) return null;

  return (
    <div className={s.presHero}>
      {/* Header */}
      <div className={s.presHeroHead}>
        <div>
          <h2 className={s.presHeroQ}>{data.headline_q || "Who wins the 2028 presidential election?"}</h2>
          <div className={s.presHeroMeta}>
            {candidates.length} candidates tracked · Market-implied probability
            {data.has_dual_source && " · Both sources"}
          </div>
        </div>
        <div className={s.presHeroActions}>
          {hasHistory && (
            <div className={s.heroVariantToggle}>
              <button
                className={variant === "bar-race" ? s.heroVariantBtnActive : s.heroVariantBtn}
                onClick={() => setVariant("bar-race")}
              >
                Rankings
              </button>
              <button
                className={variant === "evolution" ? s.heroVariantBtnActive : s.heroVariantBtn}
                onClick={() => setVariant("evolution")}
              >
                Trends
              </button>
            </div>
          )}
          {data.has_dual_source && (
            <SourceToggle mode={sourceMode} onChange={setSourceMode} />
          )}
        </div>
      </div>

      {variant === "bar-race" && (
        <PresBarRace sorted={sorted} sourceMode={sourceMode} data={data} />
      )}
      {variant === "evolution" && (
        <PresEvolution candidates={sorted.slice(0, 6)} sourceMode={sourceMode} />
      )}

      {/* Related markets */}
      {data.side_markets && data.side_markets.length > 0 && (
        <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid #E5E7EB" }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 8 }}>
            Related markets
          </div>
          <div className={s.sideGrid}>
            {data.side_markets.slice(0, 6).map((m, i) => (
              <SideMarketCard key={i} market={m} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PresBarRace({ sorted, sourceMode, data }: {
  sorted: PoliticsCandidate[];
  sourceMode: SourceMode;
  data: PoliticsThemePresidential;
}) {
  const maxProb = Math.max(...sorted.map((c) => getCandidateProb(c, sourceMode)), 1);
  const scale = 100 / Math.max(maxProb * 1.1, 10);
  const showDualBars = sourceMode === "merged" && data.has_dual_source;

  return (
    <div>
      {/* Column header */}
      <div className={s.barRaceHeader}>
        <span></span>
        <span></span>
        <span>Candidate</span>
        <span>Probability{showDualBars ? " (K / P)" : ""}</span>
        <span className={s.hideOnMobile} style={{ textAlign: "right" }}>7d trend</span>
        <span className={s.hideOnMobile} style={{ textAlign: "right" }}>Δ 7d</span>
        <span style={{ textAlign: "right" }}>Now</span>
      </div>

      {/* Candidate rows */}
      {sorted.map((c, i) => {
        const prob = getCandidateProb(c, sourceMode);
        const partyBg = PARTY_COLOR[c.party] || PARTY_COLOR.I;

        return (
          <div key={c.name} className={s.barRaceRow}>
            <span className={s.rank}>{i + 1}</span>
            <span className={s.partyBadge} style={{ background: partyBg }}>{c.party}</span>
            <span className={s.candidateName}>{c.name}</span>
            <div className={s.barWrap}>
              {showDualBars && c.kalshi != null && c.poly != null ? (
                <div className={s.barStack}>
                  <div className={s.barKalshi} style={{ width: `${c.kalshi * scale * 0.5}%` }} title={`Kalshi ${c.kalshi.toFixed(1)}%`} />
                  <div className={s.barPoly} style={{ width: `${c.poly * scale * 0.5}%` }} title={`Polymarket ${c.poly.toFixed(1)}%`} />
                </div>
              ) : (
                <div className={s.barFill} style={{ width: `${Math.max(prob * scale, 1.5)}%`, background: partyBg, opacity: i === 0 ? 0.7 : 0.45 }} />
              )}
            </div>
            <span className={s.hideOnMobile}><Sparkline history={c.history} /></span>
            <span className={s.hideOnMobile}><MoveChip change={c.change_7d} /></span>
            <span className={s.pct}>{prob.toFixed(1)}%</span>
          </div>
        );
      })}

      {/* Source legend */}
      {showDualBars && (
        <div className={s.sourceLegend}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span className={s.legendDot} style={{ background: "#22C55E" }} /> Kalshi
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span className={s.legendDot} style={{ background: "#3B82F6" }} /> Polymarket
          </span>
          <span style={{ marginLeft: "auto" }}>Bars stacked side-by-side; numerals are merged average</span>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Evolution chart — top 6 candidates over time
// ─────────────────────────────────────────────────────────

function PresEvolution({ candidates, sourceMode }: {
  candidates: PoliticsCandidate[];
  sourceMode: SourceMode;
}) {
  const [range, setRange] = useState<string>("30d");
  const ranges = ["7d", "30d", "All"] as const;

  const withHistory = candidates.filter((c) => c.history && c.history.length >= 2);
  if (withHistory.length === 0) {
    return <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>No historical data available yet</div>;
  }

  const now = Date.now();
  const cutoffMs = range === "7d" ? 7 * 86400000 : range === "30d" ? 30 * 86400000 : Infinity;

  const w = 720, h = 200, padL = 36, padR = 55, padT = 10, padB = 20;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const series = withHistory.map((c, idx) => {
    const filtered = cutoffMs === Infinity
      ? c.history
      : c.history.filter((pt) => now - new Date(pt.t).getTime() < cutoffMs);
    return { ...c, pts: filtered, color: CANDIDATE_COLORS[idx % CANDIDATE_COLORS.length] };
  });

  const allVals = series.flatMap((sr) => sr.pts.map((p) => p.p));
  if (allVals.length === 0) return null;
  const yMax = Math.max(...allVals) * 1.15;
  const yMin = 0;

  const gridLines = [5, 10, 15, 20, 25, 30, 40, 50].filter((v) => v <= yMax);

  return (
    <div className={s.evoWrap}>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
        {gridLines.map((y) => (
          <g key={y}>
            <line x1={padL} x2={w - padR} y1={padT + innerH - (y / yMax) * innerH} y2={padT + innerH - (y / yMax) * innerH} stroke="#E5E7EB" strokeWidth="1" strokeDasharray="2 3" />
            <text x={padL - 4} y={padT + innerH - (y / yMax) * innerH + 3} fontSize="9" fill="#9CA3AF" textAnchor="end" fontFamily="JetBrains Mono, monospace">{y}%</text>
          </g>
        ))}
        {series.map((sr) => {
          if (sr.pts.length < 2) return null;
          const d = sr.pts.map((pt, i) => {
            const x = padL + (i / (sr.pts.length - 1)) * innerW;
            const y = padT + innerH - (pt.p / yMax) * innerH;
            return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
          }).join(" ");
          return <path key={sr.name} d={d} fill="none" stroke={sr.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />;
        })}
        {series.map((sr) => {
          if (sr.pts.length < 1) return null;
          const last = sr.pts[sr.pts.length - 1].p;
          const x = padL + innerW + 3;
          const y = padT + innerH - (last / yMax) * innerH + 3;
          return <text key={sr.name} x={x} y={y} fontSize="9" fill={sr.color} fontFamily="JetBrains Mono, monospace" fontWeight="600">{last.toFixed(0)}%</text>;
        })}
      </svg>

      <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 6, flexWrap: "wrap" }}>
        <div className={s.rangeTabs}>
          {ranges.map((r) => (
            <button key={r} className={range === r ? s.rangeTabActive : s.rangeTab} onClick={() => setRange(r)}>{r}</button>
          ))}
        </div>
        <div className={s.evoLegend}>
          {series.map((sr) => (
            <span key={sr.name} className={s.evoLegendItem}>
              <span className={s.evoSwatch} style={{ background: sr.color }} />
              <span style={{ color: "var(--text-secondary)" }}>{sr.name}</span>
              <span className={s.probNum} style={{ fontSize: 11 }}>{getCandidateProb(sr, sourceMode).toFixed(0)}%</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function SideMarketCard({ market }: { market: PoliticsMarketRow }) {
  const leader = market.top_outcomes?.[0];
  const isBinary = market.outcome_count <= 2;

  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={s.sideCard}>
        <div className={s.sideQ}>{market.q}</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {isBinary ? (market.prob >= 50 ? "Yes" : "No") : (leader?.name || "—")}
          </span>
          <span className={s.probNum} style={{ fontSize: 16, color: "var(--text-primary)" }}>
            {Math.round(market.prob)}%
          </span>
        </div>
        <SourceBadge source={market.src} />
      </div>
    </Link>
  );
}

// ─────────────────────────────────────────────────────────
// Chamber control cards
// ─────────────────────────────────────────────────────────

function ChamberControlRow({
  senate,
  house,
}: {
  senate: ChamberControl | null;
  house: ChamberControl | null;
}) {
  if (!senate && !house) return null;
  return (
    <div className={s.chamberGrid}>
      {senate && <ChamberControlCard chamber="Senate" probs={senate} />}
      {house && <ChamberControlCard chamber="House" probs={house} />}
    </div>
  );
}

function ChamberControlCard({
  chamber,
  probs,
}: {
  chamber: string;
  probs: ChamberControl;
}) {
  const gopLeads = probs.gop >= probs.dem;
  return (
    <Link href={`/futures/${probs.market_id}`}>
      <div className={s.chamberCard}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "var(--text-muted)",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            {chamber} control
          </span>
          <SourceBadge source="both" compact />
        </div>

        <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span
              className={s.probNum}
              style={{
                fontSize: 28,
                color: gopLeads ? "#DC2626" : "#9CA3AF",
              }}
            >
              {Math.round(probs.gop)}%
            </span>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>R</span>
          </div>
          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>vs</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span
              className={s.probNum}
              style={{
                fontSize: 28,
                color: !gopLeads ? "#2563EB" : "#9CA3AF",
              }}
            >
              {Math.round(probs.dem)}%
            </span>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>D</span>
          </div>
        </div>

        <div className={s.binaryBar} style={{ height: 6 }}>
          <div className={s.binaryR} style={{ width: `${probs.gop}%` }} />
          <div className={s.binaryD} style={{ width: `${probs.dem}%` }} />
        </div>
      </div>
    </Link>
  );
}

// ─────────────────────────────────────────────────────────
// Senate map
// ─────────────────────────────────────────────────────────

const STATE_GRID = [
  ["", "", "", "", "", "", "", "", "", "", "AK"],
  ["", "", "", "", "", "", "", "", "", "", ""],
  ["", "", "", "", "", "", "", "", "", "ME", ""],
  ["WA", "", "MT", "ND", "MN", "WI", "", "MI", "", "VT", "NH"],
  ["OR", "ID", "WY", "SD", "IA", "IL", "IN", "OH", "PA", "NY", "MA"],
  ["CA", "NV", "UT", "CO", "NE", "MO", "KY", "WV", "VA", "NJ", "CT"],
  ["", "AZ", "NM", "KS", "AR", "TN", "NC", "SC", "MD", "DE", "RI"],
  ["HI", "", "", "OK", "LA", "MS", "AL", "GA", "", "", ""],
  ["", "", "", "TX", "", "", "", "FL", "", "", ""],
];

function probColor(p: number | null | undefined): string | undefined {
  if (p == null) return undefined;
  if (p >= 50) {
    const t = (p - 50) / 50;
    return `rgba(37, 99, 235, ${(0.25 + t * 0.7).toFixed(2)})`;
  }
  const t = (50 - p) / 50;
  return `rgba(220, 38, 38, ${(0.25 + t * 0.7).toFixed(2)})`;
}

function SenateMap({ map }: { map: Record<string, number> | null }) {
  const [hover, setHover] = useState<{ st: string; p: number } | null>(null);

  if (!map || Object.keys(map).length === 0) return null;

  return (
    <div className={s.card} style={{ padding: 16, marginBottom: 16, cursor: "default" }}>
      <div style={{ display: "flex", alignItems: "baseline", marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>Senate races by state</h3>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--text-muted)" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "rgba(220,38,38,0.85)" }} /> R likely
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "rgba(156,163,175,0.5)" }} /> Toss-up
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "rgba(37,99,235,0.85)" }} /> D likely
          </span>
        </span>
      </div>
      <div className={s.senateGrid}>
        {STATE_GRID.flatMap((row, r) =>
          row.map((st, c) => {
            if (!st)
              return <div key={`${r}-${c}`} />;
            const p = map[st];
            const empty = p == null;
            return (
              <div
                key={`${r}-${c}`}
                className={empty ? s.senateCellEmpty : s.senateCell}
                style={!empty ? { background: probColor(p) } : undefined}
                onMouseEnter={() => !empty && setHover({ st, p })}
                onMouseLeave={() => setHover(null)}
              >
                {st}
              </div>
            );
          })
        )}
      </div>
      <div style={{ marginTop: 10, fontSize: 11, color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
        <span>{Object.keys(map).length} states with Senate race data · Hover for detail</span>
        {hover && (
          <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono, monospace)" }}>
            <b>{hover.st}</b> — Dem prob <b className={s.probNum}>{hover.p.toFixed(0)}%</b>
          </span>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Cross-source spotlight
// ─────────────────────────────────────────────────────────

function CrossSourceSpotlight({ matches }: { matches: CrossSourceMatch[] }) {
  if (!matches || matches.length === 0) return null;

  return (
    <div className={s.section}>
      <div className={s.sectionHead}>
        <h2 className={s.sectionTitle}>
          <span className={s.sectionEmoji}>⇄</span>
          Cross-source spotlight
          <span className={s.sectionCount}>
            Markets where Kalshi and Polymarket disagree
          </span>
        </h2>
      </div>
      <div className={s.grid}>
        {matches.slice(0, 4).map((m, i) => (
          <CrossSourceCard key={i} market={m} />
        ))}
      </div>
    </div>
  );
}

function CrossSourceCard({ market }: { market: CrossSourceMatch }) {
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

// ─────────────────────────────────────────────────────────
// Market cards — binary and multi-outcome
// ─────────────────────────────────────────────────────────

function MarketCard({
  market,
  theme,
}: {
  market: PoliticsMarketRow;
  theme: string;
}) {
  const borderColor = BORDER_COLOR[theme] || "#9CA3AF";
  const isBinary = market.outcome_count <= 2;

  if (isBinary) {
    return <BinaryCard market={market} borderColor={borderColor} />;
  }
  return <MultiCard market={market} borderColor={borderColor} />;
}

function BinaryCard({
  market,
  borderColor,
}: {
  market: PoliticsMarketRow;
  borderColor: string;
}) {
  const yesProb = market.prob;
  const noProb = 100 - yesProb;
  const yesLeads = yesProb >= 50;

  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={s.marketCard} style={{ borderTop: `2px solid ${borderColor}` }}>
        <div className={s.marketCardInner}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              color: "var(--text-muted)",
            }}
          >
            <SourceBadge source={market.src} />
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

          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span
              className={s.probNum}
              style={{ fontSize: 24, color: yesLeads ? "#16A34A" : "#111827" }}
            >
              {Math.round(yesProb)}%
            </span>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {market.top_outcomes?.[0]?.name || "Yes"}
            </span>
            <span
              style={{
                marginLeft: "auto",
                fontSize: 11,
                color: "var(--text-muted)",
              }}
            >
              vs{" "}
              <span className={s.probNum}>{Math.round(noProb)}%</span>{" "}
              {market.top_outcomes?.[1]?.name || "No"}
            </span>
          </div>

          <div className={s.binaryBar}>
            <div style={{ width: `${yesProb}%`, background: "#16A34A" }} />
            <div style={{ width: `${noProb}%`, background: "#94A3B8" }} />
          </div>
        </div>
      </div>
    </Link>
  );
}

function MultiCard({
  market,
  borderColor,
}: {
  market: PoliticsMarketRow;
  borderColor: string;
}) {
  const leader = market.top_outcomes?.[0];
  if (!leader) return null;

  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={s.marketCard} style={{ borderTop: `2px solid ${borderColor}` }}>
        <div className={s.marketCardInner}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              color: "var(--text-muted)",
            }}
          >
            <SourceBadge source={market.src} />
            {market.outcome_count > 3 && (
              <span
                style={{
                  marginLeft: "auto",
                  fontFamily: "var(--font-mono, monospace)",
                  fontSize: 10,
                }}
              >
                +{market.outcome_count - 3} more
              </span>
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
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                  textTransform: "uppercase",
                }}
              >
                Leader
              </span>
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  marginTop: 2,
                }}
              >
                {leader.name}
              </span>
            </div>
            <span className={s.probNum} style={{ fontSize: 28, color: "var(--text-primary)" }}>
              {Math.round(leader.prob)}%
            </span>
          </div>

          <div
            style={{
              height: 4,
              background: "#E5E7EB",
              borderRadius: 9999,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.max(leader.prob, 2)}%`,
                height: "100%",
                background: "#8B5CF6",
                opacity: 0.7,
              }}
            />
          </div>

          {/* Runner-up outcomes */}
          {market.top_outcomes.length > 1 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 2 }}>
              {market.top_outcomes.slice(1, 3).map((o, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: "var(--text-secondary)" }}>{o.name}</span>
                  <span className={s.probNum} style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {Math.round(o.prob)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

// ─────────────────────────────────────────────────────────
// Section components
// ─────────────────────────────────────────────────────────

function SectionHead({
  themeKey,
  count,
  totalLabel,
}: {
  themeKey: string;
  count: number;
  totalLabel?: string;
}) {
  const t = THEMES.find((x) => x.key === themeKey);
  return (
    <div className={s.sectionHead}>
      <h2 className={s.sectionTitle}>
        <span className={s.sectionEmoji}>{t?.emoji}</span>
        {t?.label || themeKey}
        <span className={s.sectionCount}>
          {totalLabel || `${count} markets`}
        </span>
      </h2>
      {count > 10 && (
        <div className={s.sectionActions}>
          <span className={s.sectionLink}>View all →</span>
        </div>
      )}
    </div>
  );
}

function ThemeSection({
  themeKey,
  data,
}: {
  themeKey: string;
  data: PoliticsThemeSimple | null;
}) {
  if (!data || !data.markets?.length) return null;
  return (
    <section id={`sec-${themeKey}`} className={s.section}>
      <SectionHead
        themeKey={themeKey}
        count={data.count}
        totalLabel={`${data.markets.length} shown · ${data.count} total`}
      />
      <div className={s.grid}>
        {data.markets.map((m, i) => (
          <MarketCard key={i} market={m} theme={themeKey} />
        ))}
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────

export default function PoliticsPage() {
  usePageTracking({ pageType: "politics", pageTitle: "Politics Dashboard" });
  useScrollDepth({ pageType: "politics" });
  useEngagementTime({ pageType: "politics" });

  const [activeTheme, setActiveTheme] = useState<string | null>(null);
  const { data, error } = useSWR("politics-data", fetchPolitics, {
    refreshInterval: 60000,
  });

  if (error) {
    return (
      <div className={s.page}>
        <ErrorState message="Failed to load politics data" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className={s.page}>
        <div className="max-w-[1200px] mx-auto py-20 text-center">
          <div className="animate-pulse text-text-muted text-sm">
            Loading politics markets...
          </div>
        </div>
      </div>
    );
  }

  const handleJump = (key: string | null) => {
    setActiveTheme(key);
    if (key) {
      const el = document.getElementById(`sec-${key}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const t = data.themes;
  const counts: Record<string, number> = {
    presidential: t.presidential?.count || 0,
    congressional: t.congressional?.count || 0,
    gubernatorial: t.gubernatorial?.count || 0,
    policy: t.policy?.count || 0,
    scotus: t.scotus?.count || 0,
    international: t.international?.count || 0,
    other: t.other?.count || 0,
  };

  const updatedAgo = data.updated_at
    ? formatTimeAgo(data.updated_at)
    : "just now";

  return (
    <div className={`${s.page} -mx-3 md:-mx-6 -mt-4`}>
      {/* Page header */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "32px 20px 20px" }}>
        <div className={s.pageHead}>
          <div>
            <h1 className={s.pageTitle}>Politics</h1>
            <p className={s.pageSub}>
              Probabilities for races, policy, and power across U.S. and global
              politics.
            </p>
          </div>
          <div className={s.pageMeta}>
            <span>
              <b className={s.metaNum}>
                {data.total_markets.toLocaleString()}
              </b>{" "}
              markets
            </span>
            <span>
              <b className={s.metaNum}>2</b> sources
            </span>
            <span>
              Updated <b className={s.metaNum}>{updatedAgo}</b>
            </span>
          </div>
        </div>
      </div>

      {/* Sub-theme nav */}
      <SubNav
        themes={THEMES}
        counts={counts}
        active={activeTheme}
        onJump={handleJump}
      />

      {/* Content */}
      <div className={s.pageContent}>
        {/* Presidential hero */}
        {t.presidential && t.presidential.candidates?.length > 0 && (
          <section id="sec-presidential" className={s.section} style={{ marginTop: 0 }}>
            <SectionHead
              themeKey="presidential"
              count={t.presidential.count}
              totalLabel={`${t.presidential.candidates.length} candidates · ${t.presidential.count} markets`}
            />
            <PresHero data={t.presidential} />
          </section>
        )}

        {/* Congressional with chamber control */}
        {t.congressional && t.congressional.count > 0 && (
          <section id="sec-congressional" className={s.section}>
            <SectionHead
              themeKey="congressional"
              count={t.congressional.count}
              totalLabel={`${t.congressional.markets?.length || 0} shown · ${t.congressional.count} total`}
            />
            <ChamberControlRow
              senate={t.congressional.chamber_control?.senate || null}
              house={t.congressional.chamber_control?.house || null}
            />
            <SenateMap map={t.congressional.senate_map} />
            {t.congressional.markets && t.congressional.markets.length > 0 && (
              <div className={s.grid}>
                {t.congressional.markets.map((m, i) => (
                  <MarketCard key={i} market={m} theme="congressional" />
                ))}
              </div>
            )}
          </section>
        )}

        {/* Cross-source spotlight */}
        <CrossSourceSpotlight matches={data.cross_source} />

        {/* Remaining sections */}
        <ThemeSection themeKey="gubernatorial" data={t.gubernatorial} />
        <ThemeSection themeKey="policy" data={t.policy} />
        <ThemeSection themeKey="scotus" data={t.scotus} />
        <ThemeSection themeKey="international" data={t.international} />
        <ThemeSection themeKey="other" data={t.other} />

        {/* Footer */}
        <footer className={s.footer}>
          Bain Luck translates prediction-market prices into probabilities. Data
          from Kalshi &amp; Polymarket. Not financial advice.
        </footer>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
