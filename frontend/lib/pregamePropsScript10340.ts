/**
 * #10340 — before kickoff, a prop question is told once.
 *
 * A pregame game page drew the same family three times: "The script · 2 of 6"
 * (`PropDivergenceRail`), the "All 6 props" fold (`PlayerPropsDashboard`), and
 * THE SCRIPT (`PropsSection`) below Additional Markets — the last two at
 * different thresholds, under two headings that both say "script"
 * (Alabama @ Mississippi State, /events/15318030, 2026-10-03).
 *
 * The rail and the fold are ruled (UX-P098/UX-P106: five questions, the full
 * set behind one expand) and stay exactly as they are. This module removes,
 * from THE SCRIPT's input only, the rows the fold already draws — and nothing
 * else:
 *
 *   - Only on a KNOWN pregame page: status `scheduled` AND the scheduled start
 *     not yet passed. Live, final, suspended, an unrecognised status, or a
 *     `scheduled` row past its start (a status we cannot trust) all pass the
 *     script through untouched. Unknown fails OPEN — showing a question twice
 *     is a smaller wrong than hiding one.
 *   - Only rows whose exact `${market_name}|${outcome_name}` key is in the
 *     fold's EMITTED coverage (`groupPlayerPropsWithCoverage`): a key the
 *     grouping rejected, a line's hidden second threshold, an unidentified or
 *     ambiguous row, or a key that is missing or not a string stays.
 *   - A row that is graded or settled on its own (#5088's closed windows) always
 *     stays, before kickoff too — it is a result, and the fold does not print it.
 *
 * No label matching, no name parsing, no new identity: the key is the one
 * `_build_props_script` writes. The surviving rows keep their order and are the
 * same objects; an empty result falls to `PropsSection`'s own empty self-gate.
 */

/** The fields of a `props_script[]` row this filter reads. */
export interface PregameScriptRow {
  key?: string | number | null;
  graded_result?: "hit" | "miss" | "push" | null;
  settled?: boolean | null;
}

/**
 * Known pregame, not "not live": the status vocabulary is provider-shaped, so
 * only the one pregame value (`EventStatus` = "scheduled") qualifies, and only
 * while the scheduled start is still ahead.
 */
export function isKnownPregameForScript(
  eventStatus: string | null | undefined,
  scheduledStartPassed: boolean,
): boolean {
  return (eventStatus ?? "").trim().toLowerCase() === "scheduled" && scheduledStartPassed === false;
}

export function dropScriptRowsTheFoldDraws<T extends PregameScriptRow>(
  items: readonly T[],
  opts: { knownPregame: boolean; representedKeys: ReadonlySet<string> | null | undefined },
): readonly T[] {
  const { knownPregame, representedKeys } = opts;
  if (!knownPregame || !representedKeys || representedKeys.size === 0) return items;
  return items.filter((row) => {
    if (row.settled === true) return true;
    if (row.graded_result != null) return true;
    if (typeof row.key !== "string") return true;
    return !representedKeys.has(row.key);
  });
}
