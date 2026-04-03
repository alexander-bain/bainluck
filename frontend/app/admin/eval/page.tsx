"use client";

import { useState, useEffect, useCallback } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────────

interface GridSource {
  source: string;
  probability: number;
}

interface GridCell {
  merged_probability: number;
  sources: GridSource[];
}

interface GridTeam {
  name: string;
  short_name: string;
  logo_url: string | null;
  cells: Record<string, GridCell>;
}

interface GridData {
  league: string;
  name: string;
  columns: { key: string; label: string }[];
  teams: GridTeam[];
  sources_available: string[];
}

interface FuturesMarket {
  id: number;
  name: string;
  llm_sport_category: string | null;
  source: string;
  resolution_date: string | null;
  market_tags: string[];
  top_outcomes: {
    id: number;
    name: string;
    probability: number | null;
    movement: number | null;
  }[];
  outcome_count: number;
}

interface EvalDecision {
  market_id?: number;
  market_name: string;
  decision: "correct" | "wrong" | "interesting" | "skip" | "never";
  context: string;
  timestamp: string;
}

// ─── Config ───────────────────────────────────────────────────────────────────

const GRID_LEAGUES = [
  { slug: "nba", label: "NBA", emoji: "🏀" },
  { slug: "nhl", label: "NHL", emoji: "🏒" },
  { slug: "mlb", label: "MLB", emoji: "⚾" },
  { slug: "golf", label: "Golf", emoji: "⛳" },
];

const NON_SPORTS_CATEGORIES = [
  "politics",
  "entertainment",
  "economy",
  "science",
  "technology",
  "weather",
  "culture",
  "other",
];

// ─── Persistence ──────────────────────────────────────────────────────────────

function getStoredDecisions(): EvalDecision[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem("bainluck_eval_decisions") || "[]");
  } catch {
    return [];
  }
}

function storeDecision(decision: EvalDecision) {
  const existing = getStoredDecisions();
  existing.push(decision);
  localStorage.setItem("bainluck_eval_decisions", JSON.stringify(existing));
}

function getSeenIds(): Set<string> {
  const decisions = getStoredDecisions();
  return new Set(decisions.map((d) => d.market_name));
}

// ─── Components ───────────────────────────────────────────────────────────────

function TabBar({
  tab,
  onTab,
  gridCount,
  futuresCount,
}: {
  tab: "grid" | "futures" | "history";
  onTab: (t: "grid" | "futures" | "history") => void;
  gridCount: number;
  futuresCount: number;
}) {
  const tabs = [
    { key: "grid" as const, label: "Grid Matching", count: gridCount },
    { key: "futures" as const, label: "Interesting?", count: futuresCount },
    { key: "history" as const, label: "History", count: null },
  ];
  return (
    <div style={{ display: "flex", gap: 6, marginBottom: 20, overflowX: "auto" }}>
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onTab(t.key)}
          style={{
            padding: "10px 16px",
            borderRadius: 10,
            border: tab === t.key ? "2px solid #3b82f6" : "2px solid #333",
            background: tab === t.key ? "#1e3a5f" : "#1a1a2e",
            color: tab === t.key ? "#93c5fd" : "#888",
            fontWeight: 600,
            fontSize: 14,
            cursor: "pointer",
            whiteSpace: "nowrap",
            minHeight: 44,
          }}
        >
          {t.label}
          {t.count !== null && (
            <span
              style={{
                marginLeft: 6,
                padding: "1px 6px",
                borderRadius: 8,
                fontSize: 11,
                background: tab === t.key ? "#3b82f6" : "#333",
                color: "#fff",
              }}
            >
              {t.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

function GridMatchCard({
  team,
  column,
  cell,
  league,
  gridName,
  onDecision,
}: {
  team: string;
  column: string;
  cell: GridCell;
  league: string;
  gridName: string;
  onDecision: (decision: "correct" | "wrong" | "skip") => void;
}) {
  const [acting, setActing] = useState(false);

  const handle = async (d: "correct" | "wrong" | "skip") => {
    setActing(true);
    onDecision(d);
    setTimeout(() => setActing(false), 300);
  };

  // Calculate source disagreement
  const probs = cell.sources.map((s) => s.probability);
  const spread = Math.max(...probs) - Math.min(...probs);
  const spreadPct = (spread * 100).toFixed(0);
  const highSource = cell.sources.reduce((a, b) => (a.probability > b.probability ? a : b));
  const lowSource = cell.sources.reduce((a, b) => (a.probability < b.probability ? a : b));
  const columnLabel = column.replace(/_/g, " ");

  return (
    <div
      style={{
        background: "#161b22",
        borderRadius: 14,
        padding: 20,
        marginBottom: 12,
        border: spread > 0.3 ? "1px solid #dc2626" : spread > 0.15 ? "1px solid #d97706" : "1px solid #30363d",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "#e2e8f0", marginBottom: 4 }}>
              {team}
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span
                style={{
                  padding: "3px 10px",
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  background: "#1e3a5f",
                  color: "#93c5fd",
                }}
              >
                {columnLabel.toUpperCase()}
              </span>
              <span style={{ fontSize: 12, color: "#64748b" }}>
                {gridName || league.toUpperCase()}
              </span>
            </div>
          </div>
          {/* Disagreement badge */}
          {spread > 0.15 && (
            <span
              style={{
                padding: "4px 10px",
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 700,
                background: spread > 0.3 ? "#7f1d1d" : "#78350f",
                color: spread > 0.3 ? "#fca5a5" : "#fcd34d",
                whiteSpace: "nowrap",
              }}
            >
              {spreadPct}pp gap
            </span>
          )}
        </div>
      </div>

      {/* Source comparison — visual bar */}
      <div style={{ marginBottom: 16 }}>
        {cell.sources.map((s) => (
          <div
            key={s.source}
            style={{
              marginBottom: 8,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
              <span style={{ fontSize: 13, color: "#8b949e", textTransform: "capitalize" }}>
                {s.source}
              </span>
              <span style={{ fontSize: 15, fontWeight: 600, color: "#e2e8f0" }}>
                {(s.probability * 100).toFixed(1)}%
              </span>
            </div>
            {/* Probability bar */}
            <div style={{ height: 6, borderRadius: 3, background: "#21262d", overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  width: `${Math.min(s.probability * 100, 100)}%`,
                  borderRadius: 3,
                  background: s === highSource && spread > 0.15 ? "#3b82f6" : s === lowSource && spread > 0.15 ? "#ef4444" : "#3b82f6",
                }}
              />
            </div>
          </div>
        ))}
        {/* Merged result */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            padding: "8px 0 0",
            borderTop: "1px solid #21262d",
            marginTop: 4,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 700, color: "#93c5fd" }}>Merged</span>
          <span style={{ fontSize: 17, fontWeight: 700, color: "#93c5fd" }}>
            {(cell.merged_probability * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Eval question — reworded to be actionable */}
      <div style={{
        fontSize: 14,
        color: "#8b949e",
        marginBottom: 12,
        padding: "10px 12px",
        background: "#0d1117",
        borderRadius: 8,
        lineHeight: 1.5,
      }}>
        {spread > 0.3 ? (
          <>
            <span style={{ color: "#fca5a5", fontWeight: 600 }}>Big disagreement: </span>
            <span style={{ textTransform: "capitalize" }}>{highSource.source}</span> says{" "}
            <strong style={{ color: "#e2e8f0" }}>{(highSource.probability * 100).toFixed(0)}%</strong> but{" "}
            <span style={{ textTransform: "capitalize" }}>{lowSource.source}</span> says{" "}
            <strong style={{ color: "#e2e8f0" }}>{(lowSource.probability * 100).toFixed(0)}%</strong>.
            {" "}Are both about <strong style={{ color: "#e2e8f0" }}>{team}</strong> to <strong style={{ color: "#93c5fd" }}>{columnLabel}</strong> at the same event?
          </>
        ) : spread > 0.15 ? (
          <>
            <span style={{ color: "#fcd34d", fontWeight: 600 }}>Notable gap: </span>
            <span style={{ textTransform: "capitalize" }}>{highSource.source}</span>{" "}
            <strong style={{ color: "#e2e8f0" }}>{(highSource.probability * 100).toFixed(0)}%</strong> vs{" "}
            <span style={{ textTransform: "capitalize" }}>{lowSource.source}</span>{" "}
            <strong style={{ color: "#e2e8f0" }}>{(lowSource.probability * 100).toFixed(0)}%</strong>.
            {" "}Should these be merged for <strong style={{ color: "#e2e8f0" }}>{team}</strong>?
          </>
        ) : (
          <>
            Sources agree within {spreadPct}pp for{" "}
            <strong style={{ color: "#e2e8f0" }}>{team}</strong> to{" "}
            <strong style={{ color: "#93c5fd" }}>{columnLabel}</strong>.
            {" "}Look right?
          </>
        )}
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 10 }}>
        <button
          onClick={() => handle("correct")}
          disabled={acting}
          style={{
            flex: 1,
            padding: "14px 0",
            borderRadius: 10,
            border: "none",
            background: "#166534",
            color: "#4ade80",
            fontSize: 16,
            fontWeight: 700,
            cursor: "pointer",
            minHeight: 50,
            opacity: acting ? 0.5 : 1,
          }}
        >
          Merge OK
        </button>
        <button
          onClick={() => handle("wrong")}
          disabled={acting}
          style={{
            flex: 1,
            padding: "14px 0",
            borderRadius: 10,
            border: "none",
            background: "#7f1d1d",
            color: "#fca5a5",
            fontSize: 16,
            fontWeight: 700,
            cursor: "pointer",
            minHeight: 50,
            opacity: acting ? 0.5 : 1,
          }}
        >
          Bad Match
        </button>
        <button
          onClick={() => handle("skip")}
          disabled={acting}
          style={{
            width: 50,
            padding: "14px 0",
            borderRadius: 10,
            border: "1px solid #333",
            background: "transparent",
            color: "#64748b",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            minHeight: 50,
            opacity: acting ? 0.5 : 1,
          }}
        >
          →
        </button>
      </div>
    </div>
  );
}

function FuturesEvalCard({
  market,
  onDecision,
}: {
  market: FuturesMarket;
  onDecision: (decision: "interesting" | "skip" | "never") => void;
}) {
  const [acting, setActing] = useState(false);

  const handle = (d: "interesting" | "skip" | "never") => {
    setActing(true);
    onDecision(d);
    setTimeout(() => setActing(false), 300);
  };

  const resDate = market.resolution_date
    ? new Date(market.resolution_date).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  return (
    <div
      style={{
        background: "#161b22",
        borderRadius: 14,
        padding: 20,
        marginBottom: 12,
        border: "1px solid #30363d",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 17, fontWeight: 700, color: "#e2e8f0", marginBottom: 6, lineHeight: 1.3 }}>
          {market.name}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span
            style={{
              padding: "3px 8px",
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
              background: "#2d2d4e",
              color: "#c084fc",
              textTransform: "capitalize",
            }}
          >
            {market.llm_sport_category || "uncategorized"}
          </span>
          <span
            style={{
              padding: "3px 8px",
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
              background: "#1a1a2e",
              color: "#64748b",
              textTransform: "capitalize",
            }}
          >
            {market.source}
          </span>
          {resDate && (
            <span style={{ fontSize: 11, color: "#64748b" }}>Resolves {resDate}</span>
          )}
        </div>
      </div>

      {/* Top outcomes */}
      {market.top_outcomes.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          {market.top_outcomes.map((o) => (
            <div
              key={o.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "6px 0",
                borderBottom: "1px solid #21262d",
              }}
            >
              <span style={{ fontSize: 14, color: "#e2e8f0", flex: 1 }}>{o.name}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {o.probability !== null && (
                  <span style={{ fontSize: 15, fontWeight: 600, color: "#e2e8f0" }}>
                    {(o.probability * 100).toFixed(0)}%
                  </span>
                )}
                {o.movement !== null && Math.abs(o.movement) >= 0.01 && (
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: o.movement > 0 ? "#4ade80" : "#f87171",
                    }}
                  >
                    {o.movement > 0 ? "+" : ""}
                    {(o.movement * 100).toFixed(1)}
                  </span>
                )}
              </div>
            </div>
          ))}
          {market.outcome_count > 3 && (
            <div style={{ fontSize: 11, color: "#64748b", padding: "4px 0" }}>
              +{market.outcome_count - 3} more outcomes
            </div>
          )}
        </div>
      )}

      {/* Eval question */}
      <div style={{ fontSize: 14, color: "#8b949e", marginBottom: 12, textAlign: "center" }}>
        Would a BainLuck user find this interesting?
      </div>

      {/* Big action buttons */}
      <div style={{ display: "flex", gap: 10 }}>
        <button
          onClick={() => handle("interesting")}
          disabled={acting}
          style={{
            flex: 1,
            padding: "14px 0",
            borderRadius: 10,
            border: "none",
            background: "#1e3a5f",
            color: "#60a5fa",
            fontSize: 16,
            fontWeight: 700,
            cursor: "pointer",
            minHeight: 50,
            opacity: acting ? 0.5 : 1,
          }}
        >
          🔥 Feature
        </button>
        <button
          onClick={() => handle("skip")}
          disabled={acting}
          style={{
            flex: 1,
            padding: "14px 0",
            borderRadius: 10,
            border: "1px solid #333",
            background: "transparent",
            color: "#94a3b8",
            fontSize: 16,
            fontWeight: 700,
            cursor: "pointer",
            minHeight: 50,
            opacity: acting ? 0.5 : 1,
          }}
        >
          😐 Skip
        </button>
        <button
          onClick={() => handle("never")}
          disabled={acting}
          style={{
            width: 60,
            padding: "14px 0",
            borderRadius: 10,
            border: "1px solid #7f1d1d",
            background: "transparent",
            color: "#f87171",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            minHeight: 50,
            opacity: acting ? 0.5 : 1,
          }}
        >
          🚫
        </button>
      </div>
    </div>
  );
}

function HistoryView({ decisions }: { decisions: EvalDecision[] }) {
  const sorted = [...decisions].reverse();
  const stats = {
    correct: decisions.filter((d) => d.decision === "correct").length,
    wrong: decisions.filter((d) => d.decision === "wrong").length,
    interesting: decisions.filter((d) => d.decision === "interesting").length,
    skip: decisions.filter((d) => d.decision === "skip").length,
    never: decisions.filter((d) => d.decision === "never").length,
  };

  return (
    <div>
      {/* Stats */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Correct", value: stats.correct, color: "#4ade80" },
          { label: "Wrong", value: stats.wrong, color: "#f87171" },
          { label: "Feature", value: stats.interesting, color: "#60a5fa" },
          { label: "Skip", value: stats.skip, color: "#94a3b8" },
          { label: "Never", value: stats.never, color: "#f87171" },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              background: "#1a1a2e",
              borderRadius: 8,
              padding: "10px 14px",
              textAlign: "center",
              flex: 1,
              minWidth: 60,
            }}
          >
            <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 11, color: "#64748b" }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Export button */}
      <button
        onClick={() => {
          const blob = new Blob([JSON.stringify(sorted, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `bainluck-eval-${new Date().toISOString().slice(0, 10)}.json`;
          a.click();
          URL.revokeObjectURL(url);
        }}
        style={{
          padding: "10px 20px",
          borderRadius: 8,
          border: "1px solid #333",
          background: "#1a1a2e",
          color: "#93c5fd",
          fontSize: 13,
          fontWeight: 600,
          cursor: "pointer",
          marginBottom: 16,
          width: "100%",
          minHeight: 44,
        }}
      >
        Export Decisions as JSON ({sorted.length} total)
      </button>

      {/* Recent decisions */}
      {sorted.slice(0, 50).map((d, i) => (
        <div
          key={i}
          style={{
            padding: "10px 14px",
            background: "#161b22",
            borderRadius: 8,
            marginBottom: 6,
            borderLeft: `3px solid ${
              d.decision === "correct"
                ? "#4ade80"
                : d.decision === "wrong"
                  ? "#f87171"
                  : d.decision === "interesting"
                    ? "#60a5fa"
                    : d.decision === "never"
                      ? "#f87171"
                      : "#475569"
            }`,
          }}
        >
          <div style={{ fontSize: 13, color: "#e2e8f0", marginBottom: 2 }}>
            {d.market_name}
          </div>
          <div style={{ display: "flex", gap: 8, fontSize: 11, color: "#64748b" }}>
            <span
              style={{
                fontWeight: 600,
                color:
                  d.decision === "correct"
                    ? "#4ade80"
                    : d.decision === "interesting"
                      ? "#60a5fa"
                      : d.decision === "wrong" || d.decision === "never"
                        ? "#f87171"
                        : "#94a3b8",
              }}
            >
              {d.decision}
            </span>
            <span>{d.context}</span>
            <span>{new Date(d.timestamp).toLocaleDateString()}</span>
          </div>
        </div>
      ))}

      {sorted.length === 0 && (
        <div style={{ textAlign: "center", padding: 40, color: "#64748b" }}>
          No decisions yet. Start evaluating!
        </div>
      )}
    </div>
  );
}

// ─── Grid Matching Tab ────────────────────────────────────────────────────────

function GridMatchingTab() {
  const [league, setLeague] = useState("nba");
  const [gridData, setGridData] = useState<GridData | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [candidates, setCandidates] = useState<
    { team: string; column: string; cell: GridCell; gridName: string }[]
  >([]);

  useEffect(() => {
    setLoading(true);
    setCurrentIndex(0);
    fetch(`${API_URL}/api/playoffs/${league}`)
      .then((r) => r.json())
      .then((data: GridData) => {
        setGridData(data);

        // Build eval candidates: team×column combos with multiple sources (disagreement opportunity)
        const seen = getSeenIds();
        const items: { team: string; column: string; cell: GridCell; gridName: string }[] = [];
        for (const team of data.teams || []) {
          for (const col of data.columns || []) {
            const cell = team.cells?.[col.key];
            if (!cell || !cell.sources || cell.sources.length < 2) continue;
            const key = `${league}:${team.name}:${col.key}`;
            if (seen.has(key)) continue;
            // Prioritize disagreements
            const probs = cell.sources.map((s) => s.probability);
            const spread = Math.max(...probs) - Math.min(...probs);
            items.push({ team: team.name, column: col.key, cell, gridName: data.name || league.toUpperCase() });
            // Attach spread for sorting
            (items[items.length - 1] as Record<string, unknown>)._spread = spread;
          }
        }
        // Sort by spread descending (biggest disagreements first)
        items.sort((a, b) => {
          const as = (a as Record<string, unknown>)._spread as number;
          const bs = (b as Record<string, unknown>)._spread as number;
          return bs - as;
        });
        setCandidates(items);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [league]);

  const handleDecision = (decision: "correct" | "wrong" | "skip") => {
    const item = candidates[currentIndex];
    if (!item) return;
    storeDecision({
      market_name: `${league}:${item.team}:${item.column}`,
      decision,
      context: `${league} grid, ${item.cell.sources.length} sources, merged=${(item.cell.merged_probability * 100).toFixed(1)}%`,
      timestamp: new Date().toISOString(),
    });
    setCurrentIndex((i) => i + 1);
  };

  const current = candidates[currentIndex];
  const remaining = candidates.length - currentIndex;

  return (
    <div>
      {/* League selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, overflowX: "auto" }}>
        {GRID_LEAGUES.map((l) => (
          <button
            key={l.slug}
            onClick={() => setLeague(l.slug)}
            style={{
              padding: "10px 14px",
              borderRadius: 10,
              border: league === l.slug ? "2px solid #3b82f6" : "2px solid #333",
              background: league === l.slug ? "#1e3a5f" : "#1a1a2e",
              color: league === l.slug ? "#93c5fd" : "#888",
              fontWeight: 600,
              fontSize: 14,
              cursor: "pointer",
              minHeight: 44,
            }}
          >
            {l.emoji} {l.label}
          </button>
        ))}
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: 40, color: "#64748b" }}>
          Loading {league.toUpperCase()} grid...
        </div>
      )}

      {!loading && current && (
        <>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8, textAlign: "center" }}>
            {remaining} remaining · {candidates.length - remaining} reviewed
          </div>
          <GridMatchCard
            team={current.team}
            column={current.column}
            cell={current.cell}
            league={league}
            gridName={current.gridName}
            onDecision={handleDecision}
          />
        </>
      )}

      {!loading && !current && candidates.length > 0 && (
        <div
          style={{
            textAlign: "center",
            padding: 40,
            background: "#161b22",
            borderRadius: 14,
            color: "#4ade80",
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 8 }}>All reviewed!</div>
          <div style={{ color: "#64748b", fontSize: 14 }}>
            {candidates.length} {league.toUpperCase()} grid matches evaluated
          </div>
        </div>
      )}

      {!loading && candidates.length === 0 && (
        <div
          style={{
            textAlign: "center",
            padding: 40,
            background: "#161b22",
            borderRadius: 14,
            color: "#64748b",
          }}
        >
          No multi-source matches to evaluate for {league.toUpperCase()}.
          <br />
          Try another league.
        </div>
      )}
    </div>
  );
}

// ─── Futures Interesting Tab ──────────────────────────────────────────────────

function FuturesInterestingTab() {
  const [markets, setMarkets] = useState<FuturesMarket[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [page, setPage] = useState(1);

  const loadMarkets = useCallback(
    async (pageNum: number) => {
      setLoading(true);
      try {
        // Fetch non-sports futures: politics, entertainment, economy, etc.
        const categories = NON_SPORTS_CATEGORIES;
        const allMarkets: FuturesMarket[] = [];
        const seen = getSeenIds();

        for (const cat of categories) {
          try {
            const res = await fetch(
              `${API_URL}/api/futures/faceted?category=${cat}&page=${pageNum}&per_page=20`
            );
            if (!res.ok) continue;
            const data = await res.json();
            const unseen = (data.markets || []).filter(
              (m: FuturesMarket) => !seen.has(`futures:${m.id}`)
            );
            allMarkets.push(...unseen);
          } catch {
            // Skip categories that fail
          }
        }

        // Also try markets with no sport category (often the most interesting)
        try {
          const res = await fetch(
            `${API_URL}/api/futures/faceted?category=other&page=${pageNum}&per_page=20`
          );
          if (res.ok) {
            const data = await res.json();
            const unseen = (data.markets || []).filter(
              (m: FuturesMarket) => !seen.has(`futures:${m.id}`)
            );
            allMarkets.push(...unseen);
          }
        } catch {
          // OK
        }

        // Dedupe by market ID
        const deduped = Array.from(
          new Map(allMarkets.map((m) => [m.id, m])).values()
        );
        setMarkets(deduped);
        setCurrentIndex(0);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadMarkets(page);
  }, [page, loadMarkets]);

  const handleDecision = (decision: "interesting" | "skip" | "never") => {
    const market = markets[currentIndex];
    if (!market) return;
    storeDecision({
      market_id: market.id,
      market_name: `futures:${market.id}`,
      decision,
      context: `${market.source}: "${market.name}" (${market.llm_sport_category || "uncategorized"})`,
      timestamp: new Date().toISOString(),
    });
    setCurrentIndex((i) => i + 1);
  };

  const current = markets[currentIndex];
  const remaining = markets.length - currentIndex;

  return (
    <div>
      {loading && (
        <div style={{ textAlign: "center", padding: 40, color: "#64748b" }}>
          Loading non-sports futures...
        </div>
      )}

      {!loading && current && (
        <>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8, textAlign: "center" }}>
            {remaining} remaining · Page {page}
          </div>
          <FuturesEvalCard market={current} onDecision={handleDecision} />
        </>
      )}

      {!loading && !current && markets.length > 0 && (
        <div
          style={{
            textAlign: "center",
            padding: 40,
            background: "#161b22",
            borderRadius: 14,
          }}
        >
          <div style={{ fontSize: 24, color: "#4ade80", marginBottom: 8 }}>
            Page {page} done!
          </div>
          <button
            onClick={() => setPage((p) => p + 1)}
            style={{
              padding: "12px 24px",
              borderRadius: 10,
              border: "none",
              background: "#3b82f6",
              color: "#fff",
              fontSize: 15,
              fontWeight: 600,
              cursor: "pointer",
              minHeight: 44,
            }}
          >
            Load more futures →
          </button>
        </div>
      )}

      {!loading && markets.length === 0 && (
        <div
          style={{
            textAlign: "center",
            padding: 40,
            background: "#161b22",
            borderRadius: 14,
            color: "#64748b",
          }}
        >
          No non-sports futures found. Check back later.
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function EvalPage() {
  usePageTracking({ pageType: "admin_eval", pageTitle: "Admin: Eval" });
  useScrollDepth({ pageType: "admin_eval" });
  useEngagementTime({ pageType: "admin_eval" });

  const [tab, setTab] = useState<"grid" | "futures" | "history">("grid");
  const [decisions, setDecisions] = useState<EvalDecision[]>([]);

  // Refresh decision count periodically
  useEffect(() => {
    const update = () => setDecisions(getStoredDecisions());
    update();
    const interval = setInterval(update, 5000);
    return () => clearInterval(interval);
  }, []);

  const gridCount = decisions.filter((d) => d.market_name.includes(":") && !d.market_name.startsWith("futures:")).length;
  const futuresCount = decisions.filter((d) => d.market_name.startsWith("futures:")).length;

  return (
    <div
      style={{
        maxWidth: 500,
        margin: "0 auto",
        padding: "24px 16px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        color: "#e2e8f0",
        minHeight: "100vh",
        background: "#09090b",
      }}
    >
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
          Bain-in-the-Loop
        </h1>
        <p style={{ color: "#64748b", fontSize: 13, margin: "4px 0 0" }}>
          Evaluate matching quality &amp; surface interesting markets
        </p>
      </div>

      <TabBar tab={tab} onTab={setTab} gridCount={gridCount} futuresCount={futuresCount} />

      {tab === "grid" && <GridMatchingTab />}
      {tab === "futures" && <FuturesInterestingTab />}
      {tab === "history" && <HistoryView decisions={decisions} />}
    </div>
  );
}
