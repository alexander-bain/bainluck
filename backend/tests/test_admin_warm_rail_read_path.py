"""#2430 — the Discover warm rails' status keys get a production read path.

The defect: two rails write a status key *specifically so it can be read*, with a
6-hour TTL and, in the live rail's case, a comment justifying its idle-pass write
on gotcha #53 grounds — "'Nothing was live' and 'this beat has not run since the
deploy' are different facts with opposite remedies" — and then **no route read
either key**. The fact the producer went to the trouble of recording was
unreachable.

What that cost, concretely: #3233's fix went live on 2026-09-05 and the Sports tab
still missed on ~1 open in 3 at 5.4–8.2s. From outside, "the rail runs and
something else is wrong", "the rail selects nothing" and "a kill switch is off"
produce the SAME observation. That is what these endpoints exist to separate, and
every test below pins one of the separations staying possible.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routes import admin
from app.tasks.precompute_category_pages import (
    FEED_LIVE_PREWARM_ENABLED_KEY,
    FEED_LIVE_PREWARM_STATUS_KEY,
    FEED_PREWARM_LIVE_HEARTBEAT_FIELD,
    FEED_PREWARM_LIVE_SHAPES_KEY,
    FEED_PREWARM_LIVE_SHAPES_TTL_S,
    FEED_PREWARM_SHAPES,
    FEED_PREWARM_STATUS_KEY,
    _record_shape_liveness,
)

BOOM = RuntimeError("Error 111 connecting to rediss://h:secretpw@ec2.example:6379")


def _conn(*, values=None, hash_state=None, ttl=200, get_raises=None):
    """A MagicMock Redis scripted per key.

    ``values`` maps key -> raw string (absent key -> None, which is a DIFFERENT
    fact from the key being unset in this dict; both resolve to None here and the
    tests that care distinguish them by which key they omit).
    """
    values = dict(values or {})
    conn = MagicMock()
    if get_raises is not None:
        conn.get.side_effect = get_raises
    else:
        conn.get.side_effect = lambda key: values.get(key)
    conn.hgetall.side_effect = lambda key: dict(hash_state or {})
    conn.ttl.side_effect = lambda key: ttl
    return conn


def _with_conn(conn):
    return patch("app.utils.health_reads.client", lambda **kw: (conn, None))


def _report(**over):
    base = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "period_s": 40,
        "live_labels": ["sports", "sports_native"],
        "absent_labels": ["discover"],
        "shapes": {"sports": {"outcome": "ok"}},
        "concurrency": 3,
    }
    base.update(over)
    return json.dumps(base)


# --- The gap itself ----------------------------------------------------------


def test_both_warm_rail_status_keys_have_a_mounted_read_path():
    """The whole of #2430, asserted as a route table entry.

    Named after the invariant rather than the endpoints: a third rail that writes
    a status key nobody reads is the same defect, and this test is where it should
    be noticed. Mounting is asserted because an admin route defined but not
    mounted is gotcha #2, and it fails silently — the function exists, the URL
    404s, and the read path is "built".
    """
    from app.main import app

    paths = {r.path for r in app.routes}
    assert "/api/admin/feed-prewarm/last" in paths
    assert "/api/admin/feed-live-prewarm/last" in paths


@pytest.mark.parametrize(
    "endpoint",
    [admin.get_feed_prewarm_last, admin.get_feed_live_prewarm_last],
)
def test_every_warm_rail_endpoint_checks_the_admin_secret(endpoint):
    """A call-site guard, matched on the name, not on behaviour.

    Both of these are read-only, which is exactly the reasoning that leaves an
    admin route unauthenticated. `/api/notifications/register` (#2118) is the
    standing example of a route shipped without it.
    """
    import inspect

    src = inspect.getsource(endpoint)
    assert "_check_admin_secret(" in src, f"{endpoint.__name__} does not check the admin secret"


# --- The five conditions that must not collapse into one ---------------------


def test_a_redis_outage_is_a_503_and_never_an_empty_report():
    """The worst case: a confident answer while blind.

    An outage returning `{"report": None}` reads identically to "the beat has not
    run", and the remedies are opposite — page someone vs look at the scheduler.
    """
    with patch(
        "app.utils.health_reads.client", lambda **kw: (None, _failed_read())
    ), pytest.raises(HTTPException) as exc:
        admin._warm_rail_status(FEED_PREWARM_STATUS_KEY, ttl_s=100, absent_note="n")
    assert exc.value.status_code == 503


def _failed_read():
    from app.utils import health_reads as hr

    return hr.RedisRead(status=hr.UNAVAILABLE, key="k", error_class="RuntimeError", error="boom")


def test_an_absent_report_says_so_instead_of_reporting_a_healthy_zero():
    with _with_conn(_conn(values={})):
        out = admin._warm_rail_status(
            FEED_PREWARM_STATUS_KEY, ttl_s=100, absent_note="the beat did not run"
        )
    assert out["status"] == "unknown"
    assert out["report"] is None
    assert "did not run" in out["note"]


def test_a_malformed_payload_is_distinguished_from_a_wrong_shaped_one():
    """Two different producer bugs, two different names.

    `unparseable` means the bytes are not JSON; `wrong_shape` means they decoded
    to a list or scalar where every consumer indexes a dict. Collapsing them sends
    the reader to the wrong file.
    """
    with _with_conn(_conn(values={FEED_PREWARM_STATUS_KEY: "{not json"})):
        out = admin._warm_rail_status(FEED_PREWARM_STATUS_KEY, ttl_s=100, absent_note="n")
    assert out["status"] == "unparseable"
    assert out["report"] is None

    with _with_conn(_conn(values={FEED_PREWARM_STATUS_KEY: "[1, 2]"})):
        out = admin._warm_rail_status(FEED_PREWARM_STATUS_KEY, ttl_s=100, absent_note="n")
    assert out["status"] == "wrong_shape"
    assert out["report"] is None


def test_the_live_rail_is_graded_stale_against_its_own_period_not_the_other_rail_s_ttl():
    """40 seconds and 6 hours are both "the TTL", and only one of them is a bound.

    The host rail's key lives 6h. Reusing that as the live rail's freshness bound
    would call a beat that last ran twenty minutes ago FRESH — for a pass whose
    whole purpose is to land inside a 60s ceiling. The bound has to come from the
    pass's own period.
    """
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with _with_conn(
        _conn(
            values={FEED_LIVE_PREWARM_STATUS_KEY: _report(ran_at=old)},
            hash_state={"sports": "1"},
        )
    ):
        out = admin._live_prewarm_state()
    assert out["status"] == "ok"
    assert out["stale"] is True, (
        f"a report {out['age_seconds']:.0f}s old is not stale for a 40s beat — the "
        "freshness bound has been taken from the wrong rail"
    )


def test_live_and_absent_labels_are_never_merged():
    """LAT-P112's distinction, which the report exists to carry.

    "This shape is live" and "this shape's mirror was GONE and the 40s pass
    covered for a starved host beat" are different incidents. A reader who cannot
    separate them cannot tell a healthy live night from a `background`-queue
    outage.
    """
    with _with_conn(
        _conn(
            values={FEED_LIVE_PREWARM_STATUS_KEY: _report()},
            hash_state={"sports": "1"},
        )
    ):
        out = admin._live_prewarm_state()
    report = out["report"]
    assert report["live_labels"] == ["sports", "sports_native"]
    assert report["absent_labels"] == ["discover"]
    assert set(report["live_labels"]).isdisjoint(report["absent_labels"])


# --- The two ambiguities that cost #3233 its verdict -------------------------


def test_a_kill_switch_that_is_off_is_visible_because_it_suppresses_the_report():
    """The reason the switches are read here at all.

    `_prewarm_live_feed_shapes` returns "disabled" BEFORE writing any report. So a
    switched-off rail and a beat that never ran are the same absent key, and
    "#3233's fix did not work" is indistinguishable from "the rail is off". The
    switch value is the discriminator and it is not derivable from the report —
    by construction, because there is no report.
    """
    with _with_conn(_conn(values={FEED_LIVE_PREWARM_ENABLED_KEY: "0"})):
        out = admin._live_prewarm_state()
    assert out["status"] == "unknown", "no report was written, as a disabled pass does"
    assert out["switches"]["live_republish"]["state"] == "off"
    assert out["switches"]["warm_rail"]["state"] == "on"


def test_an_unset_switch_reads_as_ON_because_the_pass_only_stops_on_a_literal_zero():
    """The inverted-default trap, pinned.

    The producer stops only on `"0"`; `None` falls through and the pass runs. An
    endpoint that reported an unset key as `off` — the natural reading of a
    missing value — would send an operator hunting for a switch nobody set, on
    every healthy day.
    """
    with _with_conn(_conn(values={})):
        out = admin._live_prewarm_state()
    for name in ("warm_rail", "live_republish"):
        assert out["switches"][name]["state"] == "on"
        assert out["switches"][name]["value"] is None
        assert out["switches"][name]["default_when_unset"] == "on"


class _RedisHashFake:
    """Redis hash semantics, in the one respect that broke CERT-1914.

    **Redis has no empty hash.** `HDEL` of the last remaining field deletes the
    KEY, after which `HGETALL` returns `{}` and `TTL` returns -2 — the same pair
    a genuinely expired key returns. The first version of this endpoint was
    tested against a `MagicMock` scripted with `hash_state={}, ttl=180`, a state
    the real store cannot produce, and it passed while production could only ever
    show `{}` with `-2`. The fake is the fix: it is driven by the REAL writer, so
    a fixture nobody could observe cannot be written by accident.
    """

    def __init__(self):
        self.store: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}

    # --- writer surface (what `_record_shape_liveness` calls) ---
    def hset(self, key, field, value):
        self.store.setdefault(key, {})[str(field)] = str(value)

    def hdel(self, key, field):
        h = self.store.get(key)
        if not h:
            return 0
        removed = h.pop(str(field), None) is not None
        if not h:  # 🔴 the whole point: an emptied hash ceases to exist
            self.store.pop(key, None)
            self.ttls.pop(key, None)
        return int(removed)

    def expire(self, key, seconds):
        if key not in self.store:
            return 0  # EXPIRE on a missing key is a no-op in Redis
        self.ttls[key] = int(seconds)
        return 1

    # --- reader surface ---
    def hgetall(self, key):
        return dict(self.store.get(key, {}))

    def ttl(self, key):
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    def get(self, key):
        return None

    def evict(self, key):
        """The dead-man's switch firing: the TTL ran out and Redis dropped it."""
        self.store.pop(key, None)
        self.ttls.pop(key, None)


def test_the_fake_deletes_a_hash_whose_last_field_is_removed():
    """The precondition the next test depends on, asserted before it is relied on.

    If the fake tolerated an empty hash, the regression below would pass against
    a store that cannot exist and would prove nothing — which is exactly how the
    original defect survived its own test.
    """
    fake = _RedisHashFake()
    fake.hset(FEED_PREWARM_LIVE_SHAPES_KEY, "sports", "1")
    fake.expire(FEED_PREWARM_LIVE_SHAPES_KEY, 300)
    assert fake.ttl(FEED_PREWARM_LIVE_SHAPES_KEY) == 300

    fake.hdel(FEED_PREWARM_LIVE_SHAPES_KEY, "sports")
    assert fake.hgetall(FEED_PREWARM_LIVE_SHAPES_KEY) == {}
    assert fake.ttl(FEED_PREWARM_LIVE_SHAPES_KEY) == -2, (
        "the fake kept an empty hash alive — Redis does not, and a test built on "
        "it cannot see the CERT-1914 defect"
    )


def test_a_quiet_night_and_a_dead_rail_stay_distinguishable_through_the_real_writer():
    """`count: 0` twice, two different diagnoses — driven by the writer, not a fixture.

    A QUIET night: every shape warmed successfully, none of them live. The real
    `_record_shape_liveness` runs for all five and `hdel`s each label, which in
    real Redis would delete the hash and report the rail dead. The heartbeat is
    what keeps the key alive and the reading honest.

    A DEAD rail: no warm inside the dead-man's-switch TTL, so Redis dropped the
    key. `present` must be False here and only here.
    """
    fake = _RedisHashFake()
    for shape in FEED_PREWARM_SHAPES:
        _record_shape_liveness(fake, shape["label"], live=False)

    assert fake.hgetall(FEED_PREWARM_LIVE_SHAPES_KEY), (
        "a full round of quiet warms emptied the live set, so the key is gone and "
        "a healthy rail now reads as an expired dead-man's switch"
    )

    with _with_conn(fake):
        quiet = admin._live_prewarm_state()

    fake.evict(FEED_PREWARM_LIVE_SHAPES_KEY)
    with _with_conn(fake):
        dead = admin._live_prewarm_state()

    assert quiet["selection"]["count"] == dead["selection"]["count"] == 0
    assert quiet["selection"]["present"] is True, (
        "a quiet night is being reported as an expired dead-man's switch"
    )
    assert dead["selection"]["present"] is False
    assert quiet["selection"]["last_warm_age_s"] is not None
    assert dead["selection"]["last_warm_age_s"] is None
    assert quiet["selection"]["ttl_seconds"] == FEED_PREWARM_LIVE_SHAPES_TTL_S, (
        "the TTL was not refreshed by a quiet warm, so the switch expires under a "
        "rail that is succeeding every time"
    )


def test_a_live_warm_does_not_report_the_heartbeat_as_a_shape():
    """The heartbeat shares the hash and is not a first-paint shape.

    Counted as one, it would inflate `live_labels` on the surface built to make
    that number trustworthy.
    """
    fake = _RedisHashFake()
    _record_shape_liveness(fake, "sports", live=True)
    _record_shape_liveness(fake, "discover", live=False)

    with _with_conn(fake):
        out = admin._live_prewarm_state()

    assert out["selection"]["live_labels"] == ["sports"]
    assert out["selection"]["count"] == 1
    assert FEED_PREWARM_LIVE_HEARTBEAT_FIELD not in out["selection"]["live_labels"]


def test_the_live_set_reports_only_the_labels_actually_marked_live():
    """Bytes decoded, and a cleared label excluded rather than counted.

    `_record_shape_liveness` writes both directions; a label that went not-live is
    deleted, but a raw client hands back bytes and a stray value must not be read
    as membership.
    """
    with _with_conn(
        _conn(
            values={},
            hash_state={b"sports": b"1", b"discover": b"0", "sports_native": "1"},
            ttl=250,
        )
    ):
        out = admin._live_prewarm_state()
    assert out["selection"]["live_labels"] == ["sports", "sports_native"]
    assert out["selection"]["count"] == 2
    assert out["selection"]["ttl_seconds"] == 250


def test_a_redis_failure_on_the_selection_read_degrades_that_field_only():
    """A composite endpoint must not lose the report it already read.

    The status key and the live set are separate reads against the same store, and
    the second failing is a reason to say so in one field — not to 503 away a
    report the caller already has in hand.
    """
    conn = _conn(values={FEED_LIVE_PREWARM_STATUS_KEY: _report()})
    conn.hgetall.side_effect = BOOM
    with _with_conn(conn):
        out = admin._live_prewarm_state()
    assert out["status"] == "ok"
    assert out["report"]["concurrency"] == 3
    assert out["selection"]["status"] != "ok"
    assert "secretpw" not in json.dumps(out), "the credential in the error text was not redacted"
