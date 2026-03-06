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
        className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-xl p-4"
        style={
          teamColors
            ? {
                borderTopColor: `rgb(${teamColors.primary})`,
                borderTopWidth: "3px",
              }
            : undefined
        }
        variants={staggerItem}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          {logoUrl && (
            <img
              src={logoUrl}
              alt={entityName}
              className="w-8 h-8 rounded-full object-contain bg-[var(--surface-elevated)]"
            />
          )}
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            {entityName}
          </h3>
        </div>

        {/* Horizontal stages */}
        <div className="flex items-end gap-1">
          {sortedStages.map((stage, idx) => {
            const prob = stage.probability ?? 0;
            const height = Math.max(20, prob * 80); // 20px min, 100px max
            const statusIcon = stageStatusIcon(stage.status);

            return (
              <motion.button
                key={stage.id}
                className="flex-1 flex flex-col items-center gap-1"
                onClick={() => onStageClick?.(stage)}
                variants={staggerItem}
              >
                {/* Probability */}
                <span className={`text-xs font-mono font-bold ${probabilityColor(prob)}`}>
                  {(prob * 100).toFixed(0)}%
                </span>

                {/* Bar */}
                <motion.div
                  className={`w-full rounded-t-sm ${probabilityBgClass(prob)} ${
                    stage.status === "achieved" ? "ring-2 ring-green-400" : ""
                  } ${stage.status === "eliminated" ? "opacity-30" : ""}`}
                  initial={{ height: 0 }}
                  animate={{ height }}
                  transition={transitionNormal}
                />

                {/* Stage name */}
                <span className="text-[10px] text-[var(--text-muted)] text-center mt-1 truncate w-full">
                  {stage.stage_name.replace(/^(Make |Win )/, "")}
                </span>

                {/* Status icon */}
                {statusIcon && (
                  <span
                    className={`text-xs ${
                      stage.status === "achieved" ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {statusIcon}
                  </span>
                )}
              </motion.button>
            );
          })}
        </div>
      </motion.div>
    );
  }

  // Vertical layout (default)
  return (
    <motion.div
      className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-xl overflow-hidden"
      style={
        teamColors
          ? {
              borderLeftColor: `rgb(${teamColors.primary})`,
              borderLeftWidth: "4px",
            }
          : undefined
      }
      variants={staggerItem}
    >
      {/* Header */}
      <div className="p-4 pb-2 flex items-center gap-3 border-b border-[var(--surface-border)]">
        {logoUrl && (
          <img
            src={logoUrl}
            alt={entityName}
            className="w-10 h-10 rounded-full object-contain bg-[var(--surface-elevated)]"
          />
        )}
        <div>
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            {entityName}
          </h3>
          <p className="text-xs text-[var(--text-muted)]">Playoff Progression</p>
        </div>
      </div>

      {/* Vertical ladder */}
      <motion.div
        className="p-4 relative"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {/* Connecting line */}
        <div className="absolute left-8 top-4 bottom-4 w-0.5 bg-[var(--surface-border)]" />

        {/* Stages */}
        <div className="space-y-3 relative">
          {sortedStages.map((stage, idx) => {
            const prob = stage.probability ?? 0;
            const statusIcon = stageStatusIcon(stage.status);
            const isAchieved = stage.status === "achieved";
            const isEliminated = stage.status === "eliminated";

            return (
              <motion.button
                key={stage.id}
                variants={staggerItem}
                onClick={() => onStageClick?.(stage)}
                className={`
                  w-full flex items-center gap-4 p-3 rounded-lg
                  transition-colors duration-[var(--duration-fast)]
                  ${isAchieved ? "bg-green-500/10 border border-green-500/30" : ""}
                  ${isEliminated ? "opacity-50" : ""}
                  ${!isAchieved && !isEliminated ? "bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80" : ""}
                `}
              >
                {/* Stage indicator dot */}
                <div
                  className={`
                    w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold
                    ${isAchieved ? "bg-green-500 text-white" : ""}
                    ${isEliminated ? "bg-red-500/50 text-white" : ""}
                    ${!isAchieved && !isEliminated ? `${probabilityBgClass(prob)}/30` : ""}
                  `}
                >
                  {statusIcon}
                </div>

                {/* Stage name */}
                <div className="flex-1 text-left">
                  <div className="text-sm font-medium text-[var(--text-primary)]">
                    {stage.stage_name}
                  </div>
                </div>

                {/* Probability */}
                <div className="flex items-center gap-2">
                  {/* Mini bar */}
                  <div className="w-16 h-1.5 bg-[var(--surface-base)] rounded-full overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full ${probabilityBgClass(prob)}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${prob * 100}%` }}
                      transition={transitionNormal}
                    />
                  </div>

                  {/* Percentage */}
                  <span
                    className={`text-sm font-mono font-bold min-w-[40px] text-right ${probabilityColor(prob)}`}
                  >
                    {(prob * 100).toFixed(0)}%
                  </span>
                </div>
              </motion.button>
            );
          })}
        </div>
      </motion.div>
    </motion.div>
  );
}
