"""The games-led first page stops spending a fifth of itself on futures (#4497).

The corpus arm is the load-bearing one. `sports_first_page_futures_4497.json` is
the pool production actually served at 2026-09-09 23:34Z — four futures in the
first twenty slots, three of them in the top ten — and the replay asserts the
whole first-page composition, not a spot check. Synthetic cases below cover the
refusals the corpus happens not to exercise.
"""

from __future__ import annotations

import ast
import inspect
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.routes.feed import PersonalizationContext, apply_discover_display_chain
from app.utils.sports_first_page_rails import (
    FINISHED_RAIL_FIRST_PAGE_CAP,
    FUTURES_FIRST_PAGE_CAP,
    cap_futures_on_games_led_first_page,
)

CORPUS = Path(__file__).parent / "fixtures" / "sports_first_page_futures_4497.json"
NOW = datetime(2026, 9, 9, 23, 34, 13, tzinfo=timezone.utc)

#: The three real call shapes, copied from `test_sports_first_page_rails_wiring_3511`
#: so the two wiring suites cannot drift into describing different surfaces.
SPORTS = {
    "event_pct": 0.6,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": True,
}
DISCOVER = {
    "event_pct": 0.15,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": False,
}
#: `mode` and `my_teams_only` are independent query parameters, so
#: `?mode=sports&my_teams_only=true` is a request a client can actually send —
#: and it is a My Stuff request.
MY_STUFF_VIA_SPORTS_MODE = {
    "event_pct": 0.6,
    "include_events": True,
    "my_teams_only": True,
    "sports_mode": True,
}


def _corpus() -> list[dict]:
    return json.loads(CORPUS.read_text())["items"]


def _types(items, n=20) -> Counter:
    return Counter(it.get("type") for it in items[:n])


def _futures(commence=None, score=90):
    return {"type": "futures", "score": score, "headline": "X leads at 40%",
            "data": {"status": "open", "commence_time": commence}}


def _game(status="scheduled", score=90, headline="Close matchup", hours_ago=None):
    commence = (
        (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
        if hours_ago is not None
        else (NOW + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    )
    return {"type": "event", "score": score, "headline": headline,
            "data": {"status": status, "commence_time": commence}}


def _concept(score=90):
    return {"type": "concept", "score": score, "headline": "Live",
            "data": {"status": "live", "commence_time": None}}


class TestTheProductionCorpus:
    """The measured payload, replayed. This is the issue's own evidence."""

    def test_the_served_page_is_over_cap_BEFORE_the_pass(self):
        """The red arm. If this ever goes green on its own the corpus is stale,
        not the defect fixed."""
        served = _corpus()
        assert _types(served)["futures"] == 4, _types(served)
        assert sum(1 for it in served[:10] if it["type"] == "futures") == 3

    def test_the_pass_brings_the_first_page_to_cap_and_buys_games(self):
        out, meta = cap_futures_on_games_led_first_page(
            _corpus(), first_page_size=20, now=NOW
        )
        assert meta == {
            "over_cap_before": 2,
            "replacements_available": 2,
            "swapped": 2,
            "over_cap_after": 0,
            "unswapped": 0,
            "cap": 2,
        }
        # The whole point: two futures slots became two GAME slots.
        assert _types(out)["futures"] == 2
        assert _types(out)["event"] == 17, "15 games before; two futures traded in"
        assert _types(out)["concept"] == 1, "a concept is not a game and not a trade"

    def test_the_top_ten_loses_a_futures_card(self):
        """Fable's bar is stated over the top ten, so it is asserted there too
        and not only over the twenty-slot budget the swap actually reasons on."""
        out, _ = cap_futures_on_games_led_first_page(
            _corpus(), first_page_size=20, now=NOW
        )
        assert sum(1 for it in out[:10] if it["type"] == "futures") == 2

    def test_nothing_is_dropped_duplicated_or_rescored(self):
        served = _corpus()
        out, _ = cap_futures_on_games_led_first_page(
            served, first_page_size=20, now=NOW
        )
        assert len(out) == len(served)
        assert sorted(map(id, out)) == sorted(map(id, served))
        assert [it["score"] for it in sorted(out, key=id)] == [
            it["score"] for it in sorted(served, key=id)
        ]


class TestTheRefusals:
    def test_a_futures_card_is_never_admitted_as_a_replacement(self):
        """Otherwise the pass shuffles futures inside the budget and reports a
        swap the reader cannot see."""
        items = [_futures(score=s) for s in (99, 98, 97, 96)] + [_futures(score=50)] * 5
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=4, now=NOW
        )
        assert meta["swapped"] == 0
        assert meta["unswapped"] == 2
        assert out == items

    def test_a_concept_card_is_never_admitted_as_a_replacement(self):
        """A concept satisfies 'not futures' and is still not a game. The looser
        test shipped a page with the same game count as it started with."""
        items = [_futures(score=s) for s in (99, 98, 97)] + [_concept(score=95)]
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=3, now=NOW
        )
        assert meta["swapped"] == 0
        assert out == items

    def test_a_card_the_client_deletes_is_never_admitted(self):
        """#3836's rule. Trading a futures slot for a card the browser removes
        before paint spends the slot twice."""
        stale = _game(status="completed", hours_ago=20, headline="Old result")
        fresh = _game(status="live", headline="Upset brewing")
        items = [_futures(score=s) for s in (99, 98, 97)] + [stale, fresh]
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=3, now=NOW
        )
        assert meta["swapped"] == 1
        assert out[2] is fresh, "the stale card was skipped, the live one admitted"
        assert stale in out[3:]

    def test_a_replacement_never_recreates_a_capped_finished_rail(self):
        """#3511/#3805. The sibling cap has just bounded 'Recent upset' at three;
        this pass must not walk one back in."""
        window = [_game(status="completed", headline="Recent upset")
                  for _ in range(FINISHED_RAIL_FIRST_PAGE_CAP)]
        window += [_futures(score=s) for s in (99, 98, 97)]
        another_upset = _game(status="completed", headline="Recent upset", score=95)
        clean = _game(status="live", headline="Overtime", score=80)
        items = window + [another_upset, clean]
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=len(window), now=NOW
        )
        assert meta["swapped"] == 1
        assert out[len(window) - 1] is clean
        assert another_upset in out[len(window):]

    def test_a_thin_tail_keeps_the_page_and_says_so(self):
        """gotcha #53: 'we could not' must not read like 'there was nothing to
        do'."""
        items = [_futures(score=s) for s in (99, 98, 97, 96)]
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=4, now=NOW
        )
        assert out == items
        assert meta["over_cap_before"] == 2
        assert meta["unswapped"] == 2
        assert meta["swapped"] == 0

    def test_under_cap_is_a_no_op_that_reports_zero_not_none(self):
        items = [_futures(score=99), _game(), _futures(score=98), _game()]
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=4, now=NOW
        )
        assert out is items
        assert meta["over_cap_before"] == 0
        assert meta["swapped"] == 0

    def test_a_game_is_never_moved_off_the_first_page(self):
        """Only futures leave the window. #1091 is the standing lesson."""
        games = [_game(score=90 - i) for i in range(18)]
        items = games[:9] + [_futures(score=s) for s in (99, 98, 97)] + games[9:]
        out, _ = cap_futures_on_games_led_first_page(
            items, first_page_size=12, now=NOW
        )
        for g in games[:9]:
            assert g in out[:12], "a game was traded away"
        assert _types(out, 12)["event"] == 10

    def test_an_exploding_item_returns_the_page_unchanged(self):
        class Boom(dict):
            def get(self, *_a, **_k):
                raise RuntimeError("boom")

        items = [Boom(), _futures(), _futures(), _futures()]
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=4, now=NOW
        )
        assert out is items
        assert meta["swapped"] == 0


class TestReplacementsKeepDescendingRank:
    """CERT-2190's inversion, guarded on a third pass. Pairing the weakest
    surplus slot with the best replacement makes the swapped-in cards read
    75, 78, 80 going DOWN the page."""

    def test_the_earliest_surplus_slot_takes_the_best_replacement(self):
        items = [_futures(score=99), _futures(score=98)]
        items += [_futures(score=97), _futures(score=96), _futures(score=95)]
        best, mid, worst = _game(score=80), _game(score=78), _game(score=75)
        items += [best, mid, worst]
        out, meta = cap_futures_on_games_led_first_page(
            items, first_page_size=5, now=NOW
        )
        assert meta["swapped"] == 3
        assert [out[2], out[3], out[4]] == [best, mid, worst]
        assert [it["score"] for it in out[2:5]] == [80, 78, 75]


class TestWiring:
    def test_the_gate_reads_the_explicit_signal_not_the_discover_negation(self):
        """CERT-2190: `not discover_mode` is TRUE for My Stuff, whose contract is
        to skip this work entirely. A source assertion, because the two gates are
        behaviourally identical on every surface except that one."""
        src = inspect.getsource(apply_discover_display_chain)
        call = src.index("cap_futures_on_games_led_first_page(")
        gate = src.rindex("if ", 0, call)
        gate_line = src[gate : src.index("\n", gate)]
        assert "sports_mode" in gate_line, gate_line
        assert "not my_teams_only" in gate_line, gate_line
        assert "discover_mode" not in gate_line, gate_line

    def test_the_futures_cap_runs_BEFORE_the_live_hoist(self):
        """Order is the contract and a comment claiming it is not a control.

        Parsed rather than grepped: the docstrings of both passes name each
        other, so a substring search over the source is satisfied by prose.
        """
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        watched = (
            "cap_futures_on_games_led_first_page",
            "hoist_live_events_into_first_page",
        )
        calls = [
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in watched
        ]
        assert calls == list(watched), f"call order changed: {calls}"

    def test_the_pass_is_actually_called_and_its_result_is_kept(self):
        """The inert-ship guard. Deleting the one call site, or dropping the
        assignment back onto `items`, leaves every pure-function test above
        green."""
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        bound = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "cap_futures_on_games_led_first_page"
        ]
        assert len(bound) == 1, "expected exactly one call site"
        targets = bound[0].targets[0]
        assert isinstance(targets, ast.Tuple)
        assert [t.id for t in targets.elts] == ["items", "futures_cap_meta"], (
            "the pass must write back to `items` or it ships inert"
        )


class TestTheOtherSurfacesAreUnchanged:
    @staticmethod
    def _pool():
        return [_futures(score=99 - i) for i in range(5)] + [
            _game(score=80 - i) for i in range(20)
        ]

    def test_CONTROL_discover_never_invokes_the_pass(self):
        _out, meta = apply_discover_display_chain(
            self._pool(), limit=20, ctx=PersonalizationContext(), **DISCOVER
        )
        assert meta["futures_first_page_cap"] is None, (
            "None means the pass never ran; 0 would mean it ran and did nothing"
        )

    def test_CONTROL_my_stuff_via_sports_mode_never_invokes_the_pass(self):
        _out, meta = apply_discover_display_chain(
            self._pool(),
            limit=20,
            ctx=PersonalizationContext(),
            **MY_STUFF_VIA_SPORTS_MODE,
        )
        assert meta["futures_first_page_cap"] is None

    def test_sports_mode_does_invoke_the_pass(self):
        _out, meta = apply_discover_display_chain(
            self._pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert meta["futures_first_page_cap"] is not None
        assert meta["futures_first_page_cap"]["cap"] == FUTURES_FIRST_PAGE_CAP


class TestTheConstant:
    def test_the_cap_is_two_and_is_not_borrowed_authority(self):
        """`FINISHED_RAIL_FIRST_PAGE_CAP` descends from the Discover archetype
        caps. This one does not descend from anything, and the docstring says so
        — this test pins the value so a change is a deliberate edit."""
        assert FUTURES_FIRST_PAGE_CAP == 2
