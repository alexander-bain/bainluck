# Quiet live fields keep an honest current number (#12633)

Pillar: TRUTH. Ship: the Governor market opened on an installed iPhone shows
its verified current number instead of only “Open”.

## Cause and retained example

The saved November 12 Governor response has 24 outcomes. Kansas's stored raw
probability is 0.9545; the existing full-field display rule serves 0.91822992.
Its detail clock is 10:05 UTC although the socket keeps creating later chart
snapshots. The hourly price refresh skips a board with a recent snapshot; a
socket keepalive is not evidence of a new upstream price observation. The
installed reader therefore withholds the old detail number. The venue still
lists this event and all 24 legs as active; election day did not settle it.

`backend/tests/fixtures/governor_quote_12633.json` retains the public venue
field and the bounded read-only stored snapshot. The test uses both without
contacting production. It preserves the retracted `ungradeable_result` grades.

## Change

The detail route can recheck a stale, standalone Kalshi field with 2–50 legs.
It applies the existing venue parser and the writer's price rule to the fresh
event response, and requires the same event, every leg, and every selected
probability to match. Missing, extra, moved, settled, malformed or unpriced
legs refuse the whole observation. Genuine grades and composed cross-source
numbers are outside the scope.

Only an exact match supplies `observed_at` and the installed reader's legacy
`last_updated` in the response. It changes no stored price, timestamp, grade,
movement history or database row. In particular, it does not turn a chart
keepalive into an upstream read. Both source requests and the iPhone's
`verified_title` request falling back to source mode use this path.

The equality is of the selected probabilities, not of the old stored bid/ask.
The captured New Hampshire ask differs while the writer's selected probability
is identical. A successful check dates that number; it does not certify the
old book or move the response's `price_changed_at`.

## Bounds and failure behavior

- One second for client creation, fetch, parsing and close in the async timeout.
- Recheck only when at least one detail observation is 20 minutes old or absent.
- Share an in-flight fetch; at most 4 in flight and 30 reads/minute per process.
- Keep a successful observation for 5 minutes, with its original upstream
  read time. Cache/page/database reads cannot reset that time.
- Cache failures for 30 seconds and retain an explicit reason in
  `price_observation`; timeout, error or a changed field leaves the old state.
- At most 128 cache entries. No task dispatch, model call, index or migration.

An eligible cold detail read can add up to the one-second venue deadline.
Ordinary price writers still own moved prices and settlement. A moved field
continues to withhold until its stored prices agree; this change never guesses
or silently repairs it.

## Validation and remaining gates

The new controls cover the real field, full-field disagreement, invalid state,
genuine grades, withheld rows, non-Kalshi and game-board isolation, composed
prices, original clocks on cache hits, shared concurrent fetches, rate limits,
timeout/client close, and both real detail serializers. The source and native
fallback return the same Kansas probability and a verified observation without
mutating the ORM objects. Related staleness, settled-result, empty-book, rank,
source-provenance and verified-title suites are included in the local band.

The initial route test failed because the new observation was not wired; the
installed request mode also needed its source-only fallback wired. A temporary
test client omitted an inherited parser helper; that test harness was corrected.
The saved failures remain in the local #12633 receipt folder.

Before release: local test band, 12 clock points, startup, build and typecheck;
then green hosted CI, bot approval, Fable ACCEPT at head and the assigned slot.
Done requires the served detail and 390 px reader, Back and Refresh, with the
same-number clock preserved on a repeated read. Installed-phone acceptance is
reported separately from web or source-level proof.
