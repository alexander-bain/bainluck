import { formatProbability } from "@/lib/api";
import { awayIsTheComplement } from "@/lib/drawPricedWinner";
import { priceAgeClock } from "@/lib/event/liveConnectionStatus";
import { BOOKS_LABEL, BOOKS_SOURCE, prematchReading } from "@/lib/prematchReading";
import type { FeedEventData } from "@/lib/types";

export interface AtlasHeadlineObservedAtInput {
  acceptedPriceClock: string | null | undefined;
  confirmedAtShown: string | null | undefined;
  freshestSourceStamp: string | null | undefined;
  currentOddsCapturedAt: string | null | undefined;
}

/**
 * #11974 Step E5 — selects the observed-at timestamp for the atlas headline
 * phase (`"Current win chance"` vs `"Last recorded win chance"`).
 *
 * On a held live page, `priceAgeClock(acceptedPriceClock, confirmedAtShown)`
 * advances the clock when the SSE stream confirms a steady displayed price or
 * admits a one-stream blend preview, before falling back to `freshestSourceStamp`
 * or `current_odds.captured_at`.
 */
export function resolveAtlasHeadlineObservedAt({
  acceptedPriceClock,
  confirmedAtShown,
  freshestSourceStamp,
  currentOddsCapturedAt,
}: AtlasHeadlineObservedAtInput): string | null {
  return (
    priceAgeClock(acceptedPriceClock ?? null, confirmedAtShown ?? null) ??
    freshestSourceStamp ??
    currentOddsCapturedAt ??
    null
  );
}

export type EventHeadlinePhase = "current" | "last_recorded";

export const EVENT_HEADLINE_PHASE_LABELS: Record<EventHeadlinePhase, string> = {
  current: "Current win chance",
  last_recorded: "Last recorded win chance",
};

/**
 * Matches iOS `SourceAge.liveStaleAfter` (30 minutes, inclusive).
 * A quote older than 30 minutes is labelled "Last recorded win chance",
 * never "Current win chance".
 */
export const EVENT_HEADLINE_LIVE_STALE_AFTER_MS = 30 * 60 * 1000;

function isFinishedStatus(status: string | null | undefined): boolean {
  const normalized = (status || "").trim().toLowerCase();
  return (
    normalized === "completed" ||
    normalized === "closed" ||
    normalized === "final" ||
    normalized === "settled"
  );
}

/**
 * #11974 Step E1 (web port of `EventHeadlinePhase9483`):
 * Resolves the phase label printed beneath the game headline's win-chance pair.
 *
 * - Returns `null` when the event is finished, when there is no probability reading,
 *   or when the reading is already labelled as the opening line.
 * - Returns `"last_recorded"` when live delivery is interrupted, when the quote
 *   timestamp is missing or older than 30 minutes, or when the game has started
 *   and is not `live`.
 * - Returns `"current"` when the quote is fresh (<= 30 minutes old) and the game
 *   is either `live` or before its scheduled start.
 */
export function resolveEventHeadlinePhase(args: {
  status?: string | null;
  commenceTime?: string | null;
  isOpeningLine?: boolean;
  hasReading?: boolean;
  observedAt?: string | null;
  deliveryInterrupted?: boolean;
  nowMs?: number;
}): EventHeadlinePhase | null {
  const {
    status,
    commenceTime,
    isOpeningLine = false,
    hasReading = true,
    observedAt,
    deliveryInterrupted = false,
    nowMs = Date.now(),
  } = args;

  if (!hasReading || isOpeningLine || isFinishedStatus(status)) {
    return null;
  }

  if (deliveryInterrupted) {
    return "last_recorded";
  }

  const observedMs = observedAt ? Date.parse(observedAt) : Number.NaN;
  if (!Number.isFinite(observedMs)) {
    return "last_recorded";
  }
  const ageMs = nowMs - observedMs;
  if (ageMs > EVENT_HEADLINE_LIVE_STALE_AFTER_MS) {
    return "last_recorded";
  }

  if ((status || "").trim().toLowerCase() === "live") {
    return "current";
  }

  const commenceMs = commenceTime ? Date.parse(commenceTime) : Number.NaN;
  if (!Number.isFinite(commenceMs)) {
    return "last_recorded";
  }

  return commenceMs <= nowMs ? "last_recorded" : "current";
}

export interface EventHeadlinePregameBaseline {
  /** Formatted baseline string in home-away order (matching the web hero columns). */
  text: string;
  homeProbability: number;
  awayProbability: number | null;
  homePercent: number | null;
  awayPercent: number | null;
  source: string;
  /** Non-null ("sportsbooks") when the baseline fell back to the sportsbook opening median. */
  label: string | null;
}

/**
 * #11974 Step E1: Resolves the pregame win-chance baseline shown beside/under
 * "Current win chance" during play, using the same `prematchReading` ladder
 * and draw-complement withholding as the settled hero (`#8315`, `#6238`, `#6614`).
 */
export function resolveEventHeadlineBaseline(args: {
  prematchOdds?: FeedEventData["prematch_odds"] | null;
  openingHomeProb?: number | null;
  /** Raw or already-withheld opening away probability. */
  openingAwayProb?: number | null;
  openingHomePct?: number | null;
  openingAwayPct?: number | null;
  sport?: string | null;
  homeShort: string;
}): EventHeadlinePregameBaseline | null {
  const {
    prematchOdds,
    openingHomeProb = null,
    openingAwayProb = null,
    openingHomePct = null,
    openingAwayPct = null,
    sport,
    homeShort,
  } = args;

  const served = prematchOdds
    ? prematchReading({ prematch_odds: prematchOdds, opening_odds: undefined })
    : null;
  if (served) {
    const awayWithheld = awayIsTheComplement(
      served.awayProbability,
      served.homeProbability,
      sport,
    );
    const homeFormatted = formatProbability(served.homeProbability, {
      rendered: served.homePercent,
    });
    if (awayWithheld) {
      return {
        text: `Pregame ${homeShort} ${homeFormatted}`,
        homeProbability: served.homeProbability,
        awayProbability: null,
        homePercent: served.homePercent,
        awayPercent: null,
        source: served.source,
        label: served.source === BOOKS_SOURCE ? served.label : null,
      };
    }
    const awayFormatted = formatProbability(served.awayProbability, {
      rendered: served.awayPercent,
    });
    return {
      text: `Pregame ${homeFormatted} – ${awayFormatted}`,
      homeProbability: served.homeProbability,
      awayProbability: served.awayProbability,
      homePercent: served.homePercent,
      awayPercent: served.awayPercent,
      source: served.source,
      label: served.source === BOOKS_SOURCE ? served.label : null,
    };
  }

  if (
    openingHomeProb === null ||
    !Number.isFinite(openingHomeProb) ||
    openingHomeProb <= 0 ||
    openingHomeProb >= 1
  ) {
    return null;
  }

  const awayWithheld =
    openingAwayProb === null ||
    awayIsTheComplement(openingAwayProb, openingHomeProb, sport);
  const homeFormatted = formatProbability(openingHomeProb, {
    rendered: openingHomePct,
  });

  if (awayWithheld) {
    return {
      text: `Pregame ${homeShort} ${homeFormatted}`,
      homeProbability: openingHomeProb,
      awayProbability: null,
      homePercent: openingHomePct,
      awayPercent: null,
      source: BOOKS_SOURCE,
      label: BOOKS_LABEL,
    };
  }

  const awayFormatted = formatProbability(openingAwayProb, {
    rendered: openingAwayPct,
  });
  return {
    text: `Pregame ${homeFormatted} – ${awayFormatted}`,
    homeProbability: openingHomeProb,
    awayProbability: openingAwayProb,
    homePercent: openingHomePct,
    awayPercent: openingAwayPct,
    source: BOOKS_SOURCE,
    label: BOOKS_LABEL,
  };
}
