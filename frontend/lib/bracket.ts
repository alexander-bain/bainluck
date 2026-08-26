/**
 * Draw-bracket construction (UX-P131, charter amendment 2026-08-25).
 *
 * "Blockers block items, never lanes": the bracket does not wait for
 * Thursday's draw ceremony. It is built against a SYNTHETIC 128-slot fixture
 * so that 08-28 is ingest-the-real-draw day rather than start-building day.
 * The fixture lives under `__tests__/fixtures/` and is therefore outside the
 * Next.js app tree — it cannot reach production by import, which is a stronger
 * guarantee than a comment asking nobody to import it.
 *
 * The shape is deliberately dumb: a draw is an ordered array of slots, and the
 * bracket is that array folded in half repeatedly. Round N+1 is populated only
 * where a winner is actually KNOWN. An unplayed match renders as two names and
 * no probability rather than as a prediction, because the charter's reliability
 * doctrine is "every tap does what it looks like it does" and a greyed-out
 * projected winner looks exactly like a result.
 */

export const ROUND_NAMES = ["R128", "R64", "R32", "R16", "QF", "SF", "F"] as const;
export type RoundName = (typeof ROUND_NAMES)[number];

export const ROUND_LABELS: Record<RoundName, string> = {
  R128: "Round of 128",
  R64: "Round of 64",
  R32: "Round of 32",
  R16: "Round of 16",
  QF: "Quarter-finals",
  SF: "Semi-finals",
  F: "Final",
};

export interface BracketSlot {
  entity_key: string;
  display_name: string;
  seed: number | null;
  /** Blended title probability, when the register has one. Never invented. */
  probability: number | null;
}

export interface BracketMatch {
  id: string;
  round: RoundName;
  /** `null` means the slot is not yet determined — a bye, or an unplayed feeder. */
  top: BracketSlot | null;
  bottom: BracketSlot | null;
  /** Set only when the match has actually been decided. */
  winnerKey: string | null;
  /**
   * The match ids this one's two slots come from, or `null` in round one
   * (added UX-P137, Alex's ruling 3: "decided matches must not render blank").
   *
   * A `null` slot used to render as a bare em-dash, and a card reading
   * "— v —" is the single most common thing on the page for most of a
   * tournament day: on the morning of the draw 62 of 127 cards are empty, and
   * at any hour after that the round in progress is half holes. An em-dash
   * says "we have nothing"; "Winner of match 23" says the same thing while
   * being true, checkable, and a pointer to where the answer will come from.
   *
   * In round one there is no feeder, so `null` here is honest too — an empty
   * round-one slot is a register hole, not an unplayed match, and the two get
   * different words.
   */
  topFrom: string | null;
  bottomFrom: string | null;
}

/**
 * Each side's PRE-MATCH probability for a decided match, keyed by match id.
 *
 * Ruling 3: a decided match must print the pre-match probability AND the
 * outcome, the way decided event cards do everywhere else in the app. Bold
 * versus muted is not an outcome — it is a font weight, and it is the only
 * thing a settled bracket row used to say.
 *
 * These are MATCH probabilities and have nothing to do with the title
 * probability a slot carries. Keeping them in a separate structure rather than
 * on `BracketSlot` is deliberate: the two numbers answer different questions,
 * and the whole of ruling 2 is about not letting one be mistaken for the other.
 */
export interface PrematchPair {
  top: number | null;
  bottom: number | null;
}

export interface BracketRound {
  round: RoundName;
  label: string;
  matches: BracketMatch[];
}

/**
 * Fold an ordered slot list into rounds.
 *
 * `slots` is positional: index 0 plays index 1, index 2 plays index 3, and so
 * on. `results` maps a match id to the entity key that won it; absent entries
 * mean "not played", never "not yet predicted".
 *
 * NOTHING ADVANCES WITHOUT A DECLARED RESULT (fixed UX-P136).
 *
 * This used to advance a player whose opponent slot was `null`, reading it as
 * a bye. It is not a bye, and the backend that produces these slots says so in
 * its own contract — `build_bracket` returns `None` "where the draw has a slot
 * we hold no registered player for … not a bye, and never a name we invented
 * to fill the shape."
 *
 * The rule was wrong in both places it fired:
 *
 *   - In round one, `null` is a register hole. Advancing the opponent prints a
 *     player into the Round of 64 for winning a match against nobody.
 *   - In every later round, `null` is the ordinary state of a feeder that has
 *     not been played yet. On a real tournament day the draw completes a few
 *     matches at a time, so half of round one decided would have silently
 *     walked those winners two rounds forward.
 *
 * Both print a name in a round it has not reached, which is the one thing the
 * charter's reliability doctrine forbids: a projection that looks exactly like
 * a result. A bye is not currently expressible in the register at all, so
 * there is no case this loses — only the invented one.
 */
export function buildBracket(
  slots: (BracketSlot | null)[],
  results: Record<string, string> = {}
): BracketRound[] {
  const size = slots.length;
  if (size < 2 || (size & (size - 1)) !== 0) {
    // Not a power of two: refuse rather than silently truncating a draw.
    return [];
  }

  // A 128-slot draw starts at R128; a 32-slot one starts at R32. Aligning to
  // the END of ROUND_NAMES means the final is always the last column.
  const roundCount = Math.log2(size);
  const startIndex = ROUND_NAMES.length - roundCount;
  if (startIndex < 0) return [];

  const rounds: BracketRound[] = [];
  let current: (BracketSlot | null)[] = [...slots];

  for (let r = 0; r < roundCount; r += 1) {
    const round = ROUND_NAMES[startIndex + r];
    const previous = r === 0 ? null : ROUND_NAMES[startIndex + r - 1];
    const matches: BracketMatch[] = [];
    const next: (BracketSlot | null)[] = [];

    for (let i = 0; i < current.length; i += 2) {
      const top = current[i] ?? null;
      const bottom = current[i + 1] ?? null;
      const id = `${round}-${i / 2 + 1}`;
      const declared = results[id] ?? null;
      // Slot `i` of this round is fed by match `i + 1` of the previous one
      // (1-indexed ids over a 0-indexed fold). Off by one here would print a
      // confidently wrong sentence — "Winner of match 6" pointing at match 5 —
      // which is worse than the em-dash it replaces, so it has its own test.
      const topFrom = previous === null ? null : `${previous}-${i + 1}`;
      const bottomFrom = previous === null ? null : `${previous}-${i + 2}`;

      // A declared winner must actually be in the match. A result naming
      // somebody who is not one of these two slots is a data fault, and
      // advancing `null` is the honest response to it — better an empty slot
      // than a name teleported across the draw.
      const advancing =
        declared === null
          ? null
          : [top, bottom].find((s) => s?.entity_key === declared) ?? null;

      matches.push({
        id,
        round,
        top,
        bottom,
        winnerKey: advancing?.entity_key ?? null,
        topFrom,
        bottomFrom,
      });
      next.push(advancing);
    }

    rounds.push({ round, label: ROUND_LABELS[round], matches });
    current = next;
  }

  return rounds;
}

/**
 * A round nobody has reached yet: every slot in it is still undetermined.
 *
 * Worth its own predicate because the alternative is what the component used
 * to do — render 16 identical "— v —" cards for the Round of 32 on the morning
 * the draw comes out. Sixty-two empty cards is not information, it is a wall
 * that buries the two rounds that DO have names in them.
 */
export function roundIsUnreached(round: BracketRound): boolean {
  return round.matches.every((m) => m.top === null && m.bottom === null);
}

/**
 * The column header a view owes its percentages (UX-P137, Alex's ruling 2).
 *
 * THE FINDING THIS EXISTS FOR, stated plainly because it is the reason the
 * ruling was issued: the bracket's percentage is the chance of winning the
 * WHOLE TOURNAMENT, and nothing on the page said so. `build_bracket` fills a
 * slot's probability from the register player's `sources`, every one of which
 * is `kind: "outright"` against the champion market — the same outcomes the
 * championship board reads. Printed beside an opponent a player is about to
 * play, "18.0%" reads irresistibly as "18% to win this match". Alex could not
 * tell which it was, and he had the codebase.
 *
 * So a number on this page now travels with the question it answers, and views
 * that mean different things say different things. There is no default: a
 * caller adding a new percentage column has to name what it means.
 */
export const TITLE_COLUMN_LABEL = "To win the title";

/** "To reach the quarter-finals" — the advance-to-stage column (ruling 4). */
export function reachColumnLabel(round: RoundName): string {
  return `To reach the ${ROUND_LABELS[round].toLowerCase()}`;
}

/** The minimum a slate match must expose to be joined onto the bracket. */
interface JoinableMatch {
  sides: {
    entity_key: string;
    probability: number | null;
    opening_probability: number | null;
  }[];
}

/**
 * Pre-match probabilities per bracket match, joined from the day's slate.
 *
 * The join key is the unordered PAIR of entity keys, because that is the only
 * thing the two datasets share — the slate is keyed by matchup and scheduled
 * date, the bracket by fold position, and neither knows the other's id. A pair
 * that appears in the slate but not the draw is simply absent from the result;
 * this never guesses.
 *
 * It reads `opening_probability` and falls back to `probability`. Opening is
 * "THE SCRIPT" in the slate's own words, and it is the only pre-match number
 * that survives the match: once a match is decided the live probability has
 * collapsed to 1 or 0, so printing it beside the result would be a tautology
 * dressed as a forecast.
 */
export function prematchFromSlate(
  matches: JoinableMatch[],
  rounds: BracketRound[]
): Record<string, PrematchPair> {
  const byPair = new Map<string, Map<string, number>>();
  for (const match of matches) {
    if (!Array.isArray(match.sides) || match.sides.length !== 2) continue;
    const keys = match.sides.map((side) => side.entity_key);
    if (keys.some((key) => typeof key !== "string" || key === "")) continue;
    const pairKey = [...keys].sort().join("|");
    const perEntity = new Map<string, number>();
    for (const side of match.sides) {
      const value = side.opening_probability ?? side.probability;
      if (typeof value === "number" && Number.isFinite(value)) {
        perEntity.set(side.entity_key, value);
      }
    }
    if (perEntity.size > 0) byPair.set(pairKey, perEntity);
  }

  const out: Record<string, PrematchPair> = {};
  for (const round of rounds) {
    for (const match of round.matches) {
      if (match.top === null || match.bottom === null) continue;
      const pairKey = [match.top.entity_key, match.bottom.entity_key].sort().join("|");
      const found = byPair.get(pairKey);
      if (!found) continue;
      out[match.id] = {
        top: found.get(match.top.entity_key) ?? null,
        bottom: found.get(match.bottom.entity_key) ?? null,
      };
    }
  }
  return out;
}

/** How much of the draw is actually decided — for an honest progress line. */
export function bracketProgress(rounds: BracketRound[]): {
  played: number;
  total: number;
} {
  let played = 0;
  let total = 0;
  for (const round of rounds) {
    for (const match of round.matches) {
      total += 1;
      if (match.winnerKey !== null) played += 1;
    }
  }
  return { played, total };
}
