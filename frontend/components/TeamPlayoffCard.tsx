"use client";

/**
 * TeamPlayoffCard
 *
 * A compact, premium data-visualization card showing a single team's
 * championship probability funnel. Stages flow left→right; each bar's
 * width is proportional to probability, creating a natural taper.
 *
 * Used in pairs on event detail pages (e.g., Celtics vs Heat).
 */

import Link from "next/link";
import type { PlayoffTeam } from "@/lib/playoff-types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatProb(p: number): string {
  const pct = Math.round(p * 100);
  return `${pct}%`;
}

function formatChange(c: number): string | null {
  if (!c || Math.abs(c) < 0.001) return null;
  const pct = Math.abs(c * 100);
  const formatted = pct >= 1 ? Math.round(pct).toString() : pct.toFixed(1);
  return `${c > 0 ? "+" : "-"}${formatted}%`;
}

function hexToRgb(hex: string): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
}

// ---------------------------------------------------------------------------
// Stage Column
// ---------------------------------------------------------------------------

interface StageColProps {
  label: string;
  probability: number;
  change24h: number;
  status: "pending" | "clinched" | "eliminated";
  teamColor: string;
  /** 0–1 fraction of the first stage's bar that this bar should fill */
  barFraction: number;
  isLast: boolean;
}

function StageCol({
  label,
  probability,
  change24h,
  status,
  teamColor,
  barFraction,
  isLast,
}: StageColProps) {
  const rgb = hexToRgb(teamColor);
  const eliminated = status === "eliminated";
  const clinched = status === "clinched";
  const changeStr = formatChange(change24h);
  const isUp = change24h > 0;

  return (
    <div
      className={`flex flex-col items-center gap-1 min-w-0 flex-1 ${eliminated ? "opacity-40" : ""}`}
    >
      {/* Stage label */}
      <span
        className="text-[9px] font-medium uppercase tracking-wider truncate w-full text-center"
        style={{ color: "var(--text-secondary)" }}
      >
        {label}
      </span>

      {/* Bar */}
      <div className="w-full relative" style={{ height: 20 }}>
        {/* Track */}
        <div
          className="absolute inset-0 rounded-sm"
          style={{
            backgroundColor: `rgba(${rgb}, 0.10)`,
          }}
        />
        {/* Fill */}
        {!eliminated && (
          <div
            className="absolute inset-y-0 left-0 rounded-sm transition-all duration-500"
            style={{
              width: `${Math.max(barFraction * 100, 3)}%`,
              backgroundColor: `rgba(${rgb}, ${0.55 + barFraction * 0.35})`,
            }}
          />
        )}
        {/* Eliminated X overlay */}
        {eliminated && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-[10px] text-red-400 font-bold">✕</span>
          </div>
        )}
        {/* Clinched check overlay */}
        {clinched && (
          <div className="absolute right-1 inset-y-0 flex items-center">
            <span className="text-[10px] text-emerald-400 font-bold">✓</span>
          </div>
        )}
      </div>

      {/* Probability */}
      <div className="flex flex-col items-center gap-px">
        <span
          className="font-mono text-[11px] font-bold leading-none"
          style={{ color: eliminated ? "var(--text-muted)" : "var(--text-primary)" }}
        >
          {formatProb(probability)}
        </span>
        {/* 24h trend */}
        {changeStr && !eliminated && (
          <span
            className="font-mono text-[9px] leading-none"
            style={{ color: isUp ? "#22C55E" : "#EF4444" }}
          >
            {isUp ? "▲" : "▼"}
            {changeStr.replace(/^[+-]/, "")}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TeamPlayoffCard
// ---------------------------------------------------------------------------

interface TeamPlayoffCardProps {
  team: PlayoffTeam;
  /** href to the full league page, e.g. "/sport/basketball/nba" */
  gridHref?: string;
}

export default function TeamPlayoffCard({
  team,
  gridHref = "/sport/basketball/nba",
}: TeamPlayoffCardProps) {
  const rgb = hexToRgb(team.color);

  // The bar widths are relative to the first (highest) stage probability
  const maxProb = team.stages[0]?.probability ?? 1;

  // Build sources line (unique source names)
  const allSources = Array.from(
    new Set(team.stages.flatMap((s) => s.sources.map((src) => src.source)))
  );
  const sourceLine = allSources.join(" · ");

  return (
    <Link href={gridHref} className="block group">
      <div
        className="relative rounded-xl overflow-hidden border transition-all duration-200 group-hover:border-white/20"
        style={{
          backgroundColor: "var(--surface-card)",
          borderColor: "var(--surface-border)",
          borderLeftWidth: 3,
          borderLeftColor: team.color,
        }}
      >
        {/* Subtle team-color tint on background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `linear-gradient(to right, rgba(${rgb}, 0.06) 0%, transparent 60%)`,
          }}
        />

        <div className="relative px-3 pt-3 pb-2.5">
          {/* Header: logo + name + record */}
          <div className="flex items-center gap-2 mb-3">
            <img
              src={team.logo}
              alt={team.name}
              width={24}
              height={24}
              className="w-6 h-6 object-contain flex-shrink-0"
            />
            <span
              className="text-sm font-semibold leading-tight truncate"
              style={{ color: "var(--text-primary)" }}
            >
              {team.name}
            </span>
            <span
              className="text-xs font-mono ml-auto flex-shrink-0"
              style={{ color: "var(--text-muted)" }}
            >
              {team.record}
            </span>
          </div>

          {/* Funnel: stage columns */}
          <div className="flex items-stretch gap-1.5">
            {team.stages.map((stage, i) => (
              <StageCol
                key={stage.key}
                label={stage.label}
                probability={stage.probability}
                change24h={stage.change24h}
                status={stage.status}
                teamColor={team.color}
                barFraction={maxProb > 0 ? stage.probability / maxProb : 0}
                isLast={i === team.stages.length - 1}
              />
            ))}
          </div>

          {/* Sources footer */}
          {sourceLine && (
            <div
              className="mt-2.5 text-[9px] truncate"
              style={{ color: "var(--text-muted)" }}
            >
              {sourceLine}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
