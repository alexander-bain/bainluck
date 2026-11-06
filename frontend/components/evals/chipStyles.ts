import type { ResultKind, TruthKind } from "@/lib/evals/truth";

/**
 * Chip shapes and tones for /evals, in a plain module so any component can
 * import them without crossing a client boundary.
 *
 * Badge grammar from `docs/design-system.md`: an uppercase pill with the word
 * always present. Tones follow the cockpit grammar (green / amber / red /
 * neutral), darkened one step for the 11px uppercase word so it stays legible
 * on its tint. The tone repeats the word; it never carries the meaning alone.
 */
export const CHIP_SHAPE =
  "inline-flex items-center text-[11px] leading-4 font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border";

export const TRUTH_TONE: Record<TruthKind, string> = {
  live: "bg-green-500/10 text-green-700 border-green-500/20",
  last_run: "bg-surface-elevated text-text-secondary border-surface-border",
  reviewed: "bg-surface-elevated text-text-secondary border-surface-border",
  planned: "bg-surface-card text-text-secondary border-dashed border-text-muted/60",
};

export const RESULT_TONE: Record<ResultKind, string> = {
  pass: "bg-green-500/10 text-green-700 border-green-500/20",
  fail: "bg-accent-danger/10 text-red-700 border-accent-danger/30",
  held: "bg-yellow-500/10 text-yellow-700 border-yellow-500/20",
  not_run: "bg-surface-elevated text-text-secondary border-surface-border",
  not_eligible: "bg-surface-elevated text-text-secondary border-surface-border",
  unknown: "bg-surface-card text-text-secondary border-surface-border",
};
