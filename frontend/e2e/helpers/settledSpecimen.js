"use strict";

/**
 * UX-P053 (#1650) — finding a SETTLED game that actually carries player props.
 *
 * WHY THIS IS A MODULE AND NOT A `.first()`.
 *
 * The event-page pack walks the real north-star journey: open /sports, click
 * whatever game is first. That is the right shape for "can a reader get to a
 * game and read the probability", and exactly the wrong shape for #1650, whose
 * defect only appears on a settled game that PUBLISHES PROPS. Three cycles of
 * settled-prop fixes (#1638, #1642, #1650) still have no rendered evidence
 * because every dispatch landed on a prop-less game.
 *
 * UX-P049 replaced `.first()` with a run-time search. That was necessary and not
 * sufficient: run 31448073014 still found nothing, and the cause was the
 * LISTING it searched. It fails in two ways at once — the shape gotcha #41
 * warns about, where ordering is never the whole answer because the real
 * question is what the ordering STARTS ON.
 *
 * 1. THE WINDOW IS A UTC CALENDAR-DAY BOUNDARY, NOT A LOOKBACK.
 *    `list_events` admits a completed event only when
 *    `commence_time >= midnight-UTC-of-yesterday` (`routes/events.py:3907`).
 *    That is 24h wide at 00:00 UTC and 48h wide at 23:59 UTC, so what the pack
 *    can see depends on the hour it runs. `days` does NOT widen it — that
 *    parameter bounds only the SCHEDULED arm.
 *
 * 2. THE ORDER IS `commence_time` ASC (`events.py:3917`), so `limit=N` returns
 *    the N OLDEST events in the window. Player props live on big-four US
 *    evening games, the LATEST in a UTC day. The limit pointed at the wrong end.
 *
 * MEASURED 2026-08-11T01:10Z — 18:10 PT, US prime time, and the hour a human is
 * most likely to dispatch a run by hand. The window sat at its 24h NARROWEST and
 * held 16 completed events: 14 soccer, 1 tennis, and one MLB game carrying ZERO
 * props. Every big-four game with props had aged out at midnight UTC while the
 * evening slate had not finished. The run failed CORRECTLY — "no evidence
 * collected" is not a pass on this rail — but it could not have done better at
 * that hour.
 *
 * `/api/events/highlights` answers the question the pack is actually asking: a
 * real `commence_time >= now - days` LOOKBACK (`events.py:1158`), sport-
 * filterable, not day-boundary bound. Its one catch is a default
 * `min_percentile=75` interestingness filter, so it must be asked with the
 * filter OPEN — at 75 the MLB list was one prop-less game; at 0 the same request
 * returned 16 games including the 81-prop specimen (event 15191147, 60 graded).
 *
 * The day-bounded listings are KEPT as fallbacks, not replaced: they cover the
 * case highlights cannot, a game finished so recently it has not been scored
 * into a percentile yet.
 *
 * PURE apart from the injected `get` — no clock, no ambient state, no Playwright
 * import. That is what lets the contract suite prove it against fixtures instead
 * of against a live slate that changes hourly.
 */

/**
 * Player props are a big-four phenomenon. A plain completed listing is dominated
 * by soccer, AFL, NRL and WNBA, none of which publish them — measured
 * 2026-08-10, the first TEN completed events returned zero props between them.
 * Probing an unfiltered list deeply enough to stumble onto one costs a ~77 kB
 * payload per miss, so the leagues are tried first.
 */
const PROP_BEARING_SPORTS = [
  "baseball_mlb",
  "basketball_nba",
  "americanfootball_nfl",
  "icehockey_nhl",
  "basketball_wnba",
];

/** How far the lookback listing reaches. Three days spans a weekend gap. */
const HIGHLIGHT_LOOKBACK_DAYS = 3;

/**
 * Deep enough that reversing the ASC listing reaches an evening game, and that
 * the highlights list is not truncated before its prop-bearing entries. This
 * bounds a LISTING, which is one request; the probe budget is what bounds the
 * expensive per-event calls.
 */
const LISTING_LIMIT = 40;

/**
 * The real cost bound. Every miss is a `/game-markets` fetch of up to ~77 kB, so
 * the search is capped across ALL listings rather than per listing — five
 * leagues x forty events would otherwise turn one journey into a crawl, which is
 * the failure the original bounded probe existed to prevent.
 */
const MAX_PROP_PROBES = 14;

/** Statuses whose page can exhibit #1650. A live game cannot. */
const SETTLED_STATUSES = new Set(["completed", "closed"]);

/**
 * The listings to try, in order, and how to read events out of each body.
 *
 * The lookback goes first because it is the only source that survives the
 * calendar-day boundary.
 */
function specimenListings(apiBase) {
  const base = String(apiBase || "").replace(/\/$/, "");
  return [
    ...PROP_BEARING_SPORTS.map((sport) => ({
      url:
        `${base}/api/events/highlights?days=${HIGHLIGHT_LOOKBACK_DAYS}` +
        `&sport=${sport}&min_percentile=0&limit=${LISTING_LIMIT}`,
      pick: (body) => body && body.highlights,
    })),
    ...PROP_BEARING_SPORTS.map((sport) => ({
      url: `${base}/api/events?status=completed&limit=${LISTING_LIMIT}&sport=${sport}`,
      pick: (body) => body && body.events,
    })),
    {
      url: `${base}/api/events?status=completed&limit=${LISTING_LIMIT}`,
      pick: (body) => body && body.events,
    },
  ];
}

/**
 * Newest first.
 *
 * `list_events` sorts `commence_time` ASC and props are on the late games, so
 * reading a bounded listing front-to-back walks AWAY from the specimen. Applied
 * to every listing rather than just that one: `/highlights` sorts by
 * interestingness, where recency is also the better bet for a graded game.
 *
 * Non-destructive, and an unparseable date sorts last rather than throwing.
 */
function newestFirst(events) {
  const list = Array.isArray(events) ? events : [];
  return [...list].sort((a, b) => {
    const ta = Date.parse((a && a.commence_time) || "") || 0;
    const tb = Date.parse((b && b.commence_time) || "") || 0;
    return tb - ta;
  });
}

/**
 * Is this listing entry one whose page could show #1650 at all?
 *
 * `/highlights` is NOT status-filtered, so a live or scheduled game can appear
 * in it. Auditing one would photograph a surface on which the defect cannot
 * occur — the exact way the pack wasted its previous two dispatches. An entry
 * with no status at all is allowed through, because the day-bounded listing was
 * already filtered by the query that produced it.
 */
function isSettledCandidate(ev) {
  if (!ev) return false;
  const status = ev.status;
  if (status == null) return true;
  return SETTLED_STATUSES.has(String(status));
}

/**
 * Search for a settled event that publishes player props.
 *
 * `get(url)` must resolve to something with `ok()` and `json()` — Playwright's
 * `APIResponse` shape, injected so this module never imports a browser.
 *
 * Returns `null` when nothing qualifies. That is a legitimate answer on a thin
 * slate and the caller MUST fail on it: a run that collected no evidence is not
 * a pass on this rail.
 */
async function findSettledEventWithProps(get, apiBase) {
  let probes = 0;
  // One event can appear in several listings — the MLB game that is both a
  // highlight and inside the day window. Re-fetching its markets would spend the
  // probe budget re-learning the same answer.
  const probed = new Set();

  for (const listing of specimenListings(apiBase)) {
    if (probes >= MAX_PROP_PROBES) break;

    let events;
    try {
      const listRes = await get(listing.url);
      if (!listRes || !listRes.ok()) continue;
      events = listing.pick(await listRes.json());
    } catch {
      // A listing that errors is a dead source, not a dead search — the whole
      // point of having several is that any one of them can be down.
      continue;
    }
    if (!Array.isArray(events)) continue;

    for (const ev of newestFirst(events)) {
      if (probes >= MAX_PROP_PROBES) break;

      const id = Number(ev && ev.id);
      if (!Number.isFinite(id) || probed.has(id)) continue;
      if (!isSettledCandidate(ev)) continue;

      probed.add(id);
      probes += 1;

      let props;
      try {
        const res = await get(`${String(apiBase || "").replace(/\/$/, "")}/api/events/${id}/game-markets`);
        if (!res || !res.ok()) continue;
        props = (await res.json()) || {};
        props = props.player_props;
      } catch {
        continue;
      }
      if (!Array.isArray(props) || props.length === 0) continue;

      return {
        id,
        propCount: props.length,
        // Props the BACKEND typed a verdict for. Mirrors the shipped
        // narrow-positive rule (UX-P044): only an explicit `hit` is a verdict,
        // because a defaulted `is_winner: false` is what made 70 red MISS badges
        // out of nothing.
        gradedCount: props.filter((p) => p && p.hit != null).length,
      };
    }
  }

  return null;
}

module.exports = {
  PROP_BEARING_SPORTS,
  HIGHLIGHT_LOOKBACK_DAYS,
  LISTING_LIMIT,
  MAX_PROP_PROBES,
  SETTLED_STATUSES,
  specimenListings,
  newestFirst,
  isSettledCandidate,
  findSettledEventWithProps,
};
