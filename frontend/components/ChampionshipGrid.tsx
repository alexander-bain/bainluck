"use client";

/**
 * ChampionshipGrid — Unified scrollable championship probability table.
 *
 * One layout for all screen sizes: a horizontally-scrollable table with a
 * sticky team column. Tapping a row expands an inline source-breakdown row
 * showing per-source probabilities for every stage side-by-side.
 *
 * No tab-switching required — all columns visible at once.
 */

import { useState, useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { ChampionshipGridData, PlayoffTeam, LeagueTab, StageSource } from "@/lib/playoff-types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(p: number): string {
  return `${Math.round(p * 100)}%`;
}

function hexToRgb(hex: string): string {
  const h = (hex || "#888888").replace("#", "");
  const r = parseInt(h.substring(0, 2), 16) || 128;
  const g = parseInt(h.substring(2, 4), 16) || 128;
  const b = parseInt(h.substring(4, 6), 16) || 128;
  return `${r}, ${g}, ${b}`;
}

function probColor(p: number): string {
  if (p >= 0.55) return "#22C55E";
  if (p >= 0.25) return "var(--text-primary)";
  if (p <= 0.08) return "#EF4444";
  return "var(--text-secondary)";
}

/** All unique source names across the entire dataset */
function allSourceNames(teams: PlayoffTeam[]): string[] {
  const set = new Set<string>();
  teams.forEach((t) => t.stages.forEach((s) => s.sources.forEach((src) => set.add(src.source))));
  return Array.from(set);
}

// ---------------------------------------------------------------------------
// Movers Strip
// ---------------------------------------------------------------------------

function computeMovers(teams: PlayoffTeam[], stageKey: string) {
  return teams
    .map((t) => {
      const s = t.stages.find((s) => s.key === stageKey);
      return { short: t.short, color: t.color, change: s?.change24h ?? 0 };
    })
    .filter((m) => Math.abs(m.change) >= 0.005)
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
    .slice(0, 6);
}

function MoversStrip({ teams, stageKey }: { teams: PlayoffTeam[]; stageKey: string }) {
  const movers = computeMovers(teams, stageKey);
  if (!movers.length) return null;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
      {movers.map((m) => {
        const isUp = m.change > 0;
        const pct = Math.abs(m.change * 100);
        const str = pct >= 1 ? Math.round(pct) : pct.toFixed(1);
        return (
          <div
            key={m.short}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium whitespace-nowrap flex-shrink-0"
            style={{
              backgroundColor: isUp ? "rgba(34,197,94,0.10)" : "rgba(239,68,68,0.10)",
              borderColor: isUp ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)",
              color: isUp ? "#22C55E" : "#EF4444",
            }}
          >
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: m.color }} />
            <span>{m.short}</span>
            <span className="font-mono text-[10px]">
              {isUp ? "+" : "-"}{str}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// League Tabs
// ---------------------------------------------------------------------------

function LeagueTabs({
  tabs,
  activeSlug,
  onSelect,
}: {
  tabs: LeagueTab[];
  activeSlug: string;
  onSelect: (slug: string) => void;
}) {
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
      {tabs.map((tab) => {
        const active = tab.slug === activeSlug;
        return (
          <button
            key={tab.slug}
            onClick={() => onSelect(tab.slug)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap flex-shrink-0 transition-all duration-150"
            style={{
              backgroundColor: active ? "var(--surface-elevated)" : "transparent",
              color: active ? "var(--text-primary)" : "var(--text-muted)",
              border: active ? "1px solid var(--border-color)" : "1px solid transparent",
            }}
          >
            <span>{tab.emoji}</span>
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Source dots — compact visual showing per-source spread for one stage cell
// ---------------------------------------------------------------------------

function SourceDots({
  sources,
  stageKey,
  teamColor,
}: {
  sources: StageSource[];
  stageKey: string;
  teamColor: string;
}) {
  if (!sources.length) {
    return (
      <span className="text-[9px] font-mono" style={{ color: "var(--text-muted)" }}>
        —
      </span>
    );
  }

  const min = Math.min(...sources.map((s) => s.probability));
  const max = Math.max(...sources.map((s) => s.probability));
  const rgb = hexToRgb(teamColor);

  return (
    <div className="flex flex-col gap-0.5 w-full">
      {sources.map((src) => (
        <div key={src.source} className="flex items-center gap-1.5 w-full">
          <span
            className="text-[9px] font-mono whitespace-nowrap flex-shrink-0 w-14 text-right"
            style={{ color: "var(--text-muted)" }}
          >
            {src.source.length > 8 ? src.source.slice(0, 8) : src.source}
          </span>
          {/* Mini bar */}
          <div
            className="flex-1 h-1 rounded-full overflow-hidden"
            style={{ backgroundColor: `rgba(${rgb}, 0.12)` }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.round(src.probability * 100)}%`,
                backgroundColor: `rgba(${rgb}, 0.7)`,
              }}
            />
          </div>
          <span
            className="text-[9px] font-mono flex-shrink-0"
            style={{ color: "var(--text-secondary)" }}
          >
            {fmt(src.probability)}
          </span>
        </div>
      ))}
      {/* Range label if spread > 2pp */}
      {max - min >= 0.02 && (
        <div className="flex justify-between mt-0.5">
          <span className="text-[8px] font-mono" style={{ color: "var(--text-muted)" }}>
            {fmt(min)}
          </span>
          <span className="text-[8px] font-mono" style={{ color: "var(--text-muted)" }}>
            {fmt(max)}
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table cell — one stage for one team
// ---------------------------------------------------------------------------

interface StageCellProps {
  team: PlayoffTeam;
  stageKey: string;
  sortKey: string;
  showSources: boolean;
}

function StageCell({ team, stageKey, sortKey, showSources }: StageCellProps) {
  const stage = team.stages.find((s) => s.key === stageKey);
  const prob = stage?.probability ?? 0;
  const change = stage?.change24h ?? 0;
  const isSort = stageKey === sortKey;

  const pct = Math.abs(change * 100);
  const changeFmt = pct >= 0.1 ? (pct >= 1 ? Math.round(pct) : pct.toFixed(1)) : null;

  return (
    <td
      className="px-2.5 py-2.5 text-right align-top"
      style={{
        minWidth: showSources ? 110 : 68,
        backgroundColor: isSort ? "rgba(255,255,255,0.025)" : undefined,
      }}
    >
      {showSources ? (
        <div className="flex flex-col items-end gap-1.5">
          {/* Consensus number */}
          <div className="flex items-baseline gap-1 justify-end">
            <span
              className="font-mono font-bold text-sm"
              style={{ color: isSort ? probColor(prob) : "var(--text-secondary)" }}
            >
              {fmt(prob)}
            </span>
            {changeFmt && (
              <span
                className="font-mono text-[9px]"
                style={{ color: change > 0 ? "#22C55E" : "#EF4444" }}
              >
                {change > 0 ? "▲" : "▼"}{changeFmt}%
              </span>
            )}
          </div>
          {/* Per-source breakdown */}
          <div className="w-full">
            <SourceDots
              sources={stage?.sources ?? []}
              stageKey={stageKey}
              teamColor={team.color}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-end gap-0.5">
          <span
            className="font-mono font-bold text-sm"
            style={{ color: isSort ? probColor(prob) : "var(--text-secondary)" }}
          >
            {fmt(prob)}
          </span>
          {changeFmt && (
            <span
              className="font-mono text-[9px]"
              style={{ color: change > 0 ? "#22C55E" : "#EF4444" }}
            >
              {change > 0 ? "▲" : "▼"}{changeFmt}%
            </span>
          )}
        </div>
      )}
    </td>
  );
}

// ---------------------------------------------------------------------------
// Main table
// ---------------------------------------------------------------------------

interface GridTableProps {
  teams: PlayoffTeam[];
  stageKeys: string[];
  stageLabels: string[];
  sortKey: string;
  onSortKey: (k: string) => void;
  showSources: boolean;
}

function GridTable({ teams, stageKeys, stageLabels, sortKey, onSortKey, showSources }: GridTableProps) {
  return (
    <div
      className="overflow-x-auto rounded-xl border"
      style={{ borderColor: "var(--border-color)" }}
    >
      <table className="w-full text-sm border-collapse">
        {/* Header */}
        <thead>
          <tr style={{ backgroundColor: "var(--surface-elevated)" }}>
            {/* Sticky team col */}
            <th
              className="sticky left-0 z-20 px-3 py-2.5 text-left font-medium text-[10px] uppercase tracking-wider whitespace-nowrap border-b border-r"
              style={{
                backgroundColor: "var(--surface-elevated)",
                color: "var(--text-muted)",
                borderColor: "var(--border-color)",
                minWidth: 160,
              }}
            >
              Team
            </th>
            {stageLabels.map((label, i) => {
              const key = stageKeys[i];
              const isSort = key === sortKey;
              return (
                <th
                  key={key}
                  onClick={() => onSortKey(key)}
                  className="px-2.5 py-2.5 text-right font-medium text-[10px] uppercase tracking-wider whitespace-nowrap border-b cursor-pointer select-none transition-colors duration-100 hover:bg-white/5"
                  style={{
                    color: isSort ? "#10B981" : "var(--text-muted)",
                    borderColor: "var(--border-color)",
                    backgroundColor: isSort ? "rgba(16,185,129,0.06)" : undefined,
                  }}
                >
                  <span className="flex items-center justify-end gap-1">
                    {label}
                    <span className="text-[8px]" style={{ opacity: isSort ? 1 : 0.3 }}>▼</span>
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>

        {/* Body */}
        <tbody>
          {teams.map((team, idx) => {
            const rgb = hexToRgb(team.color);
            return (
              <tr
                key={team.short}
                className="group transition-colors duration-100 hover:bg-white/3"
                style={{
                  borderTop: idx > 0 ? "1px solid var(--border-color)" : undefined,
                  background: `linear-gradient(to right, rgba(${rgb}, 0.04) 0%, transparent 28%)`,
                }}
              >
                {/* Sticky team cell */}
                <td
                  className="sticky left-0 z-10 px-3 py-2.5 whitespace-nowrap border-r align-top"
                  style={{
                    backgroundColor: "var(--surface-card)",
                    borderColor: "var(--border-color)",
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="text-[10px] font-mono w-4 text-right flex-shrink-0"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {idx + 1}
                    </span>
                    <div
                      className="w-0.5 h-7 rounded-full flex-shrink-0"
                      style={{ backgroundColor: team.color }}
                    />
                    <img
                      src={team.logo}
                      alt=""
                      width={20}
                      height={20}
                      className="w-5 h-5 object-contain flex-shrink-0"
                    />
                    <div>
                      <div
                        className="font-semibold text-[13px] leading-tight"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {team.short}
                      </div>
                      <div
                        className="text-[9px] font-mono leading-tight"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {team.record}
                      </div>
                    </div>
                  </div>
                </td>

                {/* Stage cells */}
                {stageKeys.map((key) => (
                  <StageCell
                    key={key}
                    team={team}
                    stageKey={key}
                    sortKey={sortKey}
                    showSources={showSources}
                  />
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChampionshipGrid (main export)
// ---------------------------------------------------------------------------

interface ChampionshipGridProps {
  data: ChampionshipGridData;
  leagueTabs: LeagueTab[];
  activeLeagueSlug: string;
  onLeagueChange: (slug: string) => void;
  gridHref?: string;
}

export default function ChampionshipGrid({
  data,
  leagueTabs,
  activeLeagueSlug,
  onLeagueChange,
}: ChampionshipGridProps) {
  const [sortKey, setSortKey] = useState(data.stageKeys[data.stageKeys.length - 1]);
  const [showSources, setShowSources] = useState(false);
  const [conferenceFilter, setConferenceFilter] = useState("All");

  const conferences = useMemo(() => {
    const c = Array.from(new Set(data.teams.map((t) => t.conference).filter(Boolean))).sort();
    return c;
  }, [data.teams]);

  const sortedTeams = useMemo(() => {
    let teams = data.teams;
    if (conferenceFilter !== "All") {
      teams = teams.filter((t) => t.conference === conferenceFilter);
    }
    return [...teams].sort((a, b) => {
      const ap = a.stages.find((s) => s.key === sortKey)?.probability ?? 0;
      const bp = b.stages.find((s) => s.key === sortKey)?.probability ?? 0;
      return bp - ap;
    });
  }, [data.teams, sortKey, conferenceFilter]);

  const sourceNames = useMemo(() => allSourceNames(data.teams), [data.teams]);

  return (
    <div style={{ color: "var(--text-primary)" }}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-lg">{data.emoji}</span>
        <h2
          className="text-base font-bold tracking-tight text-balance"
          style={{ color: "var(--text-primary)" }}
        >
          {data.league}
        </h2>
        <span
          className="text-xs font-mono ml-auto flex-shrink-0"
          style={{ color: "var(--text-muted)" }}
        >
          {data.season}
        </span>
      </div>

      {/* League Tabs */}
      <div className="mb-4">
        <LeagueTabs tabs={leagueTabs} activeSlug={activeLeagueSlug} onSelect={onLeagueChange} />
      </div>

      {/* Movers strip */}
      <div className="mb-4">
        <p className="text-[10px] font-medium uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
          Biggest movers (24h)
        </p>
        <MoversStrip teams={data.teams} stageKey={sortKey} />
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {/* Conference filter */}
        <div className="flex gap-1 flex-wrap">
          {["All", ...conferences].map((opt) => {
            const active = opt === conferenceFilter;
            return (
              <button
                key={opt}
                onClick={() => setConferenceFilter(opt)}
                className="px-2.5 py-1 rounded-full text-[11px] font-medium transition-all duration-150"
                style={{
                  backgroundColor: active ? "rgba(16,185,129,0.15)" : "transparent",
                  color: active ? "#10B981" : "var(--text-muted)",
                  border: active ? "1px solid rgba(16,185,129,0.30)" : "1px solid transparent",
                }}
              >
                {opt}
              </button>
            );
          })}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Sources toggle */}
        {sourceNames.length > 0 && (
          <button
            onClick={() => setShowSources((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-medium transition-all duration-150"
            style={{
              backgroundColor: showSources ? "rgba(16,185,129,0.15)" : "var(--surface-elevated)",
              color: showSources ? "#10B981" : "var(--text-secondary)",
              border: showSources ? "1px solid rgba(16,185,129,0.30)" : "1px solid var(--border-color)",
            }}
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ flexShrink: 0 }}>
              <circle cx="2" cy="5" r="1.5" fill="currentColor" opacity="0.5" />
              <circle cx="5" cy="5" r="1.5" fill="currentColor" opacity="0.75" />
              <circle cx="8" cy="5" r="1.5" fill="currentColor" />
            </svg>
            {showSources ? "Hide sources" : `Show sources (${sourceNames.length})`}
          </button>
        )}
      </div>

      {/* Sort hint */}
      <p className="text-[10px] mb-2" style={{ color: "var(--text-muted)" }}>
        Tap a column header to sort. Sorted by{" "}
        <span style={{ color: "#10B981" }}>
          {data.stageLabels[data.stageKeys.indexOf(sortKey)]}
        </span>.
      </p>

      {/* The table — one layout, all sizes */}
      <GridTable
        teams={sortedTeams}
        stageKeys={data.stageKeys}
        stageLabels={data.stageLabels}
        sortKey={sortKey}
        onSortKey={setSortKey}
        showSources={showSources}
      />

      {/* Footer */}
      <div
        className="mt-3 text-[10px] font-mono text-center"
        style={{ color: "var(--text-muted)" }}
      >
        {data.teams.length} teams · {data.stageKeys.length} stages
        {sourceNames.length > 0 && ` · ${sourceNames.join(", ")}`}
      </div>
    </div>
  );
}
