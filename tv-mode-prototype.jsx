import { useState, useEffect } from "react";

/* ═══════════════════════════════════════════════════════════════════════
   BAIN LUCK — TV MODE PROTOTYPE v4
   Cascaded density: Phone=current iPad, iPad=current TV, TV=MAXIMAL
   ═══════════════════════════════════════════════════════════════════════ */

const hex2rgb = (h) => ({ r: parseInt(h.slice(1, 3), 16), g: parseInt(h.slice(3, 5), 16), b: parseInt(h.slice(5, 7), 16) });
const rgba = (h, a) => { const { r, g, b } = hex2rgb(h); return `rgba(${r},${g},${b},${a})`; };
const beatMs = (p) => Math.max(550, 2000 - p * 14.5);
const pct = (v) => Math.round(v * 100);

// ─── Enriched Mock Data ───────────────────────────────────────────────
const GAMES = [
  {
    home: { name: "Celtics", abbr: "BOS", color: "#007A33", prob: 0.62, score: 87, record: "42-18" },
    away: { name: "Warriors", abbr: "GSW", color: "#1D428A", prob: 0.38, score: 79, record: "35-25" },
    pulse: 78, period: "Q3", clock: "4:22", broadcast: "ESPN", sport: "NBA",
    opening: { home: 0.55, away: 0.45 },
    lineMove: { dir: "up", val: 7, team: "BOS" },
    context: "BOS 5-game W streak",
    implication: "Title odds: 22% → ~24% with win",
    divergence: { source: "Kalshi", delta: 6, dir: "higher" },
    related: [
      { market: "NBA Championship", outcome: "Celtics", prob: 0.22, trend: "+2.1%" },
      { market: "NBA MVP", outcome: "Tatum", prob: 0.15, trend: null },
      { market: "Finals MVP", outcome: "Tatum", prob: 0.18, trend: "+0.8%" },
    ],
    sources: {
      odds:   [55, 53, 50, 48, 51, 54, 58, 55, 57, 60, 62, 58, 61, 63, 62, 60, 62],
      espn:   [54, 52, 49, 47, 50, 53, 57, 54, 56, 59, 61, 57, 60, 62, 61, 59, 61],
      kalshi: [57, 55, 52, 50, 53, 57, 61, 59, 61, 64, 66, 62, 65, 67, 66, 64, 68],
    },
    periodScores: [
      { label: "Q1", home: 28, away: 22 },
      { label: "Q2", home: 24, away: 31 },
      { label: "Q3", home: 35, away: 26 },
    ],
    pulseComponents: { heartRate: 72, amplitude: 81, arrhythmia: 65, vitals: 85 },
  },
  {
    home: { name: "Chiefs", abbr: "KC", color: "#E31837", prob: 0.54, score: 24, record: "14-4" },
    away: { name: "Bills", abbr: "BUF", color: "#00338D", prob: 0.46, score: 21, record: "13-5" },
    pulse: 91, period: "4th", clock: "2:47", broadcast: "FOX", sport: "NFL",
    opening: { home: 0.60, away: 0.40 },
    lineMove: { dir: "down", val: 6, team: "KC" },
    context: "BUF 3 unanswered scores",
    implication: "SB odds: KC 14% / BUF 9%",
    divergence: { source: "Polymarket", delta: 8, dir: "lower" },
    related: [
      { market: "Super Bowl LXI", outcome: "Chiefs", prob: 0.14, trend: "-1.3%" },
      { market: "Super Bowl LXI", outcome: "Bills", prob: 0.09, trend: "+2.0%" },
      { market: "NFL MVP", outcome: "Mahomes", prob: 0.22, trend: null },
    ],
    sources: {
      odds:       [65, 60, 55, 50, 45, 48, 52, 55, 50, 48, 52, 54, 53, 54, 52, 54],
      espn:       [63, 58, 53, 48, 43, 46, 50, 53, 48, 46, 50, 52, 51, 52, 50, 52],
      polymarket: [62, 57, 52, 47, 42, 45, 49, 52, 47, 44, 48, 50, 48, 46, 44, 46],
    },
    periodScores: [
      { label: "Q1", home: 7, away: 0 },
      { label: "Q2", home: 10, away: 7 },
      { label: "Q3", home: 0, away: 14 },
      { label: "Q4", home: 7, away: 0 },
    ],
    pulseComponents: { heartRate: 95, amplitude: 88, arrhythmia: 91, vitals: 90 },
  },
  {
    home: { name: "Lakers", abbr: "LAL", color: "#552583", prob: 0.35, score: 68, record: "30-30" },
    away: { name: "Nuggets", abbr: "DEN", color: "#0E2240", prob: 0.65, score: 82, record: "38-22" },
    pulse: 42, period: "Q3", clock: "8:15", broadcast: "TNT", sport: "NBA",
    opening: { home: 0.42, away: 0.58 },
    lineMove: { dir: "down", val: 7, team: "LAL" },
    context: "DEN on 12-0 run",
    implication: "DEN title odds steady at 9%",
    divergence: null,
    related: [
      { market: "NBA Championship", outcome: "Nuggets", prob: 0.09, trend: "+0.4%" },
      { market: "NBA MVP", outcome: "Jokić", prob: 0.12, trend: null },
    ],
    sources: {
      odds: [50, 48, 45, 42, 40, 38, 36, 35, 33, 34, 35, 36, 35, 34, 35],
      espn: [49, 47, 44, 41, 39, 37, 35, 34, 32, 33, 34, 35, 34, 33, 34],
    },
    periodScores: [
      { label: "Q1", home: 18, away: 25 },
      { label: "Q2", home: 22, away: 28 },
      { label: "Q3", home: 28, away: 29 },
    ],
    pulseComponents: { heartRate: 35, amplitude: 42, arrhythmia: 28, vitals: 55 },
  },
  {
    home: { name: "Harris", abbr: "KH", color: "#0015BC", prob: 0.48, score: 214, record: "" },
    away: { name: "Trump", abbr: "DJT", color: "#E81B23", prob: 0.52, score: 267, record: "" },
    pulse: 96, period: "FL called", clock: "11:42 PM", broadcast: "CNN", sport: "ELECTION",
    opening: { home: 0.52, away: 0.48 },
    lineMove: { dir: "down", val: 4, team: "KH" },
    context: "FL, OH, TX called for DJT",
    implication: "Blue wall states still counting",
    divergence: { source: "Polymarket", delta: 11, dir: "higher" },
    related: [
      { market: "Senate Control", outcome: "Republican", prob: 0.72, trend: "+8%" },
      { market: "House Control", outcome: "Republican", prob: 0.55, trend: "+3%" },
    ],
    sources: {
      odds:       [52, 51, 50, 49, 48, 47, 48, 47, 46, 47, 48, 48],
      polymarket: [50, 48, 46, 44, 42, 40, 41, 39, 38, 40, 42, 41],
    },
    periodScores: [],
    pulseComponents: { heartRate: 98, amplitude: 92, arrhythmia: 96, vitals: 94 },
  },
];

const FUTURES = [
  { name: "NBA Championship", emoji: "🏆", cat: "Basketball", outcomes: [
    { name: "Boston Celtics", prob: 0.22, color: "#007A33" }, { name: "OKC Thunder", prob: 0.18, color: "#007AC1" },
    { name: "Cleveland Cavaliers", prob: 0.12, color: "#860038" }, { name: "Denver Nuggets", prob: 0.09, color: "#0E2240" },
    { name: "Milwaukee Bucks", prob: 0.07, color: "#00471B" },
  ]},
  { name: "Best Picture 2026", emoji: "🎬", cat: "Entertainment", outcomes: [
    { name: "The Brutalist", prob: 0.30, color: "#D4AF37" }, { name: "Conclave", prob: 0.22, color: "#C5A028" },
    { name: "Anora", prob: 0.15, color: "#B8963A" }, { name: "Wicked", prob: 0.10, color: "#A8862E" },
    { name: "Emilia Pérez", prob: 0.08, color: "#9A7A30" },
  ]},
  { name: "2028 Presidential Election", emoji: "🗳️", cat: "Politics", outcomes: [
    { name: "JD Vance", prob: 0.28, color: "#E81B23" }, { name: "Josh Shapiro", prob: 0.15, color: "#0015BC" },
    { name: "Gretchen Whitmer", prob: 0.12, color: "#0033A0" }, { name: "Gavin Newsom", prob: 0.08, color: "#004BA0" },
  ]},
  { name: "Bitcoin Year-End", emoji: "₿", cat: "Crypto", outcomes: [
    { name: "Above $150k", prob: 0.35, color: "#F7931A" }, { name: "Below $100k", prob: 0.22, color: "#E8850F" },
    { name: "Above $200k", prob: 0.15, color: "#D97B0A" }, { name: "Below $75k", prob: 0.08, color: "#C06E08" },
  ]},
  { name: "Super Bowl LXI", emoji: "🏈", cat: "Football", outcomes: [
    { name: "Kansas City Chiefs", prob: 0.14, color: "#E31837" }, { name: "Detroit Lions", prob: 0.11, color: "#0076B6" },
    { name: "Philadelphia Eagles", prob: 0.10, color: "#004C54" }, { name: "Buffalo Bills", prob: 0.09, color: "#00338D" },
  ]},
];

const SRC = {
  odds:       { name: "Sportsbooks", color: "#ffffff", dash: "" },
  espn:       { name: "ESPN",        color: "#f97316", dash: "6 3" },
  kalshi:     { name: "Kalshi",      color: "#22c55e", dash: "4 3" },
  polymarket: { name: "Polymarket",  color: "#3b82f6", dash: "4 3" },
  model:      { name: "BL Model",    color: "#a855f7", dash: "2 3" },
};

const CSS = `
  @keyframes tvb{0%,100%{transform:scale(1);filter:brightness(1)}50%{transform:scale(1.025);filter:brightness(1.18)}}
  @keyframes tvd{0%,100%{transform:scale(1);opacity:.6}50%{transform:scale(1.6);opacity:1}}
  @keyframes tvr{0%,100%{transform:scale(1);opacity:.35}50%{transform:scale(1.12);opacity:.8}}
  @keyframes tvf{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
  @keyframes tvs{from{opacity:0;transform:translateX(12px)}to{opacity:1;transform:translateX(0)}}
  .tvb{transition:all .15s;cursor:pointer;font-family:inherit}.tvb:hover{background:rgba(255,255,255,.12)!important}
`;

// ═══════════════════════════════════════════════════════════════════════
// SHARED DRAWING
// ═══════════════════════════════════════════════════════════════════════
function buildCurve(pts) {
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(i + 2, pts.length - 1)];
    d += ` C ${p1.x + (p2.x - p0.x) / 6} ${p1.y + (p2.y - p0.y) / 6},${p2.x - (p3.x - p1.x) / 6} ${p2.y - (p3.y - p1.y) / 6},${p2.x} ${p2.y}`;
  }
  return d;
}
function toPts(data, w, h, mn, mx) {
  const r = mx - mn || 1;
  return data.map((v, i) => ({ x: (i / (data.length - 1)) * w, y: h - ((v / 100 - mn) / r) * h }));
}

// Multi-source chart
function Chart({ sources, width = 400, height = 160, showGrid = false, showLegend = true }) {
  const all = Object.values(sources).flatMap((d) => d.map((v) => v / 100));
  const mn = Math.min(...all) - 0.06, mx = Math.max(...all) + 0.06, rng = mx - mn || 1;
  const entries = Object.entries(sources).filter(([, d]) => d?.length >= 2);
  const gridVals = showGrid ? [0.3, 0.4, 0.5, 0.6, 0.7].filter((v) => { const y = height - ((v - mn) / rng) * height; return y > 10 && y < height - 10; }) : [0.5];

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: "block", flex: "1 1 0", minHeight: 0 }}>
        {gridVals.map((v) => {
          const y = height - ((v - mn) / rng) * height;
          return (
            <g key={v}>
              <line x1="0" y1={y} x2={width} y2={y} stroke={v === 0.5 ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.03)"} strokeWidth="1" strokeDasharray={v === 0.5 ? "6 4" : "3 3"} />
              {showGrid && <text x="3" y={y - 3} fill="rgba(255,255,255,0.1)" fontSize="8" fontFamily="inherit">{Math.round(v * 100)}%</text>}
            </g>
          );
        })}
        {entries[0] && (() => {
          const pts = toPts(entries[0][1], width, height, mn, mx);
          return <path d={buildCurve(pts) + ` L ${width} ${height} L 0 ${height} Z`} fill="rgba(255,255,255,0.04)" />;
        })()}
        {entries.map(([k, data]) => {
          const m = SRC[k] || { color: "#888", dash: "" };
          const pts = toPts(data, width, height, mn, mx);
          return (
            <g key={k}>
              <path d={buildCurve(pts)} fill="none" stroke={m.color} strokeWidth={k === "odds" ? 2.5 : 1.8} strokeLinecap="round" strokeDasharray={m.dash} strokeOpacity={k === "odds" ? 1 : 0.7} />
              <circle cx={pts.at(-1).x} cy={pts.at(-1).y} r={k === "odds" ? 3.5 : 2.5} fill={m.color} fillOpacity={k === "odds" ? 1 : 0.7} />
            </g>
          );
        })}
      </svg>
      {showLegend && (
        <div style={{ display: "flex", gap: 10, justifyContent: "center", paddingTop: 6, flexShrink: 0 }}>
          {entries.map(([k]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <svg width="14" height="2"><line x1="0" y1="1" x2="14" y2="1" stroke={SRC[k].color} strokeWidth={k === "odds" ? 2.5 : 1.8} strokeDasharray={SRC[k].dash} strokeLinecap="round" /></svg>
              <span style={{ fontSize: 10, color: "rgba(255,255,255,0.35)" }}>{SRC[k].name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Mini sparkline (inline, no axes)
function Sparkline({ data, color = "#fff", w = 60, h = 18 }) {
  if (!data || data.length < 2) return null;
  const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1;
  const pts = data.map((v, i) => ({ x: (i / (data.length - 1)) * w, y: h - ((v - mn) / rng) * (h - 2) - 1 }));
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <path d={buildCurve(pts)} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.5" />
      <circle cx={pts.at(-1).x} cy={pts.at(-1).y} r="2" fill={color} fillOpacity="0.7" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// SHARED UI ATOMS
// ═══════════════════════════════════════════════════════════════════════
function BigNum({ value, color, pulse, size = 60 }) {
  return (
    <span style={{
      fontSize: size, fontWeight: 200, letterSpacing: "-0.04em", lineHeight: 1, color: "#fff",
      textShadow: `0 0 ${size * 0.35}px ${rgba(color, 0.45)},0 0 ${size * 0.7}px ${rgba(color, 0.15)}`,
      animation: `tvb ${beatMs(pulse)}ms ease-in-out infinite`,
      display: "inline-block", fontVariantNumeric: "tabular-nums", willChange: "transform",
    }}>{pct(value)}</span>
  );
}
function Dot({ score, sz = 8 }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ width: sz, height: sz, borderRadius: "50%", background: "#ef4444", boxShadow: `0 0 ${sz}px ${rgba("#ef4444", 0.5)}`, animation: `tvd ${beatMs(score)}ms ease-in-out infinite`, display: "inline-block" }} />
      <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{score}</span>
    </span>
  );
}
function Bar({ hp, hc, ac, h = 4 }) {
  return (
    <div style={{ width: "100%", height: h, borderRadius: h, overflow: "hidden", display: "flex" }}>
      <div style={{ width: `${hp * 100}%`, background: `linear-gradient(90deg,${hc},${rgba(hc, 0.6)})`, transition: "width 1.2s" }} />
      <div style={{ flex: 1, background: `linear-gradient(90deg,${rgba(ac, 0.6)},${ac})` }} />
    </div>
  );
}
function Badge({ abbr, color, sz = 28 }) {
  return (
    <div style={{ width: sz, height: sz, borderRadius: "50%", flexShrink: 0, background: rgba(color, 0.15), border: `1.5px solid ${rgba(color, 0.35)}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: sz * 0.38, fontWeight: 700, color }}>
      {abbr.slice(0, 2)}
    </div>
  );
}
function Ring({ score, sz = 100 }) {
  const sp = beatMs(score);
  const lb = score >= 85 ? "Thriller" : score >= 65 ? "Exciting" : score >= 45 ? "Moderate" : "Quiet";
  return (
    <div style={{ position: "relative", width: sz, height: sz, margin: "0 auto" }}>
      <div style={{ position: "absolute", inset: 0, borderRadius: "50%", border: `2px solid ${rgba("#ef4444", 0.3)}`, animation: `tvr ${sp}ms ease-in-out infinite` }} />
      <div style={{ position: "absolute", inset: 8, borderRadius: "50%", background: `radial-gradient(circle,${rgba("#ef4444", 0.06 + score / 1000)} 0%,transparent 70%)`, animation: `tvb ${sp}ms ease-in-out infinite` }} />
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontSize: sz * 0.32, fontWeight: 300, color: "#fff", fontVariantNumeric: "tabular-nums" }}>{score}</span>
        <span style={{ fontSize: sz * 0.1, color: "rgba(255,255,255,0.35)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{lb}</span>
      </div>
    </div>
  );
}
function Ctx({ label, value, color, small }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: small ? "4px 0" : "6px 0", borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
      <span style={{ fontSize: small ? 9 : 11, color: "rgba(255,255,255,0.25)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
      <span style={{ fontSize: small ? 11 : 13, color: color || "rgba(255,255,255,0.6)", fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
  );
}
// Mini card for "other games"
function MiniGame({ g, active, onClick, showSparkline }) {
  const lead = g.home.prob >= g.away.prob ? g.home : g.away;
  return (
    <div onClick={onClick} style={{
      padding: "7px 10px", borderRadius: 6, cursor: "pointer", transition: "all .15s",
      background: active ? "rgba(255,255,255,0.04)" : "transparent",
      borderLeft: `2px solid ${active ? lead.color : "rgba(255,255,255,0.06)"}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 11, color: "rgba(255,255,255,0.6)" }}>
        <span style={{ fontWeight: g.home.prob > g.away.prob ? 600 : 400 }}>{g.home.abbr}</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{g.home.score}</span>
        <span style={{ fontVariantNumeric: "tabular-nums", marginLeft: "auto" }}>{pct(g.home.prob)}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 11, color: "rgba(255,255,255,0.6)" }}>
        <span style={{ fontWeight: g.away.prob > g.home.prob ? 600 : 400 }}>{g.away.abbr}</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{g.away.score}</span>
        <span style={{ fontVariantNumeric: "tabular-nums", marginLeft: "auto" }}>{pct(g.away.prob)}</span>
      </div>
      {showSparkline && g.sources?.odds && (
        <div style={{ marginTop: 3 }}>
          <Sparkline data={g.sources.odds} color={lead.color} w={80} h={16} />
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 3, fontSize: 9, color: "rgba(255,255,255,0.2)" }}>
        <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#ef4444", display: "inline-block", animation: `tvd ${beatMs(g.pulse)}ms ease-in-out infinite` }} />
        <span>{g.pulse}</span>
        <span>·</span>
        <span>{g.period} {g.clock}</span>
      </div>
    </div>
  );
}
// Related futures row
function RelRow({ r, small }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: small ? "3px 0" : "5px 0" }}>
      <div>
        <span style={{ fontSize: small ? 10 : 11, color: "rgba(255,255,255,0.4)" }}>{r.market}</span>
        <span style={{ fontSize: small ? 10 : 12, color: "rgba(255,255,255,0.65)", marginLeft: 6, fontWeight: 500 }}>{r.outcome}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: small ? 11 : 13, color: "rgba(255,255,255,0.7)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{pct(r.prob)}%</span>
        {r.trend && <span style={{ fontSize: small ? 9 : 10, color: r.trend.startsWith("+") ? "#22c55e" : "#ef4444", fontVariantNumeric: "tabular-nums" }}>{r.trend}</span>}
      </div>
    </div>
  );
}

// Pulse component breakdown (TV only)
function PulseBreakdown({ components, small }) {
  const items = [
    { key: "heartRate", label: "Heart Rate", color: "#ef4444" },
    { key: "amplitude", label: "Amplitude", color: "#f97316" },
    { key: "arrhythmia", label: "Arrhythmia", color: "#a855f7" },
    { key: "vitals", label: "Vitals", color: "#22c55e" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: small ? 3 : 5 }}>
      {items.map(({ key, label, color }) => (
        <div key={key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: small ? 8 : 9, color: "rgba(255,255,255,0.25)", width: small ? 52 : 62, textAlign: "right", flexShrink: 0 }}>{label}</span>
          <div style={{ flex: 1, height: small ? 5 : 7, background: "rgba(255,255,255,0.04)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${components[key]}%`, background: `linear-gradient(90deg,${rgba(color, 0.6)},${rgba(color, 0.25)})`, borderRadius: 3, transition: "width 1s" }} />
          </div>
          <span style={{ fontSize: small ? 9 : 10, color: "rgba(255,255,255,0.4)", fontVariantNumeric: "tabular-nums", width: 22, textAlign: "right", flexShrink: 0 }}>{components[key]}</span>
        </div>
      ))}
    </div>
  );
}

// Source comparison strip (TV only)
function SourceStrip({ sources, homeColor, awayColor }) {
  const entries = Object.entries(sources).filter(([, d]) => d?.length >= 2);
  return (
    <div style={{ display: "flex", gap: 0, borderRadius: 5, overflow: "hidden", background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)" }}>
      {entries.map(([k, data]) => {
        const curr = data.at(-1);
        const prev = data.at(-2);
        const delta = curr - prev;
        const m = SRC[k] || { name: k, color: "#888" };
        return (
          <div key={k} style={{ flex: 1, padding: "6px 8px", borderRight: "1px solid rgba(255,255,255,0.04)", display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <span style={{ fontSize: 8, color: m.color, textTransform: "uppercase", letterSpacing: "0.08em", opacity: 0.7 }}>{m.name}</span>
            <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
              <span style={{ fontSize: 16, fontWeight: 500, color: "rgba(255,255,255,0.75)", fontVariantNumeric: "tabular-nums" }}>{curr}%</span>
              {delta !== 0 && <span style={{ fontSize: 9, color: delta > 0 ? "#22c55e" : "#ef4444", fontVariantNumeric: "tabular-nums" }}>{delta > 0 ? "+" : ""}{delta}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Score-by-period table (TV only)
function PeriodScores({ periods, homeAbbr, awayAbbr, homeColor, awayColor, homeTotal, awayTotal }) {
  if (!periods || periods.length === 0) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, fontSize: 10, fontVariantNumeric: "tabular-nums" }}>
      {/* Team labels */}
      <div style={{ display: "flex", flexDirection: "column", gap: 1, marginRight: 6 }}>
        <span style={{ color: rgba(homeColor, 0.7), fontWeight: 600, fontSize: 9 }}>{homeAbbr}</span>
        <span style={{ color: rgba(awayColor, 0.7), fontWeight: 600, fontSize: 9 }}>{awayAbbr}</span>
      </div>
      {/* Period cells */}
      {periods.map((p, i) => (
        <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1, padding: "0 5px", borderRight: "1px solid rgba(255,255,255,0.04)" }}>
          <span style={{ fontSize: 7, color: "rgba(255,255,255,0.15)", marginBottom: 1 }}>{p.label}</span>
          <span style={{ color: p.home > p.away ? rgba(homeColor, 0.8) : "rgba(255,255,255,0.35)", fontWeight: p.home > p.away ? 600 : 400 }}>{p.home}</span>
          <span style={{ color: p.away > p.home ? rgba(awayColor, 0.8) : "rgba(255,255,255,0.35)", fontWeight: p.away > p.home ? 600 : 400 }}>{p.away}</span>
        </div>
      ))}
      {/* Total */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1, padding: "0 6px" }}>
        <span style={{ fontSize: 7, color: "rgba(255,255,255,0.15)", marginBottom: 1 }}>T</span>
        <span style={{ color: rgba(homeColor, 0.9), fontWeight: 600 }}>{homeTotal}</span>
        <span style={{ color: rgba(awayColor, 0.9), fontWeight: 600 }}>{awayTotal}</span>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════
// PHONE LIVE — cascaded from old Tablet (sidebar content below chart)
// ═══════════════════════════════════════════════════════════════════════
function PhoneLive({ game, pulse }) {
  const lm = game.lineMove;
  const lead = game.home.prob >= game.away.prob ? game.home.color : game.away.color;
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: `radial-gradient(ellipse at 50% 15%,${rgba(lead, 0.04)} 0%,#09090b 60%)`, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 1, background: `linear-gradient(90deg,transparent,${rgba(game.home.color, 0.3)} 30%,${rgba(game.away.color, 0.3)} 70%,transparent)` }} />

      {/* Header: sport + live + teams + score + clock */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "44px 14px 8px", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", letterSpacing: "0.15em", textTransform: "uppercase" }}>{game.sport}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color: "#ef4444", fontWeight: 600 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#ef4444", animation: "tvd 1.5s ease-in-out infinite", display: "inline-block" }} />LIVE
          </span>
        </div>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", fontVariantNumeric: "tabular-nums" }}>{game.period} {game.clock} · {game.broadcast}</span>
      </div>

      {/* Teams + score row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 14px", marginBottom: 4, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Badge abbr={game.home.abbr} color={game.home.color} sz={26} />
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>{game.home.name}</div>
            {game.home.record && <div style={{ fontSize: 9, color: "rgba(255,255,255,0.25)" }}>{game.home.record}</div>}
          </div>
        </div>
        <div style={{ fontSize: 28, fontWeight: 300, color: "#fff", fontVariantNumeric: "tabular-nums" }}>
          {game.home.score} <span style={{ color: "rgba(255,255,255,0.12)", fontSize: 18 }}>–</span> {game.away.score}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>{game.away.name}</div>
            {game.away.record && <div style={{ fontSize: 9, color: "rgba(255,255,255,0.25)" }}>{game.away.record}</div>}
          </div>
          <Badge abbr={game.away.abbr} color={game.away.color} sz={26} />
        </div>
      </div>

      {/* Probabilities */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", padding: "0 14px", marginBottom: 3, flexShrink: 0 }}>
        <BigNum value={game.home.prob} color={game.home.color} pulse={pulse} size={56} />
        <span style={{ fontSize: 8, color: "rgba(255,255,255,0.1)", textTransform: "uppercase", letterSpacing: "0.1em", paddingBottom: 6 }}>win prob</span>
        <BigNum value={game.away.prob} color={game.away.color} pulse={pulse} size={56} />
      </div>
      <div style={{ padding: "0 14px" }}><Bar hp={game.home.prob} hc={game.home.color} ac={game.away.color} h={4} /></div>

      {/* Chart */}
      <div style={{ flex: "1 1 0", minHeight: 0, padding: "6px 14px 0" }}>
        <Chart sources={game.sources} width={362} height={180} showGrid />
      </div>

      {/* Scrollable context below chart */}
      <div style={{ flexShrink: 0, padding: "6px 14px 12px", overflow: "auto", maxHeight: 200 }}>
        {/* Pulse + context grid */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <Ring score={pulse} sz={58} />
          <div style={{ flex: 1 }}>
            <Ctx label="Opened" value={`${pct(game.opening.home)} / ${pct(game.opening.away)}`} small />
            <Ctx label="Line" value={`${lm.dir === "up" ? "↑" : "↓"}${lm.val}% ${lm.team}`} color={lm.dir === "up" ? "#22c55e" : "#ef4444"} small />
            {game.divergence && <Ctx label="Markets" value={`${game.divergence.source} ${game.divergence.dir === "higher" ? "+" : "-"}${game.divergence.delta}%`} color={game.divergence.delta >= 8 ? "#a855f7" : "#3b82f6"} small />}
          </div>
        </div>

        {/* Implications */}
        <div style={{ padding: "6px 8px", borderRadius: 5, background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)", marginBottom: 6 }}>
          <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>Championship Impact</div>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", lineHeight: 1.3 }}>{game.implication}</div>
          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", marginTop: 2 }}>{game.context}</div>
        </div>

        {/* Related futures */}
        {game.related?.length > 0 && (
          <div>
            <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Related Futures</div>
            {game.related.slice(0, 3).map((r, i) => <RelRow key={i} r={r} small />)}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// TABLET LIVE — cascaded from old TV (3-column: chart + context + games)
// ═══════════════════════════════════════════════════════════════════════
function TabletLive({ game, pulse, allGames, activeIdx, onSelectGame }) {
  const lm = game.lineMove;
  const lead = game.home.prob >= game.away.prob ? game.home.color : game.away.color;
  const otherGames = allGames.filter((_, i) => i !== activeIdx);
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: `radial-gradient(ellipse at 35% 10%,${rgba(lead, 0.03)} 0%,#09090b 50%)`, position: "relative" }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 1, background: `linear-gradient(90deg,transparent 5%,${rgba(game.home.color, 0.3)} 20%,rgba(255,255,255,0.06) 50%,${rgba(game.away.color, 0.3)} 80%,transparent 95%)` }} />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", letterSpacing: "0.15em", textTransform: "uppercase" }}>{game.sport}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color: "#ef4444", fontWeight: 600 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#ef4444", animation: "tvd 1.5s ease-in-out infinite", display: "inline-block" }} />LIVE
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}><Badge abbr={game.home.abbr} color={game.home.color} sz={24} /><span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>{game.home.name}</span>{game.home.record && <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)" }}>{game.home.record}</span>}</div>
          <div style={{ fontSize: 24, fontWeight: 300, color: "#fff", fontVariantNumeric: "tabular-nums" }}>{game.home.score} <span style={{ color: "rgba(255,255,255,0.12)", fontSize: 14 }}>–</span> {game.away.score}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>{game.away.record && <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)" }}>{game.away.record}</span>}<span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.85)" }}>{game.away.name}</span><Badge abbr={game.away.abbr} color={game.away.color} sz={24} /></div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: "rgba(255,255,255,0.6)", fontVariantNumeric: "tabular-nums" }}>{game.period} {game.clock}</div>
          <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)" }}>{game.broadcast}</div>
        </div>
      </div>

      {/* Main: chart + context sidebar + other games */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>

        {/* Left: probs + chart */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "10px 16px 8px", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 3 }}>
            <BigNum value={game.home.prob} color={game.home.color} pulse={pulse} size={56} />
            <span style={{ fontSize: 9, color: "rgba(255,255,255,0.1)", textTransform: "uppercase", letterSpacing: "0.1em", paddingBottom: 6 }}>win probability</span>
            <BigNum value={game.away.prob} color={game.away.color} pulse={pulse} size={56} />
          </div>
          <Bar hp={game.home.prob} hc={game.home.color} ac={game.away.color} h={4} />
          <div style={{ flex: 1, marginTop: 8, minHeight: 0 }}>
            <Chart sources={game.sources} width={480} height={200} showGrid />
          </div>
        </div>

        {/* Center-right: context + related */}
        <div style={{ width: 190, flexShrink: 0, borderLeft: "1px solid rgba(255,255,255,0.04)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 2, background: "rgba(255,255,255,0.008)", overflow: "auto" }}>
          <Ring score={pulse} sz={72} />
          <div style={{ height: 4 }} />
          <Ctx label="Opened" value={`${pct(game.opening.home)} / ${pct(game.opening.away)}`} small />
          <Ctx label="Line" value={`${lm.dir === "up" ? "↑" : "↓"}${lm.val}% ${lm.team}`} color={lm.dir === "up" ? "#22c55e" : "#ef4444"} small />
          {game.divergence && <Ctx label="Markets" value={`${game.divergence.source} ${game.divergence.dir === "higher" ? "+" : "-"}${game.divergence.delta}%`} color={game.divergence.delta >= 8 ? "#a855f7" : "#3b82f6"} small />}
          <Ctx label="Context" value={game.context} small />

          <div style={{ marginTop: 4, padding: "5px 7px", borderRadius: 5, background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)" }}>
            <div style={{ fontSize: 8, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 2 }}>Championship Impact</div>
            <div style={{ fontSize: 10, color: "rgba(255,255,255,0.5)", lineHeight: 1.3 }}>{game.implication}</div>
          </div>

          {game.related?.length > 0 && (
            <div style={{ marginTop: 4 }}>
              <div style={{ fontSize: 8, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>Related Futures</div>
              {game.related.map((r, i) => <RelRow key={i} r={r} small />)}
            </div>
          )}
        </div>

        {/* Far right: other games + trending */}
        <div style={{ width: 140, flexShrink: 0, borderLeft: "1px solid rgba(255,255,255,0.04)", padding: "8px 6px", display: "flex", flexDirection: "column", gap: 0, background: "rgba(255,255,255,0.005)", overflow: "auto" }}>
          <div style={{ fontSize: 8, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4, paddingLeft: 4 }}>Other Games</div>
          {otherGames.map((g, i) => (
            <MiniGame key={i} g={g} active={false} onClick={() => onSelectGame(allGames.indexOf(g))} />
          ))}

          <div style={{ height: 1, background: "rgba(255,255,255,0.04)", margin: "6px 0" }} />

          <div style={{ fontSize: 8, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4, paddingLeft: 4 }}>Trending</div>
          {FUTURES.slice(0, 2).map((f, i) => (
            <div key={i} style={{ padding: "4px 8px", fontSize: 9 }}>
              <div style={{ color: "rgba(255,255,255,0.4)", marginBottom: 1 }}>{f.emoji} {f.name}</div>
              <div style={{ color: "rgba(255,255,255,0.6)", fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>
                {f.outcomes[0].name.split(" ").pop()} {pct(f.outcomes[0].prob)}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// TV LIVE — MAXIMAL. Everything the other views have, plus:
// Score-by-period, Pulse component breakdown, source comparison strip,
// sparklines in other-game cards, more related futures, bigger everything.
// ═══════════════════════════════════════════════════════════════════════
function TVLive({ game, pulse, allGames, activeIdx, onSelectGame }) {
  const lm = game.lineMove;
  const lead = game.home.prob >= game.away.prob ? game.home.color : game.away.color;
  const otherGames = allGames.filter((_, i) => i !== activeIdx);
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: `radial-gradient(ellipse at 35% 10%,${rgba(lead, 0.03)} 0%,#09090b 50%)`, position: "relative" }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 1, background: `linear-gradient(90deg,transparent 5%,${rgba(game.home.color, 0.3)} 15%,rgba(255,255,255,0.06) 50%,${rgba(game.away.color, 0.3)} 85%,transparent 95%)` }} />

      {/* Header — enhanced with score-by-period */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 24px", borderBottom: "1px solid rgba(255,255,255,0.04)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.25)", letterSpacing: "0.15em", textTransform: "uppercase" }}>{game.sport}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "#ef4444", fontWeight: 600 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#ef4444", animation: "tvd 1.5s ease-in-out infinite", display: "inline-block" }} />LIVE
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}><Badge abbr={game.home.abbr} color={game.home.color} sz={32} /><span style={{ fontSize: 16, fontWeight: 600, color: "rgba(255,255,255,0.9)" }}>{game.home.name}</span><span style={{ fontSize: 11, color: "rgba(255,255,255,0.25)" }}>{game.home.record}</span></div>
          <div style={{ fontSize: 34, fontWeight: 300, color: "#fff", fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em", minWidth: 90, textAlign: "center" }}>
            {game.home.score} <span style={{ color: "rgba(255,255,255,0.12)", fontSize: 20 }}>–</span> {game.away.score}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ fontSize: 11, color: "rgba(255,255,255,0.25)" }}>{game.away.record}</span><span style={{ fontSize: 16, fontWeight: 600, color: "rgba(255,255,255,0.9)" }}>{game.away.name}</span><Badge abbr={game.away.abbr} color={game.away.color} sz={32} /></div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {/* Period scores */}
          <PeriodScores
            periods={game.periodScores} homeAbbr={game.home.abbr} awayAbbr={game.away.abbr}
            homeColor={game.home.color} awayColor={game.away.color}
            homeTotal={game.home.score} awayTotal={game.away.score}
          />
          <div style={{ borderLeft: "1px solid rgba(255,255,255,0.06)", paddingLeft: 12, textAlign: "right" }}>
            <div style={{ fontSize: 16, fontWeight: 500, color: "rgba(255,255,255,0.6)", fontVariantNumeric: "tabular-nums" }}>{game.period} {game.clock}</div>
            <div style={{ fontSize: 10, color: "rgba(255,255,255,0.2)" }}>{game.broadcast}</div>
          </div>
        </div>
      </div>

      {/* Main: chart area + context sidebar + other games */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>

        {/* Left: probs + chart + source strip */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "12px 24px 10px", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 4 }}>
            <BigNum value={game.home.prob} color={game.home.color} pulse={pulse} size={80} />
            <span style={{ fontSize: 10, color: "rgba(255,255,255,0.1)", textTransform: "uppercase", letterSpacing: "0.1em", paddingBottom: 10 }}>win probability</span>
            <BigNum value={game.away.prob} color={game.away.color} pulse={pulse} size={80} />
          </div>
          <Bar hp={game.home.prob} hc={game.home.color} ac={game.away.color} h={5} />
          <div style={{ flex: 1, marginTop: 8, minHeight: 0 }}>
            <Chart sources={game.sources} width={620} height={260} showGrid />
          </div>
          {/* Source comparison strip below chart */}
          <div style={{ flexShrink: 0, marginTop: 6 }}>
            <SourceStrip sources={game.sources} homeColor={game.home.color} awayColor={game.away.color} />
          </div>
        </div>

        {/* Center-right: Pulse ring + breakdown + context + related */}
        <div style={{ width: 240, flexShrink: 0, borderLeft: "1px solid rgba(255,255,255,0.04)", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 2, background: "rgba(255,255,255,0.008)", overflow: "auto" }}>
          <Ring score={pulse} sz={100} />
          <div style={{ height: 4 }} />
          {/* Pulse component breakdown */}
          {game.pulseComponents && (
            <div style={{ marginBottom: 6, padding: "6px 4px", borderRadius: 5, background: "rgba(255,255,255,0.015)", border: "1px solid rgba(255,255,255,0.03)" }}>
              <PulseBreakdown components={game.pulseComponents} />
            </div>
          )}
          <Ctx label="Opened" value={`${pct(game.opening.home)} / ${pct(game.opening.away)}`} />
          <Ctx label="Line" value={`${lm.dir === "up" ? "↑" : "↓"}${lm.val}% ${lm.team}`} color={lm.dir === "up" ? "#22c55e" : "#ef4444"} />
          {game.divergence && <Ctx label="Markets" value={`${game.divergence.source} ${game.divergence.dir === "higher" ? "+" : "-"}${game.divergence.delta}%`} color={game.divergence.delta >= 8 ? "#a855f7" : "#3b82f6"} />}
          <Ctx label="Context" value={game.context} />

          <div style={{ marginTop: 6, padding: "6px 8px", borderRadius: 5, background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)" }}>
            <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>Championship Impact</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.4 }}>{game.implication}</div>
          </div>

          {game.related?.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Related Futures</div>
              {game.related.map((r, i) => <RelRow key={i} r={r} />)}
            </div>
          )}
        </div>

        {/* Far right: other live games (with sparklines) + trending futures (with bars) */}
        <div style={{ width: 200, flexShrink: 0, borderLeft: "1px solid rgba(255,255,255,0.04)", padding: "10px 8px", display: "flex", flexDirection: "column", gap: 0, background: "rgba(255,255,255,0.005)", overflow: "auto" }}>
          <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 4 }}>Other Games</div>
          {otherGames.map((g, i) => (
            <MiniGame key={i} g={g} active={false} onClick={() => onSelectGame(allGames.indexOf(g))} showSparkline />
          ))}

          <div style={{ height: 1, background: "rgba(255,255,255,0.04)", margin: "8px 0" }} />

          <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 4 }}>Trending Futures</div>
          {FUTURES.slice(0, 4).map((f, i) => (
            <div key={i} style={{ padding: "5px 8px", fontSize: 10, marginBottom: 4 }}>
              <div style={{ color: "rgba(255,255,255,0.4)", marginBottom: 3 }}>{f.emoji} {f.name}</div>
              {f.outcomes.slice(0, 3).map((o, j) => (
                <div key={j} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                  <span style={{ fontSize: 9, color: "rgba(255,255,255,0.4)", width: 60, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{o.name.split(" ").pop()}</span>
                  <div style={{ flex: 1, height: 4, background: "rgba(255,255,255,0.03)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${o.prob * 100}%`, background: rgba(o.color, 0.4), borderRadius: 2 }} />
                  </div>
                  <span style={{ fontSize: 9, color: "rgba(255,255,255,0.5)", fontVariantNumeric: "tabular-nums", width: 22, textAlign: "right" }}>{pct(o.prob)}%</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// AMBIENT FUTURES VIEW (unchanged across devices)
// ═══════════════════════════════════════════════════════════════════════
function AmbientView({ futures, index, device }) {
  const f = futures[index], ph = device === "phone", tv = device === "tv";
  const mx = Math.max(...f.outcomes.map((o) => o.prob)), ac = f.outcomes[0]?.color || "#666";
  return (
    <div key={index} style={{ width: "100%", height: "100%", background: `radial-gradient(ellipse at 50% 90%,${rgba(ac, 0.03)} 0%,#09090b 50%)`, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", padding: ph ? "40px 20px 32px" : "40px 56px", gap: ph ? 16 : 24, animation: "tvf 1.2s ease", position: "relative" }}>
      <div style={{ position: "absolute", top: 0, left: "20%", right: "20%", height: 1, background: `linear-gradient(90deg,transparent,${rgba(ac, 0.2)},transparent)` }} />
      <div style={{ fontSize: ph ? 10 : 13, color: "rgba(255,255,255,0.2)", letterSpacing: "0.2em", textTransform: "uppercase" }}>{f.cat}</div>
      <div style={{ fontSize: tv ? 38 : ph ? 22 : 30, fontWeight: 300, letterSpacing: "-0.02em", color: "rgba(255,255,255,0.8)", textAlign: "center" }}><span style={{ marginRight: 10 }}>{f.emoji}</span>{f.name}</div>
      <div style={{ width: "100%", maxWidth: tv ? 560 : ph ? 340 : 460, display: "flex", flexDirection: "column", gap: ph ? 8 : 12 }}>
        {f.outcomes.map((o, i) => (
          <div key={o.name} style={{ display: "flex", alignItems: "center", gap: ph ? 8 : 14, animation: `tvs 0.6s ease ${i * 0.08}s both` }}>
            <div style={{ width: ph ? 80 : 130, fontSize: ph ? 12 : 14, color: "rgba(255,255,255,0.6)", textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0 }}>{o.name}</div>
            <div style={{ flex: 1, height: ph ? 18 : 24, background: "rgba(255,255,255,0.03)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${(o.prob / mx) * 100}%`, background: `linear-gradient(90deg,${rgba(o.color, 0.5)},${rgba(o.color, 0.2)})`, borderRadius: 3, transition: "width 1.5s" }} />
            </div>
            <div style={{ width: 38, fontSize: ph ? 13 : 15, fontWeight: 600, color: "rgba(255,255,255,0.75)", fontVariantNumeric: "tabular-nums", textAlign: "right", flexShrink: 0 }}>{Math.round(o.prob * 100)}%</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>{futures.map((_, i) => <div key={i} style={{ width: 5, height: 5, borderRadius: "50%", background: i === index ? "rgba(255,255,255,0.6)" : "rgba(255,255,255,0.1)", transition: "background 0.6s" }} />)}</div>
      <div style={{ fontSize: ph ? 9 : 11, color: "rgba(255,255,255,0.1)" }}>Polymarket · Kalshi · Odds API</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════
const DEVS = {
  phone:  { w: 390, h: 780, label: "iPhone",        r: 44, notch: true },
  tablet: { w: 900, h: 600, label: "iPad",          r: 20, notch: false },
  tv:     { w: 1280, h: 720, label: "TV / Monitor", r: 6,  notch: false },
};

export default function TVMode() {
  const [dev, setDev] = useState("tv");
  const [mode, setMode] = useState("live");
  const [gi, setGi] = useState(0);
  const [fi, setFi] = useState(0);
  const [op, setOp] = useState(null);
  const [ww, setWw] = useState(1400);

  useEffect(() => { const u = () => setWw(window.innerWidth); u(); window.addEventListener("resize", u); return () => window.removeEventListener("resize", u); }, []);
  useEffect(() => { if (mode !== "ambient") return; const t = setInterval(() => setFi((i) => (i + 1) % FUTURES.length), 8000); return () => clearInterval(t); }, [mode]);
  useEffect(() => setOp(null), [gi]);

  const d = DEVS[dev], game = GAMES[gi], pulse = op ?? game.pulse, scale = Math.min(1, (ww - 24) / d.w);

  const Pill = ({ on, fn, children }) => <button className="tvb" onClick={fn} style={{ padding: "5px 12px", borderRadius: 6, border: "none", background: on ? "rgba(255,255,255,0.1)" : "transparent", color: on ? "#fff" : "rgba(255,255,255,0.35)", fontSize: 12, fontWeight: 500 }}>{children}</button>;
  const PG = ({ children }) => <div style={{ display: "flex", gap: 2, background: "rgba(255,255,255,0.04)", borderRadius: 8, padding: 2 }}>{children}</div>;

  return (
    <div style={{ background: "#050505", minHeight: "100vh", color: "#fff", fontFamily: '-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif' }}>
      <style>{CSS}</style>
      {/* Controls */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: 8, padding: "12px 14px 10px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.06em", color: "rgba(255,255,255,0.4)", marginRight: 4 }}>BAIN LUCK <span style={{ fontWeight: 300, opacity: 0.5 }}>TV</span></span>
        <PG>{Object.entries(DEVS).map(([k, v]) => <Pill key={k} on={dev === k} fn={() => setDev(k)}>{v.label}</Pill>)}</PG>
        <PG><Pill on={mode === "live"} fn={() => setMode("live")}>Live</Pill><Pill on={mode === "ambient"} fn={() => setMode("ambient")}>Ambient</Pill></PG>
        {mode === "live" && <>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button className="tvb" onClick={() => setGi((i) => (i - 1 + GAMES.length) % GAMES.length)} style={{ background: "none", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 5, color: "rgba(255,255,255,0.4)", padding: "2px 7px", fontSize: 12 }}>←</button>
            <span style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", minWidth: 60, textAlign: "center" }}>{game.home.abbr} v {game.away.abbr}</span>
            <button className="tvb" onClick={() => setGi((i) => (i + 1) % GAMES.length)} style={{ background: "none", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 5, color: "rgba(255,255,255,0.4)", padding: "2px 7px", fontSize: 12 }}>→</button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ fontSize: 9, color: "rgba(255,255,255,0.15)" }}>Pulse</span>
            <input type="range" min="5" max="100" value={pulse} onChange={(e) => setOp(Number(e.target.value))} style={{ width: 60, accentColor: "#ef4444" }} />
            <span style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", fontVariantNumeric: "tabular-nums", width: 18 }}>{pulse}</span>
          </div>
        </>}
      </div>

      {/* Frame */}
      <div style={{ display: "flex", justifyContent: "center", padding: "20px 12px 8px" }}>
        <div style={{ width: d.w, height: d.h, borderRadius: d.r, border: `1px solid rgba(255,255,255,${dev === "phone" ? "0.1" : "0.06"})`, overflow: "hidden", transform: `scale(${scale})`, transformOrigin: "top center", boxShadow: `0 0 0 1px rgba(255,255,255,0.02),0 12px 40px rgba(0,0,0,0.6)`, position: "relative", flexShrink: 0 }}>
          {d.notch && <div style={{ position: "absolute", top: 10, left: "50%", transform: "translateX(-50%)", width: 90, height: 24, borderRadius: 14, background: "#000", zIndex: 10 }} />}
          {mode === "live" ? (
            dev === "phone" ? <PhoneLive game={game} pulse={pulse} /> :
            dev === "tablet" ? <TabletLive game={game} pulse={pulse} allGames={GAMES} activeIdx={gi} onSelectGame={setGi} /> :
            <TVLive game={game} pulse={pulse} allGames={GAMES} activeIdx={gi} onSelectGame={setGi} />
          ) : (
            <AmbientView futures={FUTURES} index={fi} device={dev} />
          )}
        </div>
      </div>

      <div style={{ maxWidth: 700, margin: "0 auto", padding: "2px 20px 28px", fontSize: 10, color: "rgba(255,255,255,0.1)", textAlign: "center", lineHeight: 1.7 }}>
        <span style={{ color: "rgba(255,255,255,0.18)" }}>v4 Cascade:</span> Phone = old iPad (Pulse ring, chart w/ gridlines, context sidebar, related futures). iPad = old TV (3-column: chart + context + other games). TV = MAXIMAL (score-by-period, Pulse breakdown, source comparison strip, sparklines, expanded futures).
      </div>
    </div>
  );
}
