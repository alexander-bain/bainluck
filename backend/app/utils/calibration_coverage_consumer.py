"""Attach the coverage-rung census to the payload being served — or don't (CAL-P1216).

The consumer half of CAL-P1214. The producer
(:mod:`app.tasks.census_coverage_rungs`) walks the eleven coverage-bridge rungs
out of band and publishes a COMPLETE, roster-stamped count to Redis. Nothing
reads it. This is the thing that reads it.

WHY THE READ LIVES AT SERVE TIME AND NOT IN THE BUILD
-----------------------------------------------------
The obvious home is ``precompute_calibration``, beside the reachability census
it already reads the same way (an O(1) Redis GET, fail-open). It cannot go
there, for the reason CAL-P1214 exists at all: ``COVERAGE_CENSUS_ENABLED`` fuses
the rung columns into the curve's own staged unit statement, and
``staged_unit_fingerprint()`` hashes that statement TEXT — so touching that file
invalidates every banked unit and freezes publication until all 128 rebuild.
Ruling 009's fence stands; the switch stays ``False``; the counts arrive here
instead.

That constraint turns out to be the right shape anyway. Whether a published
census may be attached to a payload is a **serve-time** question in exactly the
sense ``availability``, ``producer``, ``staged`` and ``scorecard`` are: it
depends on WHICH tier answered and WHICH generation that tier's copy came from,
neither of which a builder can know. A census baked into the artifact would ride
into the dated fallback tiers still describing whichever build was current when
it was baked — the identical failure those four keys were pulled out of the
producer to avoid.

WHAT THIS REFUSES TO DO
-----------------------
1. **It never invents a census.** Every failure — no cache, unreadable cache,
   wrong schema, moved roster, a payload from an older generation — leaves the
   payload's own census EXACTLY as the builder wrote it: byte-identical, still
   explicitly ``unavailable`` with the builder's reason. Absent is never
   silently upgraded to measured, and the route never becomes a second builder
   for a payload it could not vouch for.
2. **It never overwrites a real census.** If ``COVERAGE_CENSUS_ENABLED`` is ever
   flipped on, the builder's own in-band census is the authority and this steps
   aside. Two producers of one key must have a stated winner, and the one that
   counted inside the curve's own statement is closer to the curve.
3. **It never derives ``sportsbook_curve_legs`` by subtraction.** That number is
   counted directly by the builder, from the same rows the curve is built from,
   specifically so that a miscount surfaces as an observation-bridge residual
   instead of reconciling by construction. It is not in the served payload and
   it is not recoverable here, so it is passed as ``None`` — the observation
   bridge reads UNKNOWN and the census reads ``incomplete``. Deriving it would
   make that bridge reconcile every time and mean nothing, which is worse than
   admitting one of the three bridges is not wired at serve time. The COVERAGE
   bridge — the eleven rungs, which is the ship — is fully counted and
   reconciles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.utils.calibration_coverage_bridge import (
    COVERAGE_BRIDGE_SCHEMA_VERSION,
    STATUS_UNAVAILABLE,
    build_coverage_census,
)

logger = logging.getLogger(__name__)

#: The payload key both the builder and this module write. Named once.
COVERAGE_CENSUS_FIELD = "calibration_coverage_census"

#: Stated on the census this module builds, in the slot the builder fills with
#: the reachability tier's own count. The reachability rail is a SEPARATE census
#: (``app.tasks.census_reachability``) that the builder reads at build time; a
#: second Redis GET on the serve path to recover it would buy a bridge this ship
#: does not claim. Saying which bridge is unwired is the honest alternative to
#: quietly emitting ``None`` with no reason (gotcha #53).
REACHABILITY_NOT_READ_AT_SERVE_TIME = (
    "the reachability tier is the builder's rail and is not re-read at serve "
    "time; this census reconciles the coverage bridge only"
)


class _PrefetchedRedis:
    """A one-key stand-in holding bytes somebody else already fetched.

    ``read_published`` owns the validation — schema, every rung present and an
    ``int``, a non-empty roster digest — and that validation must have exactly
    one home, because a second copy of it in the route is a second thing to keep
    in step with the producer. But it reads its bytes with a SYNCHRONOUS
    ``.get()``, and Queue 271 took synchronous Redis off this endpoint's event
    loop for good (gotcha #39).

    So the fetch is done by the caller, with the route's own bounded async
    client, and the bytes are handed to the real validator through this. The
    alternative — reimplementing the checks against an async client — is how the
    two sides drift.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def get(self, _key: str) -> Any:
        return self._raw


def parse_published(raw: Any) -> Optional[dict[str, Any]]:
    """Validate pre-fetched census bytes with the producer's own reader."""
    if raw is None:
        return None
    from app.tasks.census_coverage_rungs import read_published

    return read_published(_PrefetchedRedis(raw))


@dataclass(frozen=True)
class CursorIdentity:
    """The staged cursor's answer to *which build is current*.

    Both halves are needed and they answer different questions. The
    ``roster_digest`` (the cursor's ``generation_fingerprint``) is the
    POPULATION's identity — what a count is ABOUT. The ``generation`` is the
    BUILD's identity — which beat produced the bytes a reader is holding. The
    cursor is the only place both are recorded together, which is why it is the
    hinge of :func:`app.tasks.census_coverage_rungs.reconcile`.
    """

    population_version: Optional[str]
    roster_digest: Optional[str]
    generation: Optional[int]


def cursor_identity(envelope_payload: Any) -> Optional[CursorIdentity]:
    """Pull the identity out of a staged-futures cursor payload, or ``None``.

    ``None`` for anything that is not a readable cursor. The caller's contract is
    that a missing identity refuses the census — so this never guesses, never
    fills a default, and in particular never returns a ``CursorIdentity`` whose
    fields are all ``None``, which would read as "I found a cursor" to a caller
    checking only for ``None``.

    The digest is ``generation_fingerprint`` — the SAME function
    ``plan_from_roster`` digests the walk's roster with
    (:func:`app.utils.calibration_staged_futures.generation_fingerprint`). That
    shared function is the entire reason the two sides are comparable; if either
    side ever computes its own digest the comparison silently becomes
    "never equal" and the census silently stops attaching.
    """
    if not isinstance(envelope_payload, Mapping):
        return None
    digest = envelope_payload.get("generation_fingerprint")
    generation = envelope_payload.get("generation")
    if not isinstance(digest, str) or not digest:
        return None
    if isinstance(generation, bool) or not isinstance(generation, int):
        return None
    version = envelope_payload.get("population_version")
    return CursorIdentity(
        population_version=version if isinstance(version, str) and version else None,
        roster_digest=digest,
        generation=generation,
    )


def _payload_generation(payload: Mapping[str, Any]) -> Optional[int]:
    """The generation the SERVED payload was built under, from its own census.

    The builder stamps ``generation`` onto the census object it writes — on the
    ``unavailable`` one too, which is what makes this readable while the switch
    is off. It is read from there rather than from a top-level payload key
    because there is no top-level key: the census block is where the build's own
    identity is recorded.
    """
    census = payload.get(COVERAGE_CENSUS_FIELD)
    if not isinstance(census, Mapping):
        return None
    generation = census.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int):
        return None
    return generation


def _payload_is_awaiting_a_census(payload: Mapping[str, Any]) -> bool:
    """Whether this payload's census is the placeholder this may replace.

    Only a census the builder marked ``unavailable`` is replaceable. A present,
    measured census belongs to whoever counted it inside the curve's own
    statement (refusal 2 in the module docstring), and a payload carrying no
    census key at all is not this module's case — ``ensure_census`` already owns
    that one and fills it explicitly.
    """
    census = payload.get(COVERAGE_CENSUS_FIELD)
    return (
        isinstance(census, Mapping)
        and census.get("schema_version") == COVERAGE_BRIDGE_SCHEMA_VERSION
        and census.get("status") == STATUS_UNAVAILABLE
    )


def coverage_census_for_payload(
    payload: Any,
    *,
    published: Optional[Mapping[str, Any]],
    cursor: Optional[CursorIdentity],
) -> Optional[dict[str, Any]]:
    """The census to serve WITH this payload, or ``None`` to leave it untouched.

    ``None`` is the overwhelmingly common answer and the safe one: it means the
    caller changes nothing at all, so the served bytes stay byte-identical to
    what the builder published. A dict is returned only when a complete
    published walk has been proved to describe THIS payload's build.

    The proof is :func:`app.tasks.census_coverage_rungs.reconcile`, which is
    where the chain lives and is deliberately not restated here.
    """
    if not isinstance(payload, Mapping):
        return None
    if not _payload_is_awaiting_a_census(payload):
        return None

    from app.tasks.census_coverage_rungs import reconcile

    payload_version = payload.get("population_version")
    counts, reason = reconcile(
        published,
        cursor_population_version=cursor.population_version if cursor else None,
        cursor_roster_digest=cursor.roster_digest if cursor else None,
        cursor_generation=cursor.generation if cursor else None,
        payload_population_version=payload_version if isinstance(payload_version, str) else None,
        payload_generation=_payload_generation(payload),
    )
    if counts is None:
        # Refusals are the normal path, not an error: the census is walked out
        # of band and is expected to be absent or behind most of the time.
        # Logged at debug so an operator asking "why is there no census" can
        # find the reason, without a steady-state INFO line on every serve.
        logger.debug("coverage census not attached: %s", reason)
        return None

    truth = payload.get("truth_evidence")
    crosscheck = truth.get("published_outcomes") if isinstance(truth, Mapping) else None
    observations = payload.get("total_outcomes")

    return build_coverage_census(
        rung_counts=dict(counts),
        # NOT derivable here, and deliberately not derived — see refusal 3.
        sportsbook_curve_legs=None,
        published_curve_observations=observations if isinstance(observations, int) else None,
        published_outcomes_crosscheck=crosscheck if isinstance(crosscheck, int) else None,
        population_version=str(payload_version),
        generation=str(cursor.generation) if cursor and cursor.generation is not None else None,
        with_terminal_calibration_price=(published or {}).get("with_terminal_calibration_price"),
        reachability_tier_counts=None,
        reachability_unavailable_reason=REACHABILITY_NOT_READ_AT_SERVE_TIME,
    )


def attach_coverage_census(
    payload: Any,
    *,
    published: Optional[Mapping[str, Any]],
    cursor: Optional[CursorIdentity],
) -> Any:
    """:func:`coverage_census_for_payload`, applied. Returns the payload to serve.

    Copy-on-write and single-key: the input mapping is never mutated, and the
    returned dict differs from it in ``calibration_coverage_census`` or not at
    all. Never raises — a supporting census must not be able to break the
    payload it supports, which is the same rule the builder's own read of the
    reachability rail follows.
    """
    try:
        census = coverage_census_for_payload(payload, published=published, cursor=cursor)
    except Exception:  # noqa: BLE001 — never the reason the page is down
        logger.warning("coverage census attach failed", exc_info=True)
        return payload
    if census is None:
        return payload
    out = dict(payload)
    out[COVERAGE_CENSUS_FIELD] = census
    return out
