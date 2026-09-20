"""THE LEAGUE PAGE STOPS CALLING THE NFL "PRO FOOTBALL". #7397, second surface.

═══ WHAT A READER SAW, PHOTOGRAPHED ═══

`bainluck.com/sport/americanfootball/nfl`, production, 2026-09-20 ~07:45Z, LOOK
at 390px. The page's own title is **NFL**. Scrolled to y≈18,900, four consecutive
card headers:

    PRO FOOTBALL: NEW YORK J TOTAL WINS
    PRO FOOTBALL: JACKSONVILLE TOTAL WINS
    PRO FOOTBALL: ATLANTA TOTAL WINS
    PRO FOOTBALL: LOS ANGELES R TOTAL WINS

A DOM walk of the rendered page (`tools/venue-vocab-onscreen-7397.mjs`) counts
**28 painted text nodes** carrying the venue's league word, from y=8,385 to
y=23,484. This is not a payload curiosity — it is the surface.

═══ SCOPE, MEASURED RATHER THAN GUESSED ═══

All 29 league `sport_key`s' SERVED payloads were swept for
`\\bPro (Football|Basketball|Hockey|Baseball)\\b`. Four carry it:

    /sport/football/nfl    (americanfootball_nfl)   33
    /sport/basketball/nba  (basketball_nba)         32
    /sport/baseball/mlb    (baseball_mlb)           24
    /sport/basketball/wnba (basketball_wnba)        23   <- all "Women's Pro Basketball"

`/api/feed`, `/api/politics` and `/api/entertainment` carry **zero**, which is
why this ship is the league page and not "everywhere that serializes a name".
The NHL page carries zero because no `Pro Hockey` row exists in production.

═══ THE THREE DOORS ═══

The payload keys that carried it map to exactly three serializer sites, all in
`routes/league_futures.py`:

    sections.*[].name                 -> build_league          (line ~2677)
    sections.matches[].name           -> build_linked_matches  (line ~3859)
    sections.*[].top_outcomes[].name  -> _serialize_outcomes   (line ~2370)

The third is the one that is easy to miss: it is `FuturesOutcome.name`, a
different column, and the NFL page serves ten of
"Will Sam Darnold win the Pro Football Championship Game MVP?" through it.

═══ WHY THE DISPLAY REWRITE AND THE STORED NAME STAY SEPARATE ═══

`market.name` itself is untouched. Two things in this same file read the stored
attribute to DECIDE something — `_competition_echoes_name` (line ~2488) and
`sided_yes_no_labels` (line ~2342) — and a display rename must not move a
decision. The tests below assert that separation directly, because it is the
part a later refactor would casually collapse.
"""

import inspect
import re

import pytest

from app.routes import league_futures
from app.routes.league_futures import _serialize_outcomes
from app.utils.market_label_normalization import rewrite_venue_league_vocabulary

VENUE = re.compile(r"\bPro (Football|Basketball|Hockey|Baseball)\b", re.I)


class _Outcome:
    """The attributes `_serialize_outcomes` reads off an ORM row."""

    def __init__(self, name, oid=1, prob=0.5):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.opening_probability = prob
        self.rank = 1
        self.probability_change_24h = None
        self.team_id = None
        self.is_winner = None


class _Market:
    def __init__(self, name, category="football"):
        self.id = 1
        self.name = name
        self.llm_sport_category = category
        self.status = "open"


#: Verbatim from the served payloads above.
_NFL_MARKET_NAMES = [
    ("Pro Football: Kansas City Total Wins", "NFL: Kansas City Total Wins"),
    ("Pro Football: Jacksonville Total Wins", "NFL: Jacksonville Total Wins"),
    ("Pro Football: 10+ Rushing Touchdowns Season", "NFL: 10+ Rushing Touchdowns Season"),
    ("Pro Football: Number of Ties this Season", "NFL: Number of Ties this Season"),
    ("Pro Football Championship MVP?", "NFL Championship MVP?"),
    (
        "Aaron Donald to play in a Pro Football game this season",
        "Aaron Donald to play in a NFL game this season",
    ),
]

#: `sections.awards[].top_outcomes[].name` on the NFL page — the OUTCOME column.
_NFL_OUTCOME_NAMES = [
    (
        "Will Sam Darnold win the Pro Football Championship Game MVP?",
        "Will Sam Darnold win the NFL Championship Game MVP?",
    ),
    (
        "Will Drake Maye win the Pro Football Championship Game MVP?",
        "Will Drake Maye win the NFL Championship Game MVP?",
    ),
]


class TestTheOutcomeColumnIsRewrittenToo:
    """The door a market-name-only fix would have left open.

    Ten painted rows on the NFL page come through `FuturesOutcome.name`, not
    `FuturesMarket.name`. Run through the REAL serializer, not a re-implementation.
    """

    @pytest.mark.parametrize("raw,expected", _NFL_OUTCOME_NAMES)
    def test_the_served_outcome_row_names_the_league_we_name(self, raw, expected):
        rows = _serialize_outcomes([_Outcome(raw)], _Market("Pro Football MVP"))
        assert rows[0]["name"] == expected

    @pytest.mark.parametrize("raw,_expected", _NFL_OUTCOME_NAMES)
    def test_no_served_outcome_still_says_pro_anything(self, raw, _expected):
        rows = _serialize_outcomes([_Outcome(raw)], _Market("Pro Football MVP"))
        assert not VENUE.search(rows[0]["name"]), rows[0]["name"]

    def test_the_wnba_outcome_is_not_handed_to_the_nba(self):
        raw = "Will A'ja Wilson win the Women's Pro Basketball MVP Winner?"
        rows = _serialize_outcomes(
            [_Outcome(raw)], _Market("Women's Pro Basketball MVP", "basketball")
        )
        assert not re.search(r"\bNBA\b", rows[0]["name"]), rows[0]["name"]
        assert "WNBA" in rows[0]["name"]

    def test_the_rewrite_runs_AFTER_the_sided_label_not_before(self):
        """Order inside the row. `sided_yes_no_labels` may replace a bare "Yes"
        with a curated side; the vocabulary fix has to apply to whatever that
        produced, or a curated label carrying the venue's word escapes. Asserted
        on the source because the label map is keyed on the RAW outcome name —
        rewriting first would make the lookup miss and silently lose the side.
        """
        src = inspect.getsource(_serialize_outcomes)
        assert "rewrite_venue_league_vocabulary(\n                (labels or {}).get(o.name, o.name)\n            )" in src, (
            "the vocabulary rewrite must wrap the label lookup, not its input"
        )

    def test_the_outcome_keeps_its_id(self):
        """Renamed for reading only — anything that settles or charts this row
        still addresses it by id."""
        rows = _serialize_outcomes(
            [_Outcome("Pro Football Championship MVP?", oid=4242)],
            _Market("Pro Football MVP"),
        )
        assert rows[0]["id"] == 4242

    def test_an_ordinary_outcome_is_untouched(self):
        """The control: this must not become a rewrite that edits everything."""
        rows = _serialize_outcomes(
            [_Outcome("Kansas City Chiefs")], _Market("NFL: Champion")
        )
        assert rows[0]["name"] == "Kansas City Chiefs"


class TestTheTwoMarketNameDoors:
    """`build_league` and `build_linked_matches` both serialize a market name.

    Both are async and DB-bound, so their CALL is proven from the source — the
    same shape `TestBothSurfacesCallIt` uses for the seamless typeahead arm in
    the search half of this issue.
    """

    @pytest.mark.parametrize(
        "fn", [league_futures.build_league, league_futures.build_linked_matches]
    )
    def test_the_builder_rewrites_the_market_name(self, fn):
        src = inspect.getsource(fn)
        assert '"name": rewrite_venue_league_vocabulary(market.name),' in src

    @pytest.mark.parametrize(
        "fn", [league_futures.build_league, league_futures.build_linked_matches]
    )
    def test_the_builder_no_longer_serializes_the_raw_name(self, fn):
        src = inspect.getsource(fn)
        assert '"name": market.name,' not in src

    def test_there_is_no_fourth_undiscovered_name_door(self):
        """The census found three sites. If a fourth appears, this reds rather
        than the page quietly regrowing the defect in a new section."""
        src = inspect.getsource(league_futures)
        raw = re.findall(r'^\s+"name": market\.name,$', src, re.M)
        assert raw == [], f"{len(raw)} raw market-name serializer(s) reappeared"


class TestTheStoredNameIsNotRewritten:
    """A display rename must not move a decision.

    Two call sites in this file read `market.name` to decide something. If a
    later refactor points them at the rewritten label, sided labels and the
    competition-echo dedup start keying on a string the database does not hold.
    """

    @pytest.mark.parametrize(
        "reader", ["sided_yes_no_labels", "_competition_echoes_name"]
    )
    def test_the_logic_readers_still_read_the_orm_attribute(self, reader):
        src = inspect.getsource(league_futures)
        idx = src.index(reader + "(")
        window = src[idx : idx + 220]
        assert "rewrite_venue_league_vocabulary" not in window, (
            f"{reader} is being fed a display label instead of the stored name"
        )

    def test_the_helper_does_not_mutate_its_input(self):
        raw = "Pro Football: Kansas City Total Wins"
        before = str(raw)
        rewrite_venue_league_vocabulary(raw)
        assert raw == before


class TestTheMeasuredLeaguePageSpecimens:
    """Every NFL market name the page served, end to end through the helper."""

    @pytest.mark.parametrize("raw,expected", _NFL_MARKET_NAMES)
    def test_it_reads_as_the_league_the_page_is_about(self, raw, expected):
        assert rewrite_venue_league_vocabulary(raw) == expected

    @pytest.mark.parametrize("raw,_expected", _NFL_MARKET_NAMES)
    def test_none_of_them_still_says_pro_anything(self, raw, _expected):
        assert not VENUE.search(rewrite_venue_league_vocabulary(raw))

    def test_the_four_stacked_cards_from_the_screenshot(self):
        """The literal defect: four card headers on a page titled NFL."""
        headers = [
            "Pro Football: New York J Total Wins",
            "Pro Football: Jacksonville Total Wins",
            "Pro Football: Atlanta Total Wins",
            "Pro Football: Los Angeles R Total Wins",
        ]
        out = [rewrite_venue_league_vocabulary(h) for h in headers]
        assert all(h.startswith("NFL: ") for h in out), out

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Women's Pro Basketball: Las Vegas Aces Total Wins",
             "WNBA: Las Vegas Aces Total Wins"),
            ("Women's Pro Basketball Finals Qualifiers", "WNBA Finals Qualifiers"),
            ("Women's Pro Basketball #1 Seed", "WNBA #1 Seed"),
            ("Women's Pro Basketball Worst Record", "WNBA Worst Record"),
        ],
    )
    def test_the_wnba_page_says_wnba_and_never_nba(self, raw, expected):
        """23 of the WNBA page's rows. Measured over all 29 league pages: zero
        pages end up showing a league token that is not their own."""
        out = rewrite_venue_league_vocabulary(raw)
        assert out == expected
        assert not re.search(r"\bNBA\b", out), out
