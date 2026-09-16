"""#6524 — a board stops serving a 100% row that no venue leg backs.

Two open boards each told a reader something was CERTAIN on the strength of no
market at all:

    /api/futures/113545  Will Russia enter Borova by...?
        May 31   1.0    external_id ''      <-- no venue id
        May 31   0.02   external_id 0xec84...
    /api/futures/114237  New "Stranger Things" episode released by...?
        May 31   1.0    external_id ''      <-- no venue id
        May 31   0.002  external_id 0x924d...

Measured over the whole table 2026-09-16, no sampling: **152 outcome rows carry a
blank ``external_id``, every one Polymarket, every one priced at exactly 1.000000
over a maximum-spread (bid 0.0000 / ask 1.0000) book.** No other source has one,
and not one of them is NULL — they are all the empty string, which is why the
poll's own orphan cleanup (``external_id.is_(None)``) has walked past all 152.
Six sit on OPEN markets and are what a reader can see today; 146 are resolved and
**139 of those are crowned**, which is the number that decides the shape of this
rule.

``drop_incoherent_near_certain`` (#4253) is the natural owner and is inert on
every one of them, disarmed by a SCOPE FIELD rather than by its predicate: all
six boards are ``mutually_exclusive = false`` — cumulative "by DATE?" ladders,
where several legs near 1.0 are legitimately simultaneous and #199 correctly
refuses to judge the field — and it needs two near-certain legs where the defect
is one. So the predicate here is not about the price at all. A leg with no venue
id has no member question, no ``closed``, no settlement, and cannot be refreshed
by a later pass (the upsert keys on ``(market_id, external_id)``) or withdrawn by
#4000 (which works off the ids the venue served). It is not a quote.

Each test below fails if the safety it names is removed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.utils.outcome_display import drop_unbacked_legs, is_unbacked_leg


def _row(name, external_id, prob, is_winner=None):
    return SimpleNamespace(
        id=abs(hash((name, external_id))) % 100000,
        name=name,
        external_id=external_id,
        current_probability=prob,
        is_winner=is_winner,
    )


def _drop(rows, *, open_=True):
    return drop_unbacked_legs(
        rows,
        lambda o: o.external_id,
        market_is_open=open_,
        is_winner_of=lambda o: bool(o.is_winner),
    )


def _names(rows):
    return [r.name for r in rows]


# ── The ship: the two boards the issue names ─────────────────────────────────


def test_the_borova_board_stops_saying_a_war_advance_is_certain_6524():
    """113545, as served: the unbacked 1.0 goes, the id-anchored 0.02 stays."""
    rows = [
        _row("May 31", "", 1.0),
        _row("September 30", "0xec843b00", 0.0805),
        _row("April 30", "0x11", 0.056),
        _row("May 31", "0xec843b01", 0.02),
        _row("December 31", "0x12", 0.0),
    ]

    kept = _drop(rows)

    assert [(r.name, float(r.current_probability)) for r in kept] == [
        ("September 30", 0.0805),
        ("April 30", 0.056),
        ("May 31", 0.02),
        ("December 31", 0.0),
    ]


def test_the_stranger_things_board_keeps_every_priced_leg_6524():
    """114237: one unbacked row removed out of twelve, eleven answers survive."""
    rows = [_row("May 31", "", 1.0)]
    rows += [_row(f"Leg {n}", f"0x{n:02x}", 0.002) for n in range(11)]

    kept = _drop(rows)

    assert len(kept) == 11
    assert "" not in [r.external_id for r in kept]


def test_a_rank_one_unbacked_leg_is_dropped_too_6524():
    """3821229 (*GPT-5.5 released by...?*) carries its unbacked leg at rank 1.

    The harm on that board is not clutter, it is that the fabricated row IS the
    card's subtitle and the board's headline answer.
    """
    rows = [_row("April 8", "", 1.0), _row("December 31", "0xaa", 0.31)]

    kept = _drop(rows)

    assert _names(kept) == ["December 31"]


# ── What "no venue id" means ─────────────────────────────────────────────────


def test_the_empty_string_is_the_live_shape_not_null_6524():
    """All 152 production rows are ``''``. A rule written for NULL misses them —
    which is exactly why the poll's orphan cleanup has never touched one."""
    assert is_unbacked_leg("") is True
    assert is_unbacked_leg(None) is True
    assert is_unbacked_leg("   ") is True
    assert is_unbacked_leg("0xec843b00") is False


def test_a_real_id_at_a_certain_price_is_never_dropped_6524():
    """The negative control, and it fails EXACTLY ONE clause of the predicate.

    A near-lock that a venue actually quotes is an honest answer. If this rule
    ever keys on the 1.0 instead of the missing id, this row goes with it — and
    so does every settled-shaped favourite on every board.
    """
    rows = [_row("Yes", "0xdeadbeef", 1.0), _row("No", "0xfeedface", 0.0)]

    assert _drop(rows) == rows


def test_an_unbacked_leg_at_an_ordinary_price_is_still_dropped_6524():
    """The mirror control. Today all 152 price at 1.0, but the id is the rule:
    a leg nothing backs is not a quote at 0.4 either, and a rule keyed on the
    symptom would serve the first one that arrives priced like an answer."""
    rows = [_row("Maybe", "", 0.4), _row("Yes", "0xaa", 0.6)]

    assert _names(_drop(rows)) == ["Yes"]


# ── The three exemptions ─────────────────────────────────────────────────────


def test_a_crowned_unbacked_leg_is_never_dropped_6524():
    """139 of the 146 resolved unbacked rows are crowned.

    ``is_winner`` is a settlement, not a quote. Without this exemption the rule
    deletes the displayed RESULT from those boards and leaves the losers on the
    page — "settled means settled", broken by a display helper.
    """
    rows = [_row("May 31", "", 1.0, is_winner=True), _row("June 30", "0xaa", 0.0)]

    assert _names(_drop(rows)) == ["May 31", "June 30"]


def test_a_resolved_board_is_left_entirely_alone_6524():
    """OPEN MARKETS ONLY. An unbacked row stamped a winner on a settled board is a
    GRADING defect and belongs to the grader; a display drop would paper over it."""
    rows = [_row("May 31", "", 1.0), _row("June 30", "0xaa", 0.0)]

    assert _drop(rows, open_=False) == rows


def test_a_wholly_unbacked_board_is_returned_unchanged_6524():
    """NEVER EMPTIES, matching the two siblings in this module."""
    rows = [_row("A", "", 1.0), _row("B", "", 1.0)]

    assert _drop(rows) == rows


def test_the_board_is_still_a_board_after_the_drop_6524():
    """A rule that REMOVES passes every refusal assertion on an empty list, so the
    surface has to be asserted as a surface. Production's six boards keep between
    3 and 13 backed legs each; the thinnest (112848) is built here."""
    rows = [
        _row("June 30", "", 1.0),
        _row("December 31", "0xaa", 0.0335),
        _row("March 31", "0xbb", 0.015),
        _row("September 30", "0xcc", 0.005),
    ]

    kept = _drop(rows)

    assert len(kept) == 3, "the board must still answer its own question"
    assert all(float(r.current_probability) < 0.95 for r in kept)


# ── Order, purity, and the other rows' numbers ───────────────────────────────


def test_order_is_preserved_and_the_input_is_not_mutated_6524():
    rows = [_row("A", "0xaa", 0.5), _row("B", "", 1.0), _row("C", "0xcc", 0.3)]
    before = list(rows)

    kept = _drop(rows)

    assert _names(kept) == ["A", "C"]
    assert rows == before


def test_dropping_a_leg_cannot_inflate_the_survivors_6524():
    """The failure mode that would make the repair worse than the defect.

    Removing a 1.0 from a five-leg ladder takes the field sum from 1.20 to 0.20.
    The #23 squeeze fires only ABOVE a sum of 105%, so it cannot reach the
    survivors afterwards — a 0.08 longshot must not be squeezed up into a false
    contender. Asserted through the real normalizer, not re-derived.
    """
    from app.utils.outcome_display import normalize_display_probs

    rows = [
        _row("May 31", "", 1.0),
        _row("September 30", "0xaa", 0.0805),
        _row("April 30", "0xbb", 0.056),
        _row("June 30", "0xcc", 0.04),
        _row("May 31", "0xdd", 0.02),
    ]

    kept = _drop(rows)
    dicts = [{"name": r.name, "probability": float(r.current_probability)} for r in kept]
    moved = normalize_display_probs(dicts, mutually_exclusive=True)

    assert moved is False
    assert [d["probability"] for d in dicts] == [0.0805, 0.056, 0.04, 0.02]


# ── The served payloads, not just the helper ─────────────────────────────────


def _board(**over):
    base = dict(
        id=113545, external_id="113545", name="Will Russia enter Borova by...?",
        description=None, sport=None, sport_name=None, category=None,
        llm_sport_category="geopolitics", status="open", source="polymarket",
        market_type="field", mutually_exclusive=False, commence_time=None,
        resolution_date=None, created_at=None, updated_at=None, group_id=None,
        canonical_market_key=None, hook_description=None, category_tags=None,
        image_url=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _detail_outcome(oid, name, ext, prob, winner=None, source=None):
    return SimpleNamespace(
        id=oid, name=name, external_id=ext,
        current_probability=prob, current_american_odds=-10000,
        rank=1, rank_change_24h=None, probability_change_24h=None,
        opening_probability=None, opening_american_odds=None,
        is_winner=winner, resolution_source=source, last_updated=None,
    )


def test_the_detail_payload_no_longer_serves_the_unbacked_row_6524():
    """A pure function nothing calls is inert — assert the SERIALIZER.

    113545's real shape, including the id-anchored ``May 31`` the unbacked row
    sat directly above. That duplicate label resolves here as a consequence, but
    by removing the row that is not a quote — never by picking a survivor.
    """
    from app.routes.futures import _format_market_detail

    board = _board(outcomes=[
        _detail_outcome(1, "May 31", "", 1.0),
        _detail_outcome(2, "September 30", "0xec843b00", 0.0805),
        _detail_outcome(3, "May 31", "0xec843b01", 0.02),
    ])

    served = _format_market_detail(board)
    names = [o["name"] for o in served["outcomes"]]

    assert 1.0 not in [o["probability"] for o in served["outcomes"]]
    assert names.count("May 31") == 1, names
    assert "September 30" in names
    assert served["outcome_count"] == len(served["outcomes"]), (
        "the count a reader is told must match the rows a reader is shown"
    )


def test_a_settled_board_still_serves_its_crowned_unbacked_row_6524():
    """The 139-row protection, at the serializer rather than the helper."""
    from app.routes.futures import _format_market_detail

    board = _board(status="resolved", outcomes=[
        _detail_outcome(1, "May 31", "", 1.0, winner=True, source="api_settlement"),
        _detail_outcome(2, "June 30", "0xaa", 0.0, winner=False, source="api_settlement"),
    ])

    served = _format_market_detail(board)

    assert "May 31" in [o["name"] for o in served["outcomes"]]


def test_the_search_card_stops_headlining_the_unbacked_row_6524():
    """3821229's shape at the other serializer: the fabricated leg is rank 1, so
    it is the top row of the card a reader meets first (#993 — the click-through
    has to match what search showed)."""
    from app.routes.events import _build_search_top_outcomes

    board = _board(
        id=3821229, external_id="3821229", name="GPT-5.5 released by...?",
        outcomes=[
            _detail_outcome(1, "April 8", "", 1.0),
            _detail_outcome(2, "December 31", "0xaa", 0.31),
            _detail_outcome(3, "June 30", "0xbb", 0.12),
        ],
    )

    top = _build_search_top_outcomes(board)

    assert top, "the card must still carry an answer"
    assert [o["name"] for o in top] == ["December 31", "June 30"]
