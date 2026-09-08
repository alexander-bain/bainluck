"""#3841 — the warm rail MEASURES the age of the inputs it publishes under.

LAT-P268. The ship, in the reader's terms: **a live Discover page that is older
than the system allows can now be caught being published, instead of only being
suspected.**

WHY A MEASUREMENT IS THE SHIP HERE, AND NOT A FIX. #3841's own acceptance puts a
number before a repair — "how often does a warmer-published live entry actually
carry a non-zero artifact age [...] it decides whether this is a p2 or a
footnote" — and nothing anywhere recorded it. Seven consecutive queues then
re-argued the repair on an unmeasured premise, each restating the prohibition
below to the next.

🔴 THE NUMBER IS NOT REACHABLE FROM OUTSIDE THE PUBLISHING PROCESS, which is the
whole reason it is recorded at the publish site. LAT-P268 tried from outside
first: ``cache.built_at`` on a served response is the artifact ORIGIN
(``time.time() - oldest_consumed_artifact_age_s``, routes/feed.py, CERT-1864), so
``now - built_at`` on a reader's response is the TOTAL content age — artifact age
and response-cache age already summed, with neither term recoverable from the
other. 244 production samples over 730s on a live evening bounded the SUM (p50
33.1s, p95 56.9s, max 61.6s) and could not split it. At the publish instant the
two have not yet mixed: the response age is zero, so ``now - built_at`` is the
artifact age alone. That instant is exactly where ``_prewarm_feed_shape`` writes.

AND THE COHORT SPLIT IS WHAT THE AGGREGATE HID — the audit's instruction to
measure first-time / returning / signed-in SEPARATELY is what found the harm.
Same evening, 56 reads, all three arms live on every read:

    first_time   (no session id, served the warm shared entry) max  59.9s, 0/19 over
    new_session  (a fresh session id each open)                max  55.8s, 0/19 over
    returning    (a stable session id, i.e. `stale_hit`)       max 108.9s, 10/18 over

So the warm rail keeps the cohort it serves honest, and the ceiling breach lands
entirely on the RETURNING visitor, at a p50 of 68.5s against a 60s ceiling —
close to the ~115s #3841 predicted. That cohort is served from ``stale_hit`` on
its own ``s:<uuid>`` key, which no rail republishes. Filed separately; the
mechanism is NOT proven to be this warmer's, and this file does not claim it is.

WHAT THIS IS NOT — and the tests that hold the line. It is not the one-liner
#3841 sketches. Spending the age shortens the published window to
``CEILING - age``, and the republish invariant needs the whole of it:
``PERIOD + BUDGET + MIN_HEADROOM == 30 + 20 + 10 == 60 ==
FEED_RESPONSE_STALE_TTL_LIVE_SECONDS``, an identity whose own comment in
``feed_cache.py`` says "the reserve is spent". Today's constants therefore leave
EXACTLY ZERO room for a non-zero artifact age, so the repair is a re-derivation
of the ceiling arithmetic with a fourth term, not a keyword argument.
``test_recording_the_age_does_not_shorten_the_published_window`` pins that from
the outside; #3941's ``test_the_rail_does_not_pass_an_artifact_age_into_its_own_
ttls`` pins it from the source; and the external audit of 2026-09-08 states the
same constraint in prose ("shortening TTL in isolation can bring cold builds
back").
"""

import asyncio
import importlib
import json
import time
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from app.utils import feed_cache as fc
from app.utils.feed_cache import (
    FEED_PREWARM_KEY_SCOPE_KEY,
    FEED_PREWARM_SCOPE_KEY,
)

pcp = importlib.import_module("app.tasks.precompute_category_pages")

RESOLVED_KEY = "feed_cache:lat-p268"


def _run_warm(payload, *, resolved_key=RESOLVED_KEY):
    """Drive ``_prewarm_feed_shape`` with a ``get_feed`` returning ``payload``."""
    rc = MagicMock()

    async def fake_get_feed(**kwargs):
        request = kwargs["request"]
        assert request.scope.get(FEED_PREWARM_SCOPE_KEY) is True
        if resolved_key is not None:
            request.scope[FEED_PREWARM_KEY_SCOPE_KEY] = resolved_key
        return payload

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    with patch("app.routes.feed.get_feed", fake_get_feed), patch(
        "app.tasks.base.get_task_session", fake_session
    ):
        result = asyncio.run(
            pcp._prewarm_feed_shape(dict(pcp.FEED_PREWARM_SHAPES[0]), rc)
        )
    return result, rc


def _built_live_payload(*, artifact_age_s, with_built_at=True):
    """A page THIS pass built, live, from artifacts ``artifact_age_s`` old.

    ``built_at`` is the artifact origin the route stamps, so a page built from
    inputs N seconds old carries ``now - N``. Built through
    ``build_feed_cache_metadata`` rather than hand-typed so a change to the
    metadata shape reaches this fixture instead of leaving it pinning a payload
    the route no longer produces.
    """
    meta = fc.build_feed_cache_metadata(
        "miss",
        ttl_seconds=30,
        stale_ttl_seconds=60,
        live=True,
        built_at=(time.time() - artifact_age_s) if with_built_at else None,
    )
    if not with_built_at:
        meta.pop("built_at", None)
    return {
        # Liveness is read from ``item["data"]["status"]``, not from the item —
        # asserted by `test_the_fixture_is_actually_live` below, because a
        # fixture that is quietly NOT live would make every assertion here pass
        # against the ordinary 60s/300s window and prove nothing.
        "items": [{"id": "a", "data": {"status": "live"}}],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "has_more": False,
        "cache": meta,
    }


# --- The ship: the number exists ----------------------------------------------


def test_the_rail_records_the_artifact_age_it_published_under():
    """#3841's missing number, on the report the admin endpoint serves.

    Red before LAT-P268: the ``ok`` report carried outcome/duration/items/live
    and nothing about the inputs, so "how old were they" had no answer at all.
    """
    result, _ = _run_warm(_built_live_payload(artifact_age_s=25.0))

    assert result["outcome"] == "ok"
    assert "artifact_age_s" in result, (
        "the rail published a live page without recording how old its inputs "
        "were — #3841's acceptance asks for exactly this number first"
    )
    # Wall-clock, so bound it rather than pinning it. The upper bound is
    # deliberately loose: a loaded CI runner adds real seconds between the
    # fixture's origin and the publish, and this test is about the number
    # REACHING the report, not about its precision.
    assert 25.0 <= result["artifact_age_s"] < 40.0


def test_an_unmeasured_age_is_reported_as_none_and_never_as_zero():
    """A measured zero and an unmeasured age are the two answers #3841 turns on.

    #3841 is only a footnote if the zero is the MEASURED one, so a payload the
    route stamped no ``built_at`` on must not arrive on the report wearing the
    reassuring value (gotcha #53: an empty 200 is a response shape, not an
    absence).
    """
    result, _ = _run_warm(
        _built_live_payload(artifact_age_s=0.0, with_built_at=False)
    )

    assert result["outcome"] == "ok"
    assert result["artifact_age_s"] is None


# --- The prohibition: measured, never spent -----------------------------------


def test_recording_the_age_does_not_shorten_the_published_window():
    """The load-bearing one. Measuring the age must not SPEND it.

    A 55-second-old input would take the published window to 5s if the age were
    threaded into the TTLs, which is #3841's one-liner and what
    ``PERIOD + BUDGET + MIN_HEADROOM == 60`` cannot afford: every second taken
    here comes out of the seconds this beat may run late before a reader eats a
    cold build. The window a healthy pass publishes is therefore byte-identical
    whatever the inputs' age, and this asserts the two ages against EACH OTHER
    rather than against a restated constant.
    """
    fresh_result, fresh_rc = _run_warm(_built_live_payload(artifact_age_s=0.0))
    old_result, old_rc = _run_warm(_built_live_payload(artifact_age_s=55.0))

    def _windows(rc):
        written = {call.args[0]: call.args for call in rc.setex.call_args_list}
        return (
            written[RESOLVED_KEY][1],
            written[f"{RESOLVED_KEY}:stale"][1],
        )

    assert _windows(old_rc) == _windows(fresh_rc)
    # And they are the live ceiling's own numbers, not merely equal to each other.
    assert _windows(old_rc) == fc.feed_response_cache_ttls(
        my_teams_only=False, identified=False, live=True
    )
    # The age still reached the report — equality above is not silence.
    assert old_result["artifact_age_s"] >= 55.0
    # Loose for the CI-runner reason above; anything under the reserve proves
    # the fresh arm was measured as fresh.
    assert fresh_result["artifact_age_s"] < fc.FEED_LIVE_REPUBLISH_MIN_HEADROOM_S


def test_the_body_published_is_unchanged_by_the_measurement():
    """Measuring must not edit what a reader receives."""
    payload = _built_live_payload(artifact_age_s=12.0)
    _, rc = _run_warm(payload)

    written = {call.args[0]: call.args for call in rc.setex.call_args_list}
    body = json.loads(written[RESOLVED_KEY][2])
    assert body["items"] == [{"id": "a", "data": {"status": "live"}}]
    assert "artifact_age_s" not in body


def test_the_fixture_is_actually_live():
    """The control this file's first draft needed.

    Liveness reads ``item["data"]["status"]``; the first draft set ``status`` on
    the item itself, so every payload here was NON-live and drew the ordinary
    60s/300s window. Each assertion above still passed, against a page the live
    ceiling never touched. Pin the premise.
    """
    assert fc.payload_contains_live_event(_built_live_payload(artifact_age_s=0.0))
    result, _ = _run_warm(_built_live_payload(artifact_age_s=0.0))
    assert result["live"] is True


# --- Loud when it is the case the ceiling exists to stop ----------------------


def test_an_over_ceiling_live_publication_is_named_by_the_rail(caplog):
    """`outcome: ok` while publishing an over-age live page is the #53 shape.

    55s of input age under a 60s window is 115s of total content age — the
    number #3841's own text quotes — so the rail must say so by name rather
    than reporting a clean pass.
    """
    with caplog.at_level("WARNING"):
        result, _ = _run_warm(_built_live_payload(artifact_age_s=55.0))

    assert result["outcome"] == "ok"
    assert any(
        "#3841" in rec.getMessage()
        for rec in caplog.records
    ), "an over-ceiling live publication was not named in the log"


def test_a_page_within_the_reserve_is_not_warned_about(caplog):
    """The positive control's opposite: a fresh-input pass stays quiet.

    🔴 THIS TEST IS WHY THE THRESHOLD IS THE RESERVE AND NOT THE CEILING. The
    first draft warned on ``age + stale_ttl > CEILING``, and because
    ``PERIOD + BUDGET + MIN_HEADROOM == 60 == CEILING`` exactly, that is true for
    ANY age above zero — including the milliseconds a healthy pass spends between
    the artifact's origin and the publish. It passed on this laptop and went red
    in CI on a loaded runner, which is the flakiest possible way to be told that
    the rail would have warned on every live publication in production.

    Without this control the warning above passes for a rail that warns
    unconditionally, which is an alarm nobody reads rather than an instrument.
    """
    with caplog.at_level("WARNING"):
        _run_warm(_built_live_payload(artifact_age_s=0.0))

    assert not any("#3841" in rec.getMessage() for rec in caplog.records)


def test_the_warning_threshold_is_the_rails_own_reserve(caplog):
    """Just under the reserve is silent; just over it speaks.

    Pinned against ``FEED_LIVE_REPUBLISH_MIN_HEADROOM_S`` itself rather than a
    retyped literal, so moving the reserve moves this boundary with it — the
    constant is the one already sized against measurement (LAT-P179), and a
    second copy here would be the next thing to drift.
    """
    reserve = fc.FEED_LIVE_REPUBLISH_MIN_HEADROOM_S

    with caplog.at_level("WARNING"):
        _run_warm(_built_live_payload(artifact_age_s=reserve - 5.0))
    assert not any("#3841" in rec.getMessage() for rec in caplog.records)

    caplog.clear()
    with caplog.at_level("WARNING"):
        _run_warm(_built_live_payload(artifact_age_s=reserve + 2.0))
    assert any("#3841" in rec.getMessage() for rec in caplog.records)


def test_a_non_live_page_is_never_warned_about_however_old_its_inputs(caplog):
    """The ceiling is a LIVE rule (#2216) and stays one.

    A page of futures built from an hour-old artifact is not wrong, and warning
    about it would train the operator to ignore the warning that matters.
    """
    payload = _built_live_payload(artifact_age_s=55.0)
    payload["items"] = [{"id": "a", "data": {"status": "scheduled"}}]

    with caplog.at_level("WARNING"):
        result, _ = _run_warm(payload)

    assert result["live"] is False
    assert not any(
        "#3841" in rec.getMessage()
        for rec in caplog.records
    )
