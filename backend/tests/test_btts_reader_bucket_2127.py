"""#2127 — the both-teams-to-score row stops being venue jargon on the page.

THE SHIP THESE GUARD. On 2026-09-22 `https://bainluck.com/events/15313874`
(Seattle Sounders FC vs Real Salt Lake, MLS, kickoff 2026-09-24 01:30Z) served
this card under **Additional Markets**::

    Seattle vs Salt Lake: BTTS
    Yes                                                    62%

A casual fan cannot expand "BTTS", and "Yes" on its own names nothing — the two
halves of the card each rely on the other to mean something, and neither says
it. The moneyline card immediately above it reads correctly. That is the whole
defect: the row is TRUE and unreadable.

WHY THE SHARED CLASSIFIER FIX DID NOT REACH IT. `0feb0f0f7` gave
`app/utils/game_market_class.py` a BTTS vocabulary, and that module is the
discriminator the settlement and blending gates key on. The event page does not
use it. `routes/events.py` carries its OWN coarse classifier,
`_classify_game_market`, and it had no BTTS arm either — so the reader-side half
of #2127 was untouched by the producer-side half. Measured on production the
same day, across 18,680 BTTS rows:

    reached `other`        18,612   served as a bare "Yes" under the venue's
                                    own abbreviation (the specimen above)
    reached `game_total`        68   the name contains "under" — Seattle
                                    So*under*s, S*under*land — and the
                                    over/under arm is a bare substring test

🔴 THE 68 ARE THE POINT, and they are the same defect class as the ticker arm
this issue already refused once. `game_market_class.py` rejected
`"btts" in external_id` because `btts` is not a series token — it is a substring
real GAME tickers hit inside their trailing TEAM-CODE pair. Here the identical
shape appears one layer up and in the other direction: `"under" in name` is a
substring test that hits the CLUB. A market wearing `game_total` is claiming to
price a quantity it does not price. The general clause both cases share:

    A SUBSTRING TEST FOR A MARKET KIND WILL EVENTUALLY MATCH A PROPER NOUN.
    Anchor it, or put the family's own name above it.

The arm added for this sits beside `_is_scoring_race_market` for the reason that
one's comment already gives — it would otherwise "rest on the title happening to
contain no over/under token". For BTTS that luck has demonstrably run out.

🔴 THE LOAD-BEARING CONSTRAINT ON THE NEW NAME, pinned by
`test_the_reader_facing_name_must_not_resurrect_the_fabricated_winner`.
`resolve_binary_matchup_outcome_name` renames a bare "Yes" to "<side> Win" when
the market name parses as a matchup, and its only guard is a colon in the TAIL —
which a REWRITTEN name no longer has. Its docstring names *Both Teams to Score*
as the case it was written for: reading those as moneylines printed "Cádiz CF
Win" on 217 of the 299 rows it touched. So a friendly-looking
"Seattle vs Salt Lake — Both teams to score" would match `_MONEYLINE_MATCHUP_RE`
and reprint a fabricated winner on this very row. The subject-only name is not a
style choice; it is what keeps the truthful "Yes" truthful, and the strawman is
asserted below rather than described.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes import events as events_route  # noqa: E402
from app.routes.events import (  # noqa: E402
    _PM_MARKET_PRICES_NEITHER_ARM,
    _btts_reader_facing_name,
    _classify_game_market,
    resolve_binary_matchup_outcome_name,
)

NOW = datetime(2026, 9, 22, 22, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 24, 1, 30, tzinfo=timezone.utc)

#: The three production rows whose TICKER contains "btts" while their NAME does
#: not. Every one is a basketball moneyline, resolved, feeding the win-prob
#: blend. They are why the ticker arm was refused and they are re-asserted here
#: because this module adds a second BTTS rule one layer away from that one.
TICKER_COLLISION_MONEYLINES = (
    "KXBSLGAME-26MAR220830MBBTTS",
    "KXEUROCUPGAME-26APR031300JLBTTS",
    "KXBSLGAME-26APR181100YMBTTS",
)

KALSHI_SPECIMEN = "Seattle vs Salt Lake: BTTS"
KALSHI_SPECIMEN_TICKER = "KXMLSBTTS-26SEP23SEARSL"
POLYMARKET_SPECIMEN = "Aruba vs. Antigua and Barbuda: Both Teams to Score"


# ── the classifier arm ────────────────────────────────────────────────────


def test_the_kalshi_abbreviation_is_no_longer_filed_under_other():
    assert _classify_game_market(KALSHI_SPECIMEN, KALSHI_SPECIMEN_TICKER) == "btts"


def test_the_polymarket_spelling_is_no_longer_filed_under_other():
    assert _classify_game_market(POLYMARKET_SPECIMEN, "0x386f8adc") == "btts"


def test_a_club_named_sounders_no_longer_makes_its_btts_row_a_game_total():
    """The 68-row cohort: the club supplies the "under", not the market kind.

    Written as a DIFFERENCE between two clubs on one market family, so no single
    lucky return value satisfies it — the point is that the two agree, and
    before this arm they did not.
    """
    with_under = _classify_game_market(
        "Seattle Sounders vs. Portland Timbers: Both Teams to Score", "0xdead"
    )
    without_under = _classify_game_market(
        "Aruba vs. Antigua and Barbuda: Both Teams to Score", "0xbeef"
    )
    assert with_under == without_under == "btts"
    assert with_under != "game_total"


def test_sunderland_is_the_same_defect_as_sounders():
    assert _classify_game_market("Sunderland vs Arsenal: BTTS", "KXEPLBTTS-26SEP19SUNARS") == "btts"


@pytest.mark.parametrize("ticker", TICKER_COLLISION_MONEYLINES)
def test_the_three_ticker_collision_rows_keep_their_moneyline(ticker):
    assert _classify_game_market("Bahcesehir Koleji vs Turk Telekom", ticker) == "moneyline"


def test_the_ticker_is_never_consulted_for_btts():
    """One name, two tickers; and one ticker, two names. Both must ignore it.

    A rule that read the ticker would split the first pair and join the second.
    """
    assert _classify_game_market(KALSHI_SPECIMEN, KALSHI_SPECIMEN_TICKER) == _classify_game_market(
        KALSHI_SPECIMEN, "KXBSLGAME-26MAR220830MBBTTS"
    )
    assert _classify_game_market(
        "Bahcesehir Koleji vs Turk Telekom", "KXBSLGAME-26MAR220830MBBTTS"
    ) != _classify_game_market(KALSHI_SPECIMEN, "KXBSLGAME-26MAR220830MBBTTS")


def test_btts_prices_neither_arm_of_the_game():
    """#3948 discipline: a new label owes a decision in the projection sets."""
    assert "btts" in _PM_MARKET_PRICES_NEITHER_ARM


# ── the reader-facing name ────────────────────────────────────────────────


def test_the_reader_facing_name_says_what_the_market_asks():
    assert _btts_reader_facing_name(KALSHI_SPECIMEN) == "Both teams to score"
    assert _btts_reader_facing_name(POLYMARKET_SPECIMEN) == "Both teams to score"


def test_a_half_scoped_btts_keeps_its_half():
    assert (
        _btts_reader_facing_name("FC Barcelona vs. Paris FC: Both Teams to Score in First Half")
        == "Both teams to score (1st half)"
    )
    assert (
        _btts_reader_facing_name("FC Barcelona vs. Paris FC: Both Teams to Score in Second Half")
        == "Both teams to score (2nd half)"
    )


def test_the_reader_facing_name_must_not_resurrect_the_fabricated_winner():
    """The strawman is asserted, not described (see the module docstring).

    `resolve_binary_matchup_outcome_name` is the function that stopped "Cádiz CF
    Win" appearing on BTTS rows. Its guard is a colon in the tail. A rewritten
    name has no colon, so keeping the matchup in it hands the guard nothing —
    and the fabricated winner comes straight back.
    """
    # What we serve: the bare "Yes" survives, which is what the card needs.
    for served in (
        _btts_reader_facing_name(KALSHI_SPECIMEN),
        _btts_reader_facing_name("X vs Y: Both Teams to Score in First Half"),
    ):
        assert resolve_binary_matchup_outcome_name("Yes", served) == "Yes"
        assert resolve_binary_matchup_outcome_name("No", served) == "No"

    # The tempting alternative, and why it is refused.
    assert (
        resolve_binary_matchup_outcome_name("Yes", "Seattle vs Salt Lake - Both teams to score")
        == "Seattle Win"
    )


# ── the served payload ────────────────────────────────────────────────────


def _result(*, scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _market(*, id, name, external_id, source="kalshi"):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, external_id
    market.event_id, market.category, market.status = 42, "game_prop", "open"
    market.source, market.sport_id = source, 1
    market.llm_sport_category = "soccer"
    market.commence_time = KICKOFF
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _outcome(*, id, market_id, name, prob):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = prob
    outcome.is_winner = None
    outcome.resolution_source = None
    outcome.last_updated = NOW
    return outcome


def _event():
    event = MagicMock()
    event.id, event.status, event.sport_id = 42, "scheduled", 1
    event.sport = MagicMock()
    event.sport.key = "soccer_usa_mls"
    event.home_team_name, event.away_team_name = "Seattle Sounders FC", "Real Salt Lake"
    event.home_score = event.away_score = None
    event.commence_time = KICKOFF
    event.completed_at = None
    event.box_score_data = None
    event.period, event.game_clock = None, None
    return event


def _db(markets, outcomes):
    rows = [
        SimpleNamespace(
            id=o.id,
            observed_at=NOW - timedelta(minutes=30),
            price_changed_at=None,
            resolution_source=None,
            current_probability=None,
        )
        for o in outcomes
    ]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=_event()),
            _result(rows=[]),          # #2693 folded_event_ids
            _result(rows=markets),
            _result(all_rows=[]),      # polymarket parent groups
            _result(rows=[]),          # unlinked fallback
            _result(rows=outcomes),
            _result(all_rows=rows),    # #4970 the observation load
        ]
    )
    return db


def _sounders_page():
    """The specimen page: the moneyline that reads correctly, and the BTTS row.

    The moneyline is a KNOWN-GOOD CONTROL and not decoration. A hand-built fake
    whose shape is slightly wrong makes the builder serve nothing, which would
    read exactly like a BTTS row being correctly withheld. If the control card
    is absent the rig is broken and the BTTS assertions mean nothing.
    """
    moneyline = _market(
        id=601, name="Seattle vs Salt Lake", external_id="KXMLSGAME-26SEP23SEARSL"
    )
    btts = _market(id=602, name=KALSHI_SPECIMEN, external_id=KALSHI_SPECIMEN_TICKER)
    outcomes = [
        _outcome(id=701, market_id=601, name="Seattle", prob=0.52),
        _outcome(id=702, market_id=601, name="Tie", prob=0.25),
        _outcome(id=703, market_id=601, name="Salt Lake", prob=0.24),
        _outcome(id=704, market_id=602, name="Yes", prob=0.62),
    ]
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(42, _db([moneyline, btts], outcomes))
    )
    return response


def test_the_control_moneyline_card_still_reads_correctly():
    """Proves the rig serves this page at all — see `_sounders_page`."""
    other = _sounders_page()["other"]
    moneyline_legs = [r for r in other if r["market_name"] == "Seattle vs Salt Lake"]
    assert {r["outcome_name"] for r in moneyline_legs} == {"Seattle", "Tie", "Salt Lake"}


def test_the_page_serves_the_btts_row_under_a_readable_heading():
    other = _sounders_page()["other"]
    btts_legs = [r for r in other if r["market_name"] == "Both teams to score"]
    assert len(btts_legs) == 1, f"expected one BTTS row, got {other}"
    assert btts_legs[0]["outcome_name"] == "Yes"
    assert btts_legs[0]["probability"] == pytest.approx(0.62)


def test_the_venue_abbreviation_never_reaches_the_reader():
    payload = _sounders_page()
    for bucket in payload.values():
        if not isinstance(bucket, list):
            continue
        for row in bucket:
            assert "BTTS" not in (row.get("market_name") or "")


def test_both_venues_btts_arrive_under_one_heading():
    """The largest consequence of the rename, and it is the ruled-for one.

    Measured on production 2026-09-22: of 7,459 event-linked BTTS fixtures, 330
    carry the market from BOTH venues. Today those serve two cards, because the
    venues spell the same question differently (": BTTS" / ": Both Teams to
    Score") and `buildMarketSection` groups the `other` bucket by `market_name`.

    One heading is what the frontend's existing `mergeOutcomes` needs to do the
    right thing with them: same-labelled rows collapse to ONE row, and when the
    two venues disagree beyond `AGREEMENT_TOLERANCE` the label is WITHHELD
    rather than shown twice. That is Alex's standing ruling — one number per
    question, source divergence is a data bug and not a thing to show — and it
    is also #6799, where a duplicated winner card printed Crystal Palace at both
    99% and >99%. This test owns the backend half: both rows leave here under
    the same heading, so the merge can happen at all.
    """
    kalshi = _market(id=602, name=KALSHI_SPECIMEN, external_id=KALSHI_SPECIMEN_TICKER)
    polymarket = _market(
        id=603,
        name="Seattle Sounders FC vs. Real Salt Lake: Both Teams to Score",
        external_id="0xfeed",
        source="polymarket",
    )
    moneyline = _market(
        id=601, name="Seattle vs Salt Lake", external_id="KXMLSGAME-26SEP23SEARSL"
    )
    outcomes = [
        _outcome(id=701, market_id=601, name="Seattle", prob=0.52),
        _outcome(id=702, market_id=601, name="Tie", prob=0.25),
        _outcome(id=703, market_id=601, name="Salt Lake", prob=0.24),
        _outcome(id=704, market_id=602, name="Yes", prob=0.62),
        _outcome(id=705, market_id=603, name="Yes", prob=0.63),
    ]
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(
            42, _db([moneyline, kalshi, polymarket], outcomes)
        )
    )
    btts = [r for r in response["other"] if r["market_name"] == "Both teams to score"]
    assert {r["source"] for r in btts} == {"kalshi", "polymarket"}
    # The control: the moneyline is still its own card and did not absorb them.
    assert len({r["market_name"] for r in response["other"]}) == 2


def test_the_btts_card_is_not_folded_into_the_match_winner_card():
    """One card per question. Renaming must not merge it into the moneyline."""
    other = _sounders_page()["other"]
    headings = {r["market_name"] for r in other}
    assert "Seattle vs Salt Lake" in headings
    assert "Both teams to score" in headings
