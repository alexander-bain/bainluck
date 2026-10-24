import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { SERIES_COLORS, conventionalSeriesColor } from "@/lib/seriesColors";
import type { FeedFuturesData, FeedFuturesOutcome } from "@/lib/types";

export const US_CONGRESS_CONTROL_STORY_PREFIX = "story:us_congress_control:";

const CONGRESS_STORY_KEY_RE = /^story:us_congress_control:\d{4}$/;
const TERMINAL_STATUSES = new Set([
  "closed",
  "resolved",
  "settled",
  "finalized",
  "final",
]);

/**
 * Fixed slot order on every Congress control row (#9880 / Option A ruling):
 * registry blue party (`SERIES_COLORS[0]`) on the left, red party
 * (`SERIES_COLORS[1]`) on the right. Leadership is carried by type size
 * (22px vs 15px), never by swapping sides, and only when the PRINTED percents
 * differ: an exact 50% / 50% gives neither side the larger size.
 */
export const PARTY_CONTROL_SLOT_COLORS = [
  SERIES_COLORS[0],
  SERIES_COLORS[1],
] as const;

export interface PartyControlSide {
  outcome: FeedFuturesOutcome;
  name: string;
  probability: number;
  renderedPercent: number;
  percentText: string;
  widthPercent: string;
  color: string;
  isLeader: boolean;
}

export interface PartyControlRowModel {
  a: PartyControlSide;
  b: PartyControlSide;
  /** `null` when both sides print the same percent — a tie crowns no one. */
  leaderIdx: 0 | 1 | null;
  residual: number;
}

export interface StrippedPartyLeadCaption {
  text: string;
  party: string | null;
  rest: string;
  deleted: string | null;
}

export function isCongressControlStoryKey(
  storyKey: string | null | undefined,
): boolean {
  return typeof storyKey === "string" && CONGRESS_STORY_KEY_RE.test(storyKey);
}

function isTerminalFuturesRow(data: FeedFuturesData): boolean {
  const winner = data.winner?.trim();
  const status = (data.status ?? "").toLowerCase();
  return (
    data.resolved === true || Boolean(winner) || TERMINAL_STATUSES.has(status)
  );
}

/**
 * Pure eligibility and layout model for the Option A two-sided party row (#9880).
 *
 * Returns `null` on any refusal so the caller falls back to `FuturesCompactRow`:
 * - not a `duel` market, or already resolved/terminal
 * - not an exact 2-answer board (`outcome_count !== 2` or `remaining_outcome_count !== 0`)
 * - either answer fails whole-label US party recognition via `conventionalSeriesColor`,
 *   or both map to the same party (duplicate alias)
 * - either answer lacks a finite `(0, 1]` probability or integer `rendered_percent`
 *   (no client-side `100 - x` complement or raw-probability rounding)
 * - raw probabilities sum above `1.000` (never normalized or squeezed)
 */
export function partyControlRowProps(
  data: FeedFuturesData | null | undefined,
): PartyControlRowModel | null {
  if (!data || data.market_type !== "duel") return null;
  if (isTerminalFuturesRow(data)) return null;

  const outs = Array.isArray(data.top_outcomes) ? data.top_outcomes : [];
  if (outs.length !== 2) return null;
  if (data.outcome_count != null && data.outcome_count !== 2) return null;

  const discoverCard = (
    data as { discover_card?: { remaining_outcome_count?: number | null } }
  ).discover_card;
  const directRemaining = (
    data as { remaining_outcome_count?: number | null }
  ).remaining_outcome_count;
  if ((discoverCard?.remaining_outcome_count ?? 0) !== 0) return null;
  if ((directRemaining ?? 0) !== 0) return null;

  const colors = outs.map((o) =>
    conventionalSeriesColor(String(o?.name ?? "")),
  );
  if (
    colors.some(
      (c) =>
        c === null ||
        !PARTY_CONTROL_SLOT_COLORS.includes(
          c as (typeof PARTY_CONTROL_SLOT_COLORS)[number],
        ),
    )
  ) {
    return null;
  }
  if (colors[0] === colors[1]) return null;

  for (const o of outs) {
    if (
      typeof o?.probability !== "number" ||
      !Number.isFinite(o.probability) ||
      o.probability <= 0 ||
      o.probability > 1
    ) {
      return null;
    }
    if (
      typeof o?.rendered_percent !== "number" ||
      !Number.isInteger(o.rendered_percent) ||
      o.rendered_percent < 0 ||
      o.rendered_percent > 100
    ) {
      return null;
    }
  }

  const rawSum = (outs[0].probability as number) + (outs[1].probability as number);
  if (!Number.isFinite(rawSum) || rawSum > 1 + 1e-9) return null;

  const aIdx = colors.indexOf(PARTY_CONTROL_SLOT_COLORS[0]);
  const bIdx = colors.indexOf(PARTY_CONTROL_SLOT_COLORS[1]);
  if (aIdx < 0 || bIdx < 0) return null;

  const outA = outs[aIdx];
  const outB = outs[bIdx];
  const probA = outA.probability as number;
  const probB = outB.probability as number;
  const rendA = outA.rendered_percent as number;
  const rendB = outB.rendered_percent as number;
  const textA = formatProbabilityPercent(probA, { rendered: rendA });
  const textB = formatProbabilityPercent(probB, { rendered: rendB });
  // Type size IS the lead, so it follows what the reader can see: equal printed
  // percents get equal emphasis, whatever edge the raw probabilities carry.
  const leaderIdx: 0 | 1 | null =
    textA === textB
      ? null
      : rendA !== rendB
        ? rendA > rendB
          ? 0
          : 1
        : probA > probB
          ? 0
          : 1;
  const residual = Math.max(0, 1 - rawSum);

  const buildSide = (
    outcome: FeedFuturesOutcome,
    probability: number,
    renderedPercent: number,
    percentText: string,
    color: string,
    slotIdx: 0 | 1,
  ): PartyControlSide => ({
    outcome,
    name: outcome.name.trim(),
    probability,
    renderedPercent,
    percentText,
    widthPercent: `${(probability * 100).toFixed(2)}%`,
    color,
    isLeader: leaderIdx === slotIdx,
  });

  return {
    a: buildSide(outA, probA, rendA, textA, PARTY_CONTROL_SLOT_COLORS[0], 0),
    b: buildSide(outB, probB, rendB, textB, PARTY_CONTROL_SLOT_COLORS[1], 1),
    leaderIdx,
    residual,
  };
}

/**
 * Guarded caption deletion for a two-sided party row (ruling 003; Decision D-E).
 *
 * Deletes ONLY `leads at {pct},` when the caption begins `{party} leads at {pct},`
 * and `{party}` with that exact `{pct}` is visibly printed on this row. Preserves
 * the party name attached to the remaining movement clause so the subject stays
 * unambiguous when both parties are shown. Leaves any mismatch or other shape untouched.
 */
export function stripVisiblePartyLeadClause(
  caption: string | null | undefined,
  visible: ReadonlyArray<{ name: string; pct: string }>,
): StrippedPartyLeadCaption {
  const raw = String(caption ?? "").trim();
  if (!raw) {
    return { text: "", party: null, rest: "", deleted: null };
  }
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  for (const v of visible) {
    const name = String(v?.name ?? "").trim();
    const pct = String(v?.pct ?? "").trim();
    if (!name || !pct) continue;
    const re = new RegExp(
      `^(${esc(name)})\\s+leads at\\s+(${esc(pct)}),\\s*(.+)$`,
      "i",
    );
    const m = raw.match(re);
    if (m) {
      return {
        text: `${m[1]} ${m[3]}`,
        party: m[1],
        rest: ` ${m[3]}`,
        deleted: `leads at ${m[2]},`,
      };
    }
  }
  return { text: raw, party: null, rest: raw, deleted: null };
}
