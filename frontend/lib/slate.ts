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
 * - "The script vs the divergence" is the opening price and the move. It used
 *   to be rendered a THIRD time as a sentence; UX-P138's ruling 6 deleted that
 *   generator (see the note where `matchNarrative` used to be) and left the
 *   two numbers to do the job. The dead band on the move is still the
 *   server's, not a second opinion.
 *
 * - `slateGroups` buckets by calendar day in the VIEWER's timezone, because
 *   "today" is a claim about the person reading, not about UTC.
 */

import type { TennisLinescore } from "@/lib/types";

/**
 * `unpriced` is NOT a fourth flavour of stale (UX-P142).
 *
 * `dark` means a price we once had has aged out. `unpriced` means no market
 * was ever pinned for this question — the state of all 96 released main-draw
 * fixtures, four days out, because nobody quotes a first round before
 * qualifying finishes. Collapsing them would tell a reader "the market stopped
 * quoting this" when the truth is "no market exists", and only one of those is
 * a fault of ours.
 */
export type PriceState = "live" | "stale" | "dark" | "unpriced";

/**
 * The two pinned URLs a surface may render for a player (Alex's ruling 8).
 *
 * REGISTER-OWNED, never resolved in the browser. The repo's other person
 * avatar (`FighterAvatar`) fires a bare-name Wikipedia lookup at render time;
 * for tennis that returns a Serbian footballer for Aleksandar Kovacevic and a
 * US president for Andrew Johnson, both with a photo and a 200. So the subject
 * check happens once, offline, in `scripts/census_player_images.py`, and what
 * reaches here is the answer rather than the question.
 */
export interface PlayerImage {
  /** A verified photograph of THIS person, or `null`. */
  url: string | null;
  /** Their country's flag — 100% coverage, so no row is ever blank. */
  flag_url: string | null;
}

export interface SlateSide {
  entity_key: string;
  display_name: string;
  seed: number | null;
  country: string | null;
  image?: PlayerImage | null;
  role: string;
  probability: number | null;
  opening_probability: number | null;
  move: number | null;
  raw_probability: number | null;
  raw_opening_probability: number | null;
  /** THIS side's own freshness (UX-P135). The row's verdict is the AND. */
  age_hours: number | null;
  price_state: PriceState;
  /** When a probability for THIS side last reached us. */
  observed_at?: string | null;
  /** UX-P157. This side's own book grade — see `lib/liquidity`. */
  liquidity?: string | null;
  liquidity_reasons?: string[] | null;
}

export interface SlateMatch {
  matchup_key: string;
  /**
   * Is ANY market pinned for this fixture (UX-P142)?
   *
   * `false` is the released main draw: a real fixture, from a real draw, that
   * nobody has quoted yet. Distinct from `coherent: false`, which is two
   * quotes that disagree. Optional so a payload written before this field
   * existed still parses — absent reads as priced, which is what every
   * pre-ceremony row was.
   */
  priced?: boolean;
  /**
   * OUR `events.id` for this fixture, when one exists (UX-P139, Alex's item 7).
   *
   * Register-owned (`matchup.event_id`), so the link is an identity decision
   * made once against the evidence rather than a name match at render time.
   * Optional and `null` on every US Open match today: checked 2026-08-26, none
   * of the 66 registered matchups has an `events` row.
   */
  event_id?: number | null;
  draw: string;
  draw_label: string;
  round: string;
  scheduled_date: string;
  /**
   * Is this match on RIGHT NOW (Q463)?
   *
   * ESPN's own state, not a comparison of `scheduled_date` to the clock — a
   * five-setter outlives any elapsed-time window, and "started seven hours
   * ago" is not evidence a match is over. Optional and `null` when the
   * scoreboard carries no entry for the fixture; a decided match is not here
   * at all, because it is a result.
   */
  live_state?: "in_progress" | "upcoming" | null;
  /** ESPN's words for that state — "2nd Set". Beside the enum, never instead. */
  status_detail?: string | null;
  /**
   * The set-by-set score (live/061, #2746 scope item 1).
   *
   * `status_detail` says WHICH set; this says what happened in all of them.
   * ABSENT rather than `null` when ESPN states no line — the backend drops the
   * key on all three of `authority_linescore`'s refusals, so an undefined here
   * means "no line to draw" and never "a line of zeroes".
   *
   * Off the same 180-second board read as `live_state` and `status_detail`, so
   * the line and the caption beside it describe one instant.
   */
  linescore?: TennisLinescore | null;
  /**
   * Is `scheduled_date` a TIME, or a day wearing one (Q463)?
   *
   * `true` means the source has published no order of play for this fixture
   * yet, so the timestamp is midnight local. Reading it as a start is the
   * defect that printed "No matches scheduled" through the whole of the US
   * Open's opening day; printing it is the smaller version of the same
   * mistake, so a row with this flag says TBD and shows no clock.
   */
  start_is_tbd?: boolean;
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
  /** UX-P157. The AND over both sides — see `lib/liquidity`. */
  liquidity?: string | null;
  liquidity_reasons?: string[] | null;
  /**
   * This match's OWN broadcast, when the register names one (UX-P137, ruling
   * 8). Absent today for every match — see `matchBroadcast` for why the field
   * exists anyway and what refuses to fill it with a guess.
   */
  broadcast?: Broadcast | null;
  /**
   * WHO WON, and BY WHAT (UX-P138, Alex's ruling 2: "decided matches show the
   * SCORE with the outcome — 6-1, 6-4").
   *
   * Both are optional and both are **absent from every row we have ever
   * served**. This is not a gap in the renderer, it is the state of the
   * pipeline: `build_slate` emits matchups, prices and freshness, and nothing
   * in the backend — not the register, not the slate builder, not
   * `build_bracket` — has ever held the result of a tennis match, let alone
   * its score. There is no field to read and no feed behind one.
   *
   * They are declared here anyway, for the same reason `broadcast` is: the
   * seam is the thing that makes the arrival of a result feed an INGEST change
   * rather than another layout pass. Nothing fabricates either one. A decided
   * match with no score prints the outcome alone, which is what UX-P137
   * already shipped and is strictly better than a blank row.
   */
  winner_entity_key?: string | null;
  /** "6-1, 6-4" — the set scores as the provider writes them. Never assembled here. */
  score?: string | null;
}

export interface Broadcast {
  region: string;
  channels: string[];
  note: string | null;
}

/**
 * Where to watch, for the reader's own region (Alex's item 4).
 *
 * A static per-tournament mapping is the sanctioned v1. Falls back to the US
 * entry, which is where the rights holder for this tournament is, rather than
 * to nothing.
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

export interface ResolvedBroadcast {
  channels: string[];
  region: string;
  /**
   * `match` when the register named a channel for THIS match; `tournament`
   * when it is the region-wide answer standing in. The distinction is not
   * cosmetic — see the note on `matchBroadcast`.
   */
  scope: "match" | "tournament";
}

/**
 * Where to watch THIS match (UX-P137, Alex's ruling 8).
 *
 * The ruling: "WHERE-TO-WATCH moves to match level — the answer differs match
 * to match; a single line at the top of a long list is wrong." That is true of
 * the world and this file used to argue the opposite, so the argument is gone
 * and the line moved.
 *
 * IT IS ALSO, TODAY, TRUE OF NOTHING WE HOLD, and the code says so rather than
 * hiding it. The register carries rights per REGION only — US: ESPN/ESPN2/
 * ESPN+, UK: Sky Sports Tennis, AU: Stan Sport — and there is no court, no
 * session and no per-match channel anywhere in the pipeline. So every row
 * resolves to the same string until a session feed lands, and the row is
 * tagged `scope: "tournament"` so a test can prove that is what happened
 * rather than a per-match answer that coincidentally matched.
 *
 * `match.broadcast` is the seam that day arrives through: a data change, not
 * another layout pass. Nothing fabricates one in the meantime — a plausible
 * per-match channel is worse than an honest tournament-wide one, because the
 * reader would act on it.
 */
export function matchBroadcast(
  match: Pick<SlateMatch, "broadcast">,
  broadcasts: Broadcast[] | undefined,
  region = "US"
): ResolvedBroadcast | null {
  const own = match.broadcast;
  if (own && Array.isArray(own.channels) && own.channels.length > 0) {
    return { channels: own.channels, region: own.region, scope: "match" };
  }
  const wide = broadcastFor(broadcasts, region);
  if (!wide || !Array.isArray(wide.channels) || wide.channels.length === 0) return null;
  return { channels: wide.channels, region: wide.region, scope: "tournament" };
}

export interface SlateData {
  matches: SlateMatch[];
  count: number;
  incoherent: number;
  /** How many of `matches` are being played RIGHT NOW (Q463). */
  in_progress?: number;
  /**
   * How many competitions the ESPN order-of-play overlay carried (Q463).
   *
   * `0` with an empty list means the overlay is not reaching us. Before this
   * the two were the same empty card, and the first of them ran for a full day
   * (gotcha #53).
   *
   * ⚠️ THE OTHER HALF OF THIS NOTE WAS WRONG AND IS DELETED (#2707). It read
   * "a positive number with an empty list means the tournament genuinely has
   * nothing on", and on 2026-09-03 this field was 625 with an empty list while
   * five matches were on court. The count is competitions the authority is
   * carrying, not competitions still to come, so it can never certify an empty
   * day. What it does certify is that the authority still has this tournament
   * on its board — which makes the empty list ours to explain. See
   * `slateEmptyState`, which is now the only thing allowed to draw a
   * conclusion from this number.
   */
  order_of_play_listed?: number;
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
  if (match.priced === false) {
    // Not an age. "Never priced" would be technically true and read as a
    // complaint about staleness; the fixture is four days away and nobody has
    // opened a book on it, which is ordinary and worth one plain sentence.
    // Ruling 138: "No market yet" answered a probability question with an
    // inventory fact. Worded identically to `propFreshnessLabel` so the two
    // halves of the page do not teach two vocabularies for one idea.
    return "No probability yet";
  }
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
  // UX-P145: was "never priced". *Priced* is a trading verb; "no reading yet"
  // is the same fact in the page's own honesty vocabulary.
  if (ageHours === null || !Number.isFinite(ageHours)) return "no reading yet";
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
 * `matchNarrative` WAS HERE, and was DELETED by UX-P138 (Alex's ruling 6).
 *
 * The ruling, verbatim: "probability + movement delta + a sentence restating
 * both is three renderings of one fact. Pick one primary treatment (number +
 * delta chip); a sentence appears only when it adds something the numbers
 * don't."
 *
 * It is deleted rather than left unused, and that is the whole point of doing
 * it here instead of at the call site. What it produced —
 *
 *     "Clara Burel opened at 65%, up to 72%."
 *
 * — sat directly beneath a row already printing `72%` and `+7`. Every token in
 * it except `65%` was a third rendering of a number six pixels away. Removing
 * only the JSX would have left a tested, exported, documented sentence
 * generator in the tree for the next component to reach for, and the tests
 * asserting its exact wording would have kept it alive and looking healthy.
 * The redundancy has to die in the layer that manufactures it.
 *
 * Its one genuinely additive token, the OPENING price, survives in
 * `matchList.matchDetailNote`, which returns `null` for the flat and
 * unremarkable majority of rows and is rendered only in the tapped detail view
 * (ruling 7's home for demoted content).
 */

export interface SlateNotice {
  tone: "stale" | "dark";
  headline: string;
  detail: string;
}

export interface SlateEmptyState {
  headline: string;
  detail: string;
  /**
   * Which of the three empty states this is, for the guards and for the DOM.
   *
   * - `pre-draw` — the fixtures do not exist yet. The only one of the three in
   *   which "no matches" is a true sentence.
   * - `unrendered` — the authority listed this tournament on today's board and
   *   we published none of it. OUR failure, and the card says so.
   * - `unlisted` — the authority listed nothing. Either the tournament is over
   *   or the feed is dark, and an empty slate cannot tell those apart.
   */
  cause: "pre-draw" | "unrendered" | "unlisted";
}

/**
 * WHAT AN EMPTY MATCH LIST IS ALLOWED TO SAY (#2707, defect class D27).
 *
 * ═══ THE DEFECT ═══
 *
 * On 2026-09-03 at 17:27Z the US Open hub printed "No matches scheduled —
 * Nothing is on right now" at phone width while Auger-Aliassime–Khachanov and
 * four other rows were live on court. The payload behind it: `slate.count 0`,
 * `order_of_play_listed 625`, `dropped {ALREADY_PLAYED 28, DECIDED 96}`.
 *
 * So the page did not report an empty day. It reported ITS OWN EMPTY OUTPUT as
 * a fact about the world, and the reader has no way to tell the difference.
 * That is the error-dressed-as-empty-data class, and the standing posture of
 * this file — the server decides, the UI only decides how loudly to say so —
 * says the UI may not upgrade "I rendered nothing" into "nothing exists".
 *
 * ═══ THE DISCRIMINATOR ═══
 *
 * `order_of_play_listed` was added by Q463 (gotcha #53) for exactly this, and
 * the note on `SlateData` drew HALF the right conclusion from it. Verbatim:
 * "a positive number with an empty list means the tournament genuinely has
 * nothing on." That is the sentence this function exists to retire. 625 is a
 * count of competitions the authority is carrying for this tournament — it is
 * not a claim that any of them is upcoming, so it can be large on a day whose
 * whole card we failed to render. It IS, however, proof that the authority
 * still has this tournament on its board, which makes an empty list ours to
 * explain rather than the world's.
 *
 * The `0` case stays deliberately hedged. A finished tournament and a dark
 * feed produce the same zero, and the honest sentence covers both without
 * pretending to know which: nothing is listed, and if a match is on we are not
 * seeing it.
 */
export function slateEmptyState(args: {
  /** Has the draw ceremony happened? Before it, the fixtures truly do not exist. */
  drawReleased: boolean;
  /** The payload's own words for when the draw lands — never a hard-coded weekday (UX-P145). */
  mainDrawLabel?: string | null;
  /**
   * `slate.order_of_play_listed`. `undefined` on a payload written before the
   * field existed, and read the same as `0` — hedged, never confident.
   */
  orderOfPlayListed?: number | null;
}): SlateEmptyState {
  if (!args.drawReleased) {
    return {
      cause: "pre-draw",
      headline: "No matches scheduled yet",
      detail: args.mainDrawLabel
        ? `This is where the day's matches sit, and the draw fills them in ${args.mainDrawLabel}.`
        : "This is where the day's matches sit, once the draw is made.",
    };
  }

  const listed = args.orderOfPlayListed;
  if (typeof listed === "number" && Number.isFinite(listed) && listed > 0) {
    return {
      cause: "unrendered",
      headline: "We can't show today's schedule",
      // Names OUR failure and does not soften it. A match may well be on right
      // now; saying "nothing is on" here is the thing that broke.
      detail:
        "The schedule feed has this tournament on today's board, but none of it reached this list — so a match that is on right now would be missing. We're checking.",
    };
  }

  return {
    cause: "unlisted",
    headline: "No matches listed right now",
    detail:
      "The schedule feed returned nothing for this tournament. If a match is on, we are not seeing it — we're checking.",
  };
}

/** The visible admission, same posture as the board's. `null` when genuinely live. */
export function slateNotice(slate: SlateData): SlateNotice | null {
  if (slate.price_state === "live") return null;
  if (slate.newest_observed_at === null) {
    return {
      tone: "dark",
      headline: "No numbers yet",
      detail: "No market has put a probability on today's matches.",
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
    // The SLATE-level state is computed from the newest observation across the
    // list, so it is only ever live / stale / dark. `unpriced` is a per-ROW
    // state (UX-P142) and cannot reach here; narrowed explicitly rather than
    // cast, so the day a slate-wide unpriced state does exist this stops
    // compiling instead of quietly labelling it "Updates paused".
    tone: slate.price_state === "unpriced" ? "dark" : slate.price_state,
    // UX-P146: was "Prices paused" / "the last prices we saw, not live prices".
    // Alex's product-wide ruling — the word is PROBABILITY. Kept identical to
    // the board's wording, because the boards and the slate are two halves of
    // one page and wording one admission two ways teaches a reader that one of
    // them is decorative.
    headline: "Updates paused",
    detail: `Last confirmed reading ${when}. These are the last probabilities we saw, not live ones.`,
  };
}
