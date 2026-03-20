"use client";

/**
 * ChampionshipGrid — Mobile-first championship probability leaderboard.
 *
 * Mobile: Stage-selector tabs control which probability column is shown as
 *         a ranked list. Tapping a team row expands an inline TeamPlayoffCard.
 * Desktop (≥768px): Full table with all stages as sticky columns.
 */

import { useState, useMemo } from "react";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import TeamPlayoffCard from "@/components/TeamPlayoffCard";
import type { ChampionshipGridData, PlayoffTeam, LeagueTab } from "@/lib/playoff-types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatProb(p: number): string {
  return `${Math.round(p * 100)}%`;
}

function formatChange(c: number): { str: string; isUp: boolean } | null {
  if (!c || Math.abs(c) < 0.001) return null;
  const pct = Math.abs(c * 100);
  const formatted = pct >= 1 ? Math.round(pct).toString() : pct.toFixed(1);
  return { str: `${formatted}%`, isUp: c > 0 };
}

function hexToRgb(hex: string): string {
  const h = (hex || "#888888").replace("#", "");
  const r = parseInt(h.substring(0, 2), 16) || 128;
  const g = parseInt(h.substring(2, 4), 16) || 128;
  const b = parseInt(h.substring(4, 6), 16) || 128;
  return `${r}, ${g}, ${b}`;
}

function probColor(p: number): string {
  if (p >= 0.6) return "#22C55E";
  if (p <= 0.1) return "#EF4444";
  return "var(--text-primary)";
}

// ---------------------------------------------------------------------------
// Movers Strip
// ---------------------------------------------------------------------------

interface MoversBadge {
  short: string;
  color: string;
  change: number;
  logo: string;
}

function computeMovers(teams: PlayoffTeam[], stageKey: string): MoversBadge[] {
  return teams
    .map((t) => {
      const stage = t.stages.find((s) => s.key === stageKey);
      return { short: t.short, color: t.color, logo: t.logo, change: stage?.change24h ?? 0 };
    })
    .filter((m) => Math.abs(m.change) >= 0.005)
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
    .slice(0, 6);
}

function MoversStrip({ movers }: { movers: MoversBadge[] }) {
  if (!movers.length) return null;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
      {movers.map((m) => {
        const isUp = m.change > 0;
        const pct = Math.abs(m.change * 100);
        const formatted = pct >= 1 ? Math.round(pct) : pct.toFixed(1);
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
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: m.color }}
            />
            <span>{m.short}</span>
            <span className="font-mono text-[10px]">
              {isUp ? "+" : "-"}
              {formatted}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage Selector Tabs
// ---------------------------------------------------------------------------

function StageTabs({
  labels,
  selectedIndex,
  onSelect,
}: {
  labels: string[];
  selectedIndex: number;
  onSelect: (i: number) => void;
}) {
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
      {labels.map((label, i) => {
        const active = i === selectedIndex;
        return (
          <button
            key={label}
            onClick={() => onSelect(i)}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap flex-shrink-0 transition-all duration-150"
            style={{
              backgroundColor: active ? "#10B981" : "var(--surface-elevated)",
              color: active ? "#0C0F14" : "var(--text-secondary)",
              border: active ? "1px solid transparent" : "1px solid var(--border-color)",
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Conference Filter
// ---------------------------------------------------------------------------

function ConferenceFilter({
  options,
  selected,
  onSelect,
}: {
  options: string[];
  selected: string;
  onSelect: (v: string) => void;
}) {
  return (
    <div className="flex gap-1.5">
      {["All", ...options].map((opt) => {
        const active = opt === selected;
        return (
          <button
            key={opt}
            onClick={() => onSelect(opt)}
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
// Mobile Team Row
// ---------------------------------------------------------------------------

interface TeamRowProps {
  team: PlayoffTeam;
  rank: number;
  stageKey: string;
  isExpanded: boolean;
  onToggle: () => void;
  gridHref: string;
}

function TeamRow({ team, rank, stageKey, isExpanded, onToggle, gridHref }: TeamRowProps) {
  const stage = team.stages.find((s) => s.key === stageKey) ?? team.stages[0];
  const prob = stage?.probability ?? 0;
  const change = formatChange(stage?.change24h ?? 0);
  const rgb = hexToRgb(team.color);
  const color = probColor(prob);

  return (
    <motion.div layout="position" className="overflow-hidden">
      {/* Main row */}
      <button
        onClick={onToggle}
        className="w-full text-left relative overflow-hidden rounded-xl transition-all duration-150"
        style={{
          backgroundColor: "var(--surface-card)",
          border: isExpanded ? `1px solid ${team.color}40` : "1px solid var(--border-color)",
        }}
      >
        {/* Row color tint */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `linear-gradient(to right, rgba(${rgb}, 0.05) 0%, transparent 50%)`,
          }}
        />
        {/* Probability fill bar behind the row */}
        <div
          className="absolute inset-y-0 left-0 pointer-events-none rounded-xl transition-all duration-500"
          style={{
            width: `${Math.max(prob * 100, 2)}%`,
            backgroundColor: `rgba(${rgb}, 0.07)`,
          }}
        />

        <div className="relative flex items-center gap-3 px-3 py-3">
          {/* Rank */}
          <span
            className="text-xs font-mono w-5 text-right flex-shrink-0"
            style={{ color: "var(--text-muted)" }}
          >
            {rank}
          </span>

          {/* Logo */}
          <img
            src={team.logo}
            alt={team.short}
            width={24}
            height={24}
            className="w-6 h-6 object-contain flex-shrink-0"
          />

          {/* Name + record */}
          <div className="flex-1 min-w-0">
            <div
              className="text-sm font-semibold truncate leading-tight"
              style={{ color: "var(--text-primary)" }}
            >
              {team.name}
            </div>
            <div
              className="text-[10px] font-mono leading-tight"
              style={{ color: "var(--text-muted)" }}
            >
              {team.record}
            </div>
          </div>

          {/* Probability + trend */}
          <div className="flex flex-col items-end flex-shrink-0">
            <span
              className="font-mono text-lg font-bold leading-none"
              style={{ color }}
            >
              {formatProb(prob)}
            </span>
            {change && (
              <span
                className="font-mono text-[10px] leading-none mt-0.5"
                style={{ color: change.isUp ? "#22C55E" : "#EF4444" }}
              >
                {change.isUp ? "▲" : "▼"}
                {change.str}
              </span>
            )}
          </div>

          {/* Expand chevron */}
          <span
            className="text-[10px] flex-shrink-0 transition-transform duration-200"
            style={{
              color: "var(--text-muted)",
              transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
            }}
          >
            ▼
          </span>
        </div>
      </button>

      {/* Expanded inline TeamPlayoffCard */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 35 }}
            className="overflow-hidden mt-1"
          >
            <TeamPlayoffCard team={team} gridHref={gridHref} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Desktop Table View
// ---------------------------------------------------------------------------

function DesktopTable({
  teams,
  stageKeys,
  stageLabels,
  sortStageIndex,
}: {
  teams: PlayoffTeam[];
  stageKeys: string[];
  stageLabels: string[];
  sortStageIndex: number;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--border-color)" }}>
      <table className="w-full text-sm">
        <thead>
          <tr style={{ backgroundColor: "var(--surface-elevated)", borderBottom: "1px solid var(--border-color)" }}>
            <th
              className="sticky left-0 z-10 px-4 py-2.5 text-left font-medium text-[11px] uppercase tracking-wider whitespace-nowrap"
              style={{ backgroundColor: "var(--surface-elevated)", color: "var(--text-muted)", minWidth: 200 }}
            >
              Team
            </th>
            {stageLabels.map((label, i) => (
              <th
                key={stageKeys[i]}
                className="px-3 py-2.5 text-right font-medium text-[11px] uppercase tracking-wider whitespace-nowrap"
                style={{
                  color: i === sortStageIndex ? "#10B981" : "var(--text-muted)",
                }}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {teams.map((team, idx) => {
            const rgb = hexToRgb(team.color);
            return (
              <tr
                key={team.short}
                className="border-t transition-colors duration-100 hover:bg-white/3"
                style={{
                  borderColor: "rgba(255,255,255,0.05)",
                  background: `linear-gradient(to right, rgba(${rgb}, 0.04) 0%, transparent 30%)`,
                }}
              >
                {/* Sticky team cell */}
                <td
                  className="sticky left-0 z-10 px-4 py-3 whitespace-nowrap"
                  style={{ backgroundColor: "var(--surface-card)" }}
                >
                  <div className="flex items-center gap-2.5">
                    <span className="text-xs font-mono w-4 text-right" style={{ color: "var(--text-muted)" }}>
                      {idx + 1}
                    </span>
                    <div
                      className="w-0.5 h-6 rounded-full flex-shrink-0"
                      style={{ backgroundColor: team.color }}
                    />
                    <img src={team.logo} alt="" width={20} height={20} className="w-5 h-5 object-contain" />
                    <div>
                      <div className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                        {team.name}
                      </div>
                      <div className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                        {team.record} · {team.conference}
                      </div>
                    </div>
                  </div>
                </td>

                {/* Stage cells */}
                {stageKeys.map((key, i) => {
                  const stage = team.stages.find((s) => s.key === key);
                  const prob = stage?.probability ?? 0;
                  const change = formatChange(stage?.change24h ?? 0);
                  const isSort = i === sortStageIndex;
                  return (
                    <td key={key} className="px-3 py-3 text-right">
                      <div
                        className="font-mono font-bold text-sm"
                        style={{ color: isSort ? probColor(prob) : "var(--text-secondary)" }}
                      >
                        {formatProb(prob)}
                      </div>
                      {change && (
                        <div
                          className="font-mono text-[10px]"
                          style={{ color: change.isUp ? "#22C55E" : "#EF4444" }}
                        >
                          {change.isUp ? "▲" : "▼"}
                          {change.str}
                        </div>
                      )}
                    </td>
                  );
                })}
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
  gridHref = "/playoffs/nba",
}: ChampionshipGridProps) {
  const [selectedStageIndex, setSelectedStageIndex] = useState(4); // default: Champion
  const [conferenceFilter, setConferenceFilter] = useState("All");
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  const conferences = useMemo(() => {
    const confs = Array.from(new Set(data.teams.map((t) => t.conference).filter(Boolean)));
    return confs.sort();
  }, [data.teams]);

  const selectedStageKey = data.stageKeys[selectedStageIndex];

  // Filter + sort
  const filteredTeams = useMemo(() => {
    let teams = data.teams;
    if (conferenceFilter !== "All") {
      teams = teams.filter((t) => t.conference === conferenceFilter);
    }
    return [...teams].sort((a, b) => {
      const aProb = a.stages.find((s) => s.key === selectedStageKey)?.probability ?? 0;
      const bProb = b.stages.find((s) => s.key === selectedStageKey)?.probability ?? 0;
      return bProb - aProb;
    });
  }, [data.teams, conferenceFilter, selectedStageKey]);

  // Movers for the selected stage
  const movers = useMemo(
    () => computeMovers(data.teams, selectedStageKey),
    [data.teams, selectedStageKey]
  );

  const teamCount = data.teams.length;
  const stageCount = data.stageKeys.length;
  const sourceCount = useMemo(() => {
    const allSources = new Set(
      data.teams.flatMap((t) => t.stages.flatMap((s) => s.sources.map((src) => src.source)))
    );
    return allSources.size;
  }, [data.teams]);

  return (
    <div style={{ color: "var(--text-primary)" }}>
      {/* ── Header ── */}
      <div className="mb-4">
        <div className="flex items-baseline gap-2">
          <span className="text-xl">{data.emoji}</span>
          <h1
            className="text-lg font-bold leading-tight tracking-tight text-balance"
            style={{ color: "var(--text-primary)" }}
          >
            {data.league}
          </h1>
          <span
            className="text-xs font-mono ml-auto flex-shrink-0"
            style={{ color: "var(--text-muted)" }}
          >
            {data.season}
          </span>
        </div>
      </div>

      {/* ── League Tabs ── */}
      <div className="mb-4">
        <LeagueTabs
          tabs={leagueTabs}
          activeSlug={activeLeagueSlug}
          onSelect={onLeagueChange}
        />
      </div>

      {/* ── Movers Strip ── */}
      {movers.length > 0 && (
        <div className="mb-4">
          <div
            className="text-[10px] font-medium uppercase tracking-wider mb-2"
            style={{ color: "var(--text-muted)" }}
          >
            Biggest movers (24h)
          </div>
          <MoversStrip movers={movers} />
        </div>
      )}

      {/* ── Mobile: Stage selector + conference filter ── (hidden on desktop) */}
      <div className="md:hidden mb-3 space-y-2">
        <StageTabs
          labels={data.stageLabels}
          selectedIndex={selectedStageIndex}
          onSelect={setSelectedStageIndex}
        />
        {conferences.length > 0 && (
          <ConferenceFilter
            options={conferences}
            selected={conferenceFilter}
            onSelect={setConferenceFilter}
          />
        )}
      </div>

      {/* ── Mobile: Ranked Team List ── */}
      <LayoutGroup>
        <div className="md:hidden space-y-1.5">
          <AnimatePresence initial={false}>
            {filteredTeams.map((team, i) => (
              <TeamRow
                key={team.short}
                team={team}
                rank={i + 1}
                stageKey={selectedStageKey}
                isExpanded={expandedTeam === team.short}
                onToggle={() =>
                  setExpandedTeam(expandedTeam === team.short ? null : team.short)
                }
                gridHref={gridHref}
              />
            ))}
          </AnimatePresence>
        </div>
      </LayoutGroup>

      {/* ── Desktop: Full Table ── (hidden on mobile) */}
      <div className="hidden md:block">
        <div className="flex items-center gap-3 mb-3">
          <StageTabs
            labels={data.stageLabels}
            selectedIndex={selectedStageIndex}
            onSelect={setSelectedStageIndex}
          />
          {conferences.length > 0 && (
            <ConferenceFilter
              options={conferences}
              selected={conferenceFilter}
              onSelect={setConferenceFilter}
            />
          )}
        </div>
        <DesktopTable
          teams={filteredTeams}
          stageKeys={data.stageKeys}
          stageLabels={data.stageLabels}
          sortStageIndex={selectedStageIndex}
        />
      </div>

      {/* ── Footer ── */}
      <div
        className="mt-4 text-[11px] text-center font-mono"
        style={{ color: "var(--text-muted)" }}
      >
        {teamCount} teams · {stageCount} stages · {sourceCount} {sourceCount === 1 ? "source" : "sources"}
      </div>
    </div>
  );
}
