"""#6243 — a golf ticker plus a tournament question is golf, even with no golf word.

THE DEFECT, production 2026-09-28. `/categories/golf` opened on "Alfred Dunhill
Links Championship — Win Probability" and printed "Limited price history
available". Kalshi's field for the same question, id 62455818 "Alfred Dunhill Links
Championship Winner" (`KXDPWORLDTOUR-ALDLC26`, 120 points over 8 timestamps), was
absent from `/api/golf`: the name carries no word `_GOLF_SIGNAL_RE` knows, and the
ticker that declares the tour was only ever read for names that had already passed.

THE RULE. A no-signal name is admitted when BOTH the Kalshi ticker declares golf and
the name asks a tournament question (Winner / Round N Leader / Top N Finishers).
Measured over the 3,776 golf-identity rows with a golf ticker: 216 admitted (211
resolved, 5 open), 0 lost. Of today's 69 open golf markets, 5 are admitted and only
the Dunhill card changes (the other four are prop-only fields, which carry no golfer
list and are dropped as before).

Every specimen is a real production row.
"""

import types

import pytest

from app.routes.golf import _GOLF_SIGNAL_RE, _is_golf_market


def _market(name, external_id, source="kalshi"):
    return types.SimpleNamespace(source=source, external_id=external_id, name=name)


ADMITTED = [
    # id 62455818 — the week's traded Winner field, the ship
    ("Alfred Dunhill Links Championship Winner", "KXDPWORLDTOUR-ALDLC26"),
    # id 62952894
    ("Alfred Dunhill Links Championship End of Round 1 Leader", "KXDPWORLDTOURR1LEAD-ALDLC26"),
    # id 61003871 — the issue's original specimen
    ("Biltmore Championship Asheville Winner", "KXPGATOUR-BICA26"),
    # id 62383751 — LPGA
    ("Walmart NW Arkansas Championship presented by P&G End of Round 2 Leader",
     "KXLPGAR2LEAD-WALNACPBP26"),
    # resolved — singular "Finisher"
    ("Valspar Championship Top 20 Finisher", "KXPGATOP20-VAC26"),
    # resolved — no tournament word at all
    ("Charles Schwab Challenge Winner", "KXPGATOUR-CSC26"),
]


@pytest.mark.parametrize("name,external_id", ADMITTED)
def test_golf_ticker_and_tournament_question_is_golf(name, external_id):
    assert not _GOLF_SIGNAL_RE.search(name), "specimen must be one the name gate refuses"
    assert _is_golf_market(_market(name, external_id)) is True


def test_dpwt_ticker_corroborates_a_weak_only_name():
    # id 62383753 — "Open" is weak-only, so this rides the Q446 corroboration arm,
    # which could not read Kalshi's abbreviated `KXDPWT…` series before #6243.
    assert _is_golf_market(
        _market("Fedex Open De France: Top 5 Finishers", "KXDPWTTOP5-FEODF26")
    ) is True


REFUSED = [
    # ids 62734166… — golf, but a match inside the Presidents Cup, not a tournament
    ("Singles: Xander Schauffele vs Ryan Fox", "KXPRESCUPMATCH-27SEP26R5M12"),
    # id 176 — not a golf ticker
    ("Will Scottie Scheffler win the grand slam before 2028?", "KXSCOTTIESLAM-28"),
    # a tournament question under a ticker that does not declare golf
    ("Alfred Dunhill Links Championship Winner", "KXFOO-ALDLC26"),
    ("Chennai Grand Masters Championship Winner", "KXCHESSTOURNAMENT-26CHGM"),
    # a golf ticker on a name that is not a tournament question
    ("Alfred Dunhill Links Championship: Playoff?", "KXDPWORLDTOUR-ALDLC26"),
]


@pytest.mark.parametrize("name,external_id", REFUSED)
def test_either_half_alone_is_not_enough(name, external_id):
    assert _is_golf_market(_market(name, external_id)) is False


def test_polymarket_ids_never_read_as_a_golf_ticker():
    assert _is_golf_market(
        _market("Alfred Dunhill Links Championship Winner", "602824", source="polymarket")
    ) is False


def test_winner_must_end_the_name():
    # "Winner" mid-name is a different question ("… Winner's Score"), not the field
    assert _is_golf_market(
        _market("Alfred Dunhill Links Championship Winner's Score", "KXDPWORLDTOUR-ALDLC26")
    ) is False
