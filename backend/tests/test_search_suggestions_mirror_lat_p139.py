"""LAT-P139 — opening Search stops costing 8-18 seconds once a minute.

WHAT A PERSON WAITS FOR. `frontend/app/search/page.tsx:313` calls
`fetchSearchSuggestions()` on mount and renders "Loading suggestions..." until it
answers. It is the first thing anybody sees after tapping Search, which is
product priority #4 (Instant Answers).

LAT-P124 gave this route a cache that finally wrote, and wrote down what it was
leaving: *"this degrades to slow once a minute, never to wrong."* Measured on
production `b7a7bbd0`, 2026-08-30, `x-timing-split` server time, one read taken
immediately after each idle gap so every one lands on a just-expired slot:

    first touch, cold slot     12,782 ms   (db 12,708, maxq 12,672)
    +2/+4/+6/+8 s, inside TTL      15-24 ms
    after  65 s idle            8,338 ms
    after  70 s idle           13,156 ms
    after  75 s idle           12,103 ms
    after  90 s idle           18,387 ms
    after 120 s idle           17,583 ms

FIVE OUT OF FIVE. That is not a tail, it is the price of arriving one second
after the slot expires, and on a low-traffic site that is most people. `db` is
99 % of every one of those numbers and `maxq` is 99 % of `db` — one statement,
section 3's `ORDER BY abs(probability_change_24h) DESC`, which LAT-P124 measured
at 146,437 shared blocks and an external merge to disk to keep FIVE rows.

WHAT THIS QUEUE CHANGES, AND WHAT IT DOES NOT. It does not make that statement
cheaper — the expression index that would is DDL, is Integrator-owned
(ruling 080), and is still parked as P124-1. It changes WHO PAYS: a 24 h mirror
is served immediately on a primary miss and exactly one rebuild runs behind it,
so the cost moves off the person and onto a background task.

🔴 AND THE REASON THAT WAS NOT ALREADY POSSIBLE IS THE THING MOST OF THIS FILE
DEFENDS. LAT-P124 refused to widen the TTL because `label` baked a countdown —
"Tips off in 12 min" — so an old copy prints a wrong minute count. That
objection was correct. It is dissolved rather than overruled: the deadline
travels with the suggestion and the label is rendered at SERVE time. Every test
under `TestTheCountdownIsNoLongerBaked` and `TestTheMirrorCannotPrintAWrongTime`
exists because if any one of them stops holding, this ship has bought latency
with a formatting lie — the exact trade LAT-P122 and LAT-P123 both refused.

🔴 CLOCK DISCIPLINE (gotcha #44). Every test that needs a time constructs BOTH
ends of the comparison itself and passes `now` in explicitly. Nothing here reads
the wall clock and then asserts on which branch it landed in, and no anchor
contains an `if`.
"""

from __future__ import annotations

import ast
import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import events as events_routes
from app.utils import event_concept_cache as ecc
from app.utils import game_markets_cache as gmc
from app.utils import search_suggestions_cache as ssc

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 8, 30, 4, 0, 0, tzinfo=timezone.utc)


def _item(query, label, **kw):
    return {"query": query, "label": label, "type": "event", **kw}


def _countdown_item(query, deadline):
    return _item(
        query,
        ssc.countdown_label(deadline, T0),
        event_id=1,
        **{ssc.COUNTDOWN_FIELD: deadline.isoformat()},
    )


def _stored(items, created_at=T0):
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(ssc.stamp({"suggestions": items}, created_at=created_at))


class _FakeRedis:
    """Key-addressed, unlike the P124 double — the mirror needs two slots."""

    def __init__(self, slots=None):
        self.slots = dict(slots or {})
        self.get_calls: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []
        self.delete_calls: list[str] = []

    def get(self, key):
        self.get_calls.append(key)
        return self.slots.get(key)

    def setex(self, key, ttl, payload):
        self.setex_calls.append((key, ttl, payload))
        self.slots[key] = payload

    def delete(self, key):
        self.delete_calls.append(key)
        self.slots.pop(key, None)


# ---------------------------------------------------------------------------
# 1. The countdown stops being baked — the half that makes the rest legal
# ---------------------------------------------------------------------------


class TestTheCountdownIsNoLongerBaked:
    async def test_the_minute_branch_prints_what_the_route_used_to_print(self):
        assert ssc.countdown_label(T0 + timedelta(minutes=12), T0) == "Tips off in 12 min"

    async def test_the_hour_branch_prints_what_the_route_used_to_print(self):
        assert ssc.countdown_label(T0 + timedelta(minutes=150), T0) == "Starts in 2h"

    async def test_the_branch_boundary_is_exactly_sixty_minutes(self):
        assert ssc.countdown_label(T0 + timedelta(minutes=59), T0) == "Tips off in 59 min"
        assert ssc.countdown_label(T0 + timedelta(minutes=60), T0) == "Starts in 1h"

    async def test_a_game_that_has_started_has_no_label(self):
        assert ssc.countdown_label(T0 - timedelta(seconds=1), T0) is None

    async def test_the_expiry_test_reads_seconds_and_not_truncated_minutes(self):
        """🔴 `int()` TRUNCATES TOWARD ZERO, SO A MINUTE GUARD IS OFF BY A MINUTE.

        A game that kicked off 59 s ago has `int(-59/60) == 0`, so a `minutes < 0`
        guard calls it "Tips off in 0 min" for a full minute after kickoff. That
        is a wrong clock reading produced by the guard meant to prevent one, and
        it is the single easiest way to reintroduce this ship's defect.
        """
        assert ssc.countdown_label(T0 - timedelta(seconds=59), T0) is None
        assert ssc.countdown_label(T0, T0) == "Tips off in 0 min"

    async def test_the_route_does_not_render_the_countdown_itself(self):
        """The literal must live in ONE place or the two can disagree.

        Before this ship the route formatted the text inline, which is why a
        stored copy could go wrong. If the f-string comes back into the route,
        the renderer and the builder can print different strings for the same
        instant and the mirror stops being safe — silently, because both strings
        are well-formed.

        🔴 AST AND NOT GREP, ON PURPOSE. The route's comments quote the old text
        to explain why it moved, and a substring search over the file cannot tell
        an explanation from a regression. Only string CONSTANTS reachable from
        the build are checked; comments are not in the tree.
        """
        tree = ast.parse(pathlib.Path(events_routes.__file__).read_text())
        build = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "_build_search_suggestions"
        )
        literals = [
            n.value
            for n in ast.walk(build)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        offenders = [
            s for s in literals if "Tips off in" in s or "Starts in " in s
        ]
        assert offenders == [], (
            "the countdown is being formatted in _build_search_suggestions "
            f"again ({offenders!r}); it belongs to "
            "search_suggestions_cache.countdown_label so that the build and the "
            "serve-time render cannot diverge"
        )

    async def test_the_build_and_the_renderer_are_the_same_function(self):
        """AST, not grep: section 2 must CALL `countdown_label`, not re-derive it."""
        tree = ast.parse(pathlib.Path(events_routes.__file__).read_text())
        build = next(
            n
            for n in tree.body
            if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "_build_search_suggestions"
        )
        called = {
            n.func.attr
            for n in ast.walk(build)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert "countdown_label" in called


# ---------------------------------------------------------------------------
# 2. The renderer
# ---------------------------------------------------------------------------


class TestTheRenderer:
    async def test_render_is_a_no_op_on_a_payload_built_this_instant(self):
        """🔴 THE PIN THAT MAKES A BUILD AND A MIRROR OF IT THE SAME ANSWER.

        A fresh build renders with the clock it was built on, so the text must
        come out unchanged. If this ever fails, the served body and the stored
        body have stopped describing the same moment and every downstream claim
        in this file is void.
        """
        payload = _stored([_countdown_item("Aces", T0 + timedelta(minutes=12))])
        assert ssc.render(payload, T0)["suggestions"][0]["label"] == "Tips off in 12 min"

    async def test_render_moves_the_minute_count_with_the_serving_clock(self):
        payload = _stored([_countdown_item("Aces", T0 + timedelta(minutes=12))])
        later = ssc.render(payload, T0 + timedelta(minutes=5))
        assert later["suggestions"][0]["label"] == "Tips off in 7 min"

    async def test_render_drops_a_suggestion_whose_game_has_started(self):
        payload = _stored([_countdown_item("Aces", T0 + timedelta(minutes=2))])
        assert ssc.render(payload, T0 + timedelta(minutes=3))["suggestions"] == []

    async def test_render_passes_through_a_suggestion_with_no_deadline(self):
        """Sections 3 and 4 — "Surging +4.1%" and "Pulled the upset vs X" — carry
        no clock-relative text and must be returned byte-identical."""
        item = _item("Barcelona", "Surging +4.1% — Rodri: Next Club")
        payload = _stored([item])
        out = ssc.render(payload, T0 + timedelta(hours=3))
        assert out["suggestions"] == [item]

    async def test_render_strips_the_deadline_from_the_wire(self):
        payload = _stored([_countdown_item("Aces", T0 + timedelta(minutes=12))])
        assert ssc.COUNTDOWN_FIELD not in ssc.render(payload, T0)["suggestions"][0]

    async def test_render_does_not_mutate_the_stored_artifact(self):
        """🔴 THE STORED COPY MUST KEEP ITS DEADLINES OR THE MIRROR GOES BLIND.

        `_publish_search_suggestions` renders the same dict it hands to `write`.
        If `render` mutated in place, the payload reaching Redis would have had
        its deadlines stripped and the second reader would get un-renderable
        chips — which `renders_to_something` would then refuse, turning the
        mirror into a permanent miss and this whole ship into a no-op.
        """
        payload = _stored([_countdown_item("Aces", T0 + timedelta(minutes=12))])
        ssc.render(payload, T0 + timedelta(minutes=90))
        assert ssc.COUNTDOWN_FIELD in payload["suggestions"][0]

    async def test_an_unparseable_deadline_is_dropped_not_served(self):
        payload = _stored([_item("Aces", "Tips off in 9 min", countdown_from="soon")])
        assert ssc.render(payload, T0)["suggestions"] == []

    async def test_a_stored_empty_answer_renders_as_a_real_empty_answer(self):
        assert ssc.renders_to_something(_stored([]), T0) is True

    async def test_a_payload_whose_every_chip_expired_is_not_something(self):
        payload = _stored([_countdown_item("Aces", T0 + timedelta(minutes=2))])
        assert ssc.renders_to_something(payload, T0 + timedelta(minutes=9)) is False

    async def test_one_surviving_chip_is_enough(self):
        payload = _stored(
            [
                _countdown_item("Aces", T0 + timedelta(minutes=2)),
                _item("Barcelona", "Surging +4.1% — Rodri: Next Club"),
            ]
        )
        assert ssc.renders_to_something(payload, T0 + timedelta(minutes=9)) is True


# ---------------------------------------------------------------------------
# 3. The mirror cannot print a wrong time
# ---------------------------------------------------------------------------


class TestTheMirrorCannotPrintAWrongTime:
    async def test_the_ceiling_is_five_times_the_fresh_ttl(self):
        assert ssc.stale_serve_ceiling_seconds() == 5 * ssc.FRESH_TTL == 300

    async def test_the_multiplier_is_inherited_and_not_invented(self):
        """🔴 THREE TIERS, ONE STALENESS LAW.

        `routes/events.py:_STALE_SERVE_CEILING` and
        `game_markets_cache.STALE_SERVE_CEILING` are both 5. This surface does
        not get a fourth opinion about how stale a served copy may be; if the
        site ever re-tunes that multiplier, this test is what makes the
        disagreement visible instead of silent.
        """
        assert ssc.STALE_SERVE_CEILING == gmc.STALE_SERVE_CEILING
        assert ssc.STALE_SERVE_CEILING == events_routes._STALE_SERVE_CEILING

    async def test_a_fresh_enough_mirror_is_servable(self):
        payload = _stored([_countdown_item("Aces", T0 + timedelta(hours=2))])
        assert ssc.mirror_is_servable(payload, T0 + timedelta(seconds=299)) == (
            True,
            "fresh_enough",
        )

    async def test_a_mirror_past_the_ceiling_is_refused(self):
        payload = _stored([_countdown_item("Aces", T0 + timedelta(hours=2))])
        assert ssc.mirror_is_servable(payload, T0 + timedelta(seconds=301)) == (
            False,
            "too_old",
        )

    async def test_a_mirror_that_cannot_date_itself_is_refused(self):
        payload = {"suggestions": [], ecc.ENVELOPE_FIELD: {"created_at": None}}
        assert ssc.mirror_is_servable(payload, T0)[1] == "no_created_at"

    async def test_a_mirror_whose_chips_all_expired_is_refused(self):
        """Young enough, and still not servable — a blank zero-state that no
        build produced is worse than the wait this ship removes."""
        payload = _stored([_countdown_item("Aces", T0 + timedelta(seconds=30))])
        assert ssc.mirror_is_servable(payload, T0 + timedelta(seconds=100)) == (
            False,
            "empty_after_render",
        )

    async def test_absent_is_not_servable(self):
        assert ssc.mirror_is_servable(None, T0) == (False, "absent")


# ---------------------------------------------------------------------------
# 4. Keys, read and write
# ---------------------------------------------------------------------------


class TestTheSlots:
    async def test_the_primary_keeps_the_production_key_name(self):
        """🔴 NOT A COSMETIC CHOICE. The prefix and the slot were picked so the
        primary reproduces the key that is live today. A different name would
        orphan every warm entry at deploy and put the whole fleet on the 13 s
        build at once."""
        assert ssc.keys().primary == "bainluck:search_suggestions:v1"
        assert ssc.keys().stale == "bainluck:search_suggestions:v1:stale"

    async def test_a_pre_envelope_payload_reads_as_a_miss(self):
        """The shape LAT-P124's writer produced. It must be rebuilt, never
        served as though it carried an envelope it does not have."""
        rc = _FakeRedis(
            {"bainluck:search_suggestions:v1": json.dumps({"suggestions": [_item("A", "B")]})}
        )
        assert ssc.read(rc=rc, now=T0) == (None, "miss")

    async def test_a_live_primary_is_served_rendered_and_marked_live(self):
        rc = _FakeRedis(
            {
                "bainluck:search_suggestions:v1": json.dumps(
                    _stored([_countdown_item("Aces", T0 + timedelta(minutes=12))])
                )
            }
        )
        body, state = ssc.read(rc=rc, now=T0 + timedelta(minutes=5))
        assert state == "live"
        assert body["suggestions"][0]["label"] == "Tips off in 7 min"
        assert body[ecc.ENVELOPE_FIELD]["availability"] == ecc.AVAILABILITY_LIVE

    async def test_a_mirror_only_slot_is_served_rendered_and_marked_stale(self):
        rc = _FakeRedis(
            {
                "bainluck:search_suggestions:v1:stale": json.dumps(
                    _stored([_countdown_item("Aces", T0 + timedelta(minutes=12))])
                )
            }
        )
        body, state = ssc.read(rc=rc, now=T0 + timedelta(seconds=120))
        assert state == "stale_ok"
        assert body["suggestions"][0]["label"] == "Tips off in 10 min"
        assert body[ecc.ENVELOPE_FIELD]["availability"] == ecc.AVAILABILITY_STALE_OK

    async def test_a_too_old_mirror_reports_its_own_refusal(self):
        rc = _FakeRedis(
            {
                "bainluck:search_suggestions:v1:stale": json.dumps(
                    _stored([_countdown_item("Aces", T0 + timedelta(hours=4))])
                )
            }
        )
        assert ssc.read(rc=rc, now=T0 + timedelta(seconds=400)) == (
            None,
            "stale_too_old",
        )

    async def test_write_stores_the_deadlines_and_not_the_rendered_text(self):
        """🔴 IF THE STORED COPY IS THE RENDERED ONE, THE MIRROR IS A LIE AGAIN.

        This is the single assertion standing between this ship and the defect
        LAT-P124 declined to create: a mirror holding a baked minute count.
        """
        rc = _FakeRedis()
        payload = _stored([_countdown_item("Aces", T0 + timedelta(minutes=12))])
        assert ssc.write(payload, rc=rc) is True
        for key, _ttl, blob in rc.setex_calls:
            assert ssc.COUNTDOWN_FIELD in json.loads(blob)["suggestions"][0], key

    async def test_write_uses_the_fresh_ttl_for_the_primary_and_a_day_for_the_mirror(self):
        rc = _FakeRedis()
        ssc.write(_stored([]), rc=rc)
        assert [(k.endswith(":stale"), t) for k, t, _ in rc.setex_calls] == [
            (False, 60),
            (True, 86400),
        ]

    async def test_a_redis_that_raises_is_a_miss_and_never_an_exception(self):
        """A cache outage must cost a rebuild, not a 500 on the Search page.

        `rc=None` is NOT the way to express this: `read` and `write` fall back to
        `get_client()` when handed None, so a None here tests the ambient
        environment rather than the tier. A client that raises is the real shape
        of a Redis outage.
        """

        class _Down(_FakeRedis):
            def get(self, key):
                raise RuntimeError("redis down")

            def setex(self, key, ttl, payload):
                raise RuntimeError("redis down")

        rc = _Down()
        assert ssc.read(rc=rc, now=T0) == (None, "miss")
        assert ssc.write(_stored([]), rc=rc) is True, (
            "the write was ATTEMPTED — `write_payload` swallows the failure, so "
            "True here means 'there was a client and we handed it the bytes', "
            "which is the only thing this return value is allowed to claim"
        )


# ---------------------------------------------------------------------------
# 5. The route's serve decision
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, results):
        self._results = list(results)
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self._results:
            raise AssertionError("the route queried the database more than expected")
        return self._results.pop(0)


def _soon(n):
    from datetime import datetime as _dt

    base = _dt.now(timezone.utc) + timedelta(minutes=30)
    names = ["Aces", "Sky", "Storm", "Sun", "Fever", "Sparks", "Wolves", "Devils"]
    return [
        SimpleNamespace(
            id=i + 1, home_team_name=names[i], away_team_name="Opponents", commence_time=base
        )
        for i in range(n)
    ]


def _full_db():
    return _DB([_Rows([]), _Rows(_soon(8))])


@pytest.fixture
def redis_double(monkeypatch):
    import app.tasks.redis_state as redis_state

    def install(client):
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: client)
        return client

    return install


class TestTheRoutesServeDecision:
    async def test_a_mirror_only_slot_serves_without_touching_the_database(
        self, redis_double, monkeypatch
    ):
        """🔴 THE SHIP, IN ONE ASSERTION. Before this queue the reader whose slot
        had just expired ran the whole build; now the mirror answers and one
        rebuild goes behind it."""
        rc = redis_double(
            _FakeRedis(
                {
                    "bainluck:search_suggestions:v1:stale": json.dumps(
                        _stored(
                            [_item("Barcelona", "Surging +4.1% — Rodri: Next Club")],
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                }
            )
        )
        scheduled = []
        monkeypatch.setattr(
            events_routes,
            "_serve_stale_and_refresh",
            lambda name, rebuild: scheduled.append(name) or True,
        )
        db = _DB([])

        resp = await events_routes.search_suggestions(db=db)

        assert db.executed == [], "a mirror serve must not query the database"
        assert resp["suggestions"][0]["query"] == "Barcelona"
        assert resp[ecc.ENVELOPE_FIELD]["availability"] == ecc.AVAILABILITY_STALE_OK
        assert scheduled == ["search_suggestions"], "exactly one rebuild, named once"
        assert rc.setex_calls == [], "a serve must not republish what it served"

    async def test_no_running_loop_means_build_rather_than_serve_stale_forever(
        self, redis_double, monkeypatch
    ):
        """`_serve_stale_and_refresh` returns False when nothing can run behind
        the caller. Serving stale then would be serving stale with no rebuild
        coming — the fail-closed half."""
        redis_double(
            _FakeRedis(
                {
                    "bainluck:search_suggestions:v1:stale": json.dumps(
                        _stored(
                            [_item("Barcelona", "Surging +4.1%")],
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                }
            )
        )
        monkeypatch.setattr(
            events_routes, "_serve_stale_and_refresh", lambda name, rebuild: False
        )
        db = _full_db()

        resp = await events_routes.search_suggestions(db=db)

        assert db.executed, "the route must have built"
        assert len(resp["suggestions"]) == events_routes._MAX_SUGGESTIONS

    async def test_a_too_old_mirror_makes_the_reader_build(self, redis_double):
        redis_double(
            _FakeRedis(
                {
                    "bainluck:search_suggestions:v1:stale": json.dumps(
                        _stored(
                            [_item("Barcelona", "Surging +4.1%")],
                            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
                        )
                    )
                }
            )
        )
        db = _full_db()
        resp = await events_routes.search_suggestions(db=db)
        assert db.executed, "past the ceiling the reader blocks and rebuilds"
        assert len(resp["suggestions"]) == events_routes._MAX_SUGGESTIONS

    async def test_the_tier_has_exactly_one_writer(self):
        """🔴 LAT-P001's DEFECT, PINNED. A build reached through the request path
        and one reached through the stale-refresh path must publish through the
        same function, or the two paths drift into two payloads."""
        tree = ast.parse(pathlib.Path(events_routes.__file__).read_text())
        writers = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_publish_search_suggestions"
        ]
        assert len(writers) == 2, (
            "expected exactly two call sites — the route and the rebuild — and "
            f"found {len(writers)}"
        )
        callers = {
            fn.name
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "_publish_search_suggestions"
                for n in ast.walk(fn)
            )
        }
        assert callers == {"search_suggestions", "_rebuild_search_suggestions"}

    async def test_the_rebuild_opens_its_own_session(self):
        """The request's `AsyncSession` is not ours to hold past the response —
        `_serve_stale_and_refresh`'s contract, and how a background task ends up
        writing into a closed session."""
        tree = ast.parse(pathlib.Path(events_routes.__file__).read_text())
        rebuild = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "_rebuild_search_suggestions"
        )
        assert rebuild.args.args == [], "the rebuild must be zero-arg"
        assert "async_session_maker" in ast.dump(rebuild)
