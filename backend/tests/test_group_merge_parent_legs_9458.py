"""#9458 — a sub-market's copy of a parent-row leg does not win the group pick.

Production 2026-09-28 20:50Z, /politics International at 390px: the card read
"Will any aircraft land or take off at Kyiv Boryspil Airport by October 31?"
over a "December 31 — 11%" leader. Group ``polymarket:959154`` has the parent
60130278 (external_id ``959154``, three date legs keyed by condition id) and
sub-market 60131787, which still holds the parent's three legs beside its own
Yes/No: the pre-#8609 merge reparented them for real. Five outcomes beat three,
so the sub-market became the representative and its own question titled the
card. Rows below are the production rows, ids and external ids shortened.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

from app.routes.politics import _market_row
from app.utils.cross_source_matching import group_markets_by_group_id

GROUP = "polymarket:959154"
OCT, SEP, DEC = "0xa27fd4", "0xae73a5", "0x00e19b"
NOW = datetime(2026, 9, 28, 20, 50, tzinfo=timezone.utc)


def _o(oid, name, ext, p):
    return NS(
        id=oid,
        name=name,
        external_id=ext,
        current_probability=Decimal(str(p)),
        last_updated=datetime(2026, 9, 28, 13, 51, tzinfo=timezone.utc),
        is_winner=None,
    )


def _m(mid, name, ext, outcomes, group=GROUP):
    return NS(
        id=mid,
        name=name,
        external_id=ext,
        group_id=group,
        source="polymarket",
        volume_24h=0,
        outcomes=outcomes,
    )


def _kyiv(with_parent=True):
    parent = _m(
        60130278,
        "Will any aircraft land or take off at Kyiv Boryspil Airport by...?",
        "959154",
        [
            _o(224243825, "September 30", SEP, 0.006),
            _o(231720076, "December 31", DEC, 0.105),
            _o(224222915, "October 31", OCT, 0.045),
        ],
    )
    october = _m(
        60131787,
        "Will any aircraft land or take off at Kyiv Boryspil Airport by October 31?",
        OCT,
        [
            _o(224219319, "October 31", OCT, 0.045),
            _o(224222914, "September 30", SEP, 0.006),
            _o(224219318, "No", f"{OCT}_no", 0.955),
            _o(231082370, "December 31", DEC, 0.105),
            _o(224219317, "Yes", f"{OCT}_yes", 0.045),
        ],
    )
    september = _m(
        60133208,
        "Will any aircraft land or take off at Kyiv Boryspil Airport by September 30?",
        SEP,
        [_o(224222911, "No", f"{SEP}_no", 0.994), _o(224222910, "Yes", f"{SEP}_yes", 0.006)],
    )
    rows = [october, september] + ([parent] if with_parent else [])
    return rows, parent, october


def test_parent_row_represents_the_group_not_the_sub_market_holding_its_legs():
    rows, parent, _ = _kyiv()
    (rep,) = group_markets_by_group_id(rows)
    assert rep is parent
    row = _market_row(rep, now=NOW)
    assert row["q"] == "Will any aircraft land or take off at Kyiv Boryspil Airport by...?"
    assert row["market_id"] == 60130278
    assert [o["name"] for o in row["top_outcomes"]] == [
        "December 31",
        "October 31",
        "September 30",
    ]


def test_a_borrowed_leg_under_a_different_label_is_not_merged_as_a_second_rung():
    # #8609's specimen shape: the parent says "↑ 45%", the sub-market's copy of
    # the same leg says "45%". A name dedupe keeps both; the leg id does not.
    parent = _m(
        61876974, "Republican Senate odds hit __ by October 31?", "1061741",
        [_o(1, "↑ 45%", "0xe95f", 0.3), _o(2, "↑ 40%", "0x40aa", 0.6),
         _o(6, "↑ 50%", "0x50bb", 0.1)],
        group="polymarket:1061741",
    )
    sub = _m(
        61891079, "Republican Senate odds hit 45% by October 31?", "0xe95f",
        [_o(3, "45%", "0xe95f", 0.3), _o(4, "Yes", "0xe95f_yes", 0.3),
         _o(5, "No", "0xe95f_no", 0.7)],
        group="polymarket:1061741",
    )
    (rep,) = group_markets_by_group_id([sub, parent])
    assert rep is parent
    assert [o.id for o in rep.outcomes] == [1, 2, 6, 4, 5]


def test_without_the_parent_in_the_set_the_sub_market_keeps_every_leg():
    # Control: the rule needs the parent to say whose leg it is. Absent that,
    # nothing is dropped and the pick is today's.
    rows, _, october = _kyiv(with_parent=False)
    reps = group_markets_by_group_id(rows)
    assert reps[0] is october
    assert len(reps[0].outcomes) == 5


def test_the_input_rows_are_not_rewritten():
    rows, _, october = _kyiv()
    before = {m.id: [o.id for o in m.outcomes] for m in rows}
    group_markets_by_group_id(rows)
    assert [o.id for o in october.outcomes] == before[60131787]
    assert [o.id for o in rows[1].outcomes] == before[60133208]


def test_a_kalshi_group_is_untouched_by_the_parent_rule():
    a = _m(1, "A", "KXA-1", [_o(1, "x", "KXA-1-X", 0.4), _o(2, "y", "KXA-1-Y", 0.6)],
           group="kalshi:KXA")
    b = _m(2, "B", "KXA", [_o(3, "x", "KXA-1-X", 0.4)], group="kalshi:KXA")
    (rep,) = group_markets_by_group_id([b, a])
    assert rep is a
    assert [o.id for o in rep.outcomes] == [1, 2]
