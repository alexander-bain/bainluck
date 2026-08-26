/**
 * Daily-slate types and pure presentation logic (UX-P132, charter layer 2).
 *
 * Pure functions, for the same reason as `lib/tournament.ts`: the jest gate
 * runs in the node environment with no jsdom, so logic that only exists inside
 * a component body is logic no guard can reach (ruling 005).
 *
 * The rules here that are load-bearing rather than cosmetic:
 *
 * - `slateRowIsPresentedAsLive` mirrors the board's predicate exactly. The
 *   SERVER decides liveness; this file only decides how loudly to say so, and
 *   it may never upgrade a row the server did not call live.
 *
 * - `matchNarrative` is "the script vs the divergence" in one sentence. The
 *   script is the opening price, the divergence is where it went. A row with no
 *   movement says so plainly rather than manufacturing a story out of noise —
 *   the dead band is the server's, not a second opinion.
 *
 * - `slateGroups` buckets by calendar day in the VIEWER's timezone, because
 *   "today" is a claim about the person reading, not about UTC.
 */

export type PriceState = "live" | "stale" | "dark";

export interface SlateSide {
  entity_key: string;
  display_name: string;
  seed: number | null;
  country: string | null;
  role: string;
  probability: number | null;
  opening_probability: number | null;
  move: number | null;
  raw_probability: number | null;
  raw_opening_probability: number | null;
  /** THIS side's own freshness (UX-P135). The row's verdict is the AND. */
  age_hours: number | null;
  price_state: PriceState;
}

export interface SlateMatch {
  matchup_key: string;
  draw: string;
  draw_label: string;
  round: string;
  scheduled_date: string;
  sides: SlateSide[];
  coherent: boolean;
  raw_sum: number | null;
  opening_raw_sum: number | null;
  probability_is_live: boolean;
  price_state: PriceState;
  /**
   * The GOVERNING (older) side's reading. A normalized pair bakes BOTH sides
   * into the number shown, so it is only as fresh as its older half (UX-P135).
   */
  observed_at: string | null;
  age_hours: number | null;
  /** The newer side's reading — an extra fact beside the verdict. */
  freshest_observed_at: string | null;
  freshest_age_hours: number | null;
  /** Entity keys of the sides that are not live. */
  stale_sides: string[];
  mixed_freshness: boolean;
  favourite: string | null;
  has_moved: boolean;
  source_count: number;
}

export interface Broadcast {
  region: string;
  channels: string[];
  note: string | null;
}

/**
 * Where to watch, for the reader's own region (Alex's item 4).
 *
 * A static per-tournament mapping is the sanctioned v1. It is looked up by
 * region rather than joined per match because these rights are tournament-wide
 * — pretending otherwise by stamping a channel on each row would imply we know
 * something per-match that we do not.
 *
 * Falls back to the US entry, which is where the rights holder for this
 * tournament is, rather than to nothing.
 */
export function broadcastFor(
  broadcasts: Broadcast[] | undefined,
  region = "US"
): Broadcast | null {
  if (!Array.isArray(broadcasts) || broadcasts.length === 0) return null;
  return (
    broadcasts.find((entry) => entry.region === region) ??
    broadcasts.find((entry) => entry.region === "US") ??
    broadcasts[0]
  );
}

export interface SlateData {
  matches: SlateMatch[];
  count: number;
  incoherent: number;
  dropped: Record<string, number>;
  price_state: PriceState;
  newest_observed_at: string | null;
  age_hours: number | null;
  dark_after_hours: number;
}

/**
 * The line beside a muted slate row, explaining WHICH side is old.
 *
 * `null` for a live row. Mirrors `rowFreshnessLabel` on the boards so the two
 * halves of the page word the same admission the same way — a reader should
 * not have to learn two vocabularies for one idea (UX-P135).
 */
export function slateRowFreshnessLabel(match: SlateMatch): string | null {
  if (slateRowIsPresentedAsLive(match)) return null;
  if (!match.coherent && match.price_state === "live") {
    // Muted for disagreement, not for age. The incoherent block already says
    // so in words; repeating an age here would name the wrong problem.
    return null;
  }
  const when = slateStalenessLabel(match.age_hours);
  if (match.mixed_freshness && match.stale_sides.length > 0) {
    const names = match.stale_sides.map((key) => {
      const side = match.sides.find((s) => s.entity_key === key);
      return side ? side.display_name : key;
    });
    return `${names.join(" + ")} ${when}`;
  }
  return when;
}

/** Human age, rounded DOWN — "8 days ago" must never flatter to "7". */
export function slateStalenessLabel(ageHours: number | null): string {
  if (ageHours === null || !Number.isFinite(ageHours)) return "never priced";
  if (ageHours < 1) {
    const minutes = Math.max(1, Math.floor(ageHours * 60));
    return `${minutes} min ago`;
  }
  if (ageHours < 48) {
    const hours = Math.floor(ageHours);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  return `${Math.floor(ageHours / 24)} days ago`;
}

/** A row may be presented as a live number only when the SERVER says so. */
export function slateRowIsPresentedAsLive(match: SlateMatch): boolean {
  return match.probability_is_live === true;
}

/**
 * The favourite and the underdog, in that order.
 *
 * Returns `null` when the pair is incoherent: with no trustworthy split there
 * is no favourite, and picking the larger of two numbers we have refused to
 * display would smuggle the refused comparison back onto the page.
 */
export function orderedSides(match: SlateMatch): [SlateSide, SlateSide] | null {
  if (!match.coherent || match.sides.length !== 2) return null;
  const [a, b] = match.sides;
  if ((a.probability ?? 0) >= (b.probability ?? 0)) return [a, b];
  return [b, a];
}

export function formatSlateProbability(probability: number | null): string {
  if (probability === null || !Number.isFinite(probability)) return "—";
  return `${Math.round(probability * 100)}%`;
}

/** Signed points, e.g. `+4` / `-4`. Empty string when there is no move to show. */
export function formatMove(move: number | null): string {
  if (move === null || !Number.isFinite(move)) return "";
  const points = move * 100;
  if (Math.abs(points) < 0.5) return "";
  const sign = points > 0 ? "+" : "−";
  return `${sign}${Math.abs(points).toFixed(0)}`;
}

export function moveDirection(move: number | null): "up" | "down" | "flat" {
  if (move === null || !Number.isFinite(move)) return "flat";
  if (move > 0.003) return "up";
  if (move < -0.003) return "down";
  return "flat";
}

/**
 * Local clock time for a match — `10:35 AM`.
 *
 * A slate is read to answer "when is it on", so the time is shown in the
 * reader's own timezone. Falls back to the raw string rather than throwing:
 * an unparseable date must not take the whole tab down.
 */
export function matchTime(scheduled: string): string {
  const at = new Date(scheduled);
  if (Number.isNaN(at.getTime())) return scheduled;
  return at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Calendar-day key in the VIEWER's timezone — "today" is about the reader. */
export function localDayKey(scheduled: string): string {
  const at = new Date(scheduled);
  if (Number.isNaN(at.getTime())) return scheduled.slice(0, 10);
  const month = `${at.getMonth() + 1}`.padStart(2, "0");
  const day = `${at.getDate()}`.padStart(2, "0");
  return `${at.getFullYear()}-${month}-${day}`;
}

export function dayHeading(dayKey: string, now: Date = new Date()): string {
  const todayKey = localDayKey(now.toISOString());
  if (dayKey === todayKey) return "Today";
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  if (dayKey === localDayKey(tomorrow.toISOString())) return "Tomorrow";
  const at = new Date(`${dayKey}T12:00:00`);
  if (Number.isNaN(at.getTime())) return dayKey;
  return at.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

export interface SlateGroup {
  dayKey: string;
  heading: string;
  matches: SlateMatch[];
}

/** Matches bucketed by local day, chronological, preserving server order within a day. */
export function slateGroups(matches: SlateMatch[], now: Date = new Date()): SlateGroup[] {
  const byDay = new Map<string, SlateMatch[]>();
  for (const match of matches) {
    const key = localDayKey(match.scheduled_date);
    const bucket = byDay.get(key);
    if (bucket) bucket.push(match);
    else byDay.set(key, [match]);
  }
  return Array.from(byDay.keys())
    .sort()
    .map((dayKey) => ({
      dayKey,
      heading: dayHeading(dayKey, now),
      matches: byDay.get(dayKey) as SlateMatch[],
    }));
}

/**
 * The script vs the divergence, as one readable sentence.
 *
 * Deterministic and computed from the same numbers on the row — never an LLM
 * hook, and never a claim the row's own figures do not support. A match that
 * has not moved says so; that is information, not a gap to fill.
 */
export function matchNarrative(match: SlateMatch): string {
  const ordered = orderedSides(match);
  if (ordered === null) return "Prices for this match do not agree yet.";

  const [favourite] = ordered;
  const opened = favourite.opening_probability;
  const now = favourite.probability;
  if (opened === null || now === null) {
    return `${favourite.display_name} is favoured at ${formatSlateProbability(now)}.`;
  }

  const direction = moveDirection(favourite.move);
  if (direction === "flat") {
    return `${favourite.display_name} opened at ${formatSlateProbability(
      opened
    )} and has not moved.`;
  }
  const verb = direction === "up" ? "up to" : "down to";
  return `${favourite.display_name} opened at ${formatSlateProbability(
    opened
  )}, ${verb} ${formatSlateProbability(now)}.`;
}

export interface SlateNotice {
  tone: "stale" | "dark";
  headline: string;
  detail: string;
}

/** The visible admission, same posture as the board's. `null` when genuinely live. */
export function slateNotice(slate: SlateData): SlateNotice | null {
  if (slate.price_state === "live") return null;
  if (slate.newest_observed_at === null) {
    return {
      tone: "dark",
      headline: "No prices yet",
      detail: "We have not recorded a price for today's matches.",
    };
  }
  const hours = slate.age_hours;
  const when =
    hours === null
      ? "some time ago"
      : hours < 48
        ? `${Math.floor(hours)} hour${Math.floor(hours) === 1 ? "" : "s"} ago`
        : `${Math.floor(hours / 24)} days ago`;
  return {
    tone: slate.price_state,
    headline: "Prices paused",
    detail: `Last confirmed reading ${when}. These are the last prices we saw, not live prices.`,
  };
}
