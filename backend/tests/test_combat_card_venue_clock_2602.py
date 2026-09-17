"""#2602 — the venue's clock must not decide whether a fight night crossed midnight.

═══ THE DEFECT ═══

`/hub/mma`, production, 2026-09-17 10:1xZ, first screen at 390px — UFC 331 served
as TWO upcoming cards, side by side, named after the same main event:

    event:ufc:26sep19   "331: Van vs Pantoja"   Sat, Sep 19   12 fights
    event:ufc:26sep20   "van vs Pantoja"        Sun, Sep 20   10 fights

#1712's `fold_rollover_tokens` exists precisely to collapse that pair, and it
was refusing. The span it was handed blended two clocks:

    events table (fight STARTS)  26sep19  2026-09-19 00:00Z → 22:45Z
                                 26sep20  2026-09-20 00:15Z → 07:20Z
    Kalshi tickers (CLOSE times) 26sep19  ... → 2026-09-20 07:20Z   ← gotcha #14

All thirteen `KXUFCFIGHT-26SEP19*` tickers carry the earlier token and close
02:00-07:20Z on the 20th, ~3-4 h after the bouts they price. Widening `26sep19`
with those pushed its span END past `26sep20`'s FIRST bout, and the fold's own
overlap guard (`later_first < earlier_last`) then declined to fold the exact
card it was written for. The two halves' own fight times are 1h30 apart — well
inside `ROLLOVER_MAX_GAP_HOURS`.

═══ THE RULE ═══

A token's span is measured on ONE clock. Fight starts when the token has any;
the venue's stamps only for a token that has nothing else — where they are
self-consistent, because every ticker of one card carries the same shift.

Scope: this is about WHICH TOKENS ARE ONE CARD. It does not decide which bouts
belong to which promotion — the Sep-19 UTC window also holds a six-bout Polish
promotion and four stacked rumours, which is #5603(b)/#5602 and is not touched
here.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import (
    ROLLOVER_MAX_GAP_HOURS,
    card_span_by_token,
    fold_rollover_tokens,
)
from app.utils.event_ufc import list_ufc_card_concepts


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


#: Gotcha #44 — offset FIRST, then truncate. The lister reads the wall clock and
#: `combat_status` retires a card six hours past its last bout, so every lister
#: fixture below hangs off the NEXT midnight and can never age into `settled`.
def _next_utc_midnight() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(
        days=1
    )


_MONTH_ABBRS = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)


def _token_for(d) -> str:
    return f"{d.year % 100:02d}{_MONTH_ABBRS[d.month - 1]}{d.day:02d}"


def _ticker_for(d, suffix: str) -> str:
    return f"KXUFCFIGHT-{_token_for(d).upper()}{suffix}"


# ── the measured UFC 331 specimen, verbatim ────────────────────────────────
#: Fight starts, events table (`/api/admin/db-query`, 2026-09-17).
_S19_FIGHTS = (_utc(2026, 9, 19, 0, 0), _utc(2026, 9, 19, 22, 45))
_S20_FIGHTS = (_utc(2026, 9, 20, 0, 15), _utc(2026, 9, 20, 7, 20))
#: Kalshi close stamps, all carrying the `26sep19` token.
_S19_CLOSES = (_utc(2026, 9, 15, 1, 53), _utc(2026, 9, 20, 7, 20))


class TestTheSpanIsOnOneClock:
    def test_a_venue_close_time_never_widens_a_scheduled_token(self):
        spans = card_span_by_token(
            {"26sep19": list(_S19_CLOSES)},
            {"26sep19": list(_S19_FIGHTS)},
        )
        assert spans["26sep19"] == _S19_FIGHTS

    def test_a_token_with_no_scheduled_bout_keeps_its_venue_span(self):
        """The fallback is load-bearing: Kalshi lists a card before the Odds API
        schedules it, and a token with only close stamps still has to fold."""
        spans = card_span_by_token({"26sep19": list(_S19_CLOSES)}, {})
        assert spans["26sep19"] == _S19_CLOSES

    def test_a_token_whose_times_are_all_unknown_gets_no_span(self):
        assert card_span_by_token({"26sep19": [None, None]}, {"26sep20": []}) == {}

    def test_unknown_times_do_not_shrink_a_span_they_are_mixed_into(self):
        spans = card_span_by_token(
            {}, {"26sep19": [None, _S19_FIGHTS[1], _S19_FIGHTS[0], None]}
        )
        assert spans["26sep19"] == _S19_FIGHTS


class TestTheProductionPairFolds:
    def test_ufc_331_is_one_card(self):
        """The whole defect, end to end on the measured stamps."""
        survivor = fold_rollover_tokens(
            card_span_by_token(
                {"26sep19": list(_S19_CLOSES)},
                {"26sep19": list(_S19_FIGHTS), "26sep20": list(_S20_FIGHTS)},
            )
        )
        assert survivor["26sep20"] == "26sep19"

    def test_the_blend_is_what_refused_it(self):
        """Pins the CAUSE, so a future reader cannot mistake this for a change
        to the gap bound: on the blended span the pair is unfoldable at any
        gap, because the halves read as overlapping rather than as far apart."""
        blended = {
            "26sep19": (_S19_FIGHTS[0], max(_S19_CLOSES[1], _S19_FIGHTS[1])),
            "26sep20": _S20_FIGHTS,
        }
        assert blended["26sep20"][0] < blended["26sep19"][1]
        assert fold_rollover_tokens(blended, max_gap_hours=24)["26sep20"] == "26sep20"

    def test_two_real_nights_are_not_merged_by_the_change(self):
        """The must-not-regress control, with venue stamps present on both:
        Friday and Saturday stay two cards."""
        survivor = fold_rollover_tokens(
            card_span_by_token(
                {
                    "26sep11": [_utc(2026, 9, 12, 3, 0)],
                    "26sep12": [_utc(2026, 9, 13, 3, 0)],
                },
                {
                    "26sep11": [_utc(2026, 9, 11, 22, 0), _utc(2026, 9, 11, 23, 30)],
                    "26sep12": [_utc(2026, 9, 12, 17, 0), _utc(2026, 9, 12, 23, 45)],
                },
            )
        )
        assert survivor["26sep12"] == "26sep12"

    def test_a_same_day_afternoon_card_is_still_not_swallowed(self):
        """Truer times must not become a licence to merge: 8h20 is 8h20 on
        either clock."""
        survivor = fold_rollover_tokens(
            card_span_by_token(
                {"26sep11": [_utc(2026, 9, 12, 2, 0)]},
                {
                    "26sep11": [_utc(2026, 9, 11, 20, 0), _utc(2026, 9, 11, 23, 0)],
                    "26sep12": [_utc(2026, 9, 12, 7, 20), _utc(2026, 9, 12, 11, 20)],
                },
            )
        )
        assert survivor["26sep12"] == "26sep12"


# ── the lister and the page, which is where the reader meets it ────────────


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """The lister's two reads, told apart by name — a shared answer would hand
    bout rows to `_attach_headline_bouts`, which swallows everything."""

    def __init__(self, events=(), outcomes=()):
        self._events = list(events)
        self._outcomes = list(outcomes)

    async def execute(self, statement, *_a, **_k):
        if "futures_outcomes" in str(statement):
            return _FakeResult(self._outcomes)
        return _FakeResult(self._events)


def _bout(home, away, when, event_id):
    return SimpleNamespace(
        id=event_id, home_team_name=home, away_team_name=away, commence_time=when
    )


def _fight_row(mid, ticker, name, close_time, title=None):
    """A COMBAT_PROJECTION row. `close_time`, not fight time — gotcha #14, and
    the whole point of this file: the fixture carries the clock the venue
    actually serves."""
    return (mid, ticker, name, close_time, {"event_title": title} if title else None)


@pytest.mark.asyncio
class TestTheListerServesOneCard:
    async def test_the_card_lists_once_when_its_tickers_close_after_midnight(self):
        """UFC 331's geometry: bouts either side of midnight UTC, every ticker
        on the earlier token, closing ~3h45 after the bout it prices."""
        midnight = _next_utc_midnight()
        card_day = (midnight - timedelta(days=1)).date()
        bouts = [
            ("Renato Moicano", "Brian Ortega", midnight - timedelta(hours=3)),
            (
                "Giga Chikadze",
                "Joanderson Brito",
                midnight - timedelta(hours=2, minutes=15),
            ),
            (
                "Edmen Shahbazyan",
                "Brunno Ferreira",
                midnight - timedelta(hours=1, minutes=15),
            ),
            ("Tai Tuivasa", "Robelis Despaigne", midnight + timedelta(minutes=15)),
            ("Marlon Vera", "Charles Jourdain", midnight + timedelta(minutes=45)),
            (
                "Joshua Van",
                "Alexandre Pantoja",
                midnight + timedelta(hours=3, minutes=30),
            ),
        ]
        events = [_bout(h, a, w, 100 + i) for i, (h, a, w) in enumerate(bouts)]
        rows = [
            _fight_row(
                200 + i,
                _ticker_for(card_day, f"F{i:02d}"),
                f"331: {h.split()[-1]} vs {a.split()[-1]}",
                w + timedelta(hours=3, minutes=45),  # the CLOSE stamp
                f"331: {h.split()[-1]} vs {a.split()[-1]}",
            )
            for i, (h, a, w) in enumerate(bouts)
        ]

        concepts = await list_ufc_card_concepts(
            _FakeDB(events), statuses=("upcoming", "live"), rows=rows
        )

        assert [c["key"] for c in concepts] == [f"event:ufc:{_token_for(card_day)}"]
        assert concepts[0]["fight_count"] == len(bouts)
        # The main event lives in the half that used to be its own card, so a
        # reader who taps the one surviving card still meets it.
        assert "Pantoja" in concepts[0]["name"]

    async def test_two_separate_nights_still_list_twice(self):
        """Direction two (gotcha #43): the fold that stopped duplicating did not
        start deleting."""
        midnight = _next_utc_midnight()
        first_night = midnight - timedelta(hours=2)
        second_night = midnight + timedelta(hours=22)
        events = [
            _bout("A Fighter", "B Fighter", first_night, 301),
            _bout("C Fighter", "D Fighter", second_night, 302),
        ]
        rows = [
            _fight_row(
                401,
                _ticker_for(first_night.date(), "AAABBB"),
                "Fight Night: A vs B",
                first_night + timedelta(hours=3, minutes=45),
            )
        ]
        concepts = await list_ufc_card_concepts(
            _FakeDB(events), statuses=("upcoming", "live"), rows=rows
        )
        assert {c["key"] for c in concepts} == {
            f"event:ufc:{_token_for(first_night.date())}",
            f"event:ufc:{_token_for(second_night.date())}",
        }


class TestThePageAgreesWithTheFeed:
    """A card the feed serves once must not open a page holding half of it."""

    def test_both_halves_resolve_to_one_card_despite_the_close_stamps(self):
        from app.utils.event_ufc import UFCEventAdapter

        adapter = UFCEventAdapter()
        markets = [
            SimpleNamespace(
                external_id="KXUFCFIGHT-26SEP19VANPAN",
                commence_time=_S19_CLOSES[1],
                outcomes=[object(), object()],
            )
        ]
        bouts_by_token = {
            "26sep19": [
                _bout("Edmen Shahbazyan", "Brunno Ferreira", _S19_FIGHTS[1], 501)
            ],
            # The spillover half opens at 00:15Z (Tuivasa) and runs to the main
            # event at 03:30Z — the fold reads its FIRST bout, so a fixture that
            # kept only the main event would be 4h45 from the previous half and
            # would not fold on any clock.
            "26sep20": [
                _bout(
                    "Tai Tuivasa", "Robelis Despaigne", _utc(2026, 9, 20, 0, 15), 502
                ),
                _bout("Joshua Van", "Alexandre Pantoja", _utc(2026, 9, 20, 3, 30), 503),
            ],
        }
        for slug in ("26sep19", "26sep20"):
            assert adapter._folded_card_tokens(slug, markets, bouts_by_token) == {
                "26sep19",
                "26sep20",
            }, slug

    def test_an_unrelated_card_is_still_not_swept_in(self):
        from app.utils.event_ufc import UFCEventAdapter

        adapter = UFCEventAdapter()
        bouts_by_token = {
            "26sep19": [_bout("A", "B", _utc(2026, 9, 19, 23, 45), 601)],
            "26sep26": [_bout("C", "D", _utc(2026, 9, 26, 23, 45), 602)],
        }
        assert adapter._folded_card_tokens("26sep19", [], bouts_by_token) == {"26sep19"}


def test_both_callers_build_their_span_the_same_way():
    """Named pin. The feed card and the page behind it fold independently, so a
    rule applied to one and not the other is a card that lists once and opens
    half-empty — the two callers must keep sharing the builder."""
    from app.utils import event_combat

    for source in (
        inspect.getsource(event_combat.list_card_concepts),
        inspect.getsource(event_combat.CombatEventAdapter._folded_card_tokens),
    ):
        assert "card_span_by_token(" in source


def test_the_gap_bound_did_not_move():
    """This ship changed the CLOCK the fold reads, not how long a gap may be."""
    assert ROLLOVER_MAX_GAP_HOURS == 4
