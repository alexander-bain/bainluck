/**
 * #10868 — THE HOCKEY JOURNEY SCREEN (web), SHARED PIECES.
 *
 * PILLARS: FORMATTING / TRUTH. SHIP: on `nhl-journey` the web page prints the
 * same chances, goals, forecasts, history and prop readings the iPhone screen
 * prints, decided by the same rules, in the screen's paired grammar.
 *
 * This file holds what every part of the screen shares: the phase, the slot
 * shape, the words a value is said in, and the two settlement rules. It
 * decides nothing a production authority already decides — each helper below
 * names the web authority it calls, or the native rule it mirrors and why.
 *
 * PURE: no I/O, no React, no clock — `nowMs` is always a parameter.
 */

import { isFinishedStatus, isSuspendedStatus } from "@/lib/eventState";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { formatSourceStamp } from "@/lib/sourceAge";
import { formatPoints } from "@/lib/nflEventCardDeck";
import { isAuthoritativeResolution } from "@/lib/resolutionAuthority";
import type { HockeyJourneyPhase, HockeyJourneySlot } from "./hockeyJourneyTypes";

export type { HockeyJourneyPhase, HockeyJourneySlot } from "./hockeyJourneyTypes";

/** `Date.parse`, or null for an absent or unreadable stamp. */
export function parseMs(iso: string | null | undefined): number | null {
  if (typeof iso !== "string" || iso === "") return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

/**
 * Whether the clock agrees the event has started. A missing or unreadable
 * start counts as STARTED — native `EventState.hasStarted`
 * (EventState.swift:52), mirrored because web's `eventState.ts` has no
 * clock-only predicate with that default (`startedWithoutResult` answers a
 * different question and only for `scheduled`).
 */
export function hasStartedByClock(commenceTime: string | null | undefined, nowMs: number): boolean {
  const start = parseMs(commenceTime);
  return start === null || start <= nowMs;
}

/**
 * The phase, from the STATUS alone (native `HockeyJourneyPageAdapter10868.phase`):
 * a finished status is final (`isFinishedStatus`, eventState.ts:24); `live`, or
 * `suspended` once the start has passed (`isSuspendedStatus`, eventState.ts:33,
 * plus native `isSuspendedAndStarted`), is during play; everything else —
 * including a `scheduled` row past its listed start — is before. Never read
 * from a score, a price or a clock alone.
 */
export function hockeyJourneyPhase(
  event: { status?: string | null; commence_time?: string | null },
  nowMs: number,
): HockeyJourneyPhase {
  if (isFinishedStatus(event.status)) return "final";
  if (event.status === "live") return "live";
  if (isSuspendedStatus(event.status) && hasStartedByClock(event.commence_time, nowMs)) return "live";
  return "before";
}


export function absentSlot(text: string): HockeyJourneySlot {
  return { kind: "absent", text };
}

/** `formatProbabilityPercent`'s figure said in words; the figure itself is unchanged. */
export function spokenPercent(text: string): string {
  return text.replace(/</g, "under ").replace(/>/g, "over ").replace(/%/g, " percent");
}

/**
 * A chance through production's one percent rule (`formatProbabilityPercent`,
 * probabilityDisplay.ts:118-147): whole percents, `<1%`/`>99%` at the ends, and
 * a served or pair-decided integer (`rendered`) when the caller holds one.
 */
export function probabilitySlot(value: number, rendered?: number | null): HockeyJourneySlot {
  const text = formatProbabilityPercent(value, { rendered: rendered ?? null });
  return { kind: "value", text, spoken: spokenPercent(text) };
}

/** A goal count, said as goals. */
export function goalsSlot(count: number): HockeyJourneySlot {
  return { kind: "value", text: `${count}`, spoken: count === 1 ? "1 goal" : `${count} goals` };
}

/**
 * A forecast in goals at its OWN precision: a whole number stays whole, a
 * projection keeps one decimal — `formatPoints` (nflEventCardDeck.ts:213), the
 * web twin of native `NBALadderCard9483.number`. A served 3.5 / 2.5 prints
 * "3.5" / "2.5", never a rounded "4" / "3".
 */
export function forecastSlot(goals: number): HockeyJourneySlot {
  const text = formatPoints(goals);
  return { kind: "value", text, spoken: text === "1" ? "1 goal" : `${text} goals` };
}

/**
 * "4 Oct, 5:59 AM" in the reader's own zone — `formatSourceStamp`
 * (sourceAge.ts:259), the one precise-stamp formatter on web.
 */
export function clockWords(at: string | number | null | undefined): string | null {
  if (at === null || at === undefined) return null;
  const iso = typeof at === "number" ? (Number.isFinite(at) ? new Date(at).toISOString() : null) : at;
  return iso ? formatSourceStamp(iso) : null;
}

/** "7:00 PM" in the reader's zone (the before-game state line). */
export function timeWords(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/** "Fri, Oct 30" in the reader's zone (the state line's day). */
export function dayWords(ms: number): string {
  return new Date(ms).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

/** Non-empty parts joined by " · ", or null when nothing is left. */
export function joined(parts: Array<string | null | undefined>): string | null {
  const kept = parts.filter((p): p is string => typeof p === "string" && p !== "");
  return kept.length === 0 ? null : kept.join(" · ");
}

/** A finite probability in [0, 1], or null. A real 0 stays. */
export function admissible(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
}

/** The score producer's name as served ("espn" reads "ESPN"). */
export function sourceWord(source: string): string {
  return source.toLowerCase() === "espn" ? "ESPN" : source;
}

/** The retraction a venue serves instead of a grade; never a settlement. */
export const RETRACTED_RESOLUTION_SOURCE = "ungradeable_result";

/**
 * The served settlement's verdict, or null: a winner flag with a venue's own
 * `resolution_source` (`isAuthoritativeResolution`, resolutionAuthority.ts),
 * never the retraction. Unknown is null — never "lost".
 */
export function servedSettlement(
  isWinner: boolean | null | undefined,
  resolutionSource: string | null | undefined,
): boolean | null {
  if (typeof isWinner !== "boolean") return null;
  if (!resolutionSource || resolutionSource === RETRACTED_RESOLUTION_SOURCE) return null;
  return isAuthoritativeResolution(resolutionSource) ? isWinner : null;
}

/** Which side won, from the served verdict first, else the scores. */
export type HockeyJourneyOutcome = "home" | "away" | "draw" | "undecided";

/**
 * The finished event's result. Mirrors native `EventOutcome.resolve`
 * (EventOutcome.swift:74): the served `hero_settled_result` is the authority
 * when it is one of its three known words, otherwise the scores decide; a row
 * that is not finished has no outcome. Web's `resolveEventOutcome`
 * (eventOutcome.ts:281) reads scores and tournament results only and takes no
 * served verdict, so it cannot be the authority for "from the served verdict".
 */
export function servedOutcome(
  status: string | null | undefined,
  homeScore: number | null | undefined,
  awayScore: number | null | undefined,
  served: string | null | undefined,
): HockeyJourneyOutcome {
  if (!isFinishedStatus(status)) return "undecided";
  if (served === "home" || served === "away" || served === "draw") return served;
  if (typeof homeScore !== "number" || typeof awayScore !== "number") return "undecided";
  if (homeScore > awayScore) return "home";
  if (awayScore > homeScore) return "away";
  return "draw";
}
