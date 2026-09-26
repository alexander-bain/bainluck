"""#8930 — a date ladder's settled deadlines stop heading its search answer.

WHAT A READER SAW, production 2026-09-26 20:58Z, ``/search?q=trump`` at 390px,
ANSWERS card "TRUMP"::

    Donald Trump announces departure as President? (Excluding death)   Before April 1, 2026 0%
    Will Trump buy at least part of Greenland                          Before May 1, 2026 0%
    Will Trump be impeached                                            Before Jun 1, 2026 <1%

Each of those rungs is graded NO (``api_settlement``), and 112818 also holds an
UNGRADED ``Before Jan 1, 2026`` at 1% that would head the row once its graded
neighbours left. The web row prints the
ladder's FIRST priced rung and the dropdown its first two, and #8834's window
kept graded rungs in threshold order, so a rising ``Before <date>`` ladder
always led with its expired deadlines.

THE FIXTURES ARE THE THREE SPECIMENS' STORED ROWS (109256, 108366, 112818, every
leg, read via ``db-query`` 2026-09-26 ~21:10Z), so the builder's own pre-sort
refusals run on the real bids and asks.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import _build_search_top_outcomes

#: The specimens' read date. Pinned, never the real clock (gotcha #44): every
#: `Before 2027` rung here expires on Jan 1 2027.
SPECIMEN_DAY = 20260926.0


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    monkeypatch.setattr("app.routes.events._search_today_ymd", lambda: SPECIMEN_DAY)


#: ``(id, name, external_id, prob, bid, ask, is_winner, resolution_source)`` verbatim.
DEPARTURE = [
    (1595991, "Before January 20, 2029", "KXTRUMPOUT27-27-JAN2029", 0.245, 0.24, 0.25, False, "ungradeable_result"),
    (1595992, "Before 2028", "KXTRUMPOUT27-27-28", 0.18, 0.17, 0.19, False, "ungradeable_result"),
    (1595993, "Before 2027", "KXTRUMPOUT27-27-DJT", 0.039, 0.038, 0.04, False, "ungradeable_result"),
    (1595994, "Before August 1, 2026", "KXTRUMPOUT27-27-26AUG01", 0.0, 0.0, 1.0, False, "api_settlement"),
    (1595995, "Before April 1, 2026", "KXTRUMPOUT27-27-26APR01", 0.0, 0.0, 1.0, False, "api_settlement"),
]
GREENLAND = [
    (1591896, "Before January 20, 2029", "KXGREENLAND-29", 0.115, 0.10, 0.13, False, "ungradeable_result"),
    (1591897, "Before 2027", "KXGREENLAND-29-27", 0.0405, 0.036, 0.045, False, "ungradeable_result"),
    (1591898, "Before May 1, 2026", "KXGREENLAND-29-26MAY", 0.0, 0.0, 1.0, False, "api_settlement"),
    (2558173, "Before Jul 1, 2026", "KXGREENLAND-29-26JUL", 0.0, 0.0, 1.0, False, "api_settlement"),
]
IMPEACHED = [
    (1625535, "Before Jan 1, 2028", "KXIMPEACH-28-JAN01", 0.65, 0.64, 0.66, False, "ungradeable_result"),
    (1625536, "Before Jan 1, 2026", "KXIMPEACH-26-JAN01", 0.01, 0.0, 1.0, False, None),
    (1625537, "Before Jan 1, 2027", "KXIMPEACH-27-JAN01", 0.033, 0.03, 0.036, False, "ungradeable_result"),
    (1625538, "Before Jun 1, 2026", "KXIMPEACH-26-JUN01", 0.001, 0.0, 1.0, False, "api_settlement"),
    (205820110, "Before Mar 1, 2027", "KXIMPEACH-27-MAR01", 0.22, 0.21, 0.23, False, "ungradeable_result"),
    (205820112, "Before Sep 1, 2026", "KXIMPEACH-26-SEP01", 0.0, 0.0, 1.0, False, "api_settlement"),
]

SPECIMENS = [
    (109256, "Donald Trump announces departure as President? (Excluding death)", DEPARTURE,
     "Before 2027"),
    (108366, "Will Trump buy at least part of Greenland?", GREENLAND, "Before 2027"),
    (112818, "Will Trump be impeached?", IMPEACHED, "Before Jan 1, 2027"),
]


def _leg(oid, name, ext, prob, bid, ask, is_winner, source):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=ext,
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        probability_change_24h=None,
        is_winner=is_winner,
        resolution_source=source,
        current_yes_bid=bid,
        current_yes_ask=ask,
        price_changed_at=None,
        last_updated=None,
    )


def _market(mid, name, legs):
    return SimpleNamespace(
        id=mid,
        name=name,
        source="kalshi",
        status="open",
        mutually_exclusive=False,
        outcomes=[_leg(*row) for row in legs],
    )


def _first_priced(out):
    """What the web ANSWERS row prints for a date ladder
    (`searchFamilyDisplay.ts::leaderOutcome`): the first priced row."""
    return next(o["name"] for o in out if o["probability"] is not None)


def _spent_names(legs):
    """Graded, or a `Before` deadline earlier than SPECIMEN_DAY (all 2026 rungs
    in these fixtures)."""
    return {
        row[1] for row in legs
        if row[6] is True or row[7] == "api_settlement" or row[1].endswith(", 2026")
    }


def test_each_specimen_answers_with_its_first_live_deadline():
    for mid, name, legs, answer in SPECIMENS:
        out = _build_search_top_outcomes(_market(mid, name, legs))
        assert _first_priced(out) == answer, (mid, [o["name"] for o in out])


def test_no_spent_rung_is_drawn_on_the_card_or_the_dropdown():
    # #993: the dropdown (lean) and the card are one pair, and the dropdown
    # prints the first TWO priced rows, so both shapes must lose the rungs.
    for mid, name, legs, _answer in SPECIMENS:
        spent = _spent_names(legs)
        assert spent, mid  # the fixture must carry the defect
        for kwargs in ({}, {"limit": 3, "lean": True}):
            out = _build_search_top_outcomes(_market(mid, name, legs), **kwargs)
            assert not spent & {o["name"] for o in out}, (mid, kwargs, out)


def test_an_ungraded_past_deadline_is_spent_too():
    # 112818's `Before Jan 1, 2026` (0.01 on a 0/1.00 book, resolution_source
    # NULL): with only the graded rungs gone, four live rungs fit the card and
    # this one would lead it.
    out = _build_search_top_outcomes(_market(*SPECIMENS[2][:3]))
    assert [o["name"] for o in out] == [
        "Before Jan 1, 2027", "Before Mar 1, 2027", "Before Jan 1, 2028",
    ]


def test_control_the_same_rung_is_drawn_before_its_deadline(monkeypatch):
    # The clock is the only input that changed: on Dec 1 2025 the Jan 1 2026
    # deadline is still ahead, so the rung is live and heads the card.
    monkeypatch.setattr("app.routes.events._search_today_ymd", lambda: 20251201.0)
    out = _build_search_top_outcomes(_market(*SPECIMENS[2][:3]))
    assert _first_priced(out) == "Before Jan 1, 2026"


def test_control_an_after_ladder_keeps_its_past_dates():
    # `After <date>` stays an open question once its date passes.
    legs = [
        (1, "After Jan 1, 2026", "Z-26", 0.90, 0.89, 0.91, False, None),
        (2, "After Jan 1, 2027", "Z-27", 0.60, 0.59, 0.61, False, None),
        (3, "After Jan 1, 2028", "Z-28", 0.30, 0.29, 0.31, False, None),
    ]
    out = _build_search_top_outcomes(_market(4, "When will Z happen?", legs))
    assert "After Jan 1, 2026" in {o["name"] for o in out}


def test_live_rungs_keep_threshold_order():
    out = _build_search_top_outcomes(_market(*SPECIMENS[0][:3]))
    assert [o["name"] for o in out] == [
        "Before 2027", "Before 2028", "Before January 20, 2029",
    ]


def test_control_a_wholly_graded_ladder_is_drawn_as_before():
    # Nothing live is left, so the results are all there is to show.
    legs = [row[:6] + (False, "api_settlement") for row in DEPARTURE[:3]]
    out = _build_search_top_outcomes(_market(1, SPECIMENS[0][1], legs))
    assert [o["name"] for o in out] == [
        "Before 2027", "Before 2028", "Before January 20, 2029",
    ]


def test_control_the_retraction_badge_and_default_false_are_not_verdicts():
    # `ungradeable_result` retracts a loss and `is_winner=False` + NULL is the
    # column default; neither is a grade, so neither rung may leave the card.
    legs = [
        (1, "Before 2027", "X-27", 0.04, 0.03, 0.05, False, "ungradeable_result"),
        (2, "Before 2028", "X-28", 0.18, 0.17, 0.19, False, None),
        (3, "Before 2029", "X-29", 0.25, 0.24, 0.26, False, "ungradeable_result"),
    ]
    out = _build_search_top_outcomes(_market(2, "Will X happen?", legs))
    assert [o["name"] for o in out] == ["Before 2027", "Before 2028", "Before 2029"]


def test_control_a_graded_winner_rung_also_leaves_while_live_rungs_remain():
    # `is_winner IS TRUE` is a verdict whatever the source (`leg_is_graded`).
    legs = [
        (1, "Before 2027", "Y-27", 0.99, 0.98, 1.0, True, None),
        (2, "Before 2028", "Y-28", 0.60, 0.59, 0.61, False, "ungradeable_result"),
        (3, "Before 2029", "Y-29", 0.70, 0.69, 0.71, False, "ungradeable_result"),
    ]
    out = _build_search_top_outcomes(_market(3, "Will Y happen?", legs))
    assert [o["name"] for o in out] == ["Before 2028", "Before 2029"]


def test_control_a_deadline_dated_today_is_still_drawn():
    # `<`, not `<=`: `By Sep 26, 2026` is still open on Sep 26, and holding a
    # `Before` rung one extra day costs nothing. Kills the `<=` mutant.
    legs = [
        (1, "By Sep 26, 2026", "W-0926", 0.05, 0.04, 0.06, False, None),
        (2, "By Dec 31, 2026", "W-1231", 0.30, 0.29, 0.31, False, None),
    ]
    out = _build_search_top_outcomes(_market(6, "Will W happen?", legs))
    assert _first_priced(out) == "By Sep 26, 2026"
