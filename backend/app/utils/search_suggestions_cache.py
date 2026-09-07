"""Cache policy for the `/search` zero-state chips (LAT-P139, P124-1's other half).

Extracted out of `routes/events.py` under ruling 005 (extract-on-touch): this
queue changes the tier's serve decision, adds a mirror and a serve-time
renderer, so the policy comes out of the route into a module that can be tested
without a web request, and converts to the cache envelope
(`docs/contracts/cache-envelope.md`) on the way through.

WHAT WAS MEASURED, AND IT IS NOT THE BUILD COST.

`GET /api/events/search-suggestions` is what `frontend/app/search/page.tsx:313`
calls on mount; it renders "Loading suggestions..." until it answers. It is the
first thing a person sees after tapping Search, which is product priority #4.

LAT-P124 gave this route a real 60 s cache (its `setex` had referenced two
unbound names behind a bare `except`, so it had never written) and skipped the
expensive sections when the answer window was already full. Its own closing
sentence names what was left: *"this degrades to slow once a minute, never to
wrong."*

🔴 READ THIS MODULE KNOWING THE BUILD COST BELOW IS HISTORICAL. Every millisecond
quoted from here to the end of this docstring was measured on 2026-08-30 BEFORE
LAT-P151; the build is now ~0.6 s and the reason is at the bottom, under "WHAT IS
NOT DONE HERE". The numbers are kept as written because they are what the cache
policy in this file was designed against, and a policy re-read against costs it
never saw is a policy nobody can evaluate.

This is that once a minute, measured on production `b7a7bbd0`, 2026-08-30, with
`x-timing-split` server time:

    first touch, cold slot                    12,782 ms   (db 12,708, maxq 12,672)
    +2 s, +4 s, +6 s, +8 s — inside the TTL       15-24 ms each
    after 65 s idle — ONE TTL EXPIRY LATER     8,338 ms   (db 8,282, maxq 8,191)

So the wait did not go away; it acquired a schedule. Every ~60 s the slot
expires and the next person to open Search pays the whole build. The cost is
section 3's `ORDER BY abs(probability_change_24h) DESC` over
`futures_outcomes` — LAT-P124 measured it at 146,437 shared blocks (~1.14 GB),
1,808,454 rows removed by filter, an external merge to disk, to keep FIVE rows.

The permanent form of THAT is an expression index. It is DDL, the migration slot
is Integrator-owned (ruling 080), and LAT-P124 already REQUESTED it as **P124-1**
and parked it. It is still parked. This queue does not take it and does not need
it: what it changes is that **nobody waits for the build any more**, which is a
different claim from "the build got cheaper" and is the only one made here.

WHAT THIS MODULE CHANGES.

  1. A 24 h MIRROR beside the 60 s primary, and the mirror is a first-class
     SERVE path rather than an error handler. On a primary miss the reader gets
     the mirror immediately and exactly one background rebuild is scheduled
     behind it — `_serve_stale_and_refresh`, the same primitive the two event-page
     tiers use one file over.
  2. The envelope fields, so a served payload discloses when its content was
     computed and whether it is live or stale.
  3. 🔴 **The countdown stops being baked, which is the load-bearing half.**

🔴 WHY (3) IS NOT AN EXTRA AND WHY THIS SHIP IS IMPOSSIBLE WITHOUT IT.

LAT-P124 refused to widen the TTL, and wrote down exactly why:

    THE TTL STAYS 60s BECAUSE THE PAYLOAD CARRIES A RENDERED COUNTDOWN.
    `label` is baked at build time — "Tips off in 12 min", "Starts in 2h" — so a
    mirror older than a minute prints a minute count that is wrong. A longer TTL
    would buy latency with a formatting lie.

That reasoning is correct and it is not being argued with. Serving a mirror is
exactly the thing it forbids — **so the constraint is dissolved rather than
paid for.** A suggestion whose text is time-relative stores its DEADLINE
(`countdown_from`) instead of a rendered minute count, and `render()` computes
the label at SERVE time, from the serving clock. A mirror can then be five
minutes old and still print the right number, because the number is not in it.

`render()` runs on the fresh path too, not only on the stale one. One renderer,
one code path, and `test_render_is_a_no_op_on_a_payload_built_this_instant`
pins that a build and a mirror of that build agree.

WHAT ELSE IN THE PAYLOAD CAN GO STALE, ENUMERATED RATHER THAN ASSUMED.

Five sections build this response and **two of them have never run** —
LAT-P124 found and #2286 records that section 1 (live close games) and section 5
(popular championship markets) each name a model attribute that does not exist
and die while their statement is being built. `TestSectionsThatHaveNeverRun` in
`tests/integration/test_route_search_suggestions_cold_p124.py` pins both. So the
served content is only ever:

  * section 2 — "Kicks off in N min" / "Starts in Nh". CLOCK-RELATIVE, and it is
    the one this module re-renders. An item whose start has passed is DROPPED at
    serve time rather than re-labelled, because "Kicks off in -3 min" is not a
    thing to print and a game that has started is not "starting soon".
    The verb is per-sport (`countdown_verb`, #3718) and is therefore a second
    build-time input the renderer needs: the SPORT travels in the payload beside
    the deadline, and both are stripped on the way out.
  * section 3 — "Surging +4.1% — <market>". A 24-hour statistic whose own input
    (`probability_change_24h`) is refreshed by `update_max_movement` every ten
    minutes. It cannot move meaningfully inside the ceiling below.
  * section 4 — "Pulled the upset vs X" on a game that has already finished. A
    historical fact; it does not age.

🔴 THE CEILING IS INHERITED, NOT CHOSEN. 5x the fresh TTL — the same multiplier
as `routes/events.py:_STALE_SERVE_CEILING` and `game_markets_cache
.STALE_SERVE_CEILING`, both of which are already 5. 60 s x 5 = 300 s. Past it
the reader BLOCKS and rebuilds, so a rebuild that fails forever degrades to the
old slow behaviour and never to serving hour-old chips with no signal. This is
the fail-closed half and it is the reason the mirror is not just a longer TTL.

In practice the ceiling is approached only when rebuilds are failing: the first
stale serve schedules the rebuild, so the ordinary stale window is the length of
one build, not five minutes.

WHAT IS NOT DONE HERE, NAMED SO IT IS A DECISION.

  * **The build is not made faster.** The 8-13 s is untouched; what changes is
    that a background task pays it instead of a person. P124-1 (the expression
    index) remains the fix for the build itself and remains parked.

    🔴 **SUPERSEDED 2026-08-30 by LAT-P151, and P124-1 IS WITHDRAWN.** The build
    is now ~0.6 s. The bullet above is left standing because it was true when
    written and because the reasoning under it is still the reasoning — but its
    conclusion was wrong in a way worth recording: an expression index was never
    the only fix. `/api/futures/movers`, one route file over, had solved the
    identical `ORDER BY abs(probability_change_24h) DESC` statement in LAT-P108
    two days earlier, with no DDL, by ranking inside the top-N markets by
    `max_movement_24h` — a provable superset of the answer. LAT-P124 and this
    queue each parked an index request while the shipped, proven, measured fix
    sat in the next file. `app/utils/movement_pool.py` now holds that bound in
    one place so a third surface cannot repeat it.

    Section 3 of the build, production `EXPLAIN (ANALYZE, BUFFERS)` 2026-08-30:
    **9,498 ms -> 588 ms, 146,425 shared blocks -> 3,629, external merge to disk
    -> top-N heapsort in memory.**

    This does not make the mirror redundant. The tier still caches, still serves
    stale under the ceiling, and still rebuilds behind a stale serve; what has
    changed is that the reader who falls all the way through — past the primary,
    past a ceiling-expired mirror, with no running loop to refresh behind them —
    now waits under a second instead of between eight and eighteen.
  * **No warmer, and that is not an omission.** Serve-stale has no schedule that
    can silently stop (LAT-P116's note, and LAT-P115 shipped a warmer and then
    had to prove its producer still ran): the rebuild is triggered BY the request
    that would otherwise have paid for it. `beat_schedule_change` stays FALSE,
    which also keeps this branch off `BACKGROUND_BEAT_COUNT` — the constant six
    consecutive latency integrations have collided on.
  * **Sections 1 and 5 are still dead.** Reviving them changes what a user sees
    and is a product call, exactly as LAT-P124 said. #2286 stays open.
  * **No negative caching.** This route takes no argument and cannot 404.
  * **The primary key keeps its production name.** `cache_keys("v1",
    prefix="bainluck:search_suggestions:")` yields `bainluck:search_suggestions:v1`,
    the key that is live today; the mirror and the lock slot in beside it. Live
    entries written by the pre-LAT-P139 writer carry no envelope, so `read_slot`
    reads them as a miss and they are rebuilt — a clean cutover, with no
    possibility of serving a pre-envelope payload as though it had one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.utils.event_concept_cache import (
    AVAILABILITY_LIVE,
    AVAILABILITY_STALE_OK,
    ENVELOPE_FIELD,
    STALE_TTL as _SHARED_STALE_TTL,
    ConceptCacheKeys,
    cache_keys,
    get_client,
    payload_age_seconds,
    read_slot,
    stamp_envelope,
    with_availability,
    write_payload,
)

logger = logging.getLogger(__name__)

#: This tier's Redis namespace. Chosen so that `cache_keys(CACHE_SLOT, ...)`
#: reproduces the key that is ALREADY LIVE in production, rather than migrating
#: it: `bainluck:search_suggestions:` + `v1` is `bainluck:search_suggestions:v1`.
CACHE_PREFIX = "bainluck:search_suggestions:"

#: The one slot. The endpoint takes no argument, reads no principal, and every
#: section is keyed on `now()` alone — LAT-P124's reasoning, unchanged. The `v1`
#: is part of the production key name and is kept for that reason, not as a
#: generation marker; generation lives in the envelope.
CACHE_SLOT = "v1"

#: Fresh TTL. **Unchanged at 60 s** — the number LAT-P124's (finally working)
#: `setex` used. This ship changes who can see a cached copy and what a miss
#: costs, never how often the tier rebuilds.
FRESH_TTL = 60

#: The mirror. **Imported, not re-declared** — `write_payload` does not
#: parameterize the stale TTL ("the mirror's job is to outlive an outage, and
#: that is the same job for every tier"), so a literal here would be a second
#: constant the writer never reads.
STALE_TTL = _SHARED_STALE_TTL

#: How far past the fresh TTL a mirror may be served while a rebuild runs behind
#: it. 5x, which is `_STALE_SERVE_CEILING` in `routes/events.py` and
#: `STALE_SERVE_CEILING` in `game_markets_cache` — inherited so this surface does
#: not invent a third staleness law. See the module docstring for what content
#: this bound is actually protecting, now that the countdown is re-rendered.
STALE_SERVE_CEILING = 5

#: The per-suggestion field carrying the DEADLINE a time-relative label is
#: rendered from. Present only on the STORED artifact — `render` strips it — so
#: the response on the wire keeps exactly the four/five keys it has today.
COUNTDOWN_FIELD = "countdown_from"

#: The per-suggestion field carrying the SPORT KEY the countdown's verb is
#: chosen from. Travels beside `COUNTDOWN_FIELD` and is stripped by `render`
#: for the same reason: the deadline alone is not enough to re-render the
#: label, because the verb is part of the text being rendered.
COUNTDOWN_SPORT_FIELD = "countdown_sport"

#: Sport-key PREFIX -> the verb for a countdown under an hour. Keyed on the
#: prefix (`americanfootball_ncaaf` -> `americanfootball`) because the tier-1/2
#: set spells one sport many ways — `tennis_atp_us_open`, `tennis_wta_us_open`,
#: `basketball_nba`, `basketball_ncaab` — and a per-key table would need a new
#: row for every tour spelling, which is #2552's defect in copy form.
#:
#: 🔴 A SPORT THAT IS NOT IN HERE GETS THE NEUTRAL WORDING, NOT A GUESS. That is
#: the same "Starts in ..." the >=1h branch already prints for every sport, so
#: an unmapped sport is merely plain, never wrong. #3718 exists because the verb
#: was a constant: every sport got basketball's, and on a September Saturday two
#: of the eight chips told a reader that a college FOOTBALL game tips off.
_COUNTDOWN_VERBS: dict[str, str] = {
    "basketball": "Tips off",
    "americanfootball": "Kicks off",
    "soccer": "Kicks off",
    "rugbyleague": "Kicks off",
    "rugbyunion": "Kicks off",
    "rugby": "Kicks off",
    "aussierules": "Bounces down",
    "baseball": "First pitch",
    "icehockey": "Puck drops",
    "tennis": "On court",
    "cricket": "First ball",
}

#: What every unmapped sport prints, and what the >=1h branch prints for all of
#: them. Sport-neutral by construction.
_NEUTRAL_VERB = "Starts"


def countdown_verb(sport_key: str | None) -> str:
    """The verb for `sport_key`'s countdown, or the neutral one.

    Prefix-matched, and tolerant of a missing/odd key by design — this is copy
    selection on a non-critical chip, so an unrecognised sport must degrade to
    plain wording rather than raise inside section 2's `try`. A raise there is
    logged and drops the whole section (the #2286 class), which would trade two
    wrong words for two missing chips.
    """
    if not sport_key or not isinstance(sport_key, str):
        return _NEUTRAL_VERB
    prefix = sport_key.split("_", 1)[0].strip().lower()
    return _COUNTDOWN_VERBS.get(prefix, _NEUTRAL_VERB)


def keys() -> ConceptCacheKeys:
    """Every Redis key this tier owns. There is one slot, so there is one set."""
    return cache_keys(CACHE_SLOT, prefix=CACHE_PREFIX)


def stale_serve_ceiling_seconds() -> int:
    """How old a mirror may be and still be served."""
    return STALE_SERVE_CEILING * FRESH_TTL


# ---------------------------------------------------------------------------
# The renderer — the half that makes a mirror legal
# ---------------------------------------------------------------------------


def countdown_label(
    deadline: datetime, now: datetime, sport_key: str | None = None
) -> str | None:
    """The "starting soon" label, or None once `deadline` has passed.

    `sport_key` picks the verb (`countdown_verb`); omitting it yields the
    neutral "Starts in ...". It is optional because the expiry contract below is
    what every caller depends on and it does not vary by sport — but a caller
    that HAS the sport and drops it prints plain text where the right word was
    available, so the route passes it and `render` carries it in the payload.

    🔴 THIS IS THE ROUTE'S OWN TEXT, MOVED, NOT A SECOND COPY OF IT. Section 2
    calls this to build the label and this module calls it again to re-render
    from the serving clock, so the two can never drift into printing different
    strings for the same instant — which is the whole reason a mirror is safe to
    serve. `test_render_is_a_no_op_on_a_payload_built_this_instant` is the pin.

    Returns None when the game has started. The caller DROPS such an item rather
    than re-labelling it: section 2's query is `commence_time BETWEEN now AND
    now + 3h`, so a started game is not a member of the set the section claims
    to describe, and "Tips off in -3 min" is not a thing to print.
    """
    remaining = (_as_utc(deadline) - _as_utc(now)).total_seconds()
    # 🔴 THE EXPIRY TEST READS SECONDS, NOT THE TRUNCATED MINUTE COUNT, AND THAT
    # IS NOT A STYLE CHOICE. `int()` truncates toward zero, so `int(-59/60)` is
    # 0 and a `minutes < 0` guard would let a game that kicked off fifty-nine
    # seconds ago print "Tips off in 0 min" for a whole minute after it started.
    # That is precisely the wrong-clock-text this module exists to make
    # impossible, arriving through the guard meant to prevent it.
    if remaining < 0:
        return None
    minutes = int(remaining / 60)
    if minutes < 60:
        return f"{countdown_verb(sport_key)} in {minutes} min"
    # 🔴 THE HOURS BRANCH STAYS SPORT-NEUTRAL ON PURPOSE. "Kicks off in 2h" is
    # not wrong, but the verb buys nothing at that distance and #3718 is a bug
    # about the sub-hour branch only; keeping this line a constant keeps the
    # blast radius of a copy fix to the text that was actually wrong.
    return f"{_NEUTRAL_VERB} in {minutes // 60}h"


def render(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Re-render every time-relative label from `now`, and strip the deadlines.

    Pure. Returns a new dict; `payload` is not mutated, because the caller holds
    the STORED artifact and a mutation here would strip the deadlines out of the
    thing being written to Redis.

    A suggestion carrying no `countdown_from` is passed through untouched — that
    is sections 3 and 4, whose text is not clock-relative (module docstring).
    A suggestion whose deadline has passed is dropped.
    """
    now = now or datetime.now(timezone.utc)
    out = dict(payload)
    rendered: list[dict[str, Any]] = []
    for item in payload.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        raw_deadline = item.get(COUNTDOWN_FIELD)
        if raw_deadline is None:
            rendered.append(item)
            continue
        # 🔴 THE SPORT IS READ BEFORE THE STRIP AND STRIPPED WITH THE DEADLINE.
        # Both are build-time inputs to one rendered string, so dropping the
        # sport here while keeping the deadline would make a mirror re-render
        # "Kicks off in 12 min" as "Starts in 12 min" — a build and a mirror of
        # that build printing different strings, which is exactly what
        # `test_render_is_a_no_op_on_a_payload_built_this_instant` forbids.
        sport_key = item.get(COUNTDOWN_SPORT_FIELD)
        item = {
            k: v
            for k, v in item.items()
            if k not in (COUNTDOWN_FIELD, COUNTDOWN_SPORT_FIELD)
        }
        deadline = _parse(raw_deadline)
        if deadline is None:
            # A deadline we cannot parse cannot be re-rendered, and the label
            # beside it was baked at build time. Dropping it is the only option
            # that cannot print a wrong minute count; keeping it is exactly the
            # formatting lie this module exists to make impossible.
            logger.warning(
                "search-suggestions: unparseable %s %r — item dropped",
                COUNTDOWN_FIELD,
                raw_deadline,
            )
            continue
        label = countdown_label(deadline, now, sport_key)
        if label is None:
            continue
        item["label"] = label
        rendered.append(item)
    out["suggestions"] = rendered
    return out


def renders_to_something(payload: dict[str, Any], now: datetime | None = None) -> bool:
    """False when rendering would turn a non-empty stored answer into a blank strip.

    A stored payload that was ALREADY empty renders empty and that is a real
    answer — the build genuinely found nothing, and that is what the route
    returns today. What must never happen is that a payload with chips in it
    reaches a reader with none, because every one of its countdowns expired: the
    reader would see an empty zero-state that no build produced. In that case the
    caller refuses the slot and builds, which is slow, not wrong.
    """
    stored = payload.get("suggestions") or []
    if not stored:
        return True
    return bool(render(payload, now).get("suggestions"))


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def stamp(
    response: dict[str, Any],
    *,
    created_at: datetime | None = None,
    lifecycle_watermark: datetime | None = None,
) -> dict[str, Any]:
    """Attach the producer half of the envelope to a fresh build.

    Pure. `availability` stays None here on purpose — it is the SERVE decision,
    and the same stored bytes are `live` from the primary and `stale_ok` from the
    mirror, so it is stamped on the way out by `with_availability`.
    """
    return stamp_envelope(
        response,
        created_at=created_at or datetime.now(timezone.utc),
        lifecycle_watermark=lifecycle_watermark,
    )


def mirror_is_servable(
    payload: Any, now: datetime | None = None
) -> tuple[bool, str]:
    """Is this mirror young enough to serve? Returns `(servable, reason)`.

    The reason is returned rather than logged so a test can assert WHICH branch
    fired — "too old", "no timestamp" and "everything in it expired" are three
    different facts about the tier and a bool collapses them.
    """
    if not isinstance(payload, dict):
        return False, "absent"
    age = payload_age_seconds(payload, now)
    if age is None:
        # A payload that cannot say when it was computed must not be served as
        # though it could, and here it would additionally be served under an age
        # bound we are unable to evaluate.
        return False, "no_created_at"
    if age > stale_serve_ceiling_seconds():
        return False, "too_old"
    if not renders_to_something(payload, now):
        return False, "empty_after_render"
    return True, "fresh_enough"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def read(rc=None, now: datetime | None = None) -> tuple[dict[str, Any] | None, str]:
    """Read the tier. Returns `(body, state)`, the body already RENDERED.

    `state` is one of `live`, `stale_ok`, `stale_too_old`, `miss` — the serve
    decision, made here and published in the body's envelope, never re-derived by
    a consumer (cache-envelope contract rule 1).

    Never raises: every Redis helper below is best-effort by construction, and a
    cache that cannot be read must cost a rebuild, not a 500.
    """
    client = rc if rc is not None else get_client()
    if client is None:
        return None, "miss"
    slots = keys()

    primary = read_slot(client, slots.primary)
    if primary is not None:
        if renders_to_something(primary, now):
            return with_availability(render(primary, now), AVAILABILITY_LIVE), "live"
        # Inside the fresh TTL and yet everything in it has expired. Rare — it
        # needs a payload whose only chips were countdowns that all elapsed
        # within 60 s — but the rule is the same one the mirror gets, and it is
        # applied here rather than only there so a reader cannot be handed a
        # blank strip by whichever slot happened to answer.
        logger.info(
            "search-suggestions primary rendered empty — reader will rebuild"
        )
        return None, "miss"

    mirror = read_slot(client, slots.stale)
    if mirror is None:
        return None, "miss"
    servable, reason = mirror_is_servable(mirror, now)
    if not servable:
        logger.info(
            "search-suggestions mirror refused (%s) — reader will rebuild", reason
        )
        return None, "stale_too_old"
    return with_availability(render(mirror, now), AVAILABILITY_STALE_OK), "stale_ok"


def write(enveloped: dict[str, Any], rc=None) -> bool:
    """Publish a stamped payload to both slots. Returns whether it was ATTEMPTED.

    🔴 The payload written here is the UN-RENDERED one — the artifact that still
    carries `countdown_from` on its time-relative items. Storing a rendered copy
    would bake the build clock's minute count into the mirror and put back
    exactly the defect this module removes.

    `write_payload` swallows its own Redis failures and returns None, so the
    honest thing this can report is "there was a client and we handed it the
    bytes", not "Redis has them". A caller must not read the return value as
    durability — the next read is the only thing that can establish that.
    """
    client = rc if rc is not None else get_client()
    if client is None:
        return False
    write_payload(client, keys(), enveloped, primary_ttl=FRESH_TTL)
    return True


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse(value: Any) -> datetime | None:
    """Parse a stored deadline. The codec is `json.dumps(..., default=str)`, so
    what comes back is either an ISO string or (in-process, pre-round-trip) the
    datetime itself."""
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str):
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None
