/**
 * Which direction is GOOD news for a grid column (#7745).
 *
 * The championship grid and the event page's outcomes ladder both paint a 24h
 * move green when it rises and red when it falls. That is right for every
 * column that is a rung toward something a club wants — and exactly backwards
 * for `relegation`, where the number going up is the bad outcome. On production
 * (`/sport/soccer/epl`, 2026-09-21) the Relegated column congratulated Arsenal
 * in green for `▲0.3` and printed Chelsea's `▼0.4` — their relegation risk
 * FALLING — in red. The payload was right; the colour editorialised it wrongly.
 *
 * So polarity is declared per column here rather than assumed at each renderer.
 * A renderer asks this module which way is up for the column it is drawing; it
 * does not read the label, which is a display string that re-words and
 * translates (a classifier keyed on "Relegated" misfiles the day it becomes
 * "Drop Zone"). The key is structured, straight from `league_configs.py` by way
 * of `columns[].key`.
 *
 * @see frontend/components/TournamentProgressionTable.tsx — the grid cell
 * @see frontend/components/event/AdvancementPath.tsx — the outcomes ladder
 */

/**
 * Grid columns where a RISING probability is bad news for the row.
 *
 * `relegation` is the only one in the whole vocabulary — 26 distinct key/label
 * pairs across every config in `league_configs.py`, re-counted for this fix,
 * and every other key (`top_4`, `make_playoffs`, `conference`, `final_four`,
 * `make_cut`, `championship`, …) is a step toward something good. It appears in
 * exactly three configs: `epl`, `la-liga`, `bundesliga`.
 *
 * This is also, today, exactly the set of columns that are not a rung on the
 * way to a title — the question #7206 asked of the same vocabulary — which is
 * why `AdvancementPath` reads its heading rule off this set instead of keeping
 * a second one beside it. The two predicates are not the same sentence, and if
 * a column ever answers them differently (a rung that is neutral rather than
 * good), that is the moment to split them, with the column that forced it
 * named in the split.
 */
export const ADVERSE_COLUMN_KEYS: ReadonlySet<string> = new Set(["relegation"]);

/**
 * Is a rising probability in this column good news for the row?
 *
 * An absent or unrecognised key answers `true`. There is no third colour to
 * render an unknown in, and the whole measured vocabulary bar one key rises
 * toward something good, so the default is the majority reading rather than a
 * refusal — the callers that have no structured key at all (the raw-futures
 * fallback on the event page, the tennis register) are exactly the ones with no
 * relegation rung to get wrong.
 */
export function risingIsGood(columnKey: string | null | undefined): boolean {
  if (!columnKey) return true;
  return !ADVERSE_COLUMN_KEYS.has(columnKey);
}
