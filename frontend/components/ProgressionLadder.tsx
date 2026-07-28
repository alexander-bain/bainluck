"use client";

/**
 * ProgressionLadder — Compact grouped display for playoff progression markets.
 * Designed to be similar in size/style to FuturesCard.
 */

import { motion } from "framer-motion";
import { staggerItem } from "@/lib/animations";
import { cn } from "@/lib/utils";
import { getWikipediaImage } from "@/lib/images";
import { useEntityImage } from "@/lib/entityImage";
import { probabilityTextClass } from "@/lib/probabilityColors";

/**
 * TeamLogo — resolves a team logo with fallback:
 * 1. Direct logoUrl prop
 * 2. Wikipedia image search by team name
 * 3. Colored initials square using teamColors
 */
function TeamLogo({
  entityName,
  logoUrl,
  teamColors,
  size = 28,
}: {
  entityName: string;
  logoUrl?: string;
  teamColors?: { primary: string };
  size?: number;
}) {
  // Identity-safe logo resolution (L2-199): re-seeds when the team identity
  // changes — previously this instance kept the prior team's logo after a
  // recycle because the fetch effect early-returned on a non-null resolvedUrl —
  // and drops a late Wikipedia lookup fired for a superseded team so it can't
  // land on another team. See lib/entityImage.ts.
  const { url: resolvedUrl, failed, markFailed } = useEntityImage(entityName, logoUrl, getWikipediaImage);

  const initials = entityName
    .split(" ")
    .filter((w) => w.length > 2)
    .map((w) => w[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();

  const dim = `${size}px`;
  const bg = teamColors ? `rgb(${teamColors.primary})` : undefined;

  if (resolvedUrl && !failed) {
    return (
      <img
        src={resolvedUrl}
        alt={entityName}
        width={size}
        height={size}
        className="rounded object-contain flex-shrink-0 bg-surface-elevated/30"
        style={{ width: dim, height: dim }}
        onError={markFailed}
      />
    );
  }

  return (
    <div
      className="rounded flex items-center justify-center flex-shrink-0 text-white font-bold"
      style={{ width: dim, height: dim, backgroundColor: bg || "rgb(var(--surface-elevated))", fontSize: size * 0.32 }}
      aria-label={entityName}
    >
      {initials}
    </div>
  );
}

interface Stage {
  id: number;
  name: string;
  stage_name: string;
  stage_order: number;
  probability: number | null;
  status?: "achieved" | "eliminated" | "pending";
  source?: string;
}

interface ProgressionLadderProps {
  entityName: string;
  stages: Stage[];
  logoUrl?: string;
  teamColors?: { primary: string; secondary: string };
  onStageClick?: (stage: Stage) => void;
  horizontal?: boolean;
  /** Season/year label for display, e.g. "2025-26" (BR52). */
  seasonYear?: string;
}

export default function ProgressionLadder({
  entityName,
  stages,
  logoUrl,
  teamColors,
  onStageClick,
  horizontal = false,
  seasonYear,
}: ProgressionLadderProps) {
  const sorted = [...stages].sort((a, b) => a.stage_order - b.stage_order);
  const display = sorted.slice(0, 5);

  if (horizontal) {
    return (
      <motion.div
        className="bg-surface-card border border-surface-border rounded-lg p-3"
        style={teamColors ? { borderLeftColor: `rgb(${teamColors.primary})`, borderLeftWidth: "3px" } : undefined}
        variants={staggerItem}
      >
        <div className="flex items-center gap-2 mb-2">
          <TeamLogo entityName={entityName} logoUrl={logoUrl} teamColors={teamColors} size={22} />
          <span className="text-sm font-medium text-text-primary truncate">{entityName}</span>
        </div>
        <div className="flex gap-1 overflow-x-auto">
          {display.map((stage) => {
            const prob = stage.probability ?? 0;
            const achieved = stage.status === "achieved";
            return (
              <button
                key={stage.id}
                onClick={() => onStageClick?.(stage)}
                className={cn(
                  "flex-shrink-0 px-2 py-1 rounded text-xs transition-colors",
                  achieved ? "bg-accent-brand/15 text-accent-brand" : "bg-surface-elevated hover:bg-surface-elevated/80"
                )}
              >
                <div className="text-[10px] text-text-muted truncate max-w-[60px]">
                  {stage.stage_name.replace(/^(Make |Win )/, "")}
                </div>
                <div className={cn("font-mono font-medium", achieved ? "text-accent-brand" : probabilityTextClass(prob))}>
                  {achieved ? "done" : `${(prob * 100).toFixed(0)}%`}
                </div>
              </button>
            );
          })}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="bg-surface-card border border-surface-border rounded-lg p-3 hover:bg-surface-elevated transition-colors"
      style={teamColors ? { borderLeftColor: `rgb(${teamColors.primary})`, borderLeftWidth: "3px" } : undefined}
      variants={staggerItem}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <TeamLogo
          entityName={entityName}
          logoUrl={logoUrl}
          teamColors={teamColors}
          size={28}
        />
        <span className="text-sm font-medium text-text-primary truncate flex-1">{entityName}</span>
        <span className="text-[10px] text-text-muted">{seasonYear ? `${seasonYear} PLAYOFFS` : "PLAYOFFS"}</span>
      </div>

      {/* Stages as simple rows */}
      <div className="space-y-1">
        {display.map((stage, i) => {
          const prob = stage.probability ?? 0;
          const achieved = stage.status === "achieved";
          const eliminated = stage.status === "eliminated";
          
          return (
            <button
              key={stage.id}
              onClick={() => onStageClick?.(stage)}
              className={cn(
                "w-full flex items-center gap-2 text-xs rounded px-1 py-0.5 transition-colors",
                achieved ? "bg-accent-brand/10" : "hover:bg-surface-elevated/50",
                eliminated && "opacity-40"
              )}
            >
              <span className={cn(
                "w-2 h-2 rounded-full flex-shrink-0",
                achieved ? "bg-accent-brand" : eliminated ? "bg-accent-danger/50" : "bg-text-muted/30"
              )} />
              <span className="text-text-secondary flex-1 text-left truncate">
                {stage.stage_name.replace(/^(Make |Win )/, "")}
              </span>
              <div className="w-10 h-1 bg-surface-border rounded-full overflow-hidden">
                <div
                  className={cn("h-full rounded-full", achieved ? "bg-accent-brand" : "bg-text-muted/40")}
                  style={{ width: `${prob * 100}%` }}
                />
              </div>
              <span className={cn("font-mono font-medium min-w-[32px] text-right", achieved ? "text-accent-brand" : probabilityTextClass(prob))}>
                {achieved ? "done" : `${(prob * 100).toFixed(0)}%`}
              </span>
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}
