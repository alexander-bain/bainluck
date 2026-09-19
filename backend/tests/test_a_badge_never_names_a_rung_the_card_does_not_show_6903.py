"""#6903's residual: a movement badge whose number belongs to a rung the card
never shows, printed above the rung it does.

The specimen was photographed on production 2026-09-19 03:55Z, `/categories/tech`
at 390px (`artifacts-discover/shop-0340Z/tech-ailab-30pts-390px.png`). One card
header carried two movement numbers three lines apart:

    badge    Odds up 30 points          <- December 31, 2026's move
    title    AI lab announces another Millennium Prize solution?
    caption  51% chance by December 31, 2027
    rail     51%  ·  December 31, 2027  ·  +13.5 pts   <- the card's own number

`_weak_outcome_label` refuses a bare date as a subject, so the movement
templates substituted the market title — which turns one rung's move into a
claim about a board that has no single probability to move.

Every case below is one of the four movement templates, because the defect is
shared and a repair in one is not a repair in the others. The two cases marked
UNCHANGED are the load-bearing half: this ship must not empty a sentence that
was already honest.
"""

import app.utils.feed_reasons as fr

# The specimen, verbatim from the served payload at 03:40Z
# (`GET /api/feed?limit=60&category=tech`, card 33, market 60518652).
MARKET = "AI lab announces another Millennium Prize solution?"
LEADER = "December 31, 2027"  # 51%, +13.5 — the rung the card leads with
MOVER = "December 31, 2026"  # 38%, +30.0 — the rung the badge was quoting


def test_the_badge_names_the_rung_that_moved_not_the_whole_board():
    """The photographed card. The badge may not borrow the title."""
    headline = fr.generate_futures_headline(
        market_name=MARKET,
        highlight_reasons=["major_movement_24h"],
        top_mover_name=MOVER,
        top_mover_change=0.30,
        leader_name=LEADER,
        leader_probability=0.5091,
    )
    assert headline == "December 31, 2026 up 30 points today", headline
    # The exact string the reader saw, and the reason it was wrong: it put the
    # board's name in front of one rung's number.
    assert "AI lab announces" not in headline


def test_the_reason_slot_delivers_the_move_once_the_rung_is_nameable():
    """The `reason` rung refused the NUMBER rather than make that claim.

    It was right to refuse while the subject was unnameable; on a dated board
    the subject is available, so the vaguer sentence is no longer the honest
    one — it is just a sentence with the news taken out.
    """
    reason = fr.generate_futures_reason(
        market_name=MARKET,
        highlight_reasons=["major_movement_24h"],
        top_mover_name=MOVER,
        top_mover_change=0.30,
        leader_name=LEADER,
        leader_probability=0.5091,
    )
    assert reason == (
        "December 31, 2026 moved up 30 points today in "
        "AI lab announces another Millennium Prize solution?"
    ), reason


def test_the_moderate_rungs_move_with_the_major_ones():
    """Both generators repeat the branch verbatim; both must be repaired."""
    headline = fr.generate_futures_headline(
        market_name=MARKET,
        highlight_reasons=["moderate_movement_24h"],
        top_mover_name=MOVER,
        top_mover_change=0.045,
        leader_name=LEADER,
        leader_probability=0.5091,
    )
    reason = fr.generate_futures_reason(
        market_name=MARKET,
        highlight_reasons=["moderate_movement_24h"],
        top_mover_name=MOVER,
        top_mover_change=0.045,
        leader_name=LEADER,
        leader_probability=0.5091,
    )
    assert headline == "December 31, 2026 up 4.5 points today", headline
    assert reason.startswith(
        "December 31, 2026 odds shifted up 4.5 points today in "
    ), reason


def test_UNCHANGED_when_the_rung_that_moved_IS_the_rung_the_card_leads_with():
    """`Friedrich Merz out as Chancellor of Germany odds up 2 points`.

    Served the same minute as the specimen, and NOT a defect: the mover is the
    leader, so the rail prints this number beside this rung and the market
    phrasing contradicts nothing. Rewriting it would cost the caption its level
    clause (`generate_futures_context_summary` swaps in the leader only while
    the headline restates the market), so it stays exactly as it renders today.
    """
    headline = fr.generate_futures_headline(
        market_name="Friedrich Merz out as Chancellor of Germany?",
        highlight_reasons=["major_movement_24h"],
        top_mover_name="December 31, 2026",
        top_mover_change=0.02,
        leader_name="December 31, 2026",
        leader_probability=0.275,
    )
    assert headline == (
        "Friedrich Merz out as Chancellor of Germany odds up 2 points"
    ), headline


def test_UNCHANGED_when_the_caller_does_not_say_what_the_card_leads_with():
    """No `leader_name` means the contradiction cannot be detected, so the
    sentence a caller renders today is the sentence it keeps. Two live tests
    (#4056, #5619) pin this shape and must stay green without being edited."""
    headline = fr.generate_futures_headline(
        market_name="Will Utah Mammoth advance to the Second Round of the Stanley Cup Playoffs?",
        highlight_reasons=["major_movement_24h"],
        top_mover_name="June 30, 2027",
        top_mover_change=0.08,
    )
    assert headline.endswith(" odds up 8 points"), headline


def test_a_numeric_board_is_left_alone_deliberately():
    """`How many more Millennium Prize Problems will AI solve in 2026?` — the
    `0` rung fell 39 points and IS the leader, so this is the UNCHANGED case
    above, reached by a different label class. Recorded because the sentence is
    still loose ("odds down" on a count question) and the next reader of this
    file should know it was seen and left, not missed."""
    headline = fr.generate_futures_headline(
        market_name="How many more Millennium Prize Problems will AI solve in 2026?",
        highlight_reasons=["major_movement_24h"],
        top_mover_name="0",
        top_mover_change=-0.39,
        leader_name="0",
        leader_probability=0.41,
    )
    assert headline.endswith(" odds down 39 points"), headline


def test_an_unnameable_rung_that_is_not_the_leader_gets_NO_number():
    """The manufactured third state, which has no specimen on production today.

    A mixed board — a named leader, a numeric rung moving — can neither name the
    mover nor hand its number to the market. There is no honest movement
    sentence, so the card falls through to a clause it can support rather than
    printing a number about a row the reader cannot find.
    """
    headline = fr.generate_futures_headline(
        market_name="Who will win the nomination?",
        highlight_reasons=["major_movement_24h", "resolving_soon_30d"],
        top_mover_name="102",
        top_mover_change=0.44,
        leader_name="Gavin Newsom",
        leader_probability=0.37,
    )
    assert "44 points" not in headline, headline
    assert "odds up" not in headline, headline
    # It fell through to the next signal rather than emptying the card.
    assert headline, "the card was left with nothing to say"


def test_the_resolver_is_shared_so_a_fifth_template_inherits_it():
    """The four templates read one function; that is the guard against the
    class. Pinned directly so deleting the sharing shows up here even if a
    future template is added without a test of its own."""
    assert fr.movement_subject(MOVER, LEADER) == fr.MOVEMENT_SUBJECT_NAMED
    assert (
        fr.movement_subject("December 31, 2026", "December 31, 2026")
        == fr.MOVEMENT_SUBJECT_MARKET
    )
    assert fr.movement_subject("102", "Gavin Newsom") == fr.MOVEMENT_SUBJECT_SILENT
    assert fr.movement_subject("Above 102", None) == fr.MOVEMENT_SUBJECT_NAMED
    assert fr.movement_subject(None, "December 31, 2026") == fr.MOVEMENT_SUBJECT_MARKET
