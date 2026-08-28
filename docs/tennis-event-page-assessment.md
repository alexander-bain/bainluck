# Do tennis event pages look GREAT? — measured 2026-08-26/27

Alex, UX-P139 item 7: *"Matches click through to the standard event page — confirm they do, and
assess honestly whether tennis event pages look GREAT; list what they need if not."*

Two questions. The answers are **no** and **no**, and the second is the worse news.

---

## 1. Do the matches click through today?

**No — and there is nothing to click through to.**

The affordance is built and correct. `TournamentMatches` renders an "Open the match page" link from
`entry.eventId`, which comes from `matchup.event_id` in the register — a **register-owned identity
decision**, never a name match at render time, because a link to the wrong match is worse than no
link. When `eventId` is `null` the link is simply absent; it can never render dead.

It renders on **zero** US Open matches, because no `events` row exists to point at:

| Check | Result |
|---|---|
| Registered matchups probed against `events` in the US Open window (2026-08-24 → 09-15) | **0 of 28** have a row |
| `events` rows naming any registered US Open player, all time | 654 |
| …of those, in the US Open window | effectively none for the registered pairs |

The qualifying draw currently playing was never ingested as events, so the 66 decided matches this
page now shows scores for (from ESPN — item 9) have no event page behind them. The link lights up
with no code change the moment a matchup carries an `event_id`.

## 2. Are the tennis event pages that DO exist any good?

Two real pages, fetched from production, are the whole story.

**The good case — `/events/15291004`, Gauff vs Pegula, Cincinnati, completed:**

```
sport                    tennis_wta_cincinnati_open
home/away                Coco Gauff / Jessica Pegula
score                    2 - 0
win_probability_sources  betting 95.8% (+ book count)
also present             ei, pulse, current_odds, bookmaker_odds,
                         opening_odds, hero_probability, espn block
```

That page has a hero number, a settled result, an odds history and an EI. It is fine.

**The case a US Open link would actually hit — `/events/15201774`, scheduled 2026-09-03:**

```
sport                    tennis_wta
home/away                "Sabalenka" / "Bejlek"        <- SURNAMES ONLY
score                    null / null
win_probability_sources  ABSENT
ei / pulse               ABSENT
current_odds             ABSENT
hero_probability         ABSENT
event_tags               tier:4, class:other
```

This is the shape US Open matches would land on: **surname-only names, no probability, no odds, no
hero, tier 4, class:other.** Sending a reader from a page that prints a blended probability for
every row into a page that prints nothing at all would be a downgrade dressed as a detail view.

### What they need, in priority order

1. **Full player names.** `"Sabalenka"` / `"Bejlek"` vs `"Aryna Sabalenka"` / `"Sara Bejlek"` — the
   same two people exist under both spellings in `events`, which is also a duplicate-identity smell
   worth a matching-layer look (`15206893` vs `15201774`).
2. **A win probability.** The match markets that price these players are already in
   `futures_markets` and pinned by the register's `matchups`. The event page cannot see them because
   the link is `matchup → futures market`, not `matchup → event`. Closing that is the same
   `event_provider_anchors` shaped problem as gotcha #32.
3. **The score.** Now solved upstream — `services/espn_tennis.py` fetches per-set line scores for all
   five draws. The event page does not read it yet.
4. **Round and draw context.** `tournament_round` is `NULL` on every tennis row measured;
   `is_tournament_game` unset. A US Open quarter-final currently renders with no indication that it
   is one.
5. **`class:other` / `tier:4`.** Every tennis event measured is tagged as generic low-tier, which is
   why these pages get no chrome. A Grand Slam match is not tier 4.

### The honest verdict

The tournament hub is currently a **better** surface for a US Open match than the event page would
be. Wiring the link before fixing 1–5 would move readers from a good page to a worse one, so the
link stays register-gated and dark until an `event_id` exists **and** the destination is worth the
tap. This document is the list; none of it is UX-P139's ship.
