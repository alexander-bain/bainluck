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

      // A bye advances without being a "result": one side is simply absent.
      const implicit =
        top !== null && bottom === null
          ? top.entity_key
          : bottom !== null && top === null
            ? bottom.entity_key
            : null;
      const winnerKey = declared ?? implicit;

      matches.push({ id, round, top, bottom, winnerKey: declared });
      next.push(
        winnerKey === null
          ? null
          : [top, bottom].find((s) => s?.entity_key === winnerKey) ?? null
      );
    }

    rounds.push({ round, label: ROUND_LABELS[round], matches });
    current = next;
  }

  return rounds;
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
