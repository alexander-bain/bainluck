/**
 * #9876 — a title that offers a choice gets every choice it offers.
 *
 * Alex's real-feed checkpoint, 2026-09-30: "Will AOC run for Senate or
 * President?" is interesting, but "title promises two choices but only Senate
 * is visible." The market is real and carries both answers. Polymarket 872248,
 * futures 59159859, as stored 2026-09-30:
 *
 *     Will AOC announce a run for Senate or President before 2028?
 *     Senate 48% · President 41% · Neither 3%
 *
 * The card headlined `48%` over "Senate", and the group row printed `48%` with
 * "Senate leads at 48%, up 27 points since Aug 18". President was on neither.
 * Both surfaces print ONE number by design (the blend is the product), so the
 * other choice the title names comes with its own served number beside the
 * leader's name: "Senate · President 41%". No number is derived and no market
 * is invented. This only prints outcomes the market already serves.
 *
 * WHEN IT FIRES. All four must hold, or nothing changes:
 *   1. the title names two or more of the market's own printed outcomes, by
 *      `namedAt`'s boundary rule (so `3` is not found inside "2030");
 *   2. an "or" sits between the first and last of those names, so the title
 *      offers them as alternatives ("Senate or President"), not as a list
 *      that happens to contain them;
 *   3. the hero is one of the named choices. A hero the title does not name
 *      ("Neither" leading) keeps the row's existing label logic;
 *   4. each other choice has a price. An unpriced leg is left off, not shown
 *      as a dash.
 * `Yes` / `No` / `None` / `Other` never count as named: they are the words a
 * title is built from, not choices it offers.
 */

import type { HeroCandidate } from "./heroOutcome";
import { namedAt } from "./rowAnswerLabel";

const NOT_A_CHOICE = /^(yes|no|none|neither|other|tbd|n\/a)$/i;

/** The word that makes two names alternatives rather than a list. */
const OR_BETWEEN = /\bor\b/i;

/** Most other choices the line carries. The line is clamped to one row. */
const MAX_OTHERS = 2;

/**
 * The OTHER outcomes (not `hero`) that `title` offers as alternatives to it,
 * in served order, or `[]` when the title offers no such choice.
 */
export function titleNamedChoices<T extends HeroCandidate>(
  title: string | null | undefined,
  outcomes: readonly T[] | null | undefined,
  hero: HeroCandidate | null | undefined,
): T[] {
  if (!title || !hero || !outcomes || outcomes.length < 2) return [];
  const lowered = title.replace(/\s+/g, " ").trim().toLowerCase();

  const named: Array<{ outcome: T; at: number; end: number }> = [];
  for (const outcome of outcomes) {
    const name = (outcome?.name ?? "").replace(/\s+/g, " ").trim();
    if (!name || NOT_A_CHOICE.test(name)) continue;
    const at = namedAt(title, name);
    if (at < 0) continue;
    named.push({ outcome, at, end: at + name.length });
  }
  if (named.length < 2) return [];
  if (!named.some((n) => n.outcome === hero)) return [];

  const first = Math.min(...named.map((n) => n.at));
  const firstEnd = named.find((n) => n.at === first)!.end;
  const last = Math.max(...named.map((n) => n.at));
  if (!OR_BETWEEN.test(lowered.slice(firstEnd, last))) return [];

  return named
    .map((n) => n.outcome)
    .filter((o) => o !== hero && o.probability != null && Number.isFinite(o.probability))
    .slice(0, MAX_OTHERS);
}
