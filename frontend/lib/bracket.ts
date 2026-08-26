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
    const matches: BracketMatch[] = [];
    const next: (BracketSlot | null)[] = [];

    for (let i = 0; i < current.length; i += 2) {
      const top = current[i] ?? null;
      const bottom = current[i + 1] ?? null;
      const id = `${round}-${i / 2 + 1}`;
      const declared = results[id] ?? null;

      // A declared winner must actually be in the match. A result naming
      // somebody who is not one of these two slots is a data fault, and
      // advancing `null` is the honest response to it — better an empty slot
      // than a name teleported across the draw.
      const advancing =
        declared === null
          ? null
          : [top, bottom].find((s) => s?.entity_key === declared) ?? null;

      matches.push({ id, round, top, bottom, winnerKey: advancing?.entity_key ?? null });
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
