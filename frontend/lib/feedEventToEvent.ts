/**
 * Feed game card → the SHARED event card (ux/1053, ruling 047).
 *
 * ── WHY THIS ADAPTER EXISTS AT ALL ──
 *
 * ux/1052 item 6 (#2920) measured the split Alex found: five surfaces draw
 * `components/EventCard` and the feed draws `components/FeedCard`, over the same
 * content, so a reader who learned the card on a league page meets a different
 * anatomy for the same facts on /sports. Ruling 047 already settled which wins —
 * *"a bespoke variant spends the reader's accumulated fluency to save one queue
 * an afternoon"* — and the league rail migrated under UX-P074. The feed never
 * did, and item 6 deferred it because six surfaces, the personalization/dismiss
 * paths and the four-article-root contract are a queue, not a tail-of-queue
 * change.
 *
 * This is the FIRST bite of that queue and it is deliberately one section wide:
 * the /sports Finished rail. A settled card carries no thumbs decision, no cue
 * and no live chrome, so it is the one bucket where the shared card loses
 * nothing the feed card was doing for it — which is why it goes first rather
 * than because it is easiest.
 *
 * ── THIS IS A RENAME, NOT A COMPUTATION ──
 *
 * Same discipline as `leagueGameToEvent`, which this deliberately mirrors: every
 * field either comes straight off the payload or is absent, and absent stays
 * absent. Nothing is derived, nothing is defaulted to a number, and in
 * particular an unpriced game does NOT acquire a 0 or a 50 on the way through.
 */

import type { Event, FeedEventData } from "./types";

/** The three values `OpeningOdds.favorite` is allowed to hold. */
const FAVORITE_VALUES = new Set(["home", "away", "even"]);

export function feedEventToEvent(data: FeedEventData): Event {
  const event: Event = {
    id: data.id,
    external_id: data.external_id,
    sport: data.sport,
    home_team: data.home_team,
    away_team: data.away_team,
    commence_time: data.commence_time,
    status: data.status,
    home_score: data.home_score,
    away_score: data.away_score,
  };

  if (data.current_odds) {
    // The absent members are stated as EXPLICIT nulls rather than left off, for
    // the reason `leagueGameToEvent` spells out: the shared card asks
    // `projected_home_score != null` before printing a projection, and an
    // omitted key used to reach `Math.round(undefined)` → "Proj NaN-NaN".
    //
    // `captured_at` is the one field the feed genuinely does not send. The cast
    // is the honest option: inventing a capture time would put a timestamp on
    // the card that no producer ever measured.
    //
    // 🔴 THE SERVED PERCENTS TRAVEL AS A PAIR (#2279). Copying them with a
    // per-side `?? null` would let a partial payload hand the card a served home
    // beside an absent away, which `servedDuelPercents` then splits — a served
    // 51 next to a derived 50. Either both cross or neither does, so the
    // fallback happens WHOLE at the leaf. The tree-wide guard
    // `__tests__/lib/servedDuelPercents.test.ts` scans for the per-side form and
    // caught the first draft of this file doing exactly that.
    const served =
      data.current_odds.home_rendered_percent != null &&
      data.current_odds.away_rendered_percent != null;
    event.current_odds = {
      home_probability: data.current_odds.home_probability,
      away_probability: data.current_odds.away_probability,
      home_rendered_percent: served ? data.current_odds.home_rendered_percent : null,
      away_rendered_percent: served ? data.current_odds.away_rendered_percent : null,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    } as Event["current_odds"];
  }

  if (data.opening_odds) {
    // `FeedEventData` types `favorite` as a bare string; `OpeningOdds` types it
    // as the three-value union. NARROWED, not cast: an unrecognised value
    // becomes `null` — "we do not know which side was favoured" — rather than
    // being asserted into a union it does not belong to.
    const favorite = data.opening_odds.favorite;
    event.opening_odds = {
      home_probability: data.opening_odds.home_probability,
      away_probability: data.opening_odds.away_probability,
      spread: null,
      over_under: null,
      favorite:
        favorite != null && FAVORITE_VALUES.has(favorite)
          ? (favorite as "home" | "away" | "even")
          : null,
    };
  }

  // The closing number and its rung, passed through untouched. `prematchReading`
  // owns which of this and `opening_odds` the card prints, and it is the same
  // function on every surface that prints one.
  if (data.prematch_odds) event.prematch_odds = data.prematch_odds;

  if (data.home_team_data) event.home_team_data = data.home_team_data;
  if (data.away_team_data) event.away_team_data = data.away_team_data;
  if (data.espn) event.espn = data.espn as Event["espn"];
  if (data.event_tags) event.event_tags = data.event_tags;

  return event;
}
