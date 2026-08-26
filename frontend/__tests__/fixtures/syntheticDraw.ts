/**
 * SYNTHETIC 128-slot draw — a TEST ASSET, never rendered in production.
 *
 * Charter amendment 2026-08-25, "blockers block items, never lanes": the
 * bracket does not wait for Thursday's draw ceremony. This fixture is what the
 * bracket component is built and gated against, so 08-28 is ingest-the-real-
 * draw day rather than start-building day.
 *
 * It lives under `__tests__/` deliberately. The Next.js app tree does not
 * compile this directory, so the fixture cannot reach a production bundle even
 * by accident — a structural guarantee rather than a comment asking nobody to
 * import it.
 *
 * The names are obviously synthetic on inspection but realistically shaped
 * (length, diacritics, seeding distribution), because a fixture of "Player 1"
 * through "Player 128" hides every layout problem a real draw will cause:
 * truncation, seed-badge collision, and the two-line name.
 */

import type { BracketSlot, PrematchPair } from "@/lib/bracket";

const FIRST_NAMES = [
  "Adrian", "Bastien", "Casper", "Dmitri", "Emil", "Fabio", "Gustav", "Hugo",
  "Ivan", "Jonas", "Kirill", "Lorenzo", "Mateo", "Nikola", "Oscar", "Pavel",
  "Quentin", "Rafael", "Sebastián", "Tomas", "Ugo", "Viktor", "Wei", "Yannick",
  "Zhang", "Andrés", "Bruno", "Corentin", "Diego", "Eduard", "Felix", "Grigor",
];

const LAST_NAMES = [
  "Alvarez", "Bergström", "Castellani", "Dvořák", "Escobar", "Fournier",
  "Grabowski", "Hedström", "Ibarra", "Janković", "Kowalczyk", "Lindqvist",
  "Møller", "Novotný", "Olivares", "Petrenko", "Quintana", "Rasmussen",
  "Sørensen", "Takahashi", "Ünal", "Vasquez", "Wojcik", "Ximénez",
  "Yilmaz", "Zaytsev", "Beaumont", "Cárdenas", "Delacroix", "Eriksson",
  "Ferreira", "Gómez",
];

const WOMEN_FIRST_NAMES = [
  "Alina", "Beatriz", "Camila", "Daria", "Elina", "Freja", "Greta", "Hana",
  "Iva", "Jelena", "Klara", "Lucía", "Marta", "Nadia", "Olga", "Paula",
  "Qiang", "Renata", "Sofia", "Tereza", "Ulrika", "Valeria", "Wiktoria",
  "Xenia", "Yulia", "Zofia", "Amélie", "Bianca", "Carolina", "Delphine",
  "Emilia", "Francesca",
];

/**
 * Build a deterministic draw. Deterministic matters: a fixture that reshuffles
 * turns a real regression into "probably the fixture again".
 */
function buildDraw(
  firsts: string[],
  lasts: string[],
  prefix: string,
  size = 128
): BracketSlot[] {
  const slots: BracketSlot[] = [];
  for (let i = 0; i < size; i += 1) {
    const first = firsts[i % firsts.length];
    const last = lasts[(i * 7 + 3) % lasts.length];
    // 32 seeds in a 128 draw, placed at the positions a real draw seeds:
    // 1 and 2 at the extremes, then spread. Approximated, not simulated.
    const seedIndex = Math.floor((i * 32) / size);
    const isSeeded = i % 4 === 0;
    slots.push({
      entity_key: `${prefix}-${i + 1}`,
      display_name: `${first} ${last}`,
      seed: isSeeded ? seedIndex + 1 : null,
      // Only the top of the draw carries a title probability; the rest of a
      // 128 field genuinely has none, and inventing one would make the fixture
      // lie in exactly the direction the product must not.
      probability: i < 16 ? Number((0.18 - i * 0.01).toFixed(4)) : null,
    });
  }
  return slots;
}

export const SYNTHETIC_MENS_DRAW: BracketSlot[] = buildDraw(
  FIRST_NAMES,
  LAST_NAMES,
  "syn-m"
);

export const SYNTHETIC_WOMENS_DRAW: BracketSlot[] = buildDraw(
  WOMEN_FIRST_NAMES,
  LAST_NAMES,
  "syn-w"
);

/** A partially-played draw: the first round decided, nothing after it. */
export function syntheticFirstRoundResults(
  draw: BracketSlot[]
): Record<string, string> {
  const results: Record<string, string> = {};
  for (let i = 0; i < draw.length; i += 2) {
    results[`R128-${i / 2 + 1}`] = draw[i].entity_key;
  }
  return results;
}

/**
 * The state the draw is actually in for most of a tournament day: SOME
 * first-round matches decided, the rest still on court.
 *
 * This exists because its absence hid a real bug (UX-P136). Every fixture was
 * all-or-nothing — no results, or all 64 — and the fold advanced a player
 * whose opponent slot was `null`, reading an undecided feeder as a bye. With
 * only the two extremes covered, nothing was ever half-decided, so nothing
 * ever exercised the branch that walked players into rounds they had not
 * reached. A day at the US Open is nothing BUT the half-decided state.
 */
export function syntheticPartialResults(
  draw: BracketSlot[],
  decided: number
): Record<string, string> {
  const results: Record<string, string> = {};
  for (let i = 0; i < decided * 2 && i < draw.length; i += 2) {
    results[`R128-${i / 2 + 1}`] = draw[i].entity_key;
  }
  return results;
}

/**
 * Pre-match prices for the matches a result set decided (UX-P137, ruling 3).
 *
 * A decided bracket row prints what the market said BEFORE the match beside
 * what happened, so a fixture with results and no pre-match prices exercises
 * exactly half of the rendering and hides the interesting half — the row where
 * the loser was the favourite.
 *
 * Deterministic, and deliberately NOT always favouring the winner: roughly
 * every fifth decided match here is an upset, because a fixture where the
 * bolded name always carries the bigger number would let a component that
 * simply printed the numbers in winner-first order pass.
 */
export function syntheticPrematch(
  results: Record<string, string>,
  draw: BracketSlot[]
): Record<string, PrematchPair> {
  const indexByKey = new Map(draw.map((slot, i) => [slot.entity_key, i]));
  const out: Record<string, PrematchPair> = {};
  let n = 0;
  for (const [matchId, winnerKey] of Object.entries(results)) {
    const seat = indexByKey.get(winnerKey) ?? 0;
    // 0.52 .. 0.86, stepped by the slot so it does not repeat down the column.
    const favourite = 0.52 + ((seat * 7) % 35) / 100;
    const upset = n % 5 === 4;
    const winnerSide = Number((upset ? 1 - favourite : favourite).toFixed(2));
    // The winner sits in the TOP slot of every synthetic result set, so `top`
    // is the winner's number and `bottom` is the complement.
    out[matchId] = { top: winnerSide, bottom: Number((1 - winnerSide).toFixed(2)) };
    n += 1;
  }
  return out;
}

/**
 * A draw with holes: slots the register holds no player for.
 *
 * The backend emits exactly this — `build_bracket` returns `None` "where the
 * draw has a slot we hold no registered player for … not a bye, and never a
 * name we invented to fill the shape" — so the frontend has to be gated
 * against it or the two halves disagree about what a hole means.
 */
export function syntheticDrawWithHoles(
  draw: BracketSlot[],
  holeIndexes: number[]
): (BracketSlot | null)[] {
  const holes = new Set(holeIndexes);
  return draw.map((slot, i) => (holes.has(i) ? null : slot));
}
