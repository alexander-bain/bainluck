/**
 * Search-dropdown row presentation — the SINGLE source of truth for what a
 * typeahead suggestion says, shared by the desktop `SearchBar` and the phone
 * `MobileSearchOverlay` (#1620).
 *
 * Why this module exists: the two dropdowns are mutually exclusive by viewport
 * (`layout.tsx` mounts `MobileSearchTrigger` in a `md:hidden` container and
 * `SearchBar` in a `hidden md:block` one), and their row JSX was duplicated. So
 * #993 Slice A — "lead with the answer" — shipped to desktop and silently never
 * reached a single phone. Logic lives here; each component keeps its own classes
 * and sizing. A guard test asserts neither component re-implements any of this.
 *
 * PURE: no I/O, no React, no DB. `formatEventTime` takes an injectable clock so
 * tests never seed relative to `Date.now()` (gotcha #44).
 */
import type { TypeaheadSuggestion, TypeaheadOutcome, TeamSeasonAnswer } from "@/lib/api";

/**
 * How many season facts a team row shows (T2-1 / #5058). Two, because two is
 * what the friend's task asks for — the win threshold and the playoff chance —
 * and a third would not survive a 390px row beside a logo and a type chip.
 */
export const TEAM_SEASON_ANSWER_LIMIT = 2;

/**
 * A movement arrow is only worth the pixels at >= 2 percentage points. Matches
 * the desktop threshold shipped with #993 Slice A.
 */
export const MOVEMENT_MIN_ABS = 0.02;

/** Strip a league playoff prefix and a trailing season year from a market name. */
export function formatFuturesName(name: string): string {
  return name
    .replace(/^(?:NBA|NHL|MLB|NFL|MLS|WNBA|PGA)\s+Playoffs?:\s*/i, "")
    .replace(/\s*\d{4}(-\d{2,4})?\s*$/, "")
    .trim();
}

/**
 * Kickoff, phrased by how soon it is: "Recently" once past, "In 45 min" inside
 * the hour, a clock time inside the day, otherwise a dated clock time.
 *
 * `now` is injectable purely for tests; production callers omit it.
 */
export function formatEventTime(isoString: string, now: Date = new Date()): string {
  const date = new Date(isoString);
  const diffMs = date.getTime() - now.getTime();
  const diffHours = diffMs / (1000 * 60 * 60);

  if (diffHours < 0) return "Recently";
  if (diffHours < 1) return `In ${Math.round(diffHours * 60)} min`;
  if (diffHours < 24) {
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** The title line. Futures names get cleaned; everything else reads as sent. */
export function suggestionDisplayText(s: TypeaheadSuggestion): string {
  return s.type === "futures" ? formatFuturesName(s.text) : s.text;
}

/** The trailing type chip on the right of every row. */
export function suggestionTypeLabel(s: TypeaheadSuggestion): string {
  switch (s.type) {
    case "team":
      return "Team";
    case "event":
      return "Game";
    case "event_concept":
      return "Event";
    case "hub":
      return "Hub";
    default:
      return "Futures";
  }
}

/** The answer carried by a futures suggestion (#993 Slice A). */
export interface FuturesAnswer {
  leader: TypeaheadOutcome & { probability: number };
  second: (TypeaheadOutcome & { probability: number }) | null;
  /** 24h move as a fraction; 0 when the payload carries none. */
  movement: number;
}

/**
 * Leader + runner-up for a futures suggestion, or `null` when nothing in the
 * payload is actually priced.
 *
 * Deliberately NOT coherence-checked. The live payload does contain incoherent
 * fields ("MLB: Next Red Sox Manager" returns three outcomes at 100%) — that is
 * gap-list K6, owned by calibration/data, and desktop already displays it.
 * Suppressing it here would also hide legitimate independent-binary fields,
 * which genuinely sum over 100% (gotcha #23).
 */
export function futuresAnswer(s: TypeaheadSuggestion): FuturesAnswer | null {
  const priced = (s.top_outcomes ?? []).filter(
    (o): o is TypeaheadOutcome & { probability: number } => o.probability != null
  );
  if (priced.length === 0) return null;
  return {
    leader: priced[0],
    second: priced[1] ?? null,
    movement: priced[0].movement ?? 0,
  };
}

/**
 * How many rows in a dropdown are actually leading with an answer (#993 Slice A
 * exposure). Shared so the desktop and phone surfaces count the SAME thing —
 * previously only desktop counted at all, which is part of why nobody noticed
 * phones had never received the feature.
 */
export function countAnswersShown(suggestions: TypeaheadSuggestion[]): number {
  return suggestions.filter((s) => s.type === "futures" && futuresAnswer(s) !== null).length;
}

/** Whether a movement value clears the display threshold. */
export function isMovementWorthShowing(movement: number): boolean {
  return Math.abs(movement) >= MOVEMENT_MIN_ABS;
}

/** Percentage integer for display, e.g. 0.6721 -> 67. */
export function toPercent(probability: number): number {
  return Math.round(probability * 100);
}

/**
 * What the second line of a row should say. `null` means the row has no
 * subtitle and must render no empty line.
 */
export type SuggestionSubtitle =
  | { kind: "event-time"; text: string }
  | { kind: "futures-answer"; answer: FuturesAnswer }
  | { kind: "futures-label"; text: string }
  | { kind: "concept"; text: string }
  | { kind: "hub"; text: string }
  | { kind: "team-season"; answers: TeamSeasonAnswer[] };

/**
 * The season answers a team row should print (T2-1 / #5058), or `[]`.
 *
 * The server has already elected which threshold to name and in what order the
 * two facts read; this only drops what cannot be rendered honestly — a missing
 * label, or a probability that is not a number in 0..1. An answer that fails
 * that test is omitted rather than shown as "NaN%" or "0%", because a reader
 * cannot tell a broken number from a real one and both look like our opinion.
 */
export function teamSeasonAnswers(s: TypeaheadSuggestion): TeamSeasonAnswer[] {
  if (s.type !== "team") return [];
  return (s.season_answers ?? [])
    .filter(
      (a) =>
        !!a &&
        typeof a.label === "string" &&
        a.label.length > 0 &&
        typeof a.probability === "number" &&
        Number.isFinite(a.probability) &&
        a.probability >= 0 &&
        a.probability <= 1
    )
    .slice(0, TEAM_SEASON_ANSWER_LIMIT);
}

export function suggestionSubtitle(
  s: TypeaheadSuggestion,
  now?: Date
): SuggestionSubtitle | null {
  if (s.type === "event") {
    // A game with no commence_time gets no second line rather than a blank one.
    if (!s.commence_time) return null;
    // #4411: the dropdown answers a player's name with their NEXT match, or
    // their LAST one when nothing is upcoming. A finished match carrying only
    // a date is unreadable in a list whose other rows are all upcoming — "Sep 9"
    // beside "Sep 11" looks like a fixture, not a result. Say which it is.
    // NOT `Final · ${formatEventTime(...)}`: that helper collapses every past
    // instant to the single word "Recently", so the composed line reads
    // "Final · Recently" — two vague words where one precise one will do.
    if (s.status === "completed" || s.status === "closed") {
      return { kind: "event-time", text: "Final" };
    }
    return {
      kind: "event-time",
      text: s.status === "live" ? "Live now" : formatEventTime(s.commence_time, now),
    };
  }

  if (s.type === "event_concept") {
    return { kind: "concept", text: `Event${s.sport_key ? ` · ${s.sport_key}` : ""}` };
  }

  if (s.type === "hub") {
    return { kind: "hub", text: "Browse all markets" };
  }

  if (s.type === "futures") {
    const answer = futuresAnswer(s);
    if (answer) return { kind: "futures-answer", answer };
    return s.market_type_label
      ? { kind: "futures-label", text: s.market_type_label }
      : null;
  }

  if (s.type === "team") {
    const answers = teamSeasonAnswers(s);
    // A team with no season answers keeps the row it always had — no second
    // line, not an empty one.
    return answers.length > 0 ? { kind: "team-season", answers } : null;
  }

  return null;
}
