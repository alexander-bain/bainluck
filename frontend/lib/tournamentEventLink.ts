/**
 * WHICH EVENT PAGE DOES THIS MATCHUP ROUTE TO — one answer, read by every list
 * on the tournament hub (ux/1002).
 *
 * ═══ WHY THIS IS ITS OWN MODULE ═══
 *
 * Alex, on the live hub at 10pm 2026-09-01: *"the Zverev–Sonego card (LIVE,
 * '4TH SET') is not clickable. CERT-703 wired only the FINISHED list. The API
 * already provides the mapping (event_links.by_matchup -> 15293811)."*
 *
 * The diagnosis names the real structural fault, which outlives whichever card
 * happened to be dead when it was read: **the hub had two different ideas of
 * where a match links to.** The FINISHED list read the payload's published map,
 * `event_links.by_matchup` — one id-anchored answer per matchup, resolved
 * server-side by `utils/tournament_event_link.py`. The MATCH list read
 * something else entirely: a per-row `event_id` stamped onto slate rows only.
 *
 * Those two sources agree on the rows they both cover, which is what makes the
 * split so easy to miss and so bad to keep. They stop agreeing exactly where it
 * costs a reader a click:
 *
 *   - **A name-pair join is the join this product does not do.** Gotcha #32 /
 *     ruling 048 is written against exactly this: identity travels by id. The
 *     matchup key is the id both halves of the payload already agree on.
 *
 * So the resolution moves here, both lists call it, and the rule about where a
 * match links has one definition instead of two implementations.
 *
 * ═══ WHAT THIS MODULE DOES **NOT** BUY, MEASURED (ux/1008, CERT-724) ═══
 *
 * Round one also claimed it links cards that were dead. It does not, and the
 * correction belongs here rather than in a report, because the directive that
 * produced the claim is still on file and reads persuasively:
 *
 *   - **For a SLATE row the fallback is unreachable.** `build_slate` already
 *     fills `event_id` from this very map when the register pins nothing
 *     (`tournament_slate.py:692`), so "in `by_matchup`" implies "stamped on the
 *     row". Measured on the captured payload, rendered through the real
 *     component: map and no-map produce the identical set of ten hrefs, and the
 *     live card Alex reported as dead is an anchor under BOTH rules.
 *   - **For a BRACKET row it is unreachable too, and for a different reason.**
 *     `matchListFromBracket` nulls `matchupKey` and `eventId` together, so the
 *     row has no key to look up. Left unfixed deliberately:
 *     `ingest_espn_draw.py` never writes `draw_slot`, `build_bracket` returns
 *     `[]`, and production ships no bracket rows at all.
 *
 * The module earns its place as the ONE definition of the rule, not as a
 * source of new links. The `espn:` refusal below is the part with real teeth.
 *
 * ═══ WHAT IT REFUSES, AND WHY EACH REFUSAL IS LOAD-BEARING ═══
 *
 * A missing link is a smaller harm than a wrong one — the server module says so
 * about its own four refusals, and the client must not be the layer that
 * relaxes them:
 *
 *   - **No key in the map.** The server resolved nothing for this matchup
 *     (`NO_PINNED_MARKET`, `MARKET_UNLINKED`, `MARKET_NOT_FOUND`,
 *     `EVENT_DISAGREEMENT`) and published the reason counts beside the map. We
 *     do not get to guess past a refusal that was counted.
 *   - **An `espn:` key NEVER resolves.** This is not a formatting quirk, it is
 *     Q503/Q505's whole point. When the register's pairing disagrees with the
 *     scoreboard, `authority_match_row` rebuilds the card with the authority's
 *     two players and no price, and re-keys it `espn:{competition_id}`
 *     precisely so it cannot reach a consumer that keys on the register's
 *     matchup — whose event page would print the pairing we just withheld. The
 *     register key for that same fixture is very much in `by_matchup`; looking
 *     it up would hand the reader a link to the lie. The prefix test is the
 *     guard, and it is why this function takes the KEY and not the row.
 *   - **A non-positive or non-finite id.** JSON round-trips through Redis and
 *     an id is only an id if it could address a row.
 */

/** The published map: register matchup key -> our `events.id`. */
export type MatchupEventIds = Record<string, number> | null | undefined;

/**
 * The `events.id` for a matchup key, or `null` — the ONE resolution.
 *
 * Pure and total: every refusal above returns `null` rather than throwing, so a
 * malformed payload costs a link and never a render.
 */
export function matchupEventId(
  matchupKey: string | null | undefined,
  eventIds: MatchupEventIds
): number | null {
  if (!eventIds) return null;
  if (typeof matchupKey !== "string" || matchupKey.length === 0) return null;
  // The authority-named row. See the docstring — this is the refusal that
  // stops a correct-looking link from being a wrong one.
  if (matchupKey.startsWith("espn:")) return null;
  const eventId = eventIds[matchupKey];
  if (typeof eventId !== "number" || !Number.isFinite(eventId) || eventId <= 0) {
    return null;
  }
  return eventId;
}

/** `/events/{id}`, or `null`. The standard event page; never a hub-private URL. */
export function matchupEventHref(
  matchupKey: string | null | undefined,
  eventIds: MatchupEventIds
): string | null {
  const eventId = matchupEventId(matchupKey, eventIds);
  return eventId === null ? null : `/events/${eventId}`;
}
