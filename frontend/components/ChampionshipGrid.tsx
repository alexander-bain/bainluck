"use client";

/**
 * ChampionshipGrid — Mobile-first championship probability display.
 *
 * Fits ALL stages on mobile without horizontal scroll by using:
 * - Compact 2-3 letter column headers (R1, R2, CF, FIN, WIN)
 * - Mini probability bars with intensity-encoded color instead of numbers
 * - Tap to expand any row for source-level detail
 *
 * The design prioritizes visual scanning over precise reading —
 * users can spot contenders at a glance by bar length/color.
 */

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import type { ChampionshipGridData, PlayoffTeam, LeagueTab, PlayoffStage } from "@/lib/playoff-types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(p: number): string {
  const pct = Math.round(p * 100);
  return pct < 1 && p > 0 ? "<1" : `${pct}`;
}

function hexToRgba(hex: string, alpha: number): string {
  const h = (hex || "#888888").replace("#", "");
  const r = parseInt(h.substring(0, 2), 16) || 128;
  const g = parseInt(h.substring(2, 4), 16) || 128;
  const b = parseInt(h.substring(4, 6), 16) || 128;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Encode probability as opacity — higher = more visible */
function probAlpha(p: number): number {
  // Range from 0.15 (near-zero) to 1.0 (100%)
  return 0.15 + p * 0.85;
}

// ---------------------------------------------------------------------------
// LeagueTabs
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
    <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-hide">
      {tabs.map((tab) => {
        const active = tab.slug === activeSlug;
        return (
          <button
            key={tab.slug}
            onClick={() => onSelect(tab.slug)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium whitespace-nowrap flex-shrink-0 transition-all duration-150"
            style={{
              backgroundColor: active ? "var(--surface-elevated)" : "transparent",
              color: active ? "var(--text-primary)" : "var(--text-muted)",
              border: active ? "1px solid var(--surface-border)" : "1px solid transparent",
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
// Expanded source row
// ---------------------------------------------------------------------------

function SourceBreakdown({ team, stageKeys, stageLabels }: { team: PlayoffTeam; stageKeys: string[]; stageLabels: string[] }) {
  // Collect all unique sources across this team's stages
  const allSources = useMemo(() => {
    const set = new Set<string>();
    team.stages.forEach((s) => s.sources.forEach((src) => set.add(src.source)));
    return Array.from(set);
  }, [team]);

  if (!allSources.length) {
    return (
      <div className="px-3 py-2 text-[10px]" style={{ color: "var(--text-muted)" }}>
        No source data available
      </div>
    );
  }

  return (
    <div className="px-3 py-2">
      <table className="w-full text-[10px]">
        <thead>
          <tr>
            <th className="text-left font-medium pb-1" style={{ color: "var(--text-muted)", width: "30%" }}>
              Source
            </th>
            {stageLabels.map((label, i) => (
              <th
                key={stageKeys[i]}
                className="text-center font-medium pb-1"
                style={{ color: "var(--text-muted)" }}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {allSources.map((sourceName) => (
            <tr key={sourceName}>
              <td className="py-0.5 font-medium" style={{ color: "var(--text-secondary)" }}>
                {sourceName}
              </td>
              {stageKeys.map((key) => {
                const stage = team.stages.find((s) => s.key === key);
                const srcData = stage?.sources.find((s) => s.source === sourceName);
                return (
                  <td key={key} className="text-center py-0.5 font-mono" style={{ color: "var(--text-secondary)" }}>
                    {srcData ? `${fmt(srcData.probability)}%` : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single team row with mini-bars
// ---------------------------------------------------------------------------

interface TeamRowProps {
  team: PlayoffTeam;
  rank: number;
  stageKeys: string[];
  stageLabels: string[];
  sortKey: string;
  expanded: boolean;
  onToggle: () => void;
}

function TeamRow({ team, rank, stageKeys, stageLabels, sortKey, expanded, onToggle }: TeamRowProps) {
  const teamColor = team.color || "#888888";

  return (
    <>
      {/* Main row */}
      <tr
        onClick={onToggle}
        className="cursor-pointer transition-colors duration-100"
        style={{
          backgroundColor: expanded ? hexToRgba(teamColor, 0.06) : undefined,
        }}
      >
        {/* Rank + Team */}
        <td className="py-2 pl-2 pr-1">
          <div className="flex items-center gap-1.5">
            <span
              className="text-[10px] font-mono w-4 text-right flex-shrink-0"
              style={{ color: "var(--text-muted)" }}
            >
              {rank}
            </span>
            <div
              className="w-0.5 h-6 rounded-full flex-shrink-0"
              style={{ backgroundColor: teamColor }}
            />
            <img
              src={team.logo}
              alt=""
              width={18}
              height={18}
              className="w-[18px] h-[18px] object-contain flex-shrink-0"
            />
            <div className="min-w-0">
              <div
                className="font-semibold text-[12px] leading-tight truncate"
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

        {/* Stage probability mini-bars */}
        {stageKeys.map((key) => {
          const stage = team.stages.find((s) => s.key === key);
          const prob = stage?.probability ?? 0;
          const change = stage?.change24h ?? 0;
          const isSort = key === sortKey;

          // Compute bar width and alpha
          const barWidth = Math.max(prob * 100, prob > 0 ? 4 : 0); // min 4% if non-zero
          const alpha = probAlpha(prob);

          return (
            <td
              key={key}
              className="py-2 px-0.5 text-center align-middle"
              style={{
                backgroundColor: isSort ? "rgba(16,185,129,0.04)" : undefined,
              }}
            >
              <div className="flex flex-col items-center gap-0.5">
                {/* Mini bar */}
                <div
                  className="h-2.5 rounded-sm mx-auto"
                  style={{
                    width: `${barWidth}%`,
                    minWidth: prob > 0 ? 3 : 0,
                    maxWidth: "100%",
                    backgroundColor: hexToRgba(teamColor, alpha),
                  }}
                />
                {/* Number underneath */}
                <span
                  className="text-[9px] font-mono leading-none"
                  style={{
                    color: isSort ? "var(--text-primary)" : "var(--text-muted)",
                    fontWeight: isSort ? 600 : 400,
                  }}
                >
                  {prob >= 0.995 ? "99+" : fmt(prob)}
                </span>
                {/* Trend indicator (only if significant) */}
                {Math.abs(change) >= 0.005 && (
                  <span
                    className="text-[7px] font-mono leading-none"
                    style={{ color: change > 0 ? "#22C55E" : "#EF4444" }}
                  >
                    {change > 0 ? "+" : ""}{Math.round(change * 100)}
                  </span>
                )}
              </div>
            </td>
          );
        })}

        {/* Expand indicator */}
        <td className="py-2 pr-2 pl-0.5 text-right">
          <span
            className="text-[10px] transition-transform duration-150 inline-block"
            style={{
              color: "var(--text-muted)",
              transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            }}
          >
            ▼
          </span>
        </td>
      </tr>

      {/* Expanded source breakdown */}
      {expanded && (
        <tr>
          <td
            colSpan={stageKeys.length + 2}
            className="border-t border-b"
            style={{
              backgroundColor: hexToRgba(teamColor, 0.03),
              borderColor: "var(--surface-border)",
            }}
          >
            <motion.div
              initial={{ opacity: 0, height: 0, overflow: "hidden" }}
              animate={{ opacity: 1, height: "auto", overflow: "visible" }}
              exit={{ opacity: 0, height: 0, overflow: "hidden" }}
              transition={{ duration: 0.15 }}
            >
              <SourceBreakdown team={team} stageKeys={stageKeys} stageLabels={stageLabels} />
            </motion.div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Grid
// ---------------------------------------------------------------------------

interface GridTableProps {
  teams: PlayoffTeam[];
  stageKeys: string[];
  stageLabels: string[];
  sortKey: string;
  onSortKey: (k: string) => void;
  expandedTeam: string | null;
  onExpandTeam: (short: string | null) => void;
}

function GridTable({
  teams,
  stageKeys,
  stageLabels,
  sortKey,
  onSortKey,
  expandedTeam,
  onExpandTeam,
}: GridTableProps) {
  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ borderColor: "var(--surface-border)", backgroundColor: "var(--surface-card)" }}
    >
      <table className="w-full text-sm border-collapse table-fixed">
        <colgroup>
          {/* Team column — ~32% */}
          <col style={{ width: "32%" }} />
          {/* Stage columns — divide remaining ~60% equally */}
          {stageKeys.map((k) => (
            <col key={k} style={{ width: `${60 / stageKeys.length}%` }} />
          ))}
          {/* Expand indicator — ~8% */}
          <col style={{ width: "8%" }} />
        </colgroup>

        <thead>
          <tr style={{ backgroundColor: "var(--surface-elevated)" }}>
            <th
              className="py-2 pl-2 pr-1 text-left text-[9px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
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
                  className="py-2 px-0.5 text-center text-[9px] font-semibold uppercase tracking-wider cursor-pointer select-none transition-colors duration-100"
                  style={{
                    color: isSort ? "#10B981" : "var(--text-muted)",
                    backgroundColor: isSort ? "rgba(16,185,129,0.06)" : undefined,
                  }}
                >
                  {label}
                </th>
              );
            })}
            <th className="py-2 pr-2 pl-0.5" />
          </tr>
        </thead>

        <tbody>
          {teams.map((team, idx) => (
            <TeamRow
              key={team.short}
              team={team}
              rank={idx + 1}
              stageKeys={stageKeys}
              stageLabels={stageLabels}
              sortKey={sortKey}
              expanded={expandedTeam === team.short}
              onToggle={() => onExpandTeam(expandedTeam === team.short ? null : team.short)}
            />
          ))}
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
  // Default sortKey to last stage key, or empty string if no data
  const defaultSortKey = data?.stageKeys?.[data.stageKeys.length - 1] ?? "";
  const [sortKey, setSortKey] = useState(defaultSortKey);
  const [conferenceFilter, setConferenceFilter] = useState("All");
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  const conferences = useMemo(() => {
    if (!data?.teams) return [];
    const seen: Record<string, boolean> = {};
    const result: string[] = [];
    for (const t of data.teams) {
      if (t.conference && !seen[t.conference]) {
        seen[t.conference] = true;
        result.push(t.conference);
      }
    }
    return result.sort();
  }, [data?.teams]);

  const sortedTeams = useMemo(() => {
    if (!data?.teams) return [];
    let teams = data.teams;
    if (conferenceFilter !== "All") {
      teams = teams.filter((t) => t.conference === conferenceFilter);
    }
    return [...teams].sort((a, b) => {
      const ap = a.stages.find((s) => s.key === sortKey)?.probability ?? 0;
      const bp = b.stages.find((s) => s.key === sortKey)?.probability ?? 0;
      return bp - ap;
    });
  }, [data?.teams, sortKey, conferenceFilter]);

  // Use compact labels for mobile
  const compactLabels = useMemo(() => {
    if (!data?.stageLabels) return (data?.stageKeys ?? []).map((k) => k.slice(0, 3).toUpperCase());
    return data.stageLabels.map((label) => {
      const map: Record<string, string> = {
        "Make Playoffs": "R1",
        "Playoffs": "R1",
        "Round 1": "R1",
        "Conf Semis": "R2",
        "Conference Semis": "R2",
        "Round 2": "R2",
        "Conf Finals": "CF",
        "Conference Finals": "CF",
        "Finals": "FIN",
        "NBA Finals": "FIN",
        "Championship": "WIN",
        "Win Championship": "WIN",
        "Super Bowl": "WIN",
        "World Series": "WIN",
        "Stanley Cup": "WIN",
      };
      return map[label] || label.slice(0, 3).toUpperCase();
    });
  }, [data?.stageLabels, data?.stageKeys]);

  // Defensive check for data (after hooks)
  if (!data || !data.stageKeys || data.stageKeys.length === 0) {
    return <div style={{ color: "var(--text-muted)", padding: "1rem" }}>No data available</div>;
  }

  return (
    <div style={{ color: "var(--text-primary)" }}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">{data.emoji}</span>
        <h2
          className="text-sm font-bold tracking-tight"
          style={{ color: "var(--text-primary)" }}
        >
          {data.league}
        </h2>
        <span
          className="text-[10px] font-mono ml-auto"
          style={{ color: "var(--text-muted)" }}
        >
          {data.season}
        </span>
      </div>

      {/* League Tabs */}
      <div className="mb-3">
        <LeagueTabs tabs={leagueTabs} activeSlug={activeLeagueSlug} onSelect={onLeagueChange} />
      </div>

      {/* Conference filter + sort hint */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <div className="flex gap-1">
          {["All", ...conferences].map((opt) => {
            const active = opt === conferenceFilter;
            return (
              <button
                key={opt}
                onClick={() => setConferenceFilter(opt)}
                className="px-2 py-0.5 rounded-full text-[10px] font-medium transition-all duration-150"
                style={{
                  backgroundColor: active ? "rgba(16,185,129,0.15)" : "transparent",
                  color: active ? "#10B981" : "var(--text-muted)",
                }}
              >
                {opt === "All" ? "All" : opt.slice(0, 4)}
              </button>
            );
          })}
        </div>
        <span className="text-[9px] ml-auto" style={{ color: "var(--text-muted)" }}>
          Tap header to sort · Tap row for sources
        </span>
      </div>

      {/* Grid */}
      <GridTable
        teams={sortedTeams}
        stageKeys={data.stageKeys}
        stageLabels={compactLabels}
        sortKey={sortKey}
        onSortKey={setSortKey}
        expandedTeam={expandedTeam}
        onExpandTeam={setExpandedTeam}
      />

      {/* Legend */}
      <div
        className="mt-2 flex items-center justify-center gap-3 text-[9px]"
        style={{ color: "var(--text-muted)" }}
      >
        <span>R1 = Round 1</span>
        <span>R2 = Conf Semis</span>
        <span>CF = Conf Finals</span>
        <span>FIN = Finals</span>
        <span>WIN = Champ</span>
      </div>
    </div>
  );
}
