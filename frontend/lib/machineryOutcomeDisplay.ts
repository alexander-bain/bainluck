import {
  BELOW_ONE_PERCENT,
  formatGroupedProbability,
  probabilityValue,
} from "@/lib/probabilityDisplay";
import { renderedPercent } from "@/lib/renderedPercent";

export const ELIMINATED_LABEL = "Eliminated";
export const NO_RECENT_PROBABILITY_LABEL = "No recent probability";

export type MachineryOutcomeDisplayState =
  | "live"
  | "sub_one_percent"
  | "eliminated"
  | "no_recent_probability";

export interface MachineryOutcomeDisplay {
  state: MachineryOutcomeDisplayState;
  label: string;
  barWidthPercent: number;
  muted: boolean;
}

/**
 * Resolve the displayed probability/status label and bar state for a grouped
 * machinery outcome row. Division-race rows carry an explicit boolean
 * ``settled_out`` flag (441: A / #13777); every other row omits it and keeps
 * today's exact ``formatGroupedProbability`` rendering.
 */
export function describeMachineryOutcomeDisplay(row: {
  probability?: unknown;
  rendered_percent?: unknown;
  unfloored_percent?: unknown;
  settled_out?: unknown;
}): MachineryOutcomeDisplay {
  const allocation =
    typeof row.rendered_percent === "number" && Number.isFinite(row.rendered_percent)
      ? row.rendered_percent
      : null;
  const prob =
    typeof row.probability === "number" || typeof row.probability === "string"
      ? probabilityValue(row.probability)
      : NaN;

  if (row.settled_out === true) {
    return {
      state: "eliminated",
      label: ELIMINATED_LABEL,
      barWidthPercent: 0,
      muted: true,
    };
  }

  if (typeof row.settled_out === "boolean") {
    if (!Number.isFinite(prob) || prob <= 0) {
      return {
        state: "no_recent_probability",
        label: NO_RECENT_PROBABILITY_LABEL,
        barWidthPercent: 0,
        muted: true,
      };
    }
    if (prob > 0 && prob < 0.01) {
      return {
        state: "sub_one_percent",
        label: BELOW_ONE_PERCENT,
        barWidthPercent: 2,
        muted: true,
      };
    }
    const pct = allocation ?? renderedPercent(prob) ?? 0;
    return {
      state: "live",
      label: formatGroupedProbability(row),
      barWidthPercent: Math.max(4, Math.min(100, pct)),
      muted: false,
    };
  }

  const pct =
    allocation ?? renderedPercent(Number.isFinite(prob) ? prob : null) ?? 0;
  return {
    state: "live",
    label: formatGroupedProbability(row),
    barWidthPercent: Math.max(4, Math.min(100, pct)),
    muted: false,
  };
}
