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

/**
 * ═══ THE SECOND MAP, AND WHY IT IS NOT A RELAXATION OF THE FIRST (#2693) ═══
 *
 * The `espn:` refusal above stays exactly as written. What follows is a
 * different question asked of a different map, and the distinction is the
 * whole of its safety.
 *
 * `matchupEventId` refuses an `espn:` key because the destination it would
 * reach is *the register's* event for that matchup — the one holding the
 * pairing Q503 just withheld. `espnCompetitionEventId` does not go there. It
 * reads `event_links.by_espn`, a map the server builds by dereferencing the
 * AUTHORITY's competition id through `events.espn_id`, so the row it lands on
 * is one that agrees with the authority by construction: lane1/057's anchor
 * join only stamps an `espn_id` on an event whose two players ESPN confirms.
 *
 * So the row Q503 re-keyed to `espn:184739` now links — to ESPN's match, not to
 * the register's. The refusal above was never "this row may not be linked"; it
 * was "this row may not be linked THROUGH THE REGISTER'S KEY", and it still is.
 *
 * Order is market-first, authority-second. The market channel is the reviewed
 * one, and in the disagreement case it returns `null` anyway (the row's key is
 * `espn:`), so the fallback can never overrule a link a human pinned.
 */

/** The published map: register matchup key -> our `events.id`. */
export type MatchupEventIds = Record<string, number> | null | undefined;

/** The published map: ESPN competition id -> our `events.id`. */
export type EspnEventIds = Record<string, number> | null | undefined;

/** An id is only an id if it could address a row. Shared by both channels. */
function usableEventId(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  return value;
}

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
  return usableEventId(eventIds[matchupKey]);
}

/** `/events/{id}`, or `null`. The standard event page; never a hub-private URL. */
export function matchupEventHref(
  matchupKey: string | null | undefined,
  eventIds: MatchupEventIds
): string | null {
  const eventId = matchupEventId(matchupKey, eventIds);
  return eventId === null ? null : `/events/${eventId}`;
}

/**
 * The `events.id` for an ESPN competition id, or `null` — the second channel.
 *
 * Pure and total, like its sibling. A competition id the server could not
 * resolve is simply absent from the map: it published
 * `NO_EVENT_FOR_ESPN_ID` (no row exists — most of the qualifying draw) or
 * `ESPN_ID_AMBIGUOUS` (two rows carry it, so neither is the answer) beside it.
 * The client does not get to guess past a refusal that was counted, on this
 * channel any more than on the other.
 */
export function espnCompetitionEventId(
  espnCompetitionId: string | number | null | undefined,
  espnEventIds: EspnEventIds
): number | null {
  if (!espnEventIds) return null;
  if (espnCompetitionId === null || espnCompetitionId === undefined) return null;
  const key = String(espnCompetitionId);
  if (key.length === 0) return null;
  return usableEventId(espnEventIds[key]);
}

/**
 * Where a match row links — BOTH channels, in the one order that is safe.
 *
 * Market first, authority second. See the block comment above `MatchupEventIds`
 * for why the fallback cannot resurrect the link Q503 withheld.
 */
export function matchEventHref(
  matchupKey: string | null | undefined,
  espnCompetitionId: string | number | null | undefined,
  eventIds: MatchupEventIds,
  espnEventIds?: EspnEventIds
): string | null {
  const pinned = matchupEventId(matchupKey, eventIds);
  if (pinned !== null) return `/events/${pinned}`;
  const viaAuthority = espnCompetitionEventId(espnCompetitionId, espnEventIds);
  return viaAuthority === null ? null : `/events/${viaAuthority}`;
}
