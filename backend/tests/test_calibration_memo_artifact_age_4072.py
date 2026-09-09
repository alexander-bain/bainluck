"""#4072 — the tier-1 memo is bounded by the ARTIFACT's age, not the wall clock.

The bug, measured twice in consecutive hours on production with no release in
either window: ``precompute_calibration_main`` published at 21:16:10Z and the API
went on serving the 20:16 artifact until at least 21:30 (lag ≥ 11m42s; the second
hour ≥ 14m19s). Nothing was broken — tier 1 memoised the 20:16 copy at ~20:30 and
``CACHE_TTL`` is 3600, so it held that copy until ~21:30, which is when the new
one appeared.

The two periods are equal — the artifact refreshes hourly and the memo held it for
an hour — so the phase offset between them was set by whatever minute each web
process happened to seed on, and was therefore arbitrary and per-dyno.

The fix keys the memo's lifetime to the payload's own ``generated_at``, which IS
the publish clock: an artifact reaches ``PUBLISH_PERIOD_S`` exactly when its
successor is due, so the memo lapses seconds before there is something newer to
read instead of up to an hour after.

Why it is worth a guard at p3: it silently degrades two things built specifically
for truth-telling. ``generated_at`` off this endpoint is a *serve* time that was
being read as a publish receipt, and ``producer.beats_missed`` read ``1`` at
21:24Z — accusing a healthy beat — because it is recomputed from whatever payload
is being served.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import request_cache as rc


@pytest.fixture(autouse=True)
def _clean_state():
    """``_cache`` is process-global, so it leaks between tests in this file the
    same way it leaks between requests on a dyno — which is the very thing under
    test here, and would otherwise let one case's artifact answer the next case's
    first read."""
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


def _stamp(*, seconds_ago: float) -> str:
    """A stamp ``seconds_ago`` in the past.

    Subtracted from ``now`` rather than anchored to a fixed hour, so it can never
    land in the future on any clock (gotcha #44) and the age it encodes is exact —
    these tests turn on ages either side of a one-hour boundary, so an hour-
    truncating helper cannot express what they need to say.
    """
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def _payload(*, outcomes: int = 1_000_000, generated_at=None):
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    return {
        "buckets": [{"bucket_idx": 0, "n": outcomes, "winners": outcomes // 2}],
        "by_category": [{"category": "politics", "outcomes": outcomes}],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "population_version": CALIBRATION_POPULATION_VERSION,
        "generated_at": generated_at or _stamp(seconds_ago=120),
    }


class _CountingRedis:
    """Serves ``main``, and counts reads so a test can tell WHICH tier answered."""

    def __init__(self, *, main=None, last_good=None):
        self._values = {
            "bainluck:calibration:main": main,
            "bainluck:calibration:main:last_good": last_good,
        }
        self.calls = 0

    async def get(self, key):
        self.calls += 1
        return self._values.get(key)


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


def _no_compute(monkeypatch):
    from app.tasks import precompute_calibration

    async def _boom(db):
        raise AssertionError("the request path must never build")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)


#: The store could not be reached this request, so ``_memo_may_answer`` falls back
#: to its clock rule. Named rather than repeated so a case that means "Redis is
#: down" cannot be misread as "Redis said the memo is current" — under CERT-2299
#: those are opposite worlds and the predicate branches on exactly this.
_UNREACHABLE_STORE = {
    "store_answered": False,
    "current_fingerprint": None,
    "memo_fingerprint": None,
}


# ---------------------------------------------------------------------------
# The named bug
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheMemoDoesNotOutliveItsArtifact:
    async def test_a_superseded_artifact_is_not_served_from_the_memo(
        self, monkeypatch, healthy_staged_bank
    ):
        """The measured failure, in miniature.

        A process memoises the previous hour's artifact, the beat publishes a new
        one, and the reader must see the new one on the very next request — not up
        to an hour later.
        """
        from app.routes import calibration

        old = _payload(outcomes=1_000_000, generated_at=_stamp(seconds_ago=3_601))
        _use(monkeypatch, _CountingRedis(main=json.dumps(old)))
        _no_compute(monkeypatch)

        first = await calibration.public_calibration(db=object())
        assert first["total_outcomes"] == 1_000_000

        # The beat publishes. Redis now holds the new artifact; the memo holds the old.
        new = _payload(outcomes=2_000_000, generated_at=_stamp(seconds_ago=5))
        redis = _use(monkeypatch, _CountingRedis(main=json.dumps(new)))

        second = await calibration.public_calibration(db=object())

        assert (
            second["total_outcomes"] == 2_000_000
        ), "the memo served a superseded artifact — this is #4072"
        assert redis.calls >= 1, "the memo must have gone back to Redis to find it"

    async def test_the_wall_clock_since_memoisation_does_not_keep_it_alive(
        self, monkeypatch, healthy_staged_bank
    ):
        """The precise defect: the OLD gate asked how long THIS PROCESS had held
        the copy, which is unrelated to whether the copy is current.

        Here the memo was written a heartbeat ago — trivially inside ``CACHE_TTL``,
        so the pre-fix gate admitted it — while the artifact inside it is already
        older than a publish period. Wall-clock age must not rescue it.
        """
        from app.routes import calibration

        aged = _payload(generated_at=_stamp(seconds_ago=4_000))
        _use(monkeypatch, _CountingRedis(main=json.dumps(aged)))
        _no_compute(monkeypatch)

        await calibration.public_calibration(db=object())

        # Memoised just now: `now - _cache["timestamp"]` is ~0 of a 3600 s TTL.
        assert (
            calibration._cache["timestamp"] > 0
        ), "precondition: the first read memoised something"

        redis = _use(monkeypatch, _CountingRedis(main=json.dumps(aged)))
        await calibration.public_calibration(db=object())

        assert redis.calls >= 1, (
            "a memo one second old still holds a superseded artifact; the gate must "
            "read the artifact's clock, not the process's"
        )

    @pytest.mark.parametrize("age_s", [0, 1, 60, 1_800, 3_599])
    async def test_a_current_artifact_still_skips_the_decode(
        self, monkeypatch, healthy_staged_bank, age_s
    ):
        """The memo must stay CHEAP — but cheap is no longer "reads nothing".

        This guard used to assert ``redis.calls == 0``: tier 1 answered without
        consulting anything shared. CERT-2299 proved that exact property was the
        remaining half of #4072 — a process that consults nothing cannot learn
        that somebody published, so a warm dyno and a cold dyno served different
        curves for as long as the two builds' durations differed. No bound on
        time can fix that, because the quantity being bounded is not time.

        So the contract changes shape rather than relaxing. What tier 1 buys is
        skipping the DECODE (gotcha #38 — ``json.loads`` holds the GIL for the
        whole C-level parse, and this payload is large) and the verdict/serve
        rebuild on top of it. What it now pays is one bounded ``GET`` of one key.
        This pins both halves: exactly one read, and zero decodes.
        """
        from app.routes import calibration

        current = _payload(generated_at=_stamp(seconds_ago=age_s))
        raw = json.dumps(current)
        _use(monkeypatch, _CountingRedis(main=raw))
        _no_compute(monkeypatch)

        await calibration.public_calibration(db=object())

        redis = _use(monkeypatch, _CountingRedis(main=raw))

        # Count only decodes OF THIS PAYLOAD, so an unrelated `json.loads`
        # somewhere in the request path cannot make this guard fail for a reason
        # that has nothing to do with the memo.
        decodes = []
        real_loads = json.loads

        def _counting_loads(s, *a, **kw):
            if s == raw:
                decodes.append(s)
            return real_loads(s, *a, **kw)

        monkeypatch.setattr(json, "loads", _counting_loads)
        out = await calibration.public_calibration(db=object())

        assert out["total_outcomes"] == 1_000_000
        assert redis.calls == 1, (
            "the memo must consult the store exactly ONCE — no more (a second read "
            "means it fell through to a lower tier) and no less (zero means it is "
            "short-circuiting again, which is the CERT-2299 defect)"
        )
        assert decodes == [], (
            "a current artifact must still be served WITHOUT re-decoding it — that "
            "is the whole remaining value of tier 1"
        )

    async def test_an_early_successor_cannot_coexist_with_the_old_memo(
        self, monkeypatch, healthy_staged_bank
    ):
        """CERT-2299's falsifier, as a permanent guard.

        The beat is hourly but its BUILDS are not all the same length, so a
        successor can be published while the incumbent artifact is still 3,599 s
        old — one second inside the ``PUBLISH_PERIOD_S`` gate. For that interval
        the age gate alone admitted the memo, so a warm dyno served the old curve
        while a cold dyno served the new one: two readers, one instant, different
        curves, and a refresh that moves a reader backward. That IS the ship, and
        it is why the memo is validated against the store rather than a clock.

        3,599 exactly, not "old": at 3,601 the age gate already refuses and this
        test would pass without the repair it exists to protect.
        """
        from app.routes import calibration

        old = _payload(outcomes=1_000_000, generated_at=_stamp(seconds_ago=3_599))
        _use(monkeypatch, _CountingRedis(main=json.dumps(old)))
        _no_compute(monkeypatch)

        first = await calibration.public_calibration(db=object())
        assert (
            first["total_outcomes"] == 1_000_000
        ), "precondition: the memo holds the old copy"

        # The next build finished FASTER, so its artifact lands while the memo's
        # copy is still one second inside the publish period.
        new = _payload(outcomes=2_000_000, generated_at=_stamp(seconds_ago=2))
        redis = _use(monkeypatch, _CountingRedis(main=json.dumps(new)))

        second = await calibration.public_calibration(db=object())

        assert second["total_outcomes"] == 2_000_000, (
            "a warm dyno served a superseded artifact while a cold one served the "
            "successor — same instant, two different curves (CERT-2299)"
        )
        assert redis.calls >= 1, "the memo must consult the store to see the successor"


# ---------------------------------------------------------------------------
# The predicate on its own — the boundary and the cases the route cannot reach
# ---------------------------------------------------------------------------


class TestMemoMayAnswer:
    """The predicate on its own.

    Since CERT-2299 the predicate has TWO rules and ``store_answered`` chooses
    between them, so every case here says which world it is in. The cases below
    are the ``store_answered=False`` world — the store could not be reached, so
    there is no successor visible to anyone and the clock is the only rule left.
    ``TestTheStoreIsTheAuthority`` covers the other world.
    """

    def _fresh(self, *, seconds_ago: float) -> dict:
        return {"generated_at": _stamp(seconds_ago=seconds_ago)}

    def test_the_boundary_is_the_publish_period(self):
        """At exactly one period the successor is due, so the copy is refused.

        Pinned as a boundary rather than a value: a memo admitted AT the boundary
        is the whole hour of lag back again, one second at a time.
        """
        from app.routes.calibration import PUBLISH_PERIOD_S, _memo_may_answer

        now = 1_000_000.0
        just_inside = self._fresh(seconds_ago=PUBLISH_PERIOD_S - 2)
        at_boundary = self._fresh(seconds_ago=PUBLISH_PERIOD_S)

        assert (
            _memo_may_answer(
                just_inside,
                now,
                now=now,
                age_s=PUBLISH_PERIOD_S - 2,
                **_UNREACHABLE_STORE,
            )
            is True
        )
        assert (
            _memo_may_answer(
                at_boundary, now, now=now, age_s=PUBLISH_PERIOD_S, **_UNREACHABLE_STORE
            )
            is False
        )

    def test_a_stale_marked_copy_is_still_never_memo_served(self):
        """Queue #284 Item 3 must survive the #4072 change.

        A stale-marked copy stays honestly marked and re-attempts Redis on every
        request, so a later fresh-main read replaces it promptly. Age has nothing
        to do with it: even a brand-new stale-marked copy is refused.
        """
        from app.routes.calibration import _memo_may_answer

        marked = {"generated_at": _stamp(seconds_ago=1), "cache": {"status": "stale"}}
        assert (
            _memo_may_answer(
                marked, 1_000_000.0, now=1_000_000.0, age_s=1, **_UNREACHABLE_STORE
            )
            is False
        )

    def test_an_undated_payload_falls_back_to_the_wall_clock_backstop(self):
        """Unknown age is not zero (gotcha #53) — but it is not "re-read forever"
        either.

        A payload with no parseable ``generated_at`` is already declared degraded
        by the caller. Refusing it outright would make it hit Redis on every
        request for as long as it is held, which is a lot of load to spend on a
        copy we have already stopped believing, so ``CACHE_TTL`` governs this
        case — and this case alone.
        """
        from app.routes.calibration import CACHE_TTL, _memo_may_answer

        undated = {"buckets": []}
        memoised_at = 1_000_000.0

        assert (
            _memo_may_answer(
                undated,
                memoised_at,
                now=memoised_at + 10,
                age_s=None,
                **_UNREACHABLE_STORE,
            )
            is True
        )
        assert (
            _memo_may_answer(
                undated,
                memoised_at,
                now=memoised_at + CACHE_TTL + 1,
                age_s=None,
                **_UNREACHABLE_STORE,
            )
            is False
        )

    def test_an_empty_memo_never_answers(self):
        from app.routes.calibration import _memo_may_answer

        for empty in (None, "", [], 0):
            assert (
                _memo_may_answer(empty, 0.0, now=1.0, age_s=1.0, **_UNREACHABLE_STORE)
                is False
            ), f"{empty!r} is not a payload"


# ---------------------------------------------------------------------------
# CERT-2299 — with the store reachable, the store is the authority
# ---------------------------------------------------------------------------


class TestTheStoreIsTheAuthority:
    """When the store answers, the clock does not get a vote.

    The whole CERT-2299 finding is that an age bound is necessary and not
    sufficient: the memo's question is not "how old is my copy" but "has anyone
    published since". Only the store can answer that, so when it is reachable
    the predicate must ignore age entirely — in BOTH directions, which is what
    makes these four cases a pair of pairs rather than a list.
    """

    def _fp(self, raw: str):
        from app.routes.calibration import main_artifact_fingerprint

        return main_artifact_fingerprint(raw)

    def test_matching_bytes_admit_the_memo_however_old_the_artifact(self):
        """Age does not refuse a copy the store still holds.

        If Redis is still serving these exact bytes then every other dyno is
        serving them too, so declining here would buy no agreement — it would
        only cost a decode. The publisher being late is the producer's problem
        and the banner's; it is not a reason for two readers to disagree.
        """
        from app.routes.calibration import _memo_may_answer

        raw = '{"generated_at": "whenever"}'
        fp = self._fp(raw)

        assert (
            _memo_may_answer(
                {"generated_at": "whenever"},
                0.0,
                now=1_000_000.0,
                age_s=999_999.0,
                store_answered=True,
                current_fingerprint=fp,
                memo_fingerprint=fp,
            )
            is True
        )

    def test_different_bytes_refuse_the_memo_however_young_the_artifact(self):
        """The falsifier's case, at the predicate level: a one-second-old memo
        is still refused once the store holds something else."""
        from app.routes.calibration import _memo_may_answer

        assert (
            _memo_may_answer(
                {"generated_at": "now"},
                1_000_000.0,
                now=1_000_000.0,
                age_s=1.0,
                store_answered=True,
                current_fingerprint=self._fp('{"a": 2}'),
                memo_fingerprint=self._fp('{"a": 1}'),
            )
            is False
        )

    def test_an_absent_key_is_a_miss_not_a_match(self):
        """The memo must not outlive the artifact's EVICTION either.

        ``None`` is the fingerprint of "no value", and two unreadable things are
        not the same thing (gotcha #53). If both sides collapsed to ``None`` and
        compared equal, an evicted key would pin the memo forever — the failure
        this repair exists to end, wearing a different hat.
        """
        from app.routes.calibration import _memo_may_answer

        assert (
            _memo_may_answer(
                {"generated_at": "now"},
                1_000_000.0,
                now=1_000_000.0,
                age_s=1.0,
                store_answered=True,
                current_fingerprint=None,
                memo_fingerprint=None,
            )
            is False
        )

    def test_a_memo_with_no_recorded_source_is_refused(self):
        """A payload that never came from the main key cannot prove it is current.

        Every such copy is stale-marked and refused a line earlier, so this is
        belt-and-braces — but the braces are the point: if a future tier ever
        memoises an unmarked copy without recording where it came from, it must
        fail CLOSED rather than inherit the last artifact's identity.
        """
        from app.routes.calibration import _memo_may_answer

        assert (
            _memo_may_answer(
                {"generated_at": "now"},
                1_000_000.0,
                now=1_000_000.0,
                age_s=1.0,
                store_answered=True,
                current_fingerprint=self._fp('{"a": 1}'),
                memo_fingerprint=None,
            )
            is False
        )


class TestTheFingerprint:
    def test_the_same_bytes_give_the_same_name_and_different_bytes_do_not(self):
        from app.routes.calibration import main_artifact_fingerprint as fp

        assert fp('{"a": 1}') == fp('{"a": 1}')
        assert fp('{"a": 1}') != fp('{"a": 2}')

    def test_bytes_and_str_of_the_same_value_agree(self):
        """redis-py returns ``bytes`` or ``str`` depending on ``decode_responses``.
        A fingerprint that disagreed across those would refuse every memo on one
        configuration and nobody would notice, because refusing is the SAFE
        direction — it would just quietly cost a decode per request forever."""
        from app.routes.calibration import main_artifact_fingerprint as fp

        assert fp('{"a": 1}') == fp(b'{"a": 1}')

    def test_an_unreadable_value_has_no_fingerprint(self):
        from app.routes.calibration import main_artifact_fingerprint as fp

        for junk in (None, 0, [], {}):
            assert fp(junk) is None, f"{junk!r} is not a published artifact"
