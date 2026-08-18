/**
 * THE DIVERGENCE rail — the pregame mark vs where a prop is now.
 *
 * UX-P098 (UX-AMBITION-1, slice 1). Transcribed from
 * `.claude/handoff/strategy_divergence_rail_spec.md` plus Alex's three ruled
 * verdicts, which arrived through Fable and are NOT re-litigated here:
 *
 *   V1  the pregame page LEADS with five live questions, not the whole prop
 *       set; the full set sits behind a single expand.
 *   V2  every selected row renders a travelled bar; a row that cleared the
 *       measured surprise threshold ADDITIONALLY renders a sentence. The
 *       sentence is an escalation, never an alternative rendering.
 *   V3  a prop that vanished for want of trading may vanish silently; a prop
 *       that vanished for any OTHER taxonomy reason must surface — and a
 *       reason that reads UNKNOWN renders as unknown, never as silence.
 *
 * ZERO new backend fields. Verified on production 2026-08-18: `pregame_mark`
 * ships on the `player_props[]` rows the endpoint already serves.
 */

import { parsePlayerName } from "./playerPropsGrouping";
import type { PlayerPropRow } from "./playerPropsGrouping";

/**
 * The surprise threshold — MEASURED, not tuned.
 *
 * Travel distribution over 143 production props carrying both marks
 * (`15199882` scheduled + `14788546` completed, captured 2026-08-18):
 * p50 0.5 pts · p75 11.7 · **p90 21.0** · p95 27.7 · max 40.0.
 *
 * The distribution is strongly BIMODAL — the median prop does not move at all,
 * and the ones that move, move far. That is what makes travel a real signal
 * here rather than noise being dressed up.
 *
 * 0.20 sits at p90 = 11% of props (16/143), so a typical five-row rail carries
 * one or two sentences and three or four bare bars, which is the shape V2
 * describes. At 0.15 a majority of the rail becomes prose and the escalation
 * stops meaning anything.
 *
 * If a future population flattens that bimodality that is A NEW MEASUREMENT TO
 * RECORD, not a knob to turn. Re-derive per sport when n allows — the constant
 * is a measurement's current value, not a preference.
 */
export const PROP_SURPRISE_TRAVEL = 0.2;

/** V1: five, not "about five". */
export const RAIL_MAX_ROWS = 5;

/**
 * At most two rows per player. Without it, one player having a big night owns
 * the whole rail — and the rail's job is to describe the GAME. "Hits", "Home
 * Runs" and "Hits + Runs + RBI" all move together for a player who just
 * homered, so the collision is a matter of time even when today's payload
 * happens to rank five distinct players.
 */
export const RAIL_MAX_PER_PLAYER = 2;

/**
 * V3's disappearance taxonomy. Only the first two are benign; the rest are
 * Alex's "that sounds very bad" cases and must reach the screen.
 *
 * `unknown` is deliberately a MEMBER of this enum rather than a fallback to
 * `no_real_price`. Claiming "it never traded" when we cannot tell "it never
 * traded" from "we mis-classified it" is exactly the invention gotcha #53
 * forbids — an empty is not an absence.
 */
export type PropDropReason =
  /** 1 — never traded / no real price. Benign: hide silently. */
  | "no_real_price"
  /** 2 — outside the interesting band. Benign, and applied UPSTREAM (step 9). */
  | "outside_band"
  /** 3 — mis-classified into another section. The #1976 §5 class. NOT benign. */
  | "misclassified"
  /** 4 — linked to the wrong game (#1976 §3 / #1970). NOT benign. */
  | "wrong_game"
  /** 5 — settled but never graded (#1976 §2). NOT benign. */
  | "ungraded"
  /** Unreadable for a reason we cannot name. Renders AS unknown. NOT benign. */
  | "unknown";

const BENIGN_REASONS: ReadonlySet<PropDropReason> = new Set<PropDropReason>([
  "no_real_price",
  "outside_band",
]);

export function isBenignDrop(reason: PropDropReason): boolean {
  return BENIGN_REASONS.has(reason);
}

export interface DivergenceRow {
  /** Stable identity for React keys and tests: market name + threshold. */
  key: string;
  /** The QUESTION, e.g. "Alec Bohm: 1+ home runs". Never the provider string. */
  label: string;
  player: string;
  stat: string;
  threshold: number;
  /** Where the market opened the question, 0..1. */
  pregameMark: number;
  /** Where it is now, 0..1. */
  current: number;
  /** |current - pregameMark|, 0..1. */
  travel: number;
  /** Which way it travelled. `flat` when travel rounds to nothing. */
  direction: "over" | "under" | "flat";
  /** travel >= PROP_SURPRISE_TRAVEL. */
  surprising: boolean;
  /** Present only when `surprising`. V2: the sentence is an escalation. */
  sentence: string | null;
  /** Settled games freeze: the bar shows the journey, it stops implying motion. */
  settled: boolean;
}

export interface DivergenceDrop {
  reason: PropDropReason;
  benign: boolean;
  count: number;
  /** Up to a few examples, for the surfaced explanation. */
  examples: string[];
}

export interface DivergenceResult {
  rows: DivergenceRow[];
  /** Taxonomy-classified losses. Benign ones may be hidden; others may not. */
  dropped: DivergenceDrop[];
  /** Total non-benign losses — the number V3 says must never be swallowed. */
  nonBenignCount: number;
  /**
   * Eligible props that simply ranked below the top five. NOT a taxonomy loss:
   * these are reachable through the expand, so they are not "lost markets".
   * Kept separate precisely so rail capacity can never be mistaken for a defect.
   */
  notSelected: number;
  /** Total eligible rows before the cap — the denominator for "5 of N". */
  eligible: number;
  /**
   * Why there are no rows, when there are none. Same three-way vocabulary
   * `groupPlayerProps` already uses, extended rather than reinvented.
   */
  emptyReason: "none" | "clean" | "unreadable" | null;
}

export interface DivergenceInput {
  playerProps?: readonly PlayerPropRow[] | null;
  /** Event status; a settled game freezes the rail. */
  status?: string | null;
}

const SETTLED_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "closed",
  "settled",
  "final",
  "resolved",
]);

export function isSettledStatus(status?: string | null): boolean {
  return SETTLED_STATUSES.has((status || "").toLowerCase());
}

function isFiniteNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * Both providers' lines read as "N or more", so both render as `N+`.
 *
 *   Polymarket  "... O/U 3.5" -> Over means at least 4        -> "4+"
 *   Kalshi      threshold 4.0 -> the OUTCOME says "Trea Turner: 4+", i.e. the
 *                                integer is already inclusive -> "4+"
 *
 * The Kalshi half is read off the real payload rather than inferred: on
 * `15199886`, threshold `4.0` ships beside outcome text `"Trea Turner: 4+"` and
 * threshold `1.0` beside `"Kyle Schwarber: 1+"`. Rendering those as "over 4"
 * would be a different (and wrong) question — off by one against the provider's
 * own words.
 */
function thresholdPhrase(threshold: number): string {
  return `${Math.ceil(threshold)}+`;
}

/** "Janson Junk" -> "Junk's". Deterministic; no possessive edge-case cleverness
 *  beyond the standard trailing-s rule. */
function possessive(player: string): string {
  const parts = player.trim().split(/\s+/);
  const last = parts[parts.length - 1] || player;
  return last.endsWith("s") ? `${last}'` : `${last}'s`;
}

function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/**
 * The sentence, for surprising rows only. Arithmetic over two numbers already
 * on the row — deterministic, reproducible, and renderable offline from the
 * payload alone. Never `hook_description`, never an LLM.
 */
export function divergenceSentence(
  player: string,
  label: string,
  pregameMark: number,
  current: number,
  settled: boolean,
): string {
  const question = label.includes(": ") ? label.split(": ").slice(1).join(": ") : label;
  const tail = settled
    ? `finished at ${pct(current)}.`
    : `it's ${pct(current)} now.`;
  return `${possessive(player)} ${question} opened at ${pct(pregameMark)} — ${tail}`;
}

/**
 * Select the rail's rows and account for everything that did not make it.
 *
 * Ranked by travel over the props eligible to be shown at all. Eligibility is
 * "has both a pregame mark and a current price"; the interesting band
 * (0.05..0.95) is NOT re-implemented here — the rail inherits whatever the
 * endpoint served, per spec.
 */
export function selectDivergenceRows(input: DivergenceInput): DivergenceResult {
  const rows = input.playerProps ?? [];
  const settled = isSettledStatus(input.status);

  const empty = (emptyReason: DivergenceResult["emptyReason"]): DivergenceResult => ({
    rows: [],
    dropped: [],
    nonBenignCount: 0,
    notSelected: 0,
    eligible: 0,
    emptyReason,
  });

  if (rows.length === 0) return empty("none");

  const dropCounts = new Map<PropDropReason, { count: number; examples: string[] }>();
  const noteDrop = (reason: PropDropReason, at: string) => {
    const cur = dropCounts.get(reason) ?? { count: 0, examples: [] };
    cur.count += 1;
    if (cur.examples.length < 3 && at) cur.examples.push(at);
    dropCounts.set(reason, cur);
  };

  // THE DEDUPE KEY MUST BE THE PARSED IDENTITY, NOT THE MARKET NAME.
  //
  // The two providers put the player in different places, and a name-keyed
  // dedupe is wrong for one of them in a way that DELETES DATA:
  //
  //   Polymarket  market "Alec Bohm: Home Runs O/U 0.5"    outcome "Over"/"Under"
  //               -> two legs, ONE question. Must collapse.
  //   Kalshi      market "Philadelphia vs Miami: Hits"     outcome "Edmundo Sosa: 2+"
  //               -> ONE market name covering MANY DISTINCT PLAYERS. Must NOT
  //                  collapse; two players on the same line share market name
  //                  AND threshold and differ only in the outcome.
  //
  // Keying on `market_name|threshold` reads correctly on the Polymarket shape
  // and silently drops players on the Kalshi one. That is #1639 exactly — "17
  // distinct players collapsed into ONE card, titled with the matchup and
  // wearing whichever headshot arrived first" — so this is a re-entry into a
  // known defect, not a hypothetical.
  //
  // Parsing FIRST and keying on `player|stat|threshold` is correct for both:
  // the Over/Under legs parse to the same identity and collapse, while distinct
  // players parse to distinct identities and survive.
  const seen = new Set<string>();
  const candidates: DivergenceRow[] = [];

  for (const row of rows) {
    const marketName = (row.market_name || "").trim();
    const outcomeName = (row.outcome_name || "").trim();
    const threshold = row.threshold;
    const at = marketName || outcomeName || "(unnamed row)";

    if (!marketName || !isFiniteNumber(threshold)) {
      // A prop row with no name or no line cannot be read, and we cannot tell
      // WHY it is shaped that way from here. V3: that renders as unknown.
      noteDrop("unknown", at);
      continue;
    }

    const current = row.over_probability;
    const pregameMark = (row as PlayerPropRow & { pregame_mark?: number | null })
      .pregame_mark;

    if (!isFiniteNumber(current) || !isFiniteNumber(pregameMark)) {
      // No real price on at least one end. This IS reason 1, and it is the one
      // absence Alex is willing to hide.
      noteDrop("no_real_price", at);
      continue;
    }

    const parsed = parsePlayerName(marketName, outcomeName);
    if (!parsed || !parsed.player) {
      // The row is priced and named but does not parse as a player prop — the
      // shape #1976 §5 was made of. Not benign; we do not know it never traded,
      // we know we could not read it.
      noteDrop("misclassified", at);
      continue;
    }

    const key = `${parsed.player}|${parsed.stat}|${threshold}`;
    if (seen.has(key)) continue; // the sibling Over/Under leg of the SAME question
    seen.add(key);

    const travel = Math.abs(current - pregameMark);
    candidates.push({
      key,
      label: `${parsed.player}: ${thresholdPhrase(threshold)} ${parsed.stat.toLowerCase()}`,
      player: parsed.player,
      stat: parsed.stat,
      threshold,
      pregameMark,
      current,
      travel,
      direction: travel < 0.005 ? "flat" : current > pregameMark ? "over" : "under",
      surprising: travel >= PROP_SURPRISE_TRAVEL,
      sentence: null,
      settled,
    });
  }

  const dropped: DivergenceDrop[] = [...dropCounts.entries()].map(
    ([reason, { count, examples }]) => ({
      reason,
      benign: isBenignDrop(reason),
      count,
      examples,
    }),
  );
  const nonBenignCount = dropped
    .filter((d) => !d.benign)
    .reduce((n, d) => n + d.count, 0);

  if (candidates.length === 0) {
    // Rows existed and none survived. Which empty it is depends on whether a
    // guard caught something — `unreadable` when it did, `clean` when the data
    // was simply benign-empty.
    return {
      ...empty(nonBenignCount > 0 ? "unreadable" : "clean"),
      dropped,
      nonBenignCount,
    };
  }

  // Rank by travel, then by current price so the order is total and stable
  // across renders (a pure tie on travel is common — many props do not move).
  candidates.sort(
    (a, b) => b.travel - a.travel || b.current - a.current || a.key.localeCompare(b.key),
  );

  const perPlayer = new Map<string, number>();
  const selected: DivergenceRow[] = [];
  for (const row of candidates) {
    if (selected.length >= RAIL_MAX_ROWS) break;
    const n = perPlayer.get(row.player) ?? 0;
    if (n >= RAIL_MAX_PER_PLAYER) continue;
    perPlayer.set(row.player, n + 1);
    selected.push(
      row.surprising
        ? {
            ...row,
            sentence: divergenceSentence(
              row.player,
              row.label,
              row.pregameMark,
              row.current,
              settled,
            ),
          }
        : row,
    );
  }

  return {
    rows: selected,
    dropped,
    nonBenignCount,
    notSelected: candidates.length - selected.length,
    eligible: candidates.length,
    emptyReason: null,
  };
}
