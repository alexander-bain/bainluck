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
#: 60 s is not a new tolerance. It is the same order as the two neighbouring
#: bounds this product already accepts on the same data — ``/typeahead`` at 65 s
#: (LAT-P075) and the anonymous Discover feed at 60 s
#: (``FEED_RESPONSE_TTL_ANON_SECONDS``). If that judgement ever moves, it moves
#: here, once; ``test_the_ttl_is_declared_once_and_is_the_whole_invalidation_
#: contract`` pins the route to this name rather than to a literal, because
#: ``/typeahead``'s 45→65 s change had to be made in two places and the drift
#: between them is a red test there to this day.
SEARCH_RESPONSE_TTL_SECONDS = 60

#: Reported on every ``/search`` response so hit and miss are readable from
#: OUTSIDE the process — which is what makes a production deploy check possible
#: at all. A header rather than a body key on purpose: the cached body stays
#: BYTE IDENTICAL to the built one, so the two can be compared directly, no
#: frontend type changes, and no additive field for a client to start depending
#: on. ``middleware/latency.py`` already reads the sibling ``x-feed-cache``.
SEARCH_CACHE_HEADER = "x-search-cache"

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
