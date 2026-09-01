/**
 * WHICH SHOWCASE EVENTS HAVE A HUB (#2560).
 *
 * `/sport/tennis` lists four Grand Slams and, before this file, rendered all
 * four the same way: a dead card reading *"Date TBD — odds available closer to
 * the event"*. That is the right card for Wimbledon in September. It was the
 * card the US Open got on the second day of the US Open, with a fully built,
 * fully priced hub sitting at `/tournaments/us-open` that nothing on the page
 * pointed at — so the new Tennis chip's destination was itself a dead end.
 *
 * The map is keyed by the showcase event's own `name`, which is what
 * `/api/sports/{slug}` returns and what the card already prints.
 *
 * ═══ WHY A CONSTANT AND NOT A LOOKUP ═══
 *
 * The servable slugs are an allowlist — `TOURNAMENT_SPECS` in
 * `backend/app/routes/tournaments.py` — with no endpoint that publishes it, and
 * a hub is not a data row: adding one is a backend deploy that writes that
 * allowlist. So the pair moves together by construction, and this is a
 * constant rather than a fetch.
 *
 * What it must never become is a DATE. `SHOWCASE_DATES` in the page beside it
 * and the weekday UX-P145 removed from the hub are the same bug twice: a fact
 * with an expiry compiled into a component. A slug has no expiry — the hub
 * either serves or it does not, and `backend/tests/test_tournament_hub_links.py`
 * fails the build if a slug here is not in the allowlist there.
 */
export const TOURNAMENT_HUB_SLUGS: Record<string, string> = {
  "US Open": "us-open",
};

/**
 * `/tournaments/{slug}` for a showcase event that has a hub, else `null`.
 *
 * Sport-scoped: "US Open" is a Grand Slam AND a golf major AND a fixture on
 * several other calendars, and the tennis hub is not the golf one. A name-only
 * lookup would route the golf card to the tennis draw — the same class of
 * mistake the tournament register refuses at every other seam, arrived at from
 * the frontend.
 */
export function tournamentHubHref(
  sportSlug: string,
  eventName: string
): string | null {
  if (sportSlug !== "tennis") return null;
  const slug = TOURNAMENT_HUB_SLUGS[eventName];
  return slug ? `/tournaments/${slug}` : null;
}
