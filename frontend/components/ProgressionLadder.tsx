"use client";

/**
 * ProgressionLadder — Visual ladder showing playoff/tournament progression.
 *
 * For a single team/player, shows probability of reaching each stage
 * as a vertical "ladder" with rungs representing stages. Higher stages
 * at top, lower probability as you go up (harder to reach).
 *
 * Visual design:
 * - Vertical layout with stages as horizontal "rungs"
 * - Connecting line shows progression path
 * - Probability bar fills each rung proportionally
 * - Color intensity indicates likelihood
 * - Optional "achieved" state for completed stages
 */

import { motion } from "framer-motion";
import { staggerContainer, staggerItem, transitionNormal } from "@/lib/animations";

interface ProgressionStage {
  id: number;
  name: string;
  stage_name: string;
  stage_order: number;
  probability: number | null;
  status?: "pending" | "achieved" | "eliminated";
  source?: string;
}

interface ProgressionLadderProps {
  /** Team or player name */
  entityName: string;
  /** Stages in order (lowest to highest) */
  stages: ProgressionStage[];
  /** Optional logo/avatar URL */
  logoUrl?: string;
  /** Team colors for styling */
  teamColors?: { primary: string; secondary: string };
  /** Click handler for stages */
  onStageClick?: (stage: ProgressionStage) => void;
  /** Compact horizontal layout */
  horizontal?: boolean;
}

function probabilityColor(prob: number): string {
  if (prob >= 0.7) return "text-green-400";
  if (prob >= 0.4) return "text-amber-400";
  if (prob >= 0.15) return "text-orange-400";
  return "text-red-400";
}

function probabilityBgClass(prob: number): string {
  if (prob >= 0.7) return "bg-green-500";
  if (prob >= 0.4) return "bg-amber-500";
  if (prob >= 0.15) return "bg-orange-500";
  return "bg-red-500";
}

function stageStatusIcon(status?: string): string | null {
  if (status === "achieved") return "\u2713"; // checkmark
  if (status === "eliminated") return "\u2717"; // x mark
  return null;
}

export default function ProgressionLadder({
  entityName,
  stages,
  logoUrl,
  teamColors,
  onStageClick,
  horizontal = false,
}: ProgressionLadderProps) {
  // Sort stages by order (highest first for vertical, lowest first for horizontal)
  const sortedStages = [...stages].sort((a, b) =>
    horizontal ? a.stage_order - b.stage_order : b.stage_order - a.stage_order
  );

  if (horizontal) {
    return (
      <motion.div
        className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-lg p-3"
        style={
          teamColors
            ? {
                borderTopColor: `rgb(${teamColors.primary})`,
                borderTopWidth: "2px",
              }
            : undefined
        }
        variants={staggerItem}
      >
        {/* Compact Header */}
        <div className="flex items-center gap-2 mb-2">
          {logoUrl && (
            <img
              src={logoUrl}
              alt={entityName}
              className="w-5 h-5 rounded-full object-contain bg-[var(--surface-elevated)]"
            />
          )}
          <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate flex-1">
            {entityName}
          </h3>
        </div>

        {/* Compact horizontal stages */}
        <div className="flex items-end gap-0.5">
          {sortedStages.map((stage) => {
            const prob = stage.probability ?? 0;
            const height = Math.max(12, prob * 48); // 12px min, 60px max
            const isAchieved = stage.status === "achieved";

            return (
              <button
                key={stage.id}
                className="flex-1 flex flex-col items-center gap-0.5"
                onClick={() => onStageClick?.(stage)}
              >
                {/* Probability */}
                <span className={`text-[10px] font-mono font-bold ${probabilityColor(prob)}`}>
                  {(prob * 100).toFixed(0)}%
                </span>

                {/* Bar */}
                <div
                  className={`w-full rounded-t-sm ${probabilityBgClass(prob)} ${
                    isAchieved ? "ring-1 ring-green-400" : ""
                  } ${stage.status === "eliminated" ? "opacity-30" : ""}`}
                  style={{ height }}
                />

                {/* Stage name - abbreviated */}
                <span className="text-[9px] text-[var(--text-muted)] text-center truncate w-full">
                  {stage.stage_name.replace(/^(Make |Win )/, "").slice(0, 6)}
                </span>
              </button>
            );
          })}
        </div>
      </motion.div>
    );
  }

  // Vertical layout (default) - compact version
  return (
    <motion.div
      className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-lg overflow-hidden"
      style={
        teamColors
          ? {
              borderLeftColor: `rgb(${teamColors.primary})`,
              borderLeftWidth: "3px",
            }
          : undefined
      }
      variants={staggerItem}
    >
      {/* Compact Header */}
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--surface-border)]/50">
        {logoUrl && (
          <img
            src={logoUrl}
            alt={entityName}
            className="w-6 h-6 rounded-full object-contain bg-[var(--surface-elevated)]"
          />
        )}
        <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate flex-1">
          {entityName}
        </h3>
        <span className="text-[10px] text-[var(--text-muted)] uppercase">Playoffs</span>
      </div>

      {/* Compact vertical stages */}
      <div className="px-2 py-2 space-y-1">
        {sortedStages.map((stage) => {
          const prob = stage.probability ?? 0;
          const statusIcon = stageStatusIcon(stage.status);
          const isAchieved = stage.status === "achieved";
          const isEliminated = stage.status === "eliminated";

          return (
            <button
              key={stage.id}
              onClick={() => onStageClick?.(stage)}
              className={`
                w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs
                transition-colors duration-[var(--duration-fast)]
                ${isAchieved ? "bg-green-500/10" : ""}
                ${isEliminated ? "opacity-40" : ""}
                ${!isAchieved && !isEliminated ? "hover:bg-[var(--surface-elevated)]" : ""}
              `}
            >
              {/* Status dot */}
              <div
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  isAchieved ? "bg-green-500" : 
                  isEliminated ? "bg-red-500/50" : 
                  probabilityBgClass(prob)
                }`}
              />

              {/* Stage name */}
              <span className="flex-1 text-left text-[var(--text-secondary)] truncate">
                {stage.stage_name.replace(/^(Make |Win )/, "")}
              </span>

              {/* Mini probability bar */}
              <div className="w-12 h-1 bg-[var(--surface-base)] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${probabilityBgClass(prob)}`}
                  style={{ width: `${prob * 100}%` }}
                />
              </div>

              {/* Percentage */}
              <span className={`font-mono font-bold min-w-[32px] text-right ${probabilityColor(prob)}`}>
                {(prob * 100).toFixed(0)}%
              </span>
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}
