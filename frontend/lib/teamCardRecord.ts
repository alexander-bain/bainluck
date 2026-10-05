/**
 * The record a "Bigger Picture" team card prints — the SAME string the hero
 * prints above it (#10252).
 *
 * On 2026-10-05 `/events/15169781` (Panthers @ Ducks, Final in overtime) read
 * "Panthers 1-0-1, #3 Atlantic, 3 pts" in the hero and "Panthers 1-0 · #3
 * Atlantic Division" on the team card one scroll down: the card dropped the
 * overtime loss the game had just produced. The card composed its record from
 * the standings blob and read only `ties`, while the server writes the third
 * column back as `draws` (`reconciled_record_and_standings`) — the NHL board
 * has no overtime-loss key, and every soccer board names its draws `draws`, so
 * every soccer card printed W-L too.
 *
 * The server already serves ONE record per team (`team_data.record`, #8070),
 * built by the same `record_text` that writes the hero's line. So the card
 * prints that string when it is a W-L(-D) record, and only composes from the
 * blob when it is not — reading `ties` OR `draws`, as `_snapshot_record` does.
 *
 * No standings, no record line: the card's existing rule, unchanged.
 */

export interface RecordStandings {
  wins?: number;
  losses?: number;
  draws?: number;
  ties?: number;
}

const RECORD_SHAPE = /^\d+-\d+(?:-\d+)?$/;

export function teamCardRecord(
  served: string | null | undefined,
  standings: RecordStandings | null | undefined,
): string | null {
  if (!standings) return null;
  const record = typeof served === "string" ? served.trim() : "";
  if (RECORD_SHAPE.test(record)) return record;
  const third = standings.ties || standings.draws;
  return `${standings.wins ?? 0}-${standings.losses ?? 0}${third ? `-${third}` : ""}`;
}
