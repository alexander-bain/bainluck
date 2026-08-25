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

import type { BracketSlot } from "@/lib/bracket";

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
