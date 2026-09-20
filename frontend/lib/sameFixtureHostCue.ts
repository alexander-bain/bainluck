/**
 * #7529 — WHEN TWO TRUE CARDS READ AS ONE GAME SHOWN TWICE.
 *
 * On 2026-09-20 `/search?q=maple leafs` opened with two GAMES cards that a
 * reader could not tell apart: "Toronto Maple Leafs / Ottawa Senators" and
 * "Ottawa Senators / Toronto Maple Leafs", both "Sep 23 4:00 PM", both "No
 * price yet". Nothing else separated them.
 *
 * THE DATA IS CORRECT. ESPN lists both (`401879650` at Canadian Tire Centre,
 * `401886441` at Scotiabank Arena): an NHL preseason split-squad home-and-home
 * — the same two clubs, twice, same minute, two arenas. Our rows `15313768` /
 * `15313769` are one each. So this is a LABEL defect, and de-duplicating would
 * delete a real game.
 *
 * The card conveys home/away by row order alone. That is enough when two cards
 * differ in time or in opponent, and it is not enough when they differ in
 * neither: "which name is on top" is not a thing a reader parses as "different
 * arena". #6361 is the same shape one step earlier — two FINAL cards of one
 * fixture pair, told apart by appending the date. Here the date is identical
 * too, so the next fact down is who is hosting.
 *
 * ═══ WHY THE HOST AND NOT THE VENUE ═══
 *
 * The venue is the sentence a reader would most like ("Scotiabank Arena"), and
 * we do not have it: `/api/events/search` serves no venue key on an event row
 * (measured 2026-09-20 — the payload is id / teams / commence_time / scores /
 * team data / status / metadata). The host is derivable from what every one of
 * these rows already carries, so the cue costs no backend change and cannot go
 * stale against one.
 *
 * ═══ WHY IT IS NOT ON EVERY CARD ═══
 *
 * Notice 34 / D102: the reader gets the number, the small source mark and at
 * most one short caption. A venue-or-host line on every game card in the
 * product is a page of new grey type bought to fix a handful of rows. So the
 * cue is emitted ONLY for the rows that are genuinely ambiguous against a
 * sibling in the SAME list, which is why this is a list-level function and not
 * a card-level one — a card cannot see its siblings.
 *
 * ═══ THE TRIGGER, AND THE THREE THINGS IT REFUSES ═══
 *
 * A group is two-or-more rows in one list sharing BOTH clubs and the SAME start
 * minute. Such a group gets cues only when the host tells its rows apart:
 *
 *   1. a group whose rows do not all have DISTINCT hosts gets nothing. Two
 *      cards both reading "at TOR" discriminate nothing and cost two lines of
 *      grey type; and a group that really is one row twice is a matching
 *      symptom (#2693), which a label must not paper over.
 *   2. a row with an unparseable or absent `commence_time` is never keyed. The
 *      card already refuses to print a time for those (UX-P074), and grouping
 *      on `NaN` would collide every one of them with every other.
 *   3. a row missing either club name is never keyed, for the same reason.
 *
 * Names are compared case-and-whitespace-insensitively and NOTHING ELSE — no
 * fuzzy match. The population this fires on is exact-duplicate naming by
 * construction (one provider, one fixture pair, one minute), and a near-match
 * rule here would start labelling rows that are not siblings at all.
 */

export interface HostCueEventLike {
  id: number;
  home_team: string;
  away_team: string;
  commence_time?: string | null;
  home_team_data?: { abbreviation?: string | null } | null;
}

export interface HostCue {
  /** What the card PRINTS — the club's abbreviation where we have one. */
  label: string;
  /** The host's full name, for a caller that has room for it. */
  name: string;
}

/** Cannot occur in a team name, so two fields can share one key string.
 *  Written as the escape, never as the byte: a raw NUL makes `grep` and
 *  `git grep` report NO MATCH on this whole file. */
const SEP = "\u0000";

const normalizeName = (name: string | null | undefined): string =>
  (name ?? "").trim().toLowerCase().replace(/\s+/g, " ");

/** The start instant floored to the minute, or `null` if there isn't one. */
const minuteKey = (commenceTime: string | null | undefined): number | null => {
  if (!commenceTime) return null;
  const ms = new Date(commenceTime).getTime();
  if (Number.isNaN(ms)) return null;
  return Math.floor(ms / 60_000);
};

/**
 * The cue each row needs to be told apart from its siblings, keyed by event id.
 * Rows that are already unambiguous are ABSENT from the map — callers pass
 * `cues.get(event.id) ?? null` straight into the card.
 */
export function hostCuesForEvents(
  events: ReadonlyArray<HostCueEventLike>,
): Map<number, HostCue> {
  const cues = new Map<number, HostCue>();
  const groups = new Map<string, HostCueEventLike[]>();

  for (const event of events) {
    const minute = minuteKey(event.commence_time);
    if (minute === null) continue;

    const home = normalizeName(event.home_team);
    const away = normalizeName(event.away_team);
    if (!home || !away) continue;

    // Unordered: the whole point is that one card has them the other way up.
    const pair = [home, away].sort().join(SEP);
    const key = `${minute}${SEP}${pair}`;
    const group = groups.get(key);
    if (group) group.push(event);
    else groups.set(key, [event]);
  }

  for (const group of groups.values()) {
    if (group.length < 2) continue;

    const hosts = new Set(group.map((event) => normalizeName(event.home_team)));
    // Refusal 1: the host has to be what separates them, or it says nothing.
    if (hosts.size !== group.length) continue;

    for (const event of group) {
      const name = event.home_team.trim();
      const abbreviation = event.home_team_data?.abbreviation?.trim();
      cues.set(event.id, { label: abbreviation || name, name });
    }
  }

  return cues;
}
