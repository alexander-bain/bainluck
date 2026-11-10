"""Response-cache contract for ``GET /api/events/search`` (LAT-P090, #2211).

WHY A CACHE, AND WHY NOT AN INDEX. This is the lever the LAT-P088 measurement
pointed at after the string-index lever was dropped.

LAT-P088 specified a partial trigram GIN on ``futures_markets.name WHERE
status = 'open'``, Alex built it in an attended psql batch, and the
pre-registered gate came back RED on its budget arm — median per-term collapse
0.7194 against a 0.5 ceiling. Alex dropped the index per the contract; the
standing rule is that a lane does not re-grade its own bar after seeing the
result. But the per-term table underneath that median is real evidence, and it
does not read like noise:

    super bowl 0.078 · world series 0.083 · best picture 0.368 · world cup 0.500
    champion 0.593 · presidential election 0.658 · winner 0.979 · election 0.998

The split is by term frequency, and it has a mechanical cause. A trigram index
is a selectivity instrument: ``%winner%`` matches 42,336 of 858,938 rows, so the
bitmap it builds covers most of the table and the index scan costs what the
sequential scan costs. **No string index can fix the common-word head.** That is
a property of the distribution, not of the index — a second, better-tuned index
would land in the same place.

So the lever moves from "make the scan cheaper" to "do not run the scan". The
head of the ``/search`` distribution is small, measured, and stable: the
30-day top rows in ``search_query_logs`` were ``masters winner`` (102),
``stanley cup`` (101), ``world series`` (95), ``nba champion`` (90). Those are
the queries SUBMITTED most often, so caching their answers removes the
work for exactly the traffic the index could not help.

⚠️ LAT-P117 (2026-08-29): "by definition the queries asked most often" used to
stand where that last sentence does, and it does not survive measurement — those
four rows are the Flow Sentinel's nightly gold set, not people
(`tasks/typeahead_warmer.py`, ``_QUERY_LOG_SHARE``, carries the numbers). This
module's argument is UNHARMED, and the distinction is worth keeping straight:
caching is justified by what is SUBMITTED, because a submitted query costs the
same scan whoever submitted it. Head ELECTION is the thing that needs the query
to have come from a person, and that is why ``search_head_warmer`` elects
through an attestation filter and this module does not have one. ``app/tasks/
search_head_warmer.py`` keeps them resident; this module is the contract both
that warmer and the route read the key from.

WHY THIS IS A MODULE AND NOT AN F-STRING IN THE ROUTE. Two failures, both in
this repo, both within the last month:

* **LAT-P001** — the feed pre-warm computed its cache key inline. It differed
  from the route's by one segment, so the warmer published under a key nothing
  ever read. Every pass reported success. A warmer that warms nothing is
  indistinguishable from a warmer that works, from the outside.
* **#2203 / LAT-P089**, one cycle ago — the feed key omitted a field that shaped
  the answer, so one principal's build was served to another. The fix was the
  same shape: one key function, one place to read it, and a test that pins the
  key's parameters against the route's signature.

There is therefore exactly ONE key builder, and ``tests/
test_search_response_cache.py`` asserts that its parameters equal the route's
answer-shaping parameters in both directions.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Optional

#: Namespace for every ``/search`` response entry. Deliberately a sibling of
#: ``bainluck:typeahead:`` rather than a child, so an operator clearing one
#: surface with a glob cannot silently clear the other.
SEARCH_RESPONSE_CACHE_PREFIX = "bainluck:search"

#: How long an assembled ``/search`` answer may be served for, in seconds.
#:
#: THIS CONSTANT IS THE WHOLE INVALIDATION CONTRACT, stated rather than implied.
#: A search answer is assembled from live scores, moneyline odds, blended win
#: probabilities, futures prices and team rows; there is no single write whose
#: commit could correctly invalidate it, so there is no event-driven
#: invalidation to build. What there is instead is a bound: an answer may be up
#: to this many seconds old, and nothing in the system pretends otherwise.
#:
#: It was 60 s, chosen as the same order as the two neighbouring bounds this
#: product already accepts on the same data — ``/typeahead`` at 65 s (LAT-P075)
#: and the anonymous Discover feed at 60 s (``FEED_RESPONSE_TTL_ANON_SECONDS``).
#: That comment also said: *"if that judgement ever moves, it moves here, once"*.
#:
#: 🔴 **IT HAS MOVED: 60 → 180 s, by RULING D81 = A (Alex, 2026-09-06), not by a
#: lane.** CERT-2068 blocked #3526 for extending the cold path and named the
#: repair as binding refresh eligibility to the real cadence *"without extending
#: the 60 s freshness ceiling"*. That repair is **arithmetically impossible at
#: 60 s** — see ``search_head_warmer``'s ``residency_invariant()``: the entry
#: must outlive one pass period (60 s) *plus* the full rebuild budget (100 s),
#: which is 160 s of life before any margin. So the ceiling was the binding
#: term, and it went to Alex as a product question rather than being tuned here.
#:
#: What a user actually experiences barely moves, and that is the point: the
#: head is rebuilt on **every** pass, so a served answer is typically
#: ``P_effective + wall`` ≈ **71-86 s** old, against 71-86 s before. 180 s is the
#: CEILING that makes continuous residency provable, not the typical age. What
#: it buys is the removal of the hole — measured 2026-09-06 at **77 % of
#: inter-pass gaps exceeding the TTL**, with all three probed head terms
#: returning ``x-search-cache: miss``.
#:
#: ``test_the_ttl_is_declared_once_and_is_the_whole_invalidation_contract`` pins
#: the route to this name rather than to a literal, because ``/typeahead``'s
#: 45→65 s change had to be made in two places and the drift between them is a
#: red test there to this day.
SEARCH_RESPONSE_TTL_SECONDS = 180

#: W-1 (worker audit 2026-11-06 B-2; Alex 53: A, 2026-11-06 12:07 PM PT): the
#: life of an entry the HEAD WARMER writes. Readers keep
#: :data:`SEARCH_RESPONSE_TTL_SECONDS`; only the warmer's own rebuilds live this
#: long. The warmer now passes every 300 s instead of every ~45-60 s, so its
#: entries must outlive a 300 s gap plus the rebuild budget, and a head answer a
#: reader sees can be up to ~10 minutes old instead of ~3. That is the stated cost
#: of the change; the revert is this constant and the warmer's three timing
#: constants together.
SEARCH_HEAD_WARMER_TTL_SECONDS = 600

#: Reported on every ``/search`` response so hit and miss are readable from
#: OUTSIDE the process — which is what makes a production deploy check possible
#: at all. A header rather than a body key on purpose: the cached body stays
#: BYTE IDENTICAL to the built one, so the two can be compared directly, no
#: frontend type changes, and no additive field for a client to start depending
#: on. ``middleware/latency.py`` already reads the sibling ``x-feed-cache``.
SEARCH_CACHE_HEADER = "x-search-cache"

#: #9947: how long a reader-built answer whose futures OUTCOME arm did not merge
#: may live — the arm states ``shed`` and ``budget_exceeded`` (LAT-P271).
#:
#: Those answers are not ``degraded`` and must not become so: `f1 winner` and
#: `f1 champion` blow the arm's 1,000 ms bound on EVERY read (production
#: 2026-09-30 22:1xZ, ``?debug_timing=1``: futures 1,654 / 2,183 ms, both
#: ``budget_exceeded``), so an uncacheable thin answer would hand their readers a
#: 2-3 s build on every search. But for a PLAYER the outcome arm is the answer —
#: every board the player is priced on reaches the page through a leg, not the
#: title. `ohtani` has two title matches (the MLB The Show cover prop, "Cy Young
#: and MVP Winner"), and right after the 22:00Z release of fe46e609 it served
#: exactly those two, dropping World Series MVP (Ohtani 13%) and Championship
#: Series MVP (Ohtani 7.15%, leads). Minutes later, on the same release, the arm
#: read ``merged`` in 173 ms and the page carried both boards. The arm's bound is
#: bimodal-safe for the slow query and NOT for a slow moment, and a 180 s write
#: turned a slow moment into three minutes of a wrong answer for everyone.
#:
#: So the thin answer is still cached — a query that is ALWAYS thin keeps its
#: cache — but only for long enough to absorb a burst, and never for the full
#: freshness ceiling. This is a shorter life under the D81 ceiling, never a longer
#: one. The warmer's rebuilds are exempt (see `search_response_ttl_seconds`).
SEARCH_THIN_RESPONSE_TTL_SECONDS = 30

#: The futures outcome-arm states that mean the page carries the name matches
#: ALONE. ``not_reached`` is absent on purpose: it only occurs when the futures
#: stage itself was shed, which already marks the answer ``degraded`` and keeps
#: it out of the cache entirely.
THIN_FUTURES_OUTCOME_ARM_STATES = frozenset({"shed", "budget_exceeded"})


def search_response_ttl_seconds(
    futures_outcome_arm: str,
    *,
    warmer_rebuild: bool,
    futures_split_arm: str = "absent",
) -> int:
    """The cache life of one ``/search`` answer about to be written.

    The full :data:`SEARCH_RESPONSE_TTL_SECONDS` unless the futures outcome arm
    or the futures SPLIT arm did not merge (:data:`THIN_FUTURES_OUTCOME_ARM_STATES`)
    on a reader's request, which gets :data:`SEARCH_THIN_RESPONSE_TTL_SECONDS`.

    #10024: the split arm is the outcome arm's twin for a team + competition
    query. `phillies world series` names the board in its title (`world series`)
    and the club in one leg (`phillies`), so neither the name arm nor the
    outcome arm can return it. If the split arm runs out of time, the answer is
    empty: "No results". Production 2026-10-01 14:01-14:05Z served that empty
    answer from the cache as a hit for about 3.5 minutes, on the release that
    carries the split arm, while every uncached read returned "MLB World Series
    Champion 2026". The arm's state is reported by the same window under the
    same bound, so it gets the same short life. The default keeps every other
    caller's answer exactly as before.

    A warmer rebuild gets :data:`SEARCH_HEAD_WARMER_TTL_SECONDS` (W-1), even when
    thin. The head is rebuilt on every pass (300 s since W-1), so a thin head answer is replaced by the next pass
    whatever its TTL, and `search_head_warmer.residency_invariant()` needs each
    entry to live one pass period plus the full rebuild budget (160 s): a 30 s
    head entry would open the very hole D81 was ruled to close, for exactly the
    head terms that are always thin.
    """
    if warmer_rebuild:
        return SEARCH_HEAD_WARMER_TTL_SECONDS
    if (
        futures_outcome_arm in THIN_FUTURES_OUTCOME_ARM_STATES
        or futures_split_arm in THIN_FUTURES_OUTCOME_ARM_STATES
    ):
        return SEARCH_THIN_RESPONSE_TTL_SECONDS
    return SEARCH_RESPONSE_TTL_SECONDS

#: #4437 (b): the ONE degraded stage whose answer may still be cached, briefly.
#:
#: LAT-P007 keeps every degraded answer out of the cache, and the headline lane
#: joined that rule (#7243) because its shed was RARE — `red sox` 1/45 on
#: 2026-09-19 — so the next build would almost always be fuller. For a term
#: whose headline lane sheds on EVERY build that premise is false, the
#: #3399/LAT-P241 case: `chi` timed out its headline lane on every read on
#: 2026-11-07 (2,031-2,094 ms) and so paid a 3.3-3.4 s build on every repeat,
#: never a hit. Such an answer still carries its teams, games and futures —
#: only the championship card the lane promotes is missing.
#:
#: So it lives :data:`SEARCH_THIN_RESPONSE_TTL_SECONDS` — the same short life as a
#: thin outcome-arm answer, long enough to absorb a burst of repeats, never the
#: freshness ceiling — and only when it has content, so a cut-short answer can
#: never be served back as "No results". Any stage NOT listed here, alone or
#: beside a listed one, keeps the answer out of the cache exactly as before.
#:
#: #12335 step 4: ``verified_title`` joins it. A title card whose verified-title
#: composition was still running at the search's 1 s bound prints its own
#: venue's prices, and the composition finishes in the background. Measured
#: 2026-11-08 3:25 and 5:53 AM PT: 0 of 20 title-team searches carried the
#: blend. Cached for 180 s, such a page outlived the 60 s verdict it was waiting
#: for, so the next build tripped the bound again and the blend never showed.
#: At 30 s, the next build lands inside the verdict's life.
SEARCH_CACHEABLE_SHED_STAGES = frozenset({"headline_contenders", "verified_title"})


def shed_answer_ttl_seconds(degraded: list, payload: dict, *, debug_timing: bool) -> int | None:
    """The cache life of a DEGRADED answer, or ``None`` = do not write it.

    Never a timing request; only an answer whose every shed stage is in
    :data:`SEARCH_CACHEABLE_SHED_STAGES` and which still shows something. The
    life is the short one whoever built it: a warmer rebuild that sheds gets
    30 s too, never the head's 600 s, because the warmer's long life is for
    complete answers (and the warmer flag stays off every write condition —
    `test_search_head_warmer_overwrites_not_deletes`).
    """
    if not degraded or debug_timing:
        return None
    if not set(degraded) <= SEARCH_CACHEABLE_SHED_STAGES:
        return None
    if not any(payload.get(k) for k in ("results", "futures", "teams", "event_concepts")):
        return None
    return SEARCH_THIN_RESPONSE_TTL_SECONDS


#: Operator kill switch, mirroring ``FEED_INERT_PRINCIPAL_SHARE`` (ruling from
#: LAT-P089: *an operator lever must be faster than a release when the failure
#: mode is "the wrong person's answer"*).
#:
#: The correctness argument for an unsegmented key is an EQUALITY argument — it
#: rests on ``/search`` returning the same body for every principal, which is
#: true today and is pinned by a test. If some future change makes the answer
#: principal-dependent and the test is edited rather than heeded, the remedy
#: must not be a deploy cycle.
#:
#: Unset means ENABLED. An unrecognised value also means enabled, deliberately:
#: a typo must not silently switch off a latency fix and leave everybody
#: wondering why the slow searches came back.
SEARCH_RESPONSE_CACHE_ENV = "SEARCH_RESPONSE_CACHE"
_CACHE_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def search_response_cache_enabled() -> bool:
    """Whether ``GET /api/events/search`` may read or write its response cache."""
    raw = os.environ.get(SEARCH_RESPONSE_CACHE_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _CACHE_OFF_VALUES


def normalize_search_query(q: Any) -> str:
    """Fold a raw query to the one form the cache and the head agree on.

    ``lower(btrim(...))`` — chosen to match ``_head_from_query_log``'s
    ``SELECT lower(btrim(query))`` exactly, and that agreement is load-bearing
    rather than tidy. The warmer warms whatever the query log elects; if the
    read side normalized differently, the warmer would warm ``winner`` and a
    user typing ``Winner`` would miss it. The pass would still report success.
    """
    return " ".join(str(q or "").strip().lower().split())


def search_response_cache_key(
    *,
    q: str,
    sport: Optional[str] = None,
    tags: Optional[str] = None,
    page: int = 1,
    per_page: int = 25,
    days_back: int = 30,
    include_upcoming: bool = True,
) -> str:
    """Build the Redis response-cache key for one ``GET /api/events/search`` shape.

    Every parameter here shapes the answer. The three route parameters that are
    absent are absent for stated reasons, each pinned by a test:

    * ``current_user`` — the response body is identical for every principal. The
      dependency is read once, at the very end of the route, and only to
      attribute the analytics row; no result, ordering, futures bucket or team
      row depends on it. This is what makes an unsegmented key safe here and is
      exactly what was NOT true of the feed in #2203.
    * ``debug_timing`` — never cached in either direction, so it can never key an
      entry. A cached body carries no ``debug_timing`` block, and answering a
      timing request with silence reads identically to a stage that cost nothing
      (gotcha #53).
    * ``request`` / ``response`` / ``db`` — plumbing.
    """
    parts = (
        f"{normalize_search_query(q)}|{sport or ''}|{tags or ''}|"
        f"{int(page)}|{int(per_page)}|{int(days_back)}|{bool(include_upcoming)}"
    )
    digest = hashlib.md5(parts.encode()).hexdigest()
    return f"{SEARCH_RESPONSE_CACHE_PREFIX}:{digest}"


#: The ONE request shape the head warmer keeps resident.
#:
#: It is one shape rather than several because both clients converge on it, and
#: they converge for different reasons — which is fragile enough to deserve a
#: test rather than a comment. ``frontend/lib/api.ts`` sets ``page`` and
#: ``per_page`` and omits the rest; ``ios/.../APIClient.swift`` ``fetchSearch``
#: sends only ``q`` and ``page``. Both therefore land on the ROUTE'S DECLARED
#: DEFAULTS for ``days_back`` and ``include_upcoming``, so a change to one of
#: those defaults silently moves both surfaces off the warmed shape, with no
#: diff anywhere near the warmer. ``test_the_warmed_shape_is_the_shape_both_
#: clients_actually_request`` compares these values against the route signature
#: for that reason.
#:
#: LAT-P089 is the named case for getting this wrong in the other direction: the
#: native feed shape (``limit=50``) was not enrolled in the feed warmer, so the
#: iOS app could not hit a warm key by construction while every dashboard said
#: the warmer was healthy.
SEARCH_WARM_SHAPE: dict[str, Any] = {
    "sport": None,
    "tags": None,
    "page": 1,
    "per_page": 25,
    "days_back": 30,
    "include_upcoming": True,
}


def search_warm_cache_key(q: str) -> str:
    """The cache key for query ``q`` in the warmed shape."""
    return search_response_cache_key(q=q, **SEARCH_WARM_SHAPE)
