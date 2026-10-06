"""#10570 — Search never serves an old or unattributed score as an upset happening now.

WHAT A READER WOULD SEE. Section 1 of the `/search` zero-state prints "Upset
brewing" / "Upset underway" on a live game whose opening underdog leads (#5051).
That sentence names the SCOREBOARD, and the scoreboard has its own clock
(`Event.score_observed_at`, #4571). The cache holds a build for 60 s on the
primary and serves the mirror up to 300 s past that, and before this change
`render` passed every non-countdown chip through untouched — so a score already
4m59s old at build time could still be described as happening now at 9m59s.

WHAT THIS PINS (sections 1-5 are the cache half, Phase 1; section 6 is the
builder half, Phase 2, after #10563 — the builder now stores each upset chip's
own `score_source` / `score_observed_at` and the cold path judges it too):

  1. each live-upset chip's stored `_score_claim` is judged at the SERVING clock
     by #10561's own `score_observation_is_current` — five minutes inclusive,
     closed source registry, no future stamps — on cold, primary and mirror
     paths alike, and the envelope's age is never the clock;
  2. missing, half, malformed, future, unknown-source and legacy (no evidence)
     upset chips fail closed;
  3. every sibling — tight price, countdown, movers, the historical "Pulled the
     upset" — survives without any score evidence;
  4. the evidence never reaches the wire and the stored payload is not mutated;
  5. a payload whose only chips were expired upsets takes the existing
     empty-render rebuild path, and a warm cache filters without the builder.

CLOCK DISCIPLINE (gotcha #44): every unit test builds both ends of the
comparison from the fixed `T0` and passes `now` explicitly. The two route tests
must use the wall clock (the route reads it itself); their margins are minutes
wide and neither branches on it.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.encoders import jsonable_encoder

from app.routes import events as events_routes
from app.utils import event_concept_cache as ecc
from app.utils import search_suggestions_cache as ssc
from app.utils.highlights import SCORE_CLAIM_MAX_AGE
from app.utils.score_observation import (
    SCORE_SOURCE_ESPN,
    SCORE_SOURCE_ODDS,
    SCORE_SOURCE_STATPAL,
)

T0 = datetime(2026, 10, 5, 20, 0, 0, tzinfo=timezone.utc)
PRIMARY = "bainluck:search_suggestions:v1"
MIRROR = "bainluck:search_suggestions:v1:stale"


def _upset(query, observed_at, *, source=SCORE_SOURCE_ESPN, label="Upset brewing"):
    return {
        "query": query,
        "label": label,
        "type": "event",
        "event_id": 7,
        ssc.SCORE_CLAIM_FIELD: ssc.score_claim(source, observed_at),
    }


def _legacy_upset(query, label="Upset brewing"):
    """What a payload written before #10570 holds: the label, no evidence."""
    return {"query": query, "label": label, "type": "event", "event_id": 8}


def _siblings(now):
    """One chip from every other section, none carrying score evidence."""
    deadline = now + timedelta(minutes=40)
    return [
        {
            "query": "Pumas",
            "label": "Live — tight game vs León",
            "type": "event",
            "event_id": 1,
        },
        {
            "query": "Aces",
            "label": ssc.countdown_label(deadline, now, "basketball_wnba"),
            "type": "event",
            "event_id": 2,
            ssc.COUNTDOWN_FIELD: deadline.isoformat(),
            ssc.COUNTDOWN_SPORT_FIELD: "basketball_wnba",
        },
        {
            "query": "Barcelona",
            "label": "Surging +4.1% — Rodri: Next Club",
            "type": "futures",
        },
        {
            "query": "Rays",
            "label": "Pulled the upset vs Yankees",
            "type": "event",
            "event_id": 3,
        },
    ]


def _stored(items, created_at=T0):
    """The exact shape `_publish_search_suggestions` writes."""
    return jsonable_encoder(ssc.stamp({"suggestions": items}, created_at=created_at))


def _labels(body):
    return [s["label"] for s in body["suggestions"]]


def _queries(body):
    return [s["query"] for s in body["suggestions"]]


class _FakeRedis:
    def __init__(self, slots=None):
        self.slots = dict(slots or {})
        self.setex_calls: list[tuple[str, int, str]] = []

    def get(self, key):
        return self.slots.get(key)

    def setex(self, key, ttl, payload):
        self.setex_calls.append((key, ttl, payload))
        self.slots[key] = payload

    def delete(self, key):
        self.slots.pop(key, None)


# ---------------------------------------------------------------------------
# 1. The rule is #10561's, asked at the serving clock
# ---------------------------------------------------------------------------


class TestTheServingClockDecides:
    def test_the_age_limit_is_the_inherited_five_minutes(self):
        assert SCORE_CLAIM_MAX_AGE == timedelta(minutes=5)

    @pytest.mark.parametrize("label", sorted(ssc.LIVE_UPSET_LABELS))
    @pytest.mark.parametrize(
        "source", [SCORE_SOURCE_ESPN, SCORE_SOURCE_STATPAL, SCORE_SOURCE_ODDS]
    )
    def test_a_current_score_keeps_both_upset_labels(self, label, source):
        body = ssc.render(
            _stored(
                [_upset("Rays", T0 - timedelta(seconds=30), source=source, label=label)]
            ),
            T0,
        )
        assert _labels(body) == [label]

    def test_a_score_4m59_old_at_build_is_gone_2s_later(self):
        """🔴 THE DEFECT. Built at T0 from a score observed 4m59s earlier, the
        chip is true at T0 — and false at T0+2s, from the same cached bytes."""
        stored = _stored([_upset("Rays", T0 - timedelta(minutes=4, seconds=59))])
        assert _queries(ssc.render(stored, T0)) == ["Rays"]
        assert _queries(ssc.render(stored, T0 + timedelta(seconds=2))) == []

    def test_exactly_five_minutes_is_inclusive(self):
        stored = _stored([_upset("Rays", T0 - timedelta(minutes=5))])
        assert _queries(ssc.render(stored, T0)) == ["Rays"]

    def test_five_minutes_and_a_microsecond_is_refused(self):
        stored = _stored([_upset("Rays", T0 - timedelta(minutes=5, microseconds=1))])
        assert _queries(ssc.render(stored, T0)) == []

    def test_the_envelope_age_is_not_the_clock(self):
        """A payload built THIS instant from a six-minute-old score is refused,
        and a 4-minute-old mirror holding a score observed when it was built is
        not refused for its age: the score's own stamp is the only clock."""
        just_built_old_score = _stored(
            [_upset("Rays", T0 - timedelta(minutes=6))], created_at=T0
        )
        assert _queries(ssc.render(just_built_old_score, T0)) == []

        old_build_fresh_score = _stored(
            [_upset("Rays", T0 - timedelta(minutes=4))],
            created_at=T0 - timedelta(minutes=4),
        )
        assert _queries(ssc.render(old_build_fresh_score, T0)) == ["Rays"]

    def test_evidence_survives_the_storage_codec_in_every_spelling(self):
        observed = T0 - timedelta(seconds=10)
        for value in (
            observed,
            observed.isoformat(),
            observed.isoformat().replace("+00:00", "Z"),
        ):
            item = _upset("Rays", value)
            assert _queries(ssc.render({"suggestions": [item]}, T0)) == ["Rays"], value


# ---------------------------------------------------------------------------
# 2. Anything short of real, current, attributed evidence fails closed
# ---------------------------------------------------------------------------


class TestBadEvidenceFailsClosed:
    @pytest.mark.parametrize(
        "claim",
        [
            None,
            "espn",
            [],
            {},
            {ssc.SCORE_CLAIM_SOURCE: SCORE_SOURCE_ESPN},
            {ssc.SCORE_CLAIM_OBSERVED_AT: T0.isoformat()},
            {
                ssc.SCORE_CLAIM_SOURCE: SCORE_SOURCE_ESPN,
                ssc.SCORE_CLAIM_OBSERVED_AT: None,
            },
            {
                ssc.SCORE_CLAIM_SOURCE: SCORE_SOURCE_ESPN,
                ssc.SCORE_CLAIM_OBSERVED_AT: "not a date",
            },
            {
                ssc.SCORE_CLAIM_SOURCE: SCORE_SOURCE_ESPN,
                ssc.SCORE_CLAIM_OBSERVED_AT: 1759694400,
            },
            {ssc.SCORE_CLAIM_SOURCE: None, ssc.SCORE_CLAIM_OBSERVED_AT: T0.isoformat()},
            {
                ssc.SCORE_CLAIM_SOURCE: "kalshi",
                ssc.SCORE_CLAIM_OBSERVED_AT: T0.isoformat(),
            },
            {ssc.SCORE_CLAIM_SOURCE: 1, ssc.SCORE_CLAIM_OBSERVED_AT: T0.isoformat()},
        ],
        ids=[
            "none",
            "string",
            "list",
            "empty",
            "source-only",
            "observed-only",
            "observed-none",
            "observed-garbage",
            "observed-epoch-int",
            "source-none",
            "source-unknown",
            "source-not-str",
        ],
    )
    def test_malformed_or_unattributed_evidence_is_refused(self, claim):
        item = {
            "query": "Rays",
            "label": "Upset brewing",
            "type": "event",
            ssc.SCORE_CLAIM_FIELD: claim,
        }
        assert _queries(ssc.render({"suggestions": [item]}, T0)) == []

    def test_a_stamp_from_the_future_is_refused(self):
        stored = _stored([_upset("Rays", T0 + timedelta(seconds=1))])
        assert _queries(ssc.render(stored, T0)) == []

    def test_a_row_with_no_stamp_is_refused(self):
        """What the Phase 2 builder writes for a row whose score was never
        stamped: `score_claim(None, None)`."""
        stored = _stored([_upset("Rays", None, source=None)])
        assert _queries(ssc.render(stored, T0)) == []

    @pytest.mark.parametrize("label", sorted(ssc.LIVE_UPSET_LABELS))
    def test_a_legacy_cached_upset_with_no_evidence_is_refused(self, label):
        assert _queries(ssc.render(_stored([_legacy_upset("Rays", label)]), T0)) == []

    def test_the_label_match_is_exact_and_typed(self):
        """Only section 1's two labels on an `event` chip are judged; a futures
        chip that happened to share the words is not a scoreboard claim."""
        assert ssc.is_live_upset_claim(_legacy_upset("Rays"))
        assert not ssc.is_live_upset_claim(
            {"query": "Rays", "label": "Upset brewing", "type": "futures"}
        )
        assert not ssc.is_live_upset_claim(
            {"query": "Rays", "label": "Pulled the upset vs Yankees", "type": "event"}
        )


# ---------------------------------------------------------------------------
# 3. Siblings, the wire and the stored artifact
# ---------------------------------------------------------------------------


class TestSiblingsWireAndStorage:
    def test_every_sibling_survives_without_score_evidence(self):
        stored = _stored(_siblings(T0) + [_legacy_upset("Mets")])
        body = ssc.render(stored, T0 + timedelta(seconds=30))
        assert _queries(body) == ["Pumas", "Aces", "Barcelona", "Rays"]
        assert _labels(body) == [
            "Live — tight game vs León",
            "Tips off in 39 min",
            "Surging +4.1% — Rodri: Next Club",
            "Pulled the upset vs Yankees",
        ]

    def test_a_current_upset_sits_beside_its_siblings(self):
        stored = _stored(_siblings(T0) + [_upset("Mets", T0 - timedelta(minutes=1))])
        assert _queries(ssc.render(stored, T0)) == [
            "Pumas",
            "Aces",
            "Barcelona",
            "Rays",
            "Mets",
        ]

    def test_the_evidence_never_reaches_the_wire(self):
        """Stripped from EVERY item, judged or not — including a sibling that
        carries it, which keeps its chip."""
        tagged_sibling = dict(_siblings(T0)[0])
        tagged_sibling[ssc.SCORE_CLAIM_FIELD] = ssc.score_claim("kalshi", "garbage")
        stored = _stored([tagged_sibling, _upset("Mets", T0 - timedelta(seconds=5))])
        body = ssc.render(stored, T0)
        assert _queries(body) == ["Pumas", "Mets"]
        assert all(ssc.SCORE_CLAIM_FIELD not in s for s in body["suggestions"])
        assert ssc.SCORE_CLAIM_FIELD not in json.dumps(body)

    def test_render_does_not_mutate_the_stored_payload(self):
        stored = _stored(
            _siblings(T0)
            + [
                _upset("Mets", T0 - timedelta(seconds=5)),
                _upset("Cubs", T0 - timedelta(minutes=9)),
                _legacy_upset("Reds"),
            ]
        )
        before = copy.deepcopy(stored)
        ssc.render(stored, T0)
        ssc.render(stored, T0 + timedelta(minutes=10))
        assert stored == before
        assert (
            stored["suggestions"][4][ssc.SCORE_CLAIM_FIELD]
            == before["suggestions"][4][ssc.SCORE_CLAIM_FIELD]
        )

    def test_write_stores_the_evidence(self):
        """Stored bytes keep the claim so a later serve can judge it again."""
        rc = _FakeRedis()
        ssc.write(_stored([_upset("Mets", T0)]), rc=rc)
        assert len(rc.setex_calls) == 2
        for key, _ttl, blob in rc.setex_calls:
            assert ssc.SCORE_CLAIM_FIELD in json.loads(blob)["suggestions"][0], key


# ---------------------------------------------------------------------------
# 4. Empty-render rebuild semantics, primary and mirror, no builder
# ---------------------------------------------------------------------------


class TestTheSlotsFilterWithoutTheBuilder:
    def test_only_expired_upsets_render_to_nothing(self):
        stored = _stored([_upset("Mets", T0 - timedelta(minutes=4, seconds=59))])
        assert ssc.renders_to_something(stored, T0) is True
        assert ssc.renders_to_something(stored, T0 + timedelta(seconds=2)) is False

    def test_a_stored_empty_answer_is_still_a_real_answer(self):
        assert ssc.renders_to_something(_stored([]), T0) is True

    def test_primary_mixed_payload_filters_at_the_serving_clock(self):
        stored = _stored(
            _siblings(T0) + [_upset("Mets", T0 - timedelta(minutes=4, seconds=59))]
        )
        rc = _FakeRedis({PRIMARY: json.dumps(stored)})

        body, state = ssc.read(rc=rc, now=T0)
        assert state == "live"
        assert "Mets" in _queries(body)

        body, state = ssc.read(rc=rc, now=T0 + timedelta(seconds=2))
        assert state == "live"
        assert _queries(body) == ["Pumas", "Aces", "Barcelona", "Rays"]
        assert body[ecc.ENVELOPE_FIELD]["availability"] == ecc.AVAILABILITY_LIVE
        assert rc.setex_calls == []

    def test_mirror_mixed_payload_filters_at_the_serving_clock(self):
        """The 9m59s case: a mirror inside the 300 s ceiling whose upset was
        built from a score 4m59s old at build time."""
        built = T0 - timedelta(minutes=4)
        stored = _stored(
            _siblings(built)
            + [_upset("Mets", built - timedelta(minutes=4, seconds=59))],
            created_at=built,
        )
        rc = _FakeRedis({MIRROR: json.dumps(stored)})
        body, state = ssc.read(rc=rc, now=T0)
        assert state == "stale_ok"
        assert "Mets" not in _queries(body)
        assert {"Pumas", "Barcelona", "Rays"} <= set(_queries(body))
        assert body[ecc.ENVELOPE_FIELD]["availability"] == ecc.AVAILABILITY_STALE_OK

    def test_mirror_keeps_a_current_upset(self):
        built = T0 - timedelta(minutes=3)
        stored = _stored([_upset("Mets", built)], created_at=built)
        body, state = ssc.read(rc=_FakeRedis({MIRROR: json.dumps(stored)}), now=T0)
        assert state == "stale_ok"
        assert _queries(body) == ["Mets"]

    def test_an_only_expired_upset_primary_is_a_miss(self):
        stored = _stored([_upset("Mets", T0 - timedelta(minutes=4, seconds=59))])
        rc = _FakeRedis({PRIMARY: json.dumps(stored)})
        assert ssc.read(rc=rc, now=T0 + timedelta(seconds=2)) == (None, "miss")

    def test_an_only_expired_upset_mirror_is_refused_for_emptiness(self):
        built = T0 - timedelta(minutes=2)
        stored = _stored(
            [_upset("Mets", built - timedelta(minutes=4))], created_at=built
        )
        assert ssc.mirror_is_servable(stored, T0) == (False, "empty_after_render")
        rc = _FakeRedis({MIRROR: json.dumps(stored)})
        assert ssc.read(rc=rc, now=T0) == (None, "stale_too_old")

    def test_a_legacy_only_mirror_is_refused_and_a_legacy_mixed_one_drops_only_the_upset(
        self,
    ):
        built = T0 - timedelta(minutes=1)
        legacy_only = _stored([_legacy_upset("Mets")], created_at=built)
        assert ssc.mirror_is_servable(legacy_only, T0) == (False, "empty_after_render")

        legacy_mixed = _stored(
            _siblings(built) + [_legacy_upset("Mets")], created_at=built
        )
        body, state = ssc.read(
            rc=_FakeRedis({MIRROR: json.dumps(legacy_mixed)}), now=T0
        )
        assert state == "stale_ok"
        assert "Mets" not in _queries(body)
        assert "Pumas" in _queries(body)


# ---------------------------------------------------------------------------
# 5. The route: a warm cache filters without invoking the builder
# ---------------------------------------------------------------------------


@pytest.fixture
def warm_route(monkeypatch):
    import app.tasks.redis_state as redis_state

    async def _builder_must_not_run(db):
        raise AssertionError("a warm cache must not invoke the builder")

    monkeypatch.setattr(
        events_routes, "_build_search_suggestions", _builder_must_not_run
    )

    def install(client):
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: client)
        return client

    return install


class _NoDB:
    async def execute(self, *a, **kw):
        raise AssertionError("a warm cache must not query the database")


class TestTheRouteServesWarmWithoutBuilding:
    async def test_warm_primary_drops_the_stale_upset_and_keeps_the_rest(
        self, warm_route
    ):
        now = datetime.now(timezone.utc)
        stored = _stored(
            _siblings(now)
            + [
                _upset("Mets", now - timedelta(minutes=10)),
                _upset("Cubs", now - timedelta(seconds=5), label="Upset underway"),
                _legacy_upset("Reds"),
            ],
            created_at=now,
        )
        rc = warm_route(_FakeRedis({PRIMARY: json.dumps(stored)}))

        resp = await events_routes.search_suggestions(db=_NoDB())

        assert _queries(resp) == ["Pumas", "Aces", "Barcelona", "Rays", "Cubs"]
        assert ssc.SCORE_CLAIM_FIELD not in json.dumps(resp)
        assert resp[ecc.ENVELOPE_FIELD]["availability"] == ecc.AVAILABILITY_LIVE
        assert rc.setex_calls == []

    async def test_warm_mirror_drops_the_stale_upset_and_schedules_one_rebuild(
        self, warm_route, monkeypatch
    ):
        now = datetime.now(timezone.utc)
        built = now - timedelta(minutes=2)
        stored = _stored(
            _siblings(built) + [_upset("Mets", built - timedelta(minutes=4))],
            created_at=built,
        )
        warm_route(_FakeRedis({MIRROR: json.dumps(stored)}))
        scheduled = []
        monkeypatch.setattr(
            events_routes,
            "_serve_stale_and_refresh",
            lambda name, rebuild: scheduled.append(name) or True,
        )

        resp = await events_routes.search_suggestions(db=_NoDB())

        assert "Mets" not in _queries(resp)
        assert {"Pumas", "Barcelona", "Rays"} <= set(_queries(resp))
        assert resp[ecc.ENVELOPE_FIELD]["availability"] == ecc.AVAILABILITY_STALE_OK
        assert scheduled == ["search_suggestions"]


# ---------------------------------------------------------------------------
# 6. Phase 2: the builder carries the row's own evidence, and the COLD path —
#    build, publish, render in one request — judges it like the warm ones
# ---------------------------------------------------------------------------
#
# The game is #5051's: home opened 62%, the blend has it at 30% (outside the
# 35-65% tight band, so only the upset arm speaks), and the underdog leads 10-3.
# A second, unrelated game sits in the tight band so every cold-path refusal is
# also a proof that section 1's price-only sibling survives it.

_UPSET_ID = 1057001
_TIGHT_ID = 1057002


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _OneLiveQueryDB:
    """Section 1's statement gets the live rows; every later section, none."""

    def __init__(self, live_rows):
        self._results = [_Rows(live_rows)]

    async def execute(self, *a, **kw):
        return self._results.pop(0) if self._results else _Rows([])


def _live_game(
    now,
    *,
    score_source=SCORE_SOURCE_ESPN,
    observed_ago=timedelta(seconds=30),
    now_home=0.30,
    home_score=3,
    away_score=10,
):
    from decimal import Decimal
    from types import SimpleNamespace

    return SimpleNamespace(
        id=_UPSET_ID,
        status="live",
        commence_time=now - timedelta(minutes=50),
        home_team_name="Philadelphia Eagles",
        away_team_name="Dallas Cowboys",
        home_score=home_score,
        away_score=away_score,
        opening_home_probability=Decimal("0.6200"),
        opening_away_probability=Decimal("0.3800"),
        win_probability_sources={"betting": now_home},
        espn_win_prob_home=None,
        score_source=score_source,
        score_observed_at=None if observed_ago is None else now - observed_ago,
    )


def _tight_game(now):
    """Section 1's sibling: a price-only claim, no score on the row at all."""
    from decimal import Decimal
    from types import SimpleNamespace

    return SimpleNamespace(
        id=_TIGHT_ID,
        status="live",
        commence_time=now - timedelta(minutes=20),
        home_team_name="Pumas",
        away_team_name="León",
        home_score=None,
        away_score=None,
        opening_home_probability=Decimal("0.5000"),
        opening_away_probability=Decimal("0.5000"),
        win_probability_sources={"betting": 0.50},
        espn_win_prob_home=None,
        score_source=None,
        score_observed_at=None,
    )


@pytest.fixture
def cold_route(monkeypatch):
    """An empty Redis: the route must build, publish and render in-request."""
    import app.tasks.redis_state as redis_state

    rc = _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: rc)
    return rc


def _chip(body, event_id):
    return [s for s in body["suggestions"] if s.get("event_id") == event_id]


class TestTheBuilderCarriesTheRowsOwnEvidence:
    async def test_the_upset_chip_stores_the_rows_writer_and_stamp_verbatim(self):
        now = datetime.now(timezone.utc)
        game = _live_game(now, score_source=SCORE_SOURCE_STATPAL)

        built = await events_routes._build_search_suggestions(
            _OneLiveQueryDB([game])
        )

        (chip,) = _chip(built, _UPSET_ID)
        assert chip["label"] == "Upset brewing"
        assert chip[ssc.SCORE_CLAIM_FIELD] == {
            ssc.SCORE_CLAIM_SOURCE: SCORE_SOURCE_STATPAL,
            ssc.SCORE_CLAIM_OBSERVED_AT: game.score_observed_at,
        }

    async def test_a_row_with_no_stamp_still_stores_the_empty_evidence(self):
        """The builder never judges: the refusal is `render`'s, at serve time."""
        now = datetime.now(timezone.utc)
        built = await events_routes._build_search_suggestions(
            _OneLiveQueryDB([_live_game(now, score_source=None, observed_ago=None)])
        )

        (chip,) = _chip(built, _UPSET_ID)
        assert chip[ssc.SCORE_CLAIM_FIELD] == {
            ssc.SCORE_CLAIM_SOURCE: None,
            ssc.SCORE_CLAIM_OBSERVED_AT: None,
        }

    async def test_the_price_only_sibling_carries_no_evidence(self):
        now = datetime.now(timezone.utc)
        built = await events_routes._build_search_suggestions(
            _OneLiveQueryDB([_tight_game(now)])
        )

        (chip,) = _chip(built, _TIGHT_ID)
        assert chip["label"] == "Live — tight game vs Pumas"
        assert ssc.SCORE_CLAIM_FIELD not in chip


class TestTheColdPathJudgesAtTheServingClock:
    @pytest.mark.parametrize(
        "now_home,home_score,away_score,label",
        [
            (0.30, 3, 10, "Upset brewing"),
            (0.05, 7, 24, "Upset underway"),
        ],
    )
    async def test_a_current_score_is_served_and_its_evidence_is_stored_not_sent(
        self, cold_route, now_home, home_score, away_score, label
    ):
        now = datetime.now(timezone.utc)
        game = _live_game(
            now, now_home=now_home, home_score=home_score, away_score=away_score
        )

        resp = await events_routes.search_suggestions(
            db=_OneLiveQueryDB([game, _tight_game(now)])
        )

        assert [c["label"] for c in _chip(resp, _UPSET_ID)] == [label]
        assert _chip(resp, _TIGHT_ID), "the price-only sibling must survive"
        assert ssc.SCORE_CLAIM_FIELD not in json.dumps(resp, default=str)
        # What a later reader re-judges is in the slot, in the codec's spelling.
        stored = json.loads(cold_route.slots[PRIMARY])
        (kept,) = [s for s in stored["suggestions"] if s.get("event_id") == _UPSET_ID]
        assert kept[ssc.SCORE_CLAIM_FIELD] == {
            ssc.SCORE_CLAIM_SOURCE: SCORE_SOURCE_ESPN,
            ssc.SCORE_CLAIM_OBSERVED_AT: game.score_observed_at.isoformat(),
        }

    @pytest.mark.parametrize(
        "score_source,observed_ago",
        [
            pytest.param(SCORE_SOURCE_ESPN, timedelta(minutes=10), id="stale"),
            pytest.param(None, None, id="no-stamp"),
            pytest.param(None, timedelta(seconds=30), id="half-no-source"),
            pytest.param(SCORE_SOURCE_ESPN, None, id="half-no-clock"),
            pytest.param("scraper", timedelta(seconds=30), id="unknown-writer"),
            pytest.param(SCORE_SOURCE_ODDS, timedelta(minutes=-10), id="future"),
        ],
    )
    async def test_evidence_that_is_not_current_refuses_only_the_upset(
        self, cold_route, score_source, observed_ago
    ):
        now = datetime.now(timezone.utc)
        game = _live_game(now, score_source=score_source, observed_ago=observed_ago)

        resp = await events_routes.search_suggestions(
            db=_OneLiveQueryDB([game, _tight_game(now)])
        )

        assert _chip(resp, _UPSET_ID) == []
        assert [c["label"] for c in _chip(resp, _TIGHT_ID)] == [
            "Live — tight game vs Pumas"
        ]
