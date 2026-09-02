/**
 * THE MATCH LIST — one list of matches for the whole tournament, by round.
 *
 * UX-P138, Alex's STRUCTURAL RULING 4: "Tournament tab = the MATCH LIST with
 * round pills; Bracket tab = the PLAYOFF GRID." Adopted. The counter-structure
 * argument is in the report; the short version is that the page had TWO match
 * lists — the slate on one tab, the bracket's match cards on the other — and
 * nothing told the reader why they were different lists or which one to trust.
 * They were the same list, split by which pipeline happened to produce it.
 *
 * So this file is the join. A match is a match:
 *
 *   - Qualifying matches come from the SLATE, which is a matchup-and-date feed
 *     with real prices and no draw position.
 *   - Main-draw matches come from the BRACKET, which is a draw-position fold
 *     with title probabilities and no prices.
 *   - A bracket match whose two names also appear in the slate ABSORBS that
 *     slate row: it keeps the draw position and gains the price. The slate row
 *     does not then render a second time, which is the duplicate the old
 *     two-list layout printed on every main-draw day.
 *
 * ALEX'S RULING 1, the standing rule this file exists to make structural:
 * **match odds everywhere a match shows.** A side carries TWO numbers that
 * answer two different questions, and the whole of UX-P137's ruling 2 was
 * about not letting one be mistaken for the other:
 *
 *   - `matchProbability` — to win THIS match. The primary. Big type.
 *   - `titleChance` — to win the whole tournament. A muted secondary chip,
 *     self-labelling, because Alex asked for both on the nothing-played view
 *     and then asked for it "without it being too busy".
 *
 * NEITHER IS EVER COMPUTED FROM THE OTHER, in either direction. They come from
 * different markets — a match market and the champion market — and a page that
 * derived one from the other would be printing a model output in the type
 * reserved for a price.
 *
 * ALEX'S RULING 2: a decided match prints the SCORE with the outcome. The seam
 * is `score` on both source types. **We hold no scores and no results at all
 * today** — see the note on `MatchListEntry.score` — so nothing renders one
 * until a result feed lands. The rig demonstrates it against the synthetic
 * fixture, and the report says plainly that the world has this and our data
 * does not.
 */

import {
  ROUND_LABELS,
  ROUND_NAMES,
  roundIsUnreached,
  type BracketRound,
  type PrematchPair,
  type RoundName,
} from "./bracket";
import {
  formatSlateProbability,
  matchBroadcast,
  moveDirection,
  slateRowFreshnessLabel,
  slateRowIsPresentedAsLive,
  slateStalenessLabel,
  type Broadcast,
  type PlayerImage,
  type ResolvedBroadcast,
  type SlateMatch,
} from "./slate";

/**
 * Round keys, in the order a tournament plays them.
 *
 * `qualifying` is not a `RoundName` — it is not part of the draw fold and has
 * no bracket position — but it is unquestionably a round of this tournament
 * and it is the ONLY round we hold matches for today. A pill strip that could
 * not name it would have exactly one thing to show and nothing to call it.
 */
export type MatchRoundKey = "qualifying" | RoundName;

export const MATCH_ROUND_ORDER: MatchRoundKey[] = ["qualifying", ...ROUND_NAMES];

export const MATCH_ROUND_LABELS: Record<MatchRoundKey, string> = {
  qualifying: "Qualifying",
  ...ROUND_LABELS,
};

/** Short label for the pill strip — a phone has no room for "Quarter-finals". */
export const MATCH_ROUND_PILL_LABELS: Record<MatchRoundKey, string> = {
  qualifying: "Qual",
  R128: "R128",
  R64: "R64",
  R32: "R32",
  R16: "R16",
  QF: "QF",
  SF: "SF",
  F: "Final",
};

/**
 * Normalise whatever the slate calls a round onto a key we can order.
 *
 * The slate's `round` is a free string from the register ("qualifying" today).
 * An unrecognised value returns `null` and the match is filed under
 * `qualifying` rather than dropped — losing a real match because we could not
 * classify it is strictly worse than filing it one pill to the left, and the
 * pill still names a real round the tournament plays.
 */
export function slateRoundKey(round: string | null | undefined): MatchRoundKey {
  const raw = (round ?? "").trim().toLowerCase();
  if (raw === "") return "qualifying";
  const direct = MATCH_ROUND_ORDER.find((key) => key.toLowerCase() === raw);
  if (direct) return direct;
  if (raw.startsWith("qual")) return "qualifying";
  if (raw.includes("128")) return "R128";
  if (raw.includes("64")) return "R64";
  if (raw.includes("32")) return "R32";
  if (raw.includes("16")) return "R16";
  if (raw.startsWith("quarter")) return "QF";
  if (raw.startsWith("semi")) return "SF";
  if (raw === "final" || raw === "f") return "F";
  return "qualifying";
}

/**
 * Why a side has no name yet. Three different facts, three different sentences
 * (UX-P137, ruling 3 — "nothing renders blank").
 */
export type SidePlaceholder = "none" | "register-hole" | "awaiting-feeder";

export interface MatchListSide {
  /** `null` only for a placeholder side. */
  entityKey: string | null;
  /** The player, or the sentence that says what will fill this slot. */
  displayName: string;
  seed: number | null;
  /** Register-pinned face + flag (ruling 8). `null` on a placeholder side. */
  image: PlayerImage | null;
  /** TO WIN THIS MATCH. The primary number (ruling 1). */
  matchProbability: number | null;
  /** What the market said before it started — the detail view's addition. */
  openingProbability: number | null;
  move: number | null;
  /** TO WIN THE TOURNAMENT. The muted secondary chip (ruling 1). */
  titleChance: number | null;
  isWinner: boolean;
  placeholder: SidePlaceholder;
  /** UX-P157. This side's own book grade — see `lib/liquidity`. */
  liquidity?: string | null;
  liquidity_reasons?: string[] | null;
  /** The side's own last reading, for the reveal's "precisely when". */
  observedAt?: string | null;
}

export interface MatchListEntry {
  id: string;
  /**
   * Does ANY source quote this match (UX-P142)?
   *
   * `false` is the released main draw four days out. Separate from `coherent`,
   * which is two quotes disagreeing: this row has no quotes at all, and the
   * two states get different sentences because they are different facts.
   */
  priced: boolean;
  round: MatchRoundKey;
  roundLabel: string;
  /** ISO string, or `null` for a bracket match with no scheduled date. */
  scheduledDate: string | null;
  /**
   * `scheduledDate` is a DAY, not a time (Q463) — the source has published no
   * order of play for this fixture, so the timestamp is midnight local. The
   * row says TBD and prints no clock; see `SlateMatch.start_is_tbd`.
   */
  startIsTbd: boolean;
  /** ESPN's live state for the fixture, or `null` when it carries none (Q463). */
  liveState: "in_progress" | "upcoming" | null;
  drawLabel: string | null;
  sides: [MatchListSide, MatchListSide];
  decided: boolean;
  /**
   * "6-1, 6-4" (Alex's ruling 2), or `null`.
   *
   * ALWAYS `null` on real data today, and that is a statement about our
   * pipeline rather than about this code. Neither `build_bracket` nor
   * `build_slate` emits a result, let alone a score: the register carries a
   * draw, prices and matchups, and nothing anywhere in the backend has ever
   * held who won a tennis match or by what. The seam is here, typed and
   * rendered, so the day a result feed lands it is an ingest change and not
   * another layout pass — the same posture `matchBroadcast` takes toward
   * per-match rights.
   */
  score: string | null;
  coherent: boolean;
  isLive: boolean;
  /** "3 hours ago", naming the stale side when only one is old. `null` if live. */
  freshnessLabel: string | null;
  broadcast: ResolvedBroadcast | null;
  /**
   * The one sentence this row is allowed, or `null` (Alex's ruling 6).
   * See `matchDetailNote` — most rows get `null`, on purpose.
   */
  detailNote: string | null;
  /**
   * OUR event id, when this match has an `events` row — Alex's item 7,
   * "matches click through to the standard event page".
   *
   * `null` on every US Open match today, and that is a data fact rather than a
   * missing feature: checked 2026-08-26, **zero** of the register's matchups
   * have an `events` row. The US Open qualifying draw was never ingested as
   * events at all, so there is no page to click through to.
   *
   * The seam is here, typed and rendered, because the fix is an ingest change
   * and the link should not be a second layout pass on the day it lands. It is
   * REGISTER-OWNED (`matchup.event_id`), never derived from a name match at
   * render time — a link to the wrong match is worse than no link, and a name
   * join across two systems that disagree about `Auger-Aliassime` is exactly
   * how you get one.
   *
   * The report's honest assessment of the DESTINATION is separate and less
   * comfortable: today's tennis event pages carry surname-only participants, no
   * blended win probability (`win_probability_sources` is null on every tennis
   * event checked), no player images and no props. Linking to one before that
   * is fixed would send a reader from a rich page to a bare one.
   */
  eventId: number | null;
  /**
   * THE REGISTER'S KEY FOR THIS FIXTURE, and the address of its own page
   * (UX-P149) — `/tournaments/{slug}/matches/{matchupKey}`.
   *
   * Separate from `id`, which is the LIST's key and is a draw-slot id on a
   * bracket-sourced row. Only a registered matchup has a page, so a bracket
   * row that never joined a slate row carries `null` here and renders no link
   * rather than one that 404s.
   *
   * This is what `eventId` was reaching for and could not have: it is
   * register-owned, it exists today on every priced fixture, and it needs no
   * `events` row — which is the blocker lane1's Q426 note named as the reason
   * the props had nowhere to go.
   */
  matchupKey: string | null;
  source: "slate" | "bracket";
}

/** Unordered pair key — the only thing the slate and the draw share. */
function pairKey(a: string, b: string): string {
  return [a, b].sort().join("|");
}

/**
 * The one sentence a match row may carry, or `null` (ALEX'S RULING 6).
 *
 * THE COMPLAINT, verbatim: "probability + movement delta + a sentence
 * restating both is three renderings of one fact." It was exactly that. The
 * row printed `78%`, then `−4`, then "Alcaraz opened at 82%, down to 78%" —
 * and the sentence's only new token was the opening price, buried in a clause
 * that repeated the two numbers already on the row.
 *
 * So the rule is not "shorten the sentence", it is: **a sentence appears only
 * when it adds something the numbers do not.** Three cases survive, and they
 * survive because in each one the numbers on the row cannot say it:
 *
 *   1. An INCOHERENT pair shows no numbers at all (gotcha #23), so the row is
 *      two names and nothing else. Without the sentence it is unreadable.
 *   2. A MOVED price: the row shows the delta but never the origin. "Opened at
 *      82%" is the one fact the chip cannot carry.
 *   3. A DECIDED match with no score: the outcome chip says who won, and the
 *      pre-match number says what was expected, but "the favourite lost" is
 *      only legible if you compare them yourself.
 *
 * Everything else — and it is most rows — returns `null`. A flat match's
 * silence IS the information, and "has not moved" was a sentence saying
 * nothing three times over.
 */
export function matchDetailNote(entry: {
  coherent: boolean;
  decided: boolean;
  score: string | null;
  sides: [MatchListSide, MatchListSide];
  /** Absent reads as priced — every row before UX-P142 was. */
  priced?: boolean;
}): string | null {
  if (entry.priced === false) {
    // FOURTH CASE (UX-P142). An unpriced fixture used to fall into the
    // incoherent branch and tell the reader "the two prices do not agree",
    // which names a disagreement between two numbers that do not exist. The
    // released main draw is 96 such rows; getting this sentence wrong would
    // have been the page's most-printed sentence on ceremony day.
    // UX-P146: "the price comes later" — Alex's product-wide ruling on the noun.
    // Ruling 142: "the number comes later" was still a promise about a listing
    // we do not control. The fact is the fixture is real and has no probability.
    return "Nobody is quoting this match yet. It is in the draw with no probability against it.";
  }
  if (!entry.coherent) {
    return "The two numbers for this match do not agree yet, so we are not showing a split.";
  }

  if (entry.decided) {
    const winner = entry.sides.find((side) => side.isWinner);
    const loser = entry.sides.find((side) => !side.isWinner);
    if (
      winner &&
      loser &&
      winner.matchProbability !== null &&
      loser.matchProbability !== null &&
      loser.matchProbability > winner.matchProbability
    ) {
      // The upset. The two numbers are both on the row and the comparison
      // between them is not — this is the only decided row that gets words.
      return `${loser.displayName} was favoured at ${formatSlateProbability(
        loser.matchProbability
      )}.`;
    }
    return null;
  }

  // The biggest mover of the two. One sentence per row, never two.
  const moved = entry.sides
    .filter((side) => moveDirection(side.move) !== "flat")
    .sort((a, b) => Math.abs(b.move ?? 0) - Math.abs(a.move ?? 0))[0];
  if (moved && moved.openingProbability !== null) {
    return `${moved.displayName} opened at ${formatSlateProbability(
      moved.openingProbability
    )}.`;
  }
  return null;
}

/** Title chances by entity key, read off the championship board. */
export type TitleChances = Record<string, number | null>;

function sideFromSlate(
  side: SlateMatch["sides"][number],
  titleChances: TitleChances,
  winnerKey: string | null
): MatchListSide {
  return {
    entityKey: side.entity_key,
    displayName: side.display_name,
    seed: side.seed,
    image: side.image ?? null,
    matchProbability: side.probability,
    openingProbability: side.opening_probability,
    move: side.move,
    titleChance: titleChances[side.entity_key] ?? null,
    isWinner: winnerKey !== null && winnerKey === side.entity_key,
    placeholder: "none",
    // UX-P157. PER SIDE and not per row: a 90/10 is two separate venue rows,
    // and it is routinely the underdog's that nobody will trade at.
    liquidity: side.liquidity ?? null,
    liquidity_reasons: side.liquidity_reasons ?? null,
    observedAt: side.observed_at ?? null,
  };
}

/**
 * The slate, as match-list entries.
 *
 * Preserves server order within a round; the caller groups and filters.
 */
export function matchListFromSlate(
  matches: SlateMatch[],
  options: {
    titleChances?: TitleChances;
    broadcasts?: Broadcast[];
    region?: string;
  } = {}
): MatchListEntry[] {
  const titleChances = options.titleChances ?? {};
  const out: MatchListEntry[] = [];

  for (const match of matches) {
    if (!Array.isArray(match.sides) || match.sides.length !== 2) continue;
    const winnerKey = match.winner_entity_key ?? null;
    const sides: [MatchListSide, MatchListSide] = [
      sideFromSlate(match.sides[0], titleChances, winnerKey),
      sideFromSlate(match.sides[1], titleChances, winnerKey),
    ];
    // The favourite leads, exactly as the old slate row ordered them — but
    // only when the split is trustworthy. An incoherent pair keeps server
    // order, because picking the larger of two numbers we have refused to
    // display would smuggle the refused comparison back onto the page.
    if (match.coherent) {
      sides.sort((a, b) => (b.matchProbability ?? 0) - (a.matchProbability ?? 0));
    }

    const decided = winnerKey !== null;
    const round = slateRoundKey(match.round);
    const entry: MatchListEntry = {
      id: match.matchup_key,
      priced: match.priced !== false,
      round,
      roundLabel: MATCH_ROUND_LABELS[round],
      scheduledDate: match.scheduled_date ?? null,
      startIsTbd: match.start_is_tbd === true,
      liveState: match.live_state ?? null,
      drawLabel: match.draw_label ?? null,
      sides,
      decided,
      score: match.score ?? null,
      coherent: match.coherent,
      isLive: slateRowIsPresentedAsLive(match),
      freshnessLabel: slateRowFreshnessLabel(match),
      broadcast: matchBroadcast(match, options.broadcasts, options.region),
      detailNote: null,
      eventId: match.event_id ?? null,
      matchupKey: match.matchup_key ?? null,
      source: "slate",
    };
    entry.detailNote = matchDetailNote(entry);
    out.push(entry);
  }
  return out;
}

/**
 * The draw, as match-list entries — with the slate's prices joined on.
 *
 * A bracket match has a position and a title probability per side; it has no
 * price on itself. The price for "Alcaraz beats Rublev today" lives in the
 * slate, keyed by the unordered pair. So this joins, exactly as
 * `prematchFromSlate` does, and for the same reason: the pair is the only key
 * the two datasets share.
 *
 * An undetermined slot NEVER renders blank (UX-P137, ruling 3). A round-one
 * hole is a register gap; a later hole is an unplayed feeder; the two get
 * different sentences because they are different facts.
 */
export function matchListFromBracket(
  rounds: BracketRound[],
  options: {
    slate?: SlateMatch[];
    prematch?: Record<string, PrematchPair>;
    titleChances?: TitleChances;
    broadcasts?: Broadcast[];
    region?: string;
    /** Decided-match scores by bracket match id. Empty in production — see `score`. */
    scores?: Record<string, string>;
  } = {}
): MatchListEntry[] {
  const titleChances = options.titleChances ?? {};
  const scores = options.scores ?? {};
  const slateByPair = new Map<string, SlateMatch>();
  for (const match of options.slate ?? []) {
    if (!Array.isArray(match.sides) || match.sides.length !== 2) continue;
    slateByPair.set(
      pairKey(match.sides[0].entity_key, match.sides[1].entity_key),
      match
    );
  }

  const out: MatchListEntry[] = [];
  for (const round of rounds) {
    // A ROUND NOBODY HAS REACHED CONTRIBUTES NOTHING TO A MATCH LIST.
    //
    // UX-P136's lesson, restated in this structure. On the morning of the draw
    // every round after the first is 63 cards reading "Winner of R128 #1" v
    // "Winner of R128 #2", and under ruling 4 each of those rounds would also
    // get its own pill — a strip of seven where six open onto a wall. The
    // future is the GRID's subject now, and the grid says something true about
    // it. A round appears in this list the moment one real name lands in it.
    if (roundIsUnreached(round)) continue;
    for (const match of round.matches) {
      const decided = match.winnerKey !== null;
      const joined =
        match.top && match.bottom
          ? slateByPair.get(pairKey(match.top.entity_key, match.bottom.entity_key))
          : undefined;
      const priceFor = (entityKey: string): SlateMatch["sides"][number] | undefined =>
        joined?.sides.find((side) => side.entity_key === entityKey);

      const build = (
        slot: BracketRound["matches"][number]["top"],
        from: string | null
      ): MatchListSide => {
        if (slot === null) {
          return {
            entityKey: null,
            // UX-P145: was "No registered player". The reader does not have a
            // register; they have a draw with a slot nobody has filled in.
            // `placeholder: "register-hole"` keeps our name for it where our
            // names belong — on a data attribute, not in the sentence.
            displayName:
              from === null ? "Player to be confirmed" : `Winner of ${from.replace("-", " #")}`,
            seed: null,
            image: null,
            matchProbability: null,
            openingProbability: null,
            move: null,
            titleChance: null,
            isWinner: false,
            placeholder: from === null ? "register-hole" : "awaiting-feeder",
          };
        }
        const price = priceFor(slot.entity_key);
        // Ruling 1: the MATCH number is the primary. Live price when the slate
        // has one; the pre-match number when the match is over and the live
        // price has collapsed to 1 or 0; `null` when we simply have neither.
        const pre =
          match.top && slot.entity_key === match.top.entity_key
            ? (options.prematch?.[match.id]?.top ?? null)
            : (options.prematch?.[match.id]?.bottom ?? null);
        return {
          entityKey: slot.entity_key,
          displayName: slot.display_name,
          seed: slot.seed,
          // A draw slot carries no image of its own; like the price, it comes
          // from the slate row this match absorbed.
          image: price?.image ?? null,
          matchProbability: decided ? pre : (price?.probability ?? pre),
          openingProbability: price?.opening_probability ?? pre,
          move: decided ? null : (price?.move ?? null),
          // The title chance prefers the BOARD, because the board is the
          // surface this number is published on and two surfaces printing
          // different values for one question is the divergence bug, not a
          // feature. The draw slot's own copy is the fallback.
          titleChance: titleChances[slot.entity_key] ?? slot.probability ?? null,
          isWinner: match.winnerKey === slot.entity_key,
          placeholder: "none",
        };
      };

      const sides: [MatchListSide, MatchListSide] = [
        build(match.top, match.topFrom),
        build(match.bottom, match.bottomFrom),
      ];

      const entry: MatchListEntry = {
        id: match.id,
        priced: joined ? joined.priced !== false : false,
        round: match.round,
        roundLabel: MATCH_ROUND_LABELS[match.round],
        scheduledDate: joined?.scheduled_date ?? null,
        startIsTbd: joined?.start_is_tbd === true,
        liveState: joined?.live_state ?? null,
        drawLabel: joined?.draw_label ?? null,
        sides,
        decided,
        score: scores[match.id] ?? joined?.score ?? null,
        coherent: joined ? joined.coherent : true,
        isLive: joined ? slateRowIsPresentedAsLive(joined) : false,
        freshnessLabel: joined ? slateRowFreshnessLabel(joined) : null,
        broadcast: joined
          ? matchBroadcast(joined, options.broadcasts, options.region)
          : null,
        detailNote: null,
        // A positioned draw slot has no event of its own; the link, like the
        // price, comes from the slate row it absorbed.
        eventId: joined?.event_id ?? null,
        matchupKey: joined?.matchup_key ?? null,
        source: "bracket",
      };
      entry.detailNote = matchDetailNote(entry);
      out.push(entry);
    }
  }
  return out;
}

/**
 * THE match list: the draw where we have it, the slate where we do not.
 *
 * The dedup is the point. A slate match whose pair is already positioned in
 * the draw is dropped, because the bracket entry ABSORBED it — same match, one
 * row, with both the draw position and the price. Before this, a main-draw
 * afternoon printed every match twice on two tabs and nothing said they were
 * the same match.
 */
export function buildMatchList(options: {
  slate?: SlateMatch[];
  rounds?: BracketRound[];
  prematch?: Record<string, PrematchPair>;
  titleChances?: TitleChances;
  broadcasts?: Broadcast[];
  region?: string;
  scores?: Record<string, string>;
}): MatchListEntry[] {
  const slate = options.slate ?? [];
  const rounds = options.rounds ?? [];
  const bracketEntries = matchListFromBracket(rounds, options);

  const absorbed = new Set<string>();
  for (const round of rounds) {
    for (const match of round.matches) {
      if (match.top && match.bottom) {
        absorbed.add(pairKey(match.top.entity_key, match.bottom.entity_key));
      }
    }
  }

  const remaining = slate.filter((match) => {
    if (!Array.isArray(match.sides) || match.sides.length !== 2) return false;
    return !absorbed.has(pairKey(match.sides[0].entity_key, match.sides[1].entity_key));
  });

  return [...matchListFromSlate(remaining, options), ...bracketEntries];
}

export interface MatchRoundPill {
  round: MatchRoundKey;
  label: string;
  shortLabel: string;
  total: number;
  decided: number;
}

/**
 * The round pills — ONLY rounds that actually have matches (ruling 4).
 *
 * A pill for a round we hold nothing for is the empty-tab failure with a
 * smaller footprint: the reader taps it and gets a wall. Rounds appear as the
 * draw reaches them.
 */
export function matchRoundPills(entries: MatchListEntry[]): MatchRoundPill[] {
  const counts = new Map<MatchRoundKey, { total: number; decided: number }>();
  for (const entry of entries) {
    const bucket = counts.get(entry.round) ?? { total: 0, decided: 0 };
    bucket.total += 1;
    if (entry.decided) bucket.decided += 1;
    counts.set(entry.round, bucket);
  }
  return MATCH_ROUND_ORDER.filter((round) => counts.has(round)).map((round) => ({
    round,
    label: MATCH_ROUND_LABELS[round],
    shortLabel: MATCH_ROUND_PILL_LABELS[round],
    total: counts.get(round)?.total ?? 0,
    decided: counts.get(round)?.decided ?? 0,
  }));
}

/**
 * Which round to open on: the earliest one still being played.
 *
 * "Where the tournament is" — the same rule the round strip used, kept because
 * it was right: opening on a Round of 128 that finished a week ago is the
 * default that makes a reader tap before they can read anything.
 */
export function defaultMatchRound(entries: MatchListEntry[]): MatchRoundKey | null {
  const pills = matchRoundPills(entries);
  if (pills.length === 0) return null;
  return (pills.find((pill) => pill.decided < pill.total) ?? pills[pills.length - 1]).round;
}

export function matchesInRound(
  entries: MatchListEntry[],
  round: MatchRoundKey
): MatchListEntry[] {
  return entries.filter((entry) => entry.round === round);
}

/**
 * ═══ WHAT HAPPENED TO THE REST OF THE ROUND (#2450) ═══
 *
 * Alex: *"`ROUND OF 128 · 25 matches` next to `FINISHED · Men's Singles · 71`.
 * Nothing explains how a 128-draw shows 25 live and 71 finished, or what
 * happened to the rest."*
 *
 * He is doing the only arithmetic available to him and it does not close. Both
 * numbers are correct and they count DIFFERENT POPULATIONS, which is the one
 * thing neither of them said:
 *
 *   - `25` is the matches of this round still in the list. `build_slate` drops
 *     a matchup the moment it starts (`ALREADY_PLAYED: 28, DECIDED: 66` on the
 *     live payload 2026-09-01), so the list holds the unfinished remainder of
 *     the round and never the whole of it.
 *   - `71` is every finished match in this DRAW across every round, qualifying
 *     included — 178 rows platform-side, of which the men's singles held 84 on
 *     2026-09-01: 41 in the main draw and 43 across three qualifying rounds.
 *
 * So the two numbers cannot be added, subtracted or compared, and the page was
 * inviting a reader to do all three.
 *
 * ### The size of a round is definitional, and that is the missing anchor
 *
 * A round of 128 is 64 matches. Not a lookup, not a payload field, not an
 * assumption about the draw — `R128` MEANS 128 players, and 128 players is 64
 * matches. So the list can state the round's true size beside the count it is
 * showing, and the reader's arithmetic closes on the spot: 64 in the round, 16
 * here, the rest have finished.
 *
 * `null` for `qualifying`, which is the one key that is not a `RoundName`: it
 * buckets three rounds of a draw whose size we genuinely do not know, and
 * inventing a number for it would be exactly the unexplained figure this
 * function exists to remove.
 */
export function matchRoundSize(round: MatchRoundKey): number | null {
  if (round === "qualifying") return null;
  const players = ROUND_PLAYER_COUNTS[round];
  return players === undefined ? null : players / 2;
}

const ROUND_PLAYER_COUNTS: Record<RoundName, number> = {
  R128: 128,
  R64: 64,
  R32: 32,
  R16: 16,
  QF: 8,
  SF: 4,
  F: 2,
};

/**
 * The sentence that reconciles the two counts, or `null` when there is nothing
 * to reconcile.
 *
 * Deliberately does NOT say how many have finished. We know the round's size
 * and we know what is in this list; we do NOT know how many of the remainder
 * our results feed actually holds — 17 of the live payload's 82 Round-1 results
 * had already lost their register matchup, and 134 finished matches were
 * dropped for players the register does not carry. Printing `the other 48 have
 * finished` beside a Finished list showing 41 would replace one arithmetic
 * anyone can check with another one that also fails.
 *
 * So it states the two facts we can stand behind — the round's size, and that
 * finished matches leave this list — and lets the reader stop looking for the
 * missing rows.
 */
export function matchRoundReconciliation(
  round: MatchRoundKey,
  shown: number
): string | null {
  const size = matchRoundSize(round);
  if (size === null) return null;
  // The whole round is here: nothing is missing, so nothing needs explaining.
  if (shown >= size) return null;
  // "This round is 64 matches", not "a round of 128 is 64 matches": the label
  // reads naturally for the draw-size rounds and not at all for the named ones
  // ("a quarter-finals is 4 matches"), and the heading directly above already
  // says which round this is.
  return `This round is ${size} matches. Finished ones move to Finished, below.`;
}

/**
 * The muted secondary chip's text (ruling 1).
 *
 * SELF-LABELLING, and that is not decoration. The whole of UX-P137's ruling 2
 * was Alex being unable to tell what a bare percentage on this page meant, and
 * the answer turned out to be the chance of winning the entire tournament
 * printed beside the opponent a player was about to play. A chip that reads
 * "22%" beside a match number would re-create that exact confusion in a
 * smaller font. `null` when there is nothing to say — never "—", because an
 * absent chip is quieter than a chip apologising for being empty, and Alex's
 * density constraint is the binding one here.
 */
export function titleChipLabel(titleChance: number | null): string | null {
  if (titleChance === null || !Number.isFinite(titleChance)) return null;
  return `${Math.round(titleChance * 100)}% title`;
}

/** Full sentence for screen readers and `title=` — the chip is terse by design. */
export function titleChipDescription(displayName: string, titleChance: number): string {
  return `${displayName}: ${Math.round(
    titleChance * 100
  )}% chance of winning the tournament`;
}

/** The row's age line — mirrors the boards so the page words one idea one way. */
export function matchAgeLabel(ageHours: number | null): string {
  return slateStalenessLabel(ageHours);
}
