"""#1712 shape 1 / ux/1070 item 2 — one fight night is ONE card.

═══ THE DEFECT ═══

A combat card is grouped by a UTC calendar date, and a US fight night does not
respect one. Measured on production 2026-09-04, `GET /api/feed?tags=["sport:mma"]`
served ELEVEN UFC concepts, and four of them were the spillover halves of cards
already in the list:

    event:ufc:26sep05  14 fights   last bout 21:45Z  ─┐ one card
    event:ufc:26sep06   1 fight    first bout 00:40Z ─┘ 2h55 later

    event:ufc:26sep12  21 fights   last bout 23:45Z  ─┐ one card
    event:ufc:26sep13   3 fights   first bout 00:00Z ─┘ 15 min later

    event:ufc:26sep19   6 fights   last bout 23:45Z  ─┐ one card, and the MAIN
    event:ufc:26sep20   7 fights   first bout 00:15Z ─┘ EVENT is in the spillover

    event:ufc:26sep22   3 fights   last bout 23:40Z  ─┐ one card
    event:ufc:26sep23   2 fights   first bout 00:00Z ─┘ 20 min later

Alex saw this as "six separate UFC cards scattered" through My Stuff's Upcoming
section on 2026-09-04. #1712 filed the same shape on 2026-08-10 (UFC 330:
Makhachev vs Garry, minted as `26aug15` AND `26aug16`), so it is not a one-off
of this week's schedule — it is what the grain of the key does to every card
that starts on a US evening.

═══ WHAT THIS DOES AND DOES NOT FIX ═══

Shape 1 only. #1712's shape 2 — `Alexandre Pantoja vs Joshua Van` on 26sep10 and
`Joshua Van vs Alexandre Pantoja` on 26sep20, ten days apart with the fighter
names reversed — is a DUPLICATE EVENT ROW upstream of this grouper (measured
2026-09-04: ten bouts of the Sep 19 card also exist as events dated
2026-09-10T00:00:00Z, a placeholder midnight). No grouping rule can merge two
dates ten days apart, and it must not try: that is the events layer's fix.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import (
    ROLLOVER_MAX_GAP_HOURS,
    fold_rollover_tokens,
    token_date,
)
from app.utils.event_ufc import UFC_CONFIG, list_ufc_card_concepts


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


class TestTokenDate:
    def test_reads_a_card_token(self):
        assert token_date("26sep19") == date(2026, 9, 19)
        assert token_date("26JUL18") == date(2026, 7, 18)

    def test_is_none_for_anything_that_is_not_one(self):
        assert token_date(None) is None
        assert token_date("") is None
        assert token_date("26xxx19") is None
        assert token_date("2026-09-19") is None
        assert token_date("26sep99") is None


class TestFoldRolloverTokens:
    def test_the_sept_19_card_is_one_card(self):
        """The measured span, and the main event is in the spillover half."""
        survivor = fold_rollover_tokens(
            {
                "26sep19": (_utc(2026, 9, 19, 22, 15), _utc(2026, 9, 19, 23, 45)),
                "26sep20": (_utc(2026, 9, 20, 0, 15), _utc(2026, 9, 20, 3, 15)),
            }
        )
        assert survivor["26sep20"] == "26sep19"
        assert survivor["26sep19"] == "26sep19"

    @pytest.mark.parametrize(
        "early_last,late_first",
        [
            (_utc(2026, 9, 5, 21, 45), _utc(2026, 9, 6, 0, 40)),  # 2h55
            (_utc(2026, 9, 12, 23, 45), _utc(2026, 9, 13, 0, 0)),  # 15 min
            (_utc(2026, 9, 22, 23, 40), _utc(2026, 9, 23, 0, 0)),  # 20 min
        ],
    )
    def test_every_measured_spillover_folds(self, early_last, late_first):
        early = f"26sep{early_last.day:02d}"
        late = f"26sep{late_first.day:02d}"
        survivor = fold_rollover_tokens(
            {early: (early_last - timedelta(hours=4), early_last),
             late: (late_first, late_first + timedelta(minutes=30))}
        )
        assert survivor[late] == early

    def test_two_real_nights_stay_two_cards(self):
        """Adjacent days are not enough — Friday and Saturday are two cards."""
        survivor = fold_rollover_tokens(
            {
                "26sep11": (_utc(2026, 9, 11, 22, 0), _utc(2026, 9, 12, 0, 0)),
                "26sep12": (_utc(2026, 9, 12, 17, 0), _utc(2026, 9, 12, 23, 45)),
            }
        )
        # 17 hours apart: a separate night, not a spillover.
        assert survivor["26sep12"] == "26sep12"

    def test_a_same_day_asian_card_is_not_swallowed(self):
        """Contiguity is not enough either — the gap test is a real bound."""
        survivor = fold_rollover_tokens(
            {
                "26sep11": (_utc(2026, 9, 11, 20, 0), _utc(2026, 9, 11, 23, 0)),
                # 07:20Z the next day is a Chinese afternoon card, 8h20 later.
                "26sep12": (_utc(2026, 9, 12, 7, 20), _utc(2026, 9, 12, 11, 20)),
            }
        )
        assert survivor["26sep12"] == "26sep12"

    def test_the_bound_is_the_named_constant(self):
        base = _utc(2026, 9, 19, 23, 0)
        inside = {
            "26sep19": (base, base),
            "26sep20": (
                base + timedelta(hours=ROLLOVER_MAX_GAP_HOURS),
                base + timedelta(hours=ROLLOVER_MAX_GAP_HOURS),
            ),
        }
        outside = {
            "26sep19": (base, base),
            "26sep20": (
                base + timedelta(hours=ROLLOVER_MAX_GAP_HOURS, minutes=1),
                base + timedelta(hours=ROLLOVER_MAX_GAP_HOURS, minutes=1),
            ),
        }
        assert fold_rollover_tokens(inside)["26sep20"] == "26sep19"
        assert fold_rollover_tokens(outside)["26sep20"] == "26sep20"

    def test_a_chain_of_folds_lands_on_the_first_token(self):
        """Synthetic — no real card spans three UTC dates, and the map must
        still be a forest of depth one so a caller never has to chase it."""
        survivor = fold_rollover_tokens(
            {
                "26sep19": (_utc(2026, 9, 19, 20, 0), _utc(2026, 9, 19, 23, 45)),
                "26sep20": (_utc(2026, 9, 20, 0, 15), _utc(2026, 9, 20, 23, 0)),
                "26sep21": (_utc(2026, 9, 21, 1, 0), _utc(2026, 9, 21, 2, 0)),
            }
        )
        assert survivor["26sep20"] == "26sep19"
        assert survivor["26sep21"] == "26sep19"
        assert all(survivor[v] == v for v in survivor.values())

    def test_the_map_is_total_and_never_reverses_time(self):
        spans = {
            "26sep19": (_utc(2026, 9, 19, 22, 0), _utc(2026, 9, 19, 23, 0)),
            "notatoken": (_utc(2026, 9, 20, 0, 10), _utc(2026, 9, 20, 0, 20)),
            "26sep20": (None, None),
        }
        survivor = fold_rollover_tokens(spans)
        assert set(survivor) == set(spans)
        assert all(survivor[t] in spans for t in spans)
        # A token with no usable span is never folded and never a target.
        assert survivor["26sep20"] == "26sep20"
        assert survivor["notatoken"] == "notatoken"

    def test_ten_days_apart_is_not_this_functions_problem(self):
        """#1712 shape 2 stays visible — a duplicate event row, not a rollover."""
        survivor = fold_rollover_tokens(
            {
                "26sep10": (_utc(2026, 9, 10, 0, 0), _utc(2026, 9, 10, 0, 0)),
                "26sep20": (_utc(2026, 9, 20, 0, 15), _utc(2026, 9, 20, 3, 15)),
            }
        )
        assert survivor["26sep20"] == "26sep20"
        assert survivor["26sep10"] == "26sep10"


# ---------------------------------------------------------------------------
# The lister actually applies it — the pure function above is replayable and
# would stay green if `list_card_concepts` stopped calling it (UX-P176).
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """Just enough session for the lister's TWO reads, told apart by name.

    `list_card_concepts` selects Event rows (`_list_event_bouts`) and then
    FuturesOutcome rows (`_attach_headline_bouts`). A fake that answers both
    with one list is the shared-mock trap: handing the bout rows to the outcome
    reader used to raise inside `_attach_headline_bouts`, which catches
    everything on purpose, so the fold assertions below stayed green while the
    headline path was never exercised at all. Dispatch on the statement so a
    wrong answer is a wrong answer rather than a silent skip.
    """

    def __init__(self, events=(), outcomes=()):
        self._events = list(events)
        self._outcomes = list(outcomes)

    async def execute(self, statement, *_a, **_k):
        if "futures_outcomes" in str(statement):
            return _FakeResult(self._outcomes)
        return _FakeResult(self._events)


def _bout(home, away, when):
    return SimpleNamespace(
        home_team_name=home, away_team_name=away, commence_time=when
    )


def _fight_row(mid, ticker, name, when, title=None):
    """A COMBAT_PROJECTION row: (id, external_id, name, commence_time, metadata)."""
    return (mid, ticker, name, when, {"event_title": title} if title else None)


@pytest.mark.asyncio
class TestTheListerFoldsTheCard:
    async def test_the_sept_19_card_lists_once_with_every_fight(self):
        """Both sources, both halves — one concept, 13 bouts, right main event."""
        events = [
            _bout("Casey O'Neill", "Eduarda Moura", _utc(2026, 9, 19, 22, 15)),
            _bout("Giga Chikadze", "Joanderson Brito", _utc(2026, 9, 19, 22, 45)),
            _bout("Edmen Shahbazyan", "Brunno Ferreira", _utc(2026, 9, 19, 23, 15)),
            _bout("Tai Tuivasa", "Robelis Despaigne", _utc(2026, 9, 19, 23, 45)),
            _bout("Marlon Vera", "Charles Jourdain", _utc(2026, 9, 20, 0, 15)),
            _bout("Gable Steveson", "Sean Sharaf", _utc(2026, 9, 20, 0, 45)),
            _bout("Renato Moicano", "Brian Ortega", _utc(2026, 9, 20, 1, 45)),
            _bout("Joshua Van", "Alexandre Pantoja", _utc(2026, 9, 20, 3, 15)),
        ]
        concepts = await list_ufc_card_concepts(
            _FakeDB(events), statuses=("upcoming", "live"), rows=[]
        )
        assert len(concepts) == 1, [c["key"] for c in concepts]
        card = concepts[0]
        assert card["key"] == "event:ufc:26sep19"
        assert card["fight_count"] == 8
        # The main event is the LAST bout of the night, which lives in the half
        # that used to be its own card.
        assert "Pantoja" in card["name"]

    async def test_kalshi_and_events_halves_land_on_one_token(self):
        events = [_bout("Daniel Hooker", "Salahdine Parnasse", _utc(2026, 9, 5, 21, 45))]
        rows = [
            _fight_row(
                1,
                "KXUFCFIGHT-26SEP05HOOPAR",
                "Fight Night: Hooker vs Parnasse",
                _utc(2026, 9, 5, 21, 45),
                "Fight Night: Hooker vs Parnasse",
            ),
            _fight_row(
                2,
                "KXUFCFIGHT-26SEP06SPIPET",
                "Fight Night: Spivac vs Petrino",
                _utc(2026, 9, 6, 0, 40),
            ),
        ]
        concepts = await list_ufc_card_concepts(
            _FakeDB(events + [_bout("Spivac", "Petrino", _utc(2026, 9, 6, 0, 40))]),
            statuses=("upcoming", "live"),
            rows=rows,
        )
        assert [c["key"] for c in concepts] == ["event:ufc:26sep05"]
        assert concepts[0]["fight_count"] == 2

    async def test_two_real_nights_still_list_twice(self):
        """The must-not-regress control: folding is not merging everything."""
        events = [
            _bout("A Fighter", "B Fighter", _utc(2026, 9, 11, 22, 0)),
            _bout("C Fighter", "D Fighter", _utc(2026, 9, 12, 22, 0)),
        ]
        concepts = await list_ufc_card_concepts(
            _FakeDB(events), statuses=("upcoming", "live"), rows=[]
        )
        assert sorted(c["key"] for c in concepts) == [
            "event:ufc:26sep11",
            "event:ufc:26sep12",
        ]


class TestTheCardPageFoldsTheSameWay:
    """A card of 13 fights must not link to a page that shows 6.

    The adapter groups by the same token the feed card does, so it has to fold
    the same way — and either half's URL has to resolve onto the whole card, or
    every link minted before this change breaks.
    """

    def test_the_adapter_resolves_both_halves_to_one_card(self):
        from app.utils.event_ufc import UFCEventAdapter

        adapter = UFCEventAdapter()
        bouts_by_token = {
            "26sep19": [
                _bout("Tai Tuivasa", "Robelis Despaigne", _utc(2026, 9, 19, 23, 45))
            ],
            "26sep20": [
                _bout("Joshua Van", "Alexandre Pantoja", _utc(2026, 9, 20, 3, 15))
            ],
        }
        for slug in ("26sep19", "26sep20"):
            tokens = adapter._folded_card_tokens(slug, [], bouts_by_token)
            assert tokens == {"26sep19", "26sep20"}, slug

    def test_an_unrelated_card_is_not_swept_in(self):
        from app.utils.event_ufc import UFCEventAdapter

        adapter = UFCEventAdapter()
        bouts_by_token = {
            "26sep19": [_bout("A", "B", _utc(2026, 9, 19, 23, 45))],
            "26sep26": [_bout("C", "D", _utc(2026, 9, 26, 23, 45))],
        }
        assert adapter._folded_card_tokens("26sep19", [], bouts_by_token) == {
            "26sep19"
        }


def test_the_lister_calls_the_fold():
    """Named pin: the replayable tests above cannot see the call being deleted."""
    import inspect

    from app.utils import event_combat

    src = inspect.getsource(event_combat.list_card_concepts)
    assert "fold_rollover_tokens(" in src, (
        "the card lister no longer folds midnight-crossing cards — #1712 shape 1 "
        "is back and one fight night lists as two"
    )
    assert "_folded_card_tokens" in inspect.getsource(
        event_combat.CombatEventAdapter.build_event
    ), "the card PAGE stopped folding; it will answer with half of a folded card"


def test_the_config_is_shared_by_every_combat_sport():
    """Boxing inherits the fold — it is engine behaviour, not a UFC special case."""
    from app.utils.event_boxing import BOXING_CONFIG

    assert UFC_CONFIG.domain == "ufc"
    assert BOXING_CONFIG.domain == "boxing"
