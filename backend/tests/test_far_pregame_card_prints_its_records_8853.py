"""#8853 — a game four hours out prints the records its near siblings print.

Production, 2026-09-26 15:55Z, anonymous `/api/feed`: slots 1 and 2 (Mets @
Nationals in 45m, Pirates @ Tigers in 1h) carried `NYM 73-87 · WSH 76-84` and
`PIT 81-79 · DET 75-85`. Slot 3, Braves @ Marlins (event 15319168) in 4h, had
`headline: null`, no `highlight` block, and printed nothing under its bar —
while its payload held `ATL 93-67` and `MIA 79-81`.

`get_highlight_label` gives no bucket to a game that is not yet "starting
soon", and #6567's pass only replaced the bucket label. These tests pin the new
arm and the three things it must not do: overwrite a caption, touch a game
that is not `scheduled`, or move rank.
"""

import pytest

from app.routes.feed import (
    _DISCOVER_EVENT_EXCEPTION_KEYWORDS,
    _is_discover_event_demotion_exception,
    apply_pregame_record_caption,
)


def _far_card(
    *,
    headline=None,
    highlight=None,
    status="scheduled",
    away=("ATL", "93-67"),
    home=("MIA", "79-81"),
):
    """The served slot-3 shape: no caption, no pill, both records present."""
    data = {
        "id": 15319168,
        "status": status,
        "away_team": "Atlanta Braves",
        "home_team": "Miami Marlins",
        "commence_time": "2026-09-26T20:10:00+00:00",
        "highlight": highlight,
    }
    if away is not None:
        data["away_team_data"] = {"abbreviation": away[0], "record": away[1]}
    if home is not None:
        data["home_team_data"] = {"abbreviation": home[0], "record": home[1]}
    return {"type": "event", "headline": headline, "reason": "", "data": data}


def test_the_production_specimen_prints_both_records():
    items = [_far_card()]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == "ATL 93-67 · MIA 79-81"


@pytest.mark.parametrize(
    "headline,highlight",
    [(None, None), ("", None), (None, {}), ("", {"label": None}), (None, {"label": ""})],
)
def test_every_spelling_of_no_caption_is_captioned(headline, highlight):
    items = [_far_card(headline=headline, highlight=highlight)]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == "ATL 93-67 · MIA 79-81"


def test_the_reason_stays_byte_identical():
    """The page-one floor and explanation coverage read `reason`, not the caption."""
    items = [_far_card()]
    apply_pregame_record_caption(items)
    assert items[0]["reason"] == ""


@pytest.mark.parametrize(
    "status", ["live", "completed", "closed", "postponed", "", None]
)
def test_only_a_scheduled_game_gains_a_caption(status):
    """A final's blank is a scoreline's space; an unknown state keeps its blank."""
    items = [_far_card(status=status)]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] is None


def test_a_card_with_a_pill_but_no_caption_is_left_alone():
    """Pill and caption have diverged; that is not a card this pass wrote."""
    items = [_far_card(headline=None, highlight={"label": "Rivalry game"})]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] is None


def test_a_specific_caption_is_never_overwritten():
    items = [_far_card(headline="Braves clinch with a win")]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == "Braves clinch with a win"


@pytest.mark.parametrize(
    "away,home",
    [(None, ("MIA", "79-81")), (("ATL", None), ("MIA", "79-81")), (("", "93-67"), ("MIA", "79-81"))],
)
def test_one_record_is_never_printed(away, home):
    items = [_far_card(away=away, home=home)]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] is None


def test_the_caption_cannot_move_the_demotion_predicate():
    """On a label-less card the predicate falls back to `headline`; the records
    text holds no exception keyword, so the verdict is identical either side."""
    before = _far_card()
    after = _far_card()
    apply_pregame_record_caption([after])
    assert after["headline"] == "ATL 93-67 · MIA 79-81"
    assert _is_discover_event_demotion_exception(
        after
    ) == _is_discover_event_demotion_exception(before)


@pytest.mark.parametrize("keyword", _DISCOVER_EVENT_EXCEPTION_KEYWORDS)
def test_a_caption_holding_an_exception_keyword_is_refused(keyword):
    """Rank-neutral by construction: an abbreviation that happened to spell a
    keyword would otherwise hand a label-less card the demotion exception."""
    items = [_far_card(away=(keyword.upper(), "93-67"))]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] is None


def test_the_pass_is_idempotent():
    items = [_far_card()]
    apply_pregame_record_caption(items)
    once = items[0]["headline"]
    apply_pregame_record_caption(items)
    assert items[0]["headline"] == once
