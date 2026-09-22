"""#6567 — a pregame game card stops captioning itself with the bar it draws.

The defect, measured on production 2026-09-22 19:44Z (`/api/feed?limit=120`,
cache MISS, 106 items): the three unsettled game cards on page one were slots
0, 1 and 2, home prices 0.5279 / 0.56 / 0.54, and all three carried the single
caption ``Close matchup`` — the only repeated headline on the page. The card
prints that same fact one line above, in colour, as a probability bar, and the
label reads identically anywhere in the twenty-point ``[0.40, 0.60]`` band.

The ship replaces that caption with the two teams' season records, which the
payload already carries and the card does not print.

WHAT THESE TESTS ARE FOR, BEYOND "IT WORKS"
-------------------------------------------
Three properties are the whole reason this shape was chosen over yielding the
line, and each is asserted here because each is one careless edit from being
lost:

* ``reason`` is byte-identical — it carries the ``starting soon`` why-now marker
  and it is what keeps ``explanation-coverage@20`` at 20/20. Blank both fields
  and the Flow Sentinel files nightly.
* ``data.highlight.label`` is byte-identical — it is the field
  ``_is_discover_event_demotion_exception`` reads, so the caption change cannot
  move a card's rank.
* the pass FAILS TO TODAY'S COPY. Every unknown returns the string the site
  serves now; a caption is never invented.
"""

import pytest

from app.routes.feed import apply_pregame_record_caption
from app.utils.feed_reasons import (
    PREGAME_CLOSE_MATCHUP_LABEL,
    pregame_records_caption,
)


def _card(
    *,
    headline=PREGAME_CLOSE_MATCHUP_LABEL,
    label=PREGAME_CLOSE_MATCHUP_LABEL,
    status="scheduled",
    away=("TOR", "77-80"),
    home=("BAL", "76-81"),
    item_type="event",
):
    data = {
        "id": 15316846,
        "status": status,
        "away_team": "Toronto Blue Jays",
        "home_team": "Baltimore Orioles",
        "highlight": {"label": label} if label is not None else {},
    }
    if away is not None:
        data["away_team_data"] = {"abbreviation": away[0], "record": away[1]}
    if home is not None:
        data["home_team_data"] = {"abbreviation": home[0], "record": home[1]}
    return {
        "type": item_type,
        "headline": headline,
        "reason": "Starting soon — close matchup",
        "data": data,
    }


# ── The ship ─────────────────────────────────────────────────────────────────


def test_the_page_one_specimen_stops_restating_its_own_bar():
    """The 2026-09-22 slot-0 card, with its production values."""
    items = [_card()]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == "TOR 77-80 · BAL 76-81"


def test_two_close_games_that_looked_identical_no_longer_do():
    """Acceptance 3: the caption separates cards the bucket label could not.

    Both of these are ``close_matchup`` and both read ``Close matchup`` today.
    The bucket cannot tell them apart at any threshold; two records always can.
    """
    items = [
        _card(away=("TOR", "77-80"), home=("BAL", "76-81")),
        _card(away=("MIL", "98-58"), home=("PHI", "86-70")),
    ]
    apply_pregame_record_caption(items)
    captions = [i["headline"] for i in items]
    assert captions == ["TOR 77-80 · BAL 76-81", "MIL 98-58 · PHI 86-70"]
    assert captions[0] != captions[1]


def test_the_away_team_is_named_first_because_the_card_heading_is():
    """``{away} @ {home}`` is the heading and the away price draws on the left.

    A caption in the other order makes the reader map two crests onto two
    records backwards — worse than the label it replaces, not better.
    """
    caption = pregame_records_caption(
        away_label="TOR", away_record="77-80", home_label="BAL", home_record="76-81"
    )
    assert caption is not None
    assert caption.index("TOR") < caption.index("BAL")


# ── The two fields that must not move ────────────────────────────────────────


def test_the_reason_is_byte_identical_so_explanation_coverage_cannot_fall():
    """`has_specific_explanation` reads `reason`; emptying it reds the sentinel."""
    items = [_card()]
    before = items[0]["reason"]
    apply_pregame_record_caption(items)
    assert items[0]["reason"] == before == "Starting soon — close matchup"


def test_the_highlight_label_is_byte_identical_so_the_rank_cannot_move():
    """`_is_discover_event_demotion_exception` reads the PILL, not the caption.

    T10-1 retargeted it off `headline` for exactly this reason. If a later edit
    rewrites the label as well as the caption, a truth fix silently becomes a
    ranking change.
    """
    items = [_card()]
    apply_pregame_record_caption(items)
    assert items[0]["data"]["highlight"]["label"] == PREGAME_CLOSE_MATCHUP_LABEL
    assert items[0]["headline"] != items[0]["data"]["highlight"]["label"]


# ── Fail to today's copy: every unknown keeps the served string ──────────────


@pytest.mark.parametrize(
    "kwargs,why",
    [
        ({"away": None}, "no away team row at all"),
        ({"home": None}, "no home team row at all"),
        ({"away": ("TOR", None)}, "away record missing"),
        ({"home": ("BAL", "")}, "home record blank"),
        ({"away": (None, "77-80")}, "away abbreviation missing"),
        ({"home": ("", "76-81")}, "home abbreviation blank"),
        ({"away": ("TOR", "TBD")}, "a placeholder is not a record"),
        ({"home": ("BAL", "2nd in AL East")}, "a table position is not a record"),
    ],
)
def test_an_unknown_keeps_the_caption_the_site_serves_today(kwargs, why):
    items = [_card(**kwargs)]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == PREGAME_CLOSE_MATCHUP_LABEL, why


def test_one_record_beside_a_nameless_opponent_is_never_printed():
    """A comparison with one arm reads as a fact about the wrong team."""
    assert (
        pregame_records_caption(
            away_label="TOR", away_record="77-80", home_label="BAL", home_record=None
        )
        is None
    )


def test_a_three_column_record_is_a_record():
    """NHL and soccer carry a third column; the card prints it as the league does."""
    assert (
        pregame_records_caption(
            away_label="BOS",
            away_record="12-4-3",
            home_label="NYR",
            home_record="9-8-2",
        )
        == "BOS 12-4-3 · NYR 9-8-2"
    )


# ── Everything this pass must not touch ──────────────────────────────────────


def test_a_card_that_already_earned_a_sentence_is_never_overwritten():
    """A rivalry tag, a line move, a live claim — all outrank the bucket label.

    The pass fires only where BOTH the caption and the pill are the bucket, so a
    card whose caption says something specific keeps it.
    """
    items = [_card(headline="Rivalry game", label="Rivalry game")]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == "Rivalry game"


def test_a_caption_that_disagrees_with_its_own_pill_is_left_alone():
    """Two fields, one decision: if they have already diverged, this is not ours."""
    items = [_card(headline=PREGAME_CLOSE_MATCHUP_LABEL, label="Upset brewing")]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == PREGAME_CLOSE_MATCHUP_LABEL


def test_a_specific_caption_over_a_bucket_pill_survives_this_pass():
    """The other direction of the same divergence, and a FORWARD guard.

    Today a pregame card's caption and pill are one call
    (`routes/feed.py`: `headline` is `get_highlight_label(...)` whenever the
    live-claim selector declines), so this shape is not reachable on the pregame
    path and the caption gate looks redundant — a mutation that deletes it
    survives every other specimen in this file.

    It is not redundant. T10-1 already made `headline` diverge from
    `data.highlight.label` on the LIVE path, which is the same composition site;
    the next lane to give a pregame card a specific sentence reaches this shape,
    and without the gate this pass would overwrite the sentence it just wrote.
    """
    items = [
        _card(
            headline="Brewers chasing the division", label=PREGAME_CLOSE_MATCHUP_LABEL
        )
    ]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == "Brewers chasing the division"


@pytest.mark.parametrize("status", ["live", "completed", "closed"])
def test_a_settled_or_live_card_never_prints_two_season_records(status):
    """A scoreline is the story once the game starts; a season record is not."""
    items = [_card(status=status)]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == PREGAME_CLOSE_MATCHUP_LABEL


def test_a_futures_card_is_not_a_game_and_is_untouched():
    items = [_card(item_type="futures")]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == PREGAME_CLOSE_MATCHUP_LABEL


def test_an_item_with_no_highlight_block_keeps_its_caption():
    """The one caption-sensitive ranking row: a label-less card's headline IS the
    ranking input, so this pass must never be the thing that rewrites it."""
    items = [_card(label=None)]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == PREGAME_CLOSE_MATCHUP_LABEL


def test_one_malformed_item_does_not_cost_the_page_its_captions():
    """Gotcha #42 — a feed pass that raises loses every card, not one."""
    items = [
        {"type": "event", "headline": PREGAME_CLOSE_MATCHUP_LABEL, "data": None},
        _card(),
    ]
    apply_pregame_record_caption(items)
    assert items[1]["headline"] == "TOR 77-80 · BAL 76-81"


def test_the_pass_is_idempotent():
    """It rewrites only the bucket label, so a second run finds nothing to do."""
    items = [_card()]
    apply_pregame_record_caption(items)
    once = items[0]["headline"]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == once


def test_an_empty_page_is_not_an_error():
    apply_pregame_record_caption([])
