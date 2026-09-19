"""The golf card may say "today" only about a move the day actually made (#7179).

Sub-issue of #4079. This is the FOURTH claim-producing path; A8 repaired the other
three and structurally could not reach this one.

    pos  5 — PGA Tour: Neal Shipley leads at 28.3% (up 25.4 points today)
    pos 41 — Korn Ferry Tour: Phichaksn Maichon leads at 18.8% (up 8 points today)

served on production ``/api/feed?limit=100``, 2026-09-19.

═══ WHAT THE MEASUREMENT SAID, WHICH IS NOT WHAT THE ISSUE ASSUMED ═══

#7179 reads the fallback comment in ``_aggregate_golfer_outcome`` and concludes both
specimens print a per-write delta. **Both were measured and both are genuinely
dated.** Shipley's basis is a real ``FuturesOddsSnapshot`` 23h00m old — 0.0321 ->
0.2832, a true +25.1 points — and Maichon's ``probability_change_24h`` is NULL, so
the fallback arm could not have run for him at all.

The population agrees. Over all 4,319 open golf outcomes on production
(``external_id ILIKE 'golf_%' OR llm_sport_category = 'golf'``):

    DATED (snapshot 23-25h old)    2,766
    no movement at all             1,553
    per-write fallback                 0

So the defect is LATENT, and this ship's honest prediction is that **it changes zero
served chips today**. It is not dead, which is why it is worth closing: 66 Kalshi
golf outcomes carry a meaningful ``probability_change_24h``, and each takes the
fallback the moment its snapshot lapses — a market younger than 23h has no in-window
snapshot and can already have a per-write delta. The fallback is one missing
snapshot away, on a path with no natural specimen, which is precisely the class that
gets manufactured rather than waited for.

═══ THE REPAIR IS PROVENANCE, NOT A SECOND BANK ═══

A8 keys a banked basis on ``outcome_id`` and a ``golfers[]`` entry has none — it is
an AVERAGE across several markets' outcomes. But golf needs no bank: the aggregation
ALREADY subtracts a 23-25h snapshot, a TIGHTER dated window than A8's own 12-24h. It
only falls back when no snapshot is in range. Two measurements, one field name, and
the card spending whichever it got on the word "today".

So ``movement_is_dated`` records which arm produced the number, and the card asks
before it speaks. Nothing about the VALUE changes anywhere.

═══ THE CONTROL IS THE POINT ═══

``TestTheFixNarrowsTheSentenceAndNothingElse`` is not decoration. The whole risk of
this change is that silencing a sentence quietly becomes a ranking policy — the same
trap A8 named when it refused to let its bank promote an outcome the highlight did
not pick. An undated mover must still score identically and still read "Live". Those
assertions pass before this ship and after it; that is what makes them a control.

The harness drives the REAL ``_score_golf_tournaments`` over a stubbed golf base,
copied from ``test_golf_movement_is_points_not_percent_d1.py`` — whose own docstring
records that rebuilding the f-string under test is the vacuity trap for this exact
line.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.golf import (
    _aggregate_golfer_outcome,
    _build_tournament_entry,
    _merge_abbreviated_golfers,
)


#: Gotcha #44 — offset from the clock, never a literal date.
_FEED_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)

#: The production specimen, with its real measured numbers (see the docstring).
_SHIPLEY_BASIS = 0.032050
_SHIPLEY_NOW = 0.283153
_SHIPLEY_MOVE = round(_SHIPLEY_NOW - _SHIPLEY_BASIS, 4)

#: A sentinel that is unmistakably NOT the leader's own price, so an assertion
#: about the movement clause can never be satisfied by the "leads at X%" half.
_UNDATED_MOVE = 0.254


class _Outcome:
    """The attributes `_aggregate_golfer_outcome` actually reads."""

    def __init__(
        self,
        id: int,
        name: str,
        current_probability: float,
        probability_change_24h: float | None = None,
        opening_probability: float | None = None,
    ):
        self.id = id
        self.name = name
        self.current_probability = current_probability
        self.probability_change_24h = probability_change_24h
        self.opening_probability = opening_probability


def _tournament(golfer: dict) -> dict:
    """One golf-base entry, shaped as `get_golf_base` publishes it."""
    return {
        "key": "biltmore",
        "name": "Biltmore Championship Asheville",
        "slug": "biltmore-championship-asheville",
        "tour": "pga",
        "tour_label": "PGA Tour",
        "is_major": False,
        "is_tour_event": True,
        "commence_time": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "resolution_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "start_date": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "end_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "market_names": ["Biltmore Championship Asheville - Winner"],
        "market_ids": [1],
        "golfers": [golfer],
    }


def _golfer(movement: float, *, dated: bool | None, probability: float = 0.283) -> dict:
    """A published golfer. `dated=None` OMITS the key — a pre-#7179 base."""
    entry = {
        "id": 1,
        "name": "Neal Shipley",
        "probability": probability,
        "movement_24h": movement,
        "american_odds": None,
        "is_winner": None,
        "rank": 1,
    }
    if dated is not None:
        entry["movement_is_dated"] = dated
    return entry


def _card(monkeypatch, golfer: dict) -> dict:
    """The feed item the REAL scorer serves for that tournament."""
    import app.utils.golf_base as golf_base
    from app.routes import feed as feed_module

    async def _fake_base(db, now, stages=None):
        return ([_tournament(golfer)], "fresh")

    monkeypatch.setattr(golf_base, "get_golf_base", _fake_base)
    items = asyncio.run(feed_module._score_golf_tournaments(None, _FEED_NOW, None, None))
    assert len(items) == 1, f"card dropped, so the sentence is untested: {items}"
    return items[0]


def _reason(monkeypatch, golfer: dict) -> str:
    return _card(monkeypatch, golfer)["reason"]


# --- 1. The reported defect ----------------------------------------------


class TestAnUndatedMoveIsNotCalledToday:
    """The acceptance: state the dated move, or state no movement clause at all."""

    def test_a_per_write_delta_produces_no_movement_clause(self, monkeypatch):
        reason = _reason(monkeypatch, _golfer(_UNDATED_MOVE, dated=False))
        assert reason == "PGA Tour: Neal Shipley leads at 28.3%"

    def test_the_word_today_does_not_appear(self, monkeypatch):
        """Asserted on the word itself, because "today" IS the false claim.

        The equality above would also pass if the clause were merely reworded;
        this fails unless the temporal claim is gone.
        """
        reason = _reason(monkeypatch, _golfer(_UNDATED_MOVE, dated=False))
        assert "today" not in reason.lower(), reason

    @pytest.mark.parametrize("movement", [0.254, -0.254, 0.02, -0.5, 0.011])
    def test_no_undated_magnitude_reaches_the_reader(self, monkeypatch, movement):
        """Every size of undated move is silenced, not just the big ones."""
        reason = _reason(monkeypatch, _golfer(movement, dated=False))
        assert "point" not in reason, reason

    def test_the_price_survives_the_silencing(self, monkeypatch):
        """"or states no movement clause at all" — the card's price is preserved.

        Silencing the clause by dropping the whole card, or by blanking the
        leader's number, would satisfy a naive "no wrong claim" test and lose the
        reader the thing they came for.
        """
        reason = _reason(monkeypatch, _golfer(_UNDATED_MOVE, dated=False))
        assert "Neal Shipley" in reason
        assert "28.3%" in reason


# --- 2. A dated move is preserved exactly --------------------------------


class TestADatedMoveStillSpeaks:
    """"Genuinely dated moves ... are preserved" — the other half of acceptance.

    A fix that silenced everything would pass section 1 completely.
    """

    def test_the_production_specimen_still_states_its_move(self, monkeypatch):
        reason = _reason(monkeypatch, _golfer(_SHIPLEY_MOVE, dated=True))
        assert reason == "PGA Tour: Neal Shipley leads at 28.3% (up 25.1 points today)"

    @pytest.mark.parametrize("movement", [0.1, 0.015, -0.225, 0.078, 0.01])
    def test_the_dated_magnitude_is_untouched(self, monkeypatch, movement):
        """This ship changes WHETHER a number may be said, never WHICH number."""
        reason = _reason(monkeypatch, _golfer(movement, dated=True))
        expected = round(abs(movement) * 100, 1)
        if expected == int(expected):
            expected = int(expected)
        assert f"{expected} point" in reason, reason

    def test_direction_survives(self, monkeypatch):
        assert "(down 7.5 points today)" in _reason(monkeypatch, _golfer(-0.075, dated=True))
        assert "(up 7.5 points today)" in _reason(monkeypatch, _golfer(0.075, dated=True))

    def test_the_sub_threshold_floor_still_applies_to_dated_moves(self, monkeypatch):
        """Unchanged by this ship: dated does not mean loud."""
        reason = _reason(monkeypatch, _golfer(0.004, dated=True))
        assert reason == "PGA Tour: Neal Shipley leads at 28.3%"


# --- 3. The release transition -------------------------------------------


class TestAPreShipBaseFailsClosed:
    """A base published by the PREVIOUS release carries no such key.

    `get_golf_base` serves a last-good payload for up to 2h, so these entries are
    live across the deploy. An old payload cannot be asked what it measured, so
    the honest answer is to say nothing until the hourly precompute republishes.
    This is the same property that makes a STOPPED snapshot sweep silence these
    captions by itself rather than let them drift into fiction.
    """

    def test_an_absent_flag_is_a_refusal_not_a_yes(self, monkeypatch):
        reason = _reason(monkeypatch, _golfer(_UNDATED_MOVE, dated=None))
        assert "today" not in reason.lower(), reason
        assert reason == "PGA Tour: Neal Shipley leads at 28.3%"

    def test_absent_and_false_are_the_same_refusal(self, monkeypatch):
        """Every refusal is the same refusal — no third rendering to maintain."""
        assert _reason(monkeypatch, _golfer(_UNDATED_MOVE, dated=None)) == _reason(
            monkeypatch, _golfer(_UNDATED_MOVE, dated=False)
        )


# --- 4. The control: nothing but the sentence moved ----------------------


class TestTheFixNarrowsTheSentenceAndNothingElse:
    """Silencing a claim must not become a ranking policy (the A8 rule).

    These pass BEFORE this ship and after. That is the point: they pin the blast
    radius, and they are the assertions that fail if someone later "tidies up" by
    filtering undated movers out of the pool.
    """

    def test_an_undated_mover_scores_exactly_as_a_dated_one(self, monkeypatch):
        undated = _card(monkeypatch, _golfer(_UNDATED_MOVE, dated=False))
        dated = _card(monkeypatch, _golfer(_UNDATED_MOVE, dated=True))
        assert undated["score"] == dated["score"], (
            "the movement provenance changed the card's SCORE — this ship is only "
            "allowed to change what the card SAYS"
        )

    def test_an_undated_mover_is_still_live(self, monkeypatch):
        """`_tournament_is_live` reads `movement_24h` and must keep reading it."""
        undated = _card(monkeypatch, _golfer(_UNDATED_MOVE, dated=False))
        assert undated["headline"] == "Live"

    def test_the_card_is_still_served(self, monkeypatch):
        """The refusal removes a clause, never the card (`_card` asserts len == 1)."""
        assert _card(monkeypatch, _golfer(_UNDATED_MOVE, dated=False))["type"] == "tournament"


# --- 5. The producer sets the flag from the arm that ran -----------------


class TestTheAggregationRecordsWhichArmRan:
    """Gating on a flag is worthless if the flag is not measured at the source."""

    def test_the_snapshot_arm_is_dated(self):
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(229405109, "Neal Shipley", _SHIPLEY_NOW),
            "datagolf_model",
            data,
            {229405109: _SHIPLEY_BASIS},
        )
        entry = data["neal shipley"]
        assert entry["movement_is_dated"] is True
        assert entry["movement_24h"] == pytest.approx(_SHIPLEY_MOVE, abs=1e-4)

    def test_the_per_write_fallback_is_not_dated(self):
        """No snapshot in range, but a stored delta — the 66-outcome exposure."""
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(228977771, "Neal Shipley", 0.285, probability_change_24h=0.254),
            "kalshi",
            data,
            {},
        )
        entry = data["neal shipley"]
        assert entry["movement_24h"] == pytest.approx(0.254)
        assert entry["movement_is_dated"] is False

    def test_no_movement_at_all_is_not_dated(self):
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(_Outcome(1, "Neal Shipley", 0.285), "kalshi", data, {})
        entry = data["neal shipley"]
        assert entry["movement_24h"] is None
        assert entry["movement_is_dated"] is False

    def test_a_dated_arm_that_loses_the_max_abs_race_does_not_claim_the_flag(self):
        """Two sources, and the flag must describe the value that WON.

        The aggregation keeps the largest absolute move across sources. A flag
        that recorded "some source was dated" rather than "THIS number is dated"
        would relabel an undated winner as dated — the defect, wearing the fix's
        name.
        """
        data: dict[str, dict] = {}
        # Undated but large, seen first.
        _aggregate_golfer_outcome(
            _Outcome(1, "Neal Shipley", 0.285, probability_change_24h=0.30),
            "kalshi",
            data,
            {},
        )
        # Dated but smaller — must NOT displace the larger value.
        _aggregate_golfer_outcome(
            _Outcome(2, "Neal Shipley", 0.283), "datagolf_model", data, {2: 0.273}
        )
        entry = data["neal shipley"]
        assert entry["movement_24h"] == pytest.approx(0.30)
        assert entry["movement_is_dated"] is False, (
            "the surviving value is the undated one, so the flag must say so"
        )

    def test_a_dated_arm_that_wins_the_race_sets_the_flag(self):
        """The mirror of the above, so the guard is not one-sided."""
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(1, "Neal Shipley", 0.285, probability_change_24h=0.02),
            "kalshi",
            data,
            {},
        )
        _aggregate_golfer_outcome(
            _Outcome(2, "Neal Shipley", 0.283), "datagolf_model", data, {2: 0.033}
        )
        entry = data["neal shipley"]
        assert entry["movement_24h"] == pytest.approx(0.25, abs=1e-3)
        assert entry["movement_is_dated"] is True


# --- 6. The flag survives the merge --------------------------------------


class TestTheProvenanceTravelsWithTheValue:
    """`_merge_abbreviated_golfers` moves a move between entries."""

    @staticmethod
    def _pair(short_dated: bool) -> dict[str, dict]:
        return {
            "s scheffler": {
                "name": "S. Scheffler",
                "sources": {"odds_api": 0.2},
                "movement_24h": 0.03,
                "movement_is_dated": short_dated,
                "opening_probability": 0.1,
            },
            "scottie scheffler": {
                "name": "Scottie Scheffler",
                "sources": {"datagolf_model": 0.22},
                "movement_24h": None,
                "movement_is_dated": False,
                "opening_probability": None,
            },
        }

    @pytest.mark.parametrize("dated", [True, False])
    def test_the_merged_move_keeps_its_own_provenance(self, dated):
        merged = _merge_abbreviated_golfers(self._pair(dated))
        assert "s scheffler" not in merged
        entry = merged["scottie scheffler"]
        assert entry["movement_24h"] == 0.03
        assert entry["movement_is_dated"] is dated, (
            "the value moved to the recipient entry but its provenance did not — "
            "the merged golfer would publish under the recipient's flag"
        )

    def test_the_published_golfer_carries_the_flag(self):
        """The join: the aggregation's flag must reach the SERVED golfer dict.

        Everything above tests one end or the other. `_build_tournament_entry` is
        the only path from `golfer_data` to the `golfers[]` the feed reads, and it
        rebuilds each entry field by field — so a flag set perfectly upstream and
        omitted here is dropped silently.

        That failure is invisible by construction: the consumer fails CLOSED, so
        a dropped flag does not raise, does not change a number, and does not drop
        a card. Every golf movement caption simply goes quiet forever, which looks
        exactly like a field with no movement in it. This is the assertion that
        tells those two apart.
        """

        class _Market:
            id = 1
            name = "Biltmore Championship Asheville - Winner"
            external_id = "golf_biltmore"
            source = "datagolf"
            market_metadata: dict = {}

        entry = _build_tournament_entry(
            "biltmore",
            [_Market()],
            {
                "neal shipley": {
                    "name": "Neal Shipley",
                    "sources": {"datagolf_model": 0.283},
                    "movement_24h": _SHIPLEY_MOVE,
                    "movement_is_dated": True,
                    "opening_probability": 0.03,
                }
            },
            [],
            [1],
            ["datagolf"],
            None,
            None,
        )
        assert entry is not None
        golfer = entry["golfers"][0]
        assert golfer["name"] == "Neal Shipley"
        assert golfer["movement_24h"] == pytest.approx(_SHIPLEY_MOVE, abs=1e-4)
        assert golfer["movement_is_dated"] is True, (
            "the aggregation dated this move but the published golfer does not "
            "say so — every golf movement caption would silently go quiet"
        )

    def test_an_undated_move_publishes_as_undated(self):
        """The mirror, so the assertion above cannot be satisfied by a constant."""

        class _Market:
            id = 1
            name = "Biltmore Championship Asheville - Winner"
            external_id = "golf_biltmore"
            source = "kalshi"
            market_metadata: dict = {}

        entry = _build_tournament_entry(
            "biltmore",
            [_Market()],
            {
                "neal shipley": {
                    "name": "Neal Shipley",
                    "sources": {"kalshi": 0.285},
                    "movement_24h": _UNDATED_MOVE,
                    "movement_is_dated": False,
                    "opening_probability": None,
                }
            },
            [],
            [1],
            ["kalshi"],
            None,
            None,
        )
        assert entry is not None
        assert entry["golfers"][0]["movement_is_dated"] is False

    def test_the_merge_does_not_raise(self):
        """Regression: it referenced a `probabilities` key no entry ever had.

        `_aggregate_golfer_outcome` builds exactly name/sources/movement_24h/
        movement_is_dated/opening_probability, so the merge body could only ever
        raise `KeyError`, and its caller `_build_tournament_entry` is unguarded —
        one abbreviated name would have taken down the whole golf base, and with
        it every golf card on Discover and the `/golf` page. Never fired in
        production because `to_merge` is empty on today's field.
        """
        merged = _merge_abbreviated_golfers(self._pair(True))
        assert merged["scottie scheffler"]["sources"] == {
            "odds_api": 0.2,
            "datagolf_model": 0.22,
        }


# --- 7. The wire (#7226) --------------------------------------------------


class TestTheFlagReachesTheFeedCard:
    """The LAST link: the served feed card must carry the flag, not just compute it.

    #7179 (every class above) stopped the server SENTENCE lying. It could not stop
    the BADGE lying, because the badge is drawn by the client and the client was
    never sent the flag: `_score_golf_tournaments` rebuilds each golfer field by
    field for the feed, and that projection listed `name / probability / rank /
    movement_24h` only. So on one card, in one render:

        server `reason`  — gated on `movement_is_dated`, went quiet when undated
        client `MovementBadge` — "Up 17 points in the last 24h", ungated

    Measured on production 2026-09-19 18:10Z, AFTER #7179 was live: `/api/golf`
    served the flag on 135/135 golfer entries (108 dated, 27 not), and
    `/api/feed?category=golf` served golfer keys `['movement_24h', 'name',
    'probability', 'rank']` — the flag absent from every one. The producer had it
    and the projection dropped it.

    `TestTheProvenanceTravelsWithTheValue` above guards the same drop one hop
    earlier (`_build_tournament_entry` -> the golf base). This guards golf base ->
    feed card. Both hops rebuild field by field, and both fail CLOSED and silently
    when a flag is dropped, which is why each needs its own assertion rather than
    one at the end.
    """

    @staticmethod
    def _served_golfer(monkeypatch, *, dated: bool | None) -> dict:
        card = _card(monkeypatch, _golfer(_SHIPLEY_MOVE, dated=dated))
        golfers = card["data"]["golfers"]
        assert len(golfers) == 1, f"projection changed shape: {golfers}"
        return golfers[0]

    def test_a_dated_move_is_published_as_dated(self, monkeypatch):
        golfer = self._served_golfer(monkeypatch, dated=True)
        assert golfer["movement_is_dated"] is True, (
            "the feed card does not tell the client this move is dated, so the "
            "badge cannot gate and announces every move as 'in the last 24h'"
        )

    def test_an_undated_move_is_published_as_undated(self, monkeypatch):
        """The mirror, so the assertion above cannot pass on a hardcoded True."""
        golfer = self._served_golfer(monkeypatch, dated=False)
        assert golfer["movement_is_dated"] is False

    def test_a_pre_ship_base_publishes_the_refusal_explicitly(self, monkeypatch):
        """A base with NO key must serve `False`, not a missing key.

        Absent and False are the same refusal (the A8 paragraph in the route says
        why: an old base cannot be asked what it measured). But the client gate is
        `=== true`, and shipping a real boolean rather than a hole means the gate
        reads identically whichever base the card was built from — including the
        up-to-2h `last_good` window after a deploy, which is exactly when the two
        bases are both in flight.
        """
        golfer = self._served_golfer(monkeypatch, dated=None)
        assert "movement_is_dated" in golfer, (
            "a pre-#7179 base leaves the key absent all the way to the wire"
        )
        assert golfer["movement_is_dated"] is False

    @pytest.mark.parametrize("dated", [True, False, None])
    def test_the_number_itself_is_untouched(self, monkeypatch, dated):
        """The control. This ship narrows what the card may SAY about the move.

        It must not change the move, drop the card, or reorder anything — the same
        property `TestTheFixNarrowsTheSentenceAndNothingElse` pins for the
        sentence. These assertions pass before this change and after it.
        """
        golfer = self._served_golfer(monkeypatch, dated=dated)
        assert golfer["movement_24h"] == pytest.approx(_SHIPLEY_MOVE, abs=1e-9)
        assert golfer["probability"] == pytest.approx(0.283, abs=1e-9)
        assert golfer["rank"] == 1
        assert golfer["name"] == "Neal Shipley"
