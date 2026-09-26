"""#8661 — search stops printing a price the market's own page withholds as a dead board.

WHAT A READER SAW, production 2026-09-25 17:0xZ, `/search?q=nfl mvp` at 390px:
the third card, *NFL Championship MVP?*, drew `Sam Darnold 45% · Drake Maye 27% ·
Jaxon Smith-Njigba 15%` under a "Feb 3" stamp, as a live question. It is Kalshi
`KXNFLSBMVP-26` (futures_markets 479) — LAST season's Super Bowl MVP, a game played
in February. Nobody graded it (the venue has since purged the contracts:
`GET /events/KXNFLSBMVP-26` returns `markets: []`), every leg was last written
2026-02-04 04:45Z, and the row is still stored `open` (#2644's field class).

`/api/futures/479` serves the same board as `prices_withheld: 79`, every leg
null, in the same minute. The page withholds on SIX arms; search asked the helper
`_withheld_price_outcome_ids`, which is five of them (+ #8265's), because
`get_futures_market` adds #8011's unobserved-board arm outside it. #8102 found the
same split on `/entertainment`; search was still trusting the helper as "the"
refusal.

THE FIXTURE IS THE SPECIMEN'S OWN STORED ROWS, all 79 legs of market 479, read off
production via `db-query` 2026-09-25 17:1xZ, verbatim. The fleet stamp is the real
`max(futures_outcomes.last_updated)` read the same minute.

The rule (`unobserved_board_keys`) and the gate (`_fleet_newest_observation`) are
the REAL helpers — they carry their own guards; these tests assert that search
applies them, and that a board they refuse entirely leaves the page instead of
drawing a ladder of dashes.
"""

import inspect
import textwrap
from datetime import datetime
from types import SimpleNamespace

import pytest

import app.routes.events as events_module
from app.routes.events import (
    _build_search_top_outcomes,
    _futures_card_has_no_answer,
    _futures_market_prices_all_withheld,
    _search_withheld_price_ids,
)

MARKET_ID = 479

#: `max(futures_outcomes.last_updated)`, production, 2026-09-25.
FLEET_NEWEST = datetime.fromisoformat("2026-09-25T17:13:05.577360+00:00")

#: The parent row's `updated_at` (the poller stamp the rule's second clause reads).
BOARD_TOUCHED_AT = datetime.fromisoformat("2026-06-29T18:40:00.099677+00:00")

#: The three legs the search card headlined.
HEADLINED = {6958, 6983, 6971}

#: `(id, external_id, name, prob, bid, ask, stored_rank, last_updated)` — all 79
#: legs of market 479, verbatim. Every one is `is_winner=False`,
#: `resolution_source=None`.
SPECIMEN_LEGS = (
    (6916, 'KXNFLSBMVP-26-TIE', 'Will Tie/Co-Winner win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 1, '2026-02-04T04:45:07.938434+00:00'),
    (6917, 'KXNFLSBMVP-26-BMURPHY91', 'Will Byron Murphy II win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 2, '2026-02-04T04:45:07.938434+00:00'),
    (6918, 'KXNFLSBMVP-26-GHOLANI36', 'Will George Holani win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 3, '2026-02-04T04:45:07.938434+00:00'),
    (6919, 'KXNFLSBMVP-26-JBOBO19', 'Will Jake Bobo win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 4, '2026-02-04T04:45:07.938434+00:00'),
    (6920, 'KXNFLSBMVP-26-NEMMANWORI3', 'Will Nick Emmanwori win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 5, '2026-02-04T04:45:07.938434+00:00'),
    (6921, 'KXNFLSBMVP-26-JLOVE20', 'Will Julian Love win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 6, '2026-02-04T04:45:07.938434+00:00'),
    (6922, 'KXNFLSBMVP-26-MDICKSON4', 'Will Michael Dickson win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 7, '2026-02-04T04:45:07.938434+00:00'),
    (6923, 'KXNFLSBMVP-26-EJONES13', 'Will Ernest Jones IV win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 8, '2026-02-04T04:45:07.938434+00:00'),
    (6924, 'KXNFLSBMVP-26-ALUCAS72', 'Will Abraham Lucas win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 9, '2026-02-04T04:45:07.938434+00:00'),
    (6925, 'KXNFLSBMVP-26-JDOBBS11', 'Will Joshua Dobbs win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 10, '2026-02-04T04:45:07.938434+00:00'),
    (6926, 'KXNFLSBMVP-26-KWILLIAMS18', 'Will Kyle Williams win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 11, '2026-02-04T04:45:07.938434+00:00'),
    (6927, 'KXNFLSBMVP-26-DDOUGLAS3', 'Will DeMario Douglas win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 12, '2026-02-04T04:45:07.938434+00:00'),
    (6928, 'KXNFLSBMVP-26-WCAMPBELL66', 'Will Will Campbell win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 13, '2026-02-04T04:45:07.938434+00:00'),
    (6929, 'KXNFLSBMVP-26-BBARINGER17', 'Will Bryce Baringer win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 14, '2026-02-04T04:45:07.938434+00:00'),
    (6930, 'KXNFLSBMVP-26-ABORREGALES36', 'Will Andy Borregales win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 15, '2026-02-04T04:45:07.938434+00:00'),
    (6931, 'KXNFLSBMVP-26-MJONES25', 'Will Marcus Jones win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 16, '2026-02-04T04:45:07.938434+00:00'),
    (6932, 'KXNFLSBMVP-26-CGONZALEZ0', 'Will Christian Gonzalez win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 17, '2026-02-04T04:45:07.938434+00:00'),
    (6933, 'KXNFLSBMVP-26-CDAVIS7', 'Will Carlton Davis III win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 18, '2026-02-04T04:45:07.938434+00:00'),
    (6934, 'KXNFLSBMVP-26-RSPILLANE14', 'Will Robert Spillane win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 19, '2026-02-04T04:45:07.938434+00:00'),
    (6935, 'KXNFLSBMVP-26-HLANDRY2', 'Will Harold Landry III win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 20, '2026-02-04T04:45:07.938434+00:00'),
    (6936, 'KXNFLSBMVP-26-MWILLIAMS97', 'Will Milton Williams win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 21, '2026-02-04T04:45:07.938434+00:00'),
    (6937, 'KXNFLSBMVP-26-CBARMORE90', 'Will Christian Barmore win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 22, '2026-02-04T04:45:07.938434+00:00'),
    (6938, 'KXNFLSBMVP-26-JMYERS5', 'Will Jason Myers win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 23, '2026-02-04T04:45:07.938434+00:00'),
    (6939, 'KXNFLSBMVP-26-CBRYANT8', 'Will Coby Bryant win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 24, '2026-02-04T04:45:07.938434+00:00'),
    (6940, 'KXNFLSBMVP-26-DWITHERSPOON21', 'Will Devon Witherspoon win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 25, '2026-02-04T04:45:07.938434+00:00'),
    (6941, 'KXNFLSBMVP-26-LWILLIAMS99', 'Will Leonard Williams win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 26, '2026-02-04T04:45:07.938434+00:00'),
    (6942, 'KXNFLSBMVP-26-DLAWRENCE0', 'Will DeMarcus Lawrence win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 27, '2026-02-04T04:45:07.938434+00:00'),
    (6943, 'KXNFLSBMVP-26-DLOCK2', 'Will Drew Lock win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 28, '2026-02-04T04:45:07.938434+00:00'),
    (6944, 'KXNFLSBMVP-26-ABARNER88', 'Will AJ Barner win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 29, '2026-02-04T04:45:07.938434+00:00'),
    (6945, 'KXNFLSBMVP-26-MHOLLINS13', 'Will Mack Hollins win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 30, '2026-02-04T04:45:07.938434+00:00'),
    (6946, 'KXNFLSBMVP-26-JSTIDHAM8', 'Will Jarrett Stidham win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 31, '2026-02-04T04:45:07.938434+00:00'),
    (6947, 'KXNFLSBMVP-26-NBONITTO15', 'Will Nik Bonitto win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 32, '2026-02-04T04:45:07.938434+00:00'),
    (6948, 'KXNFLSBMVP-26-BCORUM22', 'Will Blake Corum win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 33, '2026-02-04T04:45:07.938434+00:00'),
    (6949, 'KXNFLSBMVP-26-CKUPP10', 'Will Cooper Kupp win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 34, '2026-02-04T04:45:07.938434+00:00'),
    (6950, 'KXNFLSBMVP-26-KBOUTTE9', 'Will Kayshon Boutte win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 35, '2026-02-04T04:45:07.938434+00:00'),
    (6951, 'KXNFLSBMVP-26-HHENRY85', 'Will Hunter Henry win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 36, '2026-02-04T04:45:07.938434+00:00'),
    (6952, 'KXNFLSBMVP-26-RSHAHEED22', 'Will Rashid Shaheed win the Pro Football Championship Game MVP?', 0.015000, 0.0100, 0.0200, 37, '2026-02-04T04:45:07.938434+00:00'),
    (6953, 'KXNFLSBMVP-26-ZCHARBONNET26', 'Will Zach Charbonnet win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 38, '2026-02-04T04:45:07.938434+00:00'),
    (6954, 'KXNFLSBMVP-26-TLAWRENCE16', 'Will Trevor Lawrence win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 39, '2026-02-04T04:45:07.938434+00:00'),
    (6955, 'KXNFLSBMVP-26-THENDERSON32', 'Will TreVeyon Henderson win the Pro Football Championship Game MVP?', 0.005000, 0.0000, 0.0100, 40, '2026-02-04T04:45:07.938434+00:00'),
    (6956, 'KXNFLSBMVP-26-TETIENNE1', 'Will Travis Etienne Jr. win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 41, '2026-02-04T04:45:07.938434+00:00'),
    (6957, 'KXNFLSBMVP-26-SDIGGS8', 'Will Stefon Diggs win the Pro Football Championship Game MVP?', 0.015000, 0.0100, 0.0200, 42, '2026-02-04T04:45:07.938434+00:00'),
    (6958, 'KXNFLSBMVP-26-SDARNOLD14', 'Will Sam Darnold win the Pro Football Championship Game MVP?', 0.445000, 0.4400, 0.4500, 43, '2026-02-04T04:45:07.938434+00:00'),
    (6959, 'KXNFLSBMVP-26-SBARKLEY26', 'Will Saquon Barkley win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 44, '2026-02-04T04:45:07.938434+00:00'),
    (6960, 'KXNFLSBMVP-26-RSTEVENSON38', 'Will Rhamondre Stevenson win the Pro Football Championship Game MVP?', 0.025000, 0.0200, 0.0300, 45, '2026-02-04T04:45:07.938434+00:00'),
    (6961, 'KXNFLSBMVP-26-RHARVEY12', 'Will RJ Harvey win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 46, '2026-02-04T04:45:07.938434+00:00'),
    (6962, 'KXNFLSBMVP-26-PSURTAIN2', 'Will Pat Surtain II win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 47, '2026-02-04T04:45:07.938434+00:00'),
    (6963, 'KXNFLSBMVP-26-PNACUA12', 'Will Puka Nacua win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 48, '2026-02-04T04:45:07.938434+00:00'),
    (6964, 'KXNFLSBMVP-26-OHAMPTON8', 'Will Omarion Hampton win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 49, '2026-02-04T04:45:07.938434+00:00'),
    (6965, 'KXNFLSBMVP-26-NCOLLINS12', 'Will Nico Collins win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 50, '2026-02-04T04:45:07.938434+00:00'),
    (6966, 'KXNFLSBMVP-26-MSTAFFORD9', 'Will Matthew Stafford win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 51, '2026-02-04T04:45:07.938434+00:00'),
    (6967, 'KXNFLSBMVP-26-KWILLIAMS23', 'Will Kyren Williams win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 52, '2026-02-04T04:45:07.938434+00:00'),
    (6968, 'KXNFLSBMVP-26-KWALKER9', 'Will Kenneth Walker III win the Pro Football Championship Game MVP?', 0.085000, 0.0800, 0.0900, 53, '2026-02-04T04:45:07.938434+00:00'),
    (6969, 'KXNFLSBMVP-26-KMONANGAI25', 'Will Kyle Monangai win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 54, '2026-02-04T04:45:07.938434+00:00'),
    (6970, 'KXNFLSBMVP-26-JWARREN30', 'Will Jaylen Warren win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 55, '2026-02-04T04:45:07.938434+00:00'),
    (6971, 'KXNFLSBMVP-26-JSMITHNJIGBA11', 'Will Jaxon Smith-Njigba win the Pro Football Championship Game MVP?', 0.145000, 0.1400, 0.1500, 56, '2026-02-04T04:45:07.938434+00:00'),
    (6972, 'KXNFLSBMVP-26-JMEYERS3', 'Will Jakobi Meyers win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 57, '2026-02-04T04:45:07.938434+00:00'),
    (6973, 'KXNFLSBMVP-26-JLOVE10', 'Will Jordan Love win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 58, '2026-02-04T04:45:07.938434+00:00'),
    (6974, 'KXNFLSBMVP-26-JJACOBS8', 'Will Josh Jacobs win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 59, '2026-02-04T04:45:07.938434+00:00'),
    (6975, 'KXNFLSBMVP-26-JHURTS1', 'Will Jalen Hurts win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 60, '2026-02-04T04:45:07.938434+00:00'),
    (6976, 'KXNFLSBMVP-26-JHERBERT10', 'Will Justin Herbert win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 61, '2026-02-04T04:45:07.938434+00:00'),
    (6977, 'KXNFLSBMVP-26-JCOOK4', 'Will James Cook III win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 62, '2026-02-04T04:45:07.938434+00:00'),
    (6978, 'KXNFLSBMVP-26-JALLEN17', 'Will Josh Allen win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 63, '2026-02-04T04:45:07.938434+00:00'),
    (6979, 'KXNFLSBMVP-26-GKITTLE85', 'Will George Kittle win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 64, '2026-02-04T04:45:07.938434+00:00'),
    (6980, 'KXNFLSBMVP-26-DSWIFT4', "Will D'Andre Swift win the Pro Football Championship Game MVP?", 0.500000, 0.0000, 1.0000, 65, '2026-02-04T04:45:07.938434+00:00'),
    (6981, 'KXNFLSBMVP-26-DSMITH6', 'Will DeVonta Smith win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 66, '2026-02-04T04:45:07.938434+00:00'),
    (6982, 'KXNFLSBMVP-26-DMETCALF14', 'Will DK Metcalf win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 67, '2026-02-04T04:45:07.938434+00:00'),
    (6983, 'KXNFLSBMVP-26-DMAYE10', 'Will Drake Maye win the Pro Football Championship Game MVP?', 0.265000, 0.2600, 0.2700, 68, '2026-02-04T04:45:07.938434+00:00'),
    (6984, 'KXNFLSBMVP-26-DADAMS17', 'Will Davante Adams win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 69, '2026-02-04T04:45:07.938434+00:00'),
    (6985, 'KXNFLSBMVP-26-CWILLIAMS18', 'Will Caleb Williams win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 70, '2026-02-04T04:45:07.938434+00:00'),
    (6986, 'KXNFLSBMVP-26-CSUTTON14', 'Will Courtland Sutton win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 71, '2026-02-04T04:45:07.938434+00:00'),
    (6987, 'KXNFLSBMVP-26-CSTROUD7', 'Will C.J. Stroud win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 72, '2026-02-04T04:45:07.938434+00:00'),
    (6988, 'KXNFLSBMVP-26-CMCCAFFREY23', 'Will Christian McCaffrey win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 73, '2026-02-04T04:45:07.938434+00:00'),
    (6989, 'KXNFLSBMVP-26-BYOUNG9', 'Will Bryce Young win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 74, '2026-02-04T04:45:07.938434+00:00'),
    (6990, 'KXNFLSBMVP-26-BTHOMAS7', 'Will Brian Thomas Jr. win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 75, '2026-02-04T04:45:07.938434+00:00'),
    (6991, 'KXNFLSBMVP-26-BPURDY13', 'Will Brock Purdy win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 76, '2026-02-04T04:45:07.938434+00:00'),
    (6992, 'KXNFLSBMVP-26-BNIX10', 'Will Bo Nix win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 77, '2026-02-04T04:45:07.938434+00:00'),
    (6993, 'KXNFLSBMVP-26-ARODGERS8', 'Will Aaron Rodgers win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 78, '2026-02-04T04:45:07.938434+00:00'),
    (6994, 'KXNFLSBMVP-26-ABROWN11', 'Will A.J. Brown win the Pro Football Championship Game MVP?', 0.500000, 0.0000, 1.0000, 79, '2026-02-04T04:45:07.938434+00:00'),
)


def _legs(*, graded_id=None, stamp=None):
    return [
        SimpleNamespace(
            id=oid,
            external_id=ext,
            name=name,
            current_probability=prob,
            current_yes_bid=bid,
            current_yes_ask=ask,
            current_american_odds=None,
            probability_change_24h=None,
            opening_probability=None,
            rank=rank,
            is_winner=oid == graded_id,
            resolution_source="api_settlement" if oid == graded_id else None,
            last_updated=stamp or datetime.fromisoformat(lu),
        )
        for oid, ext, name, prob, bid, ask, rank, lu in SPECIMEN_LEGS
    ]


def _market(legs=None, *, touched=BOARD_TOUCHED_AT, status="open"):
    return SimpleNamespace(
        id=MARKET_ID,
        name="Pro Football Championship MVP?",
        source="kalshi",
        external_id="KXNFLSBMVP-26",
        status=status,
        market_type="field",
        mutually_exclusive=True,
        updated_at=touched,
        outcomes=_legs() if legs is None else legs,
    )


class _FleetDB:
    """Answers the one read `_fleet_newest_observation` makes, and counts it."""

    def __init__(self, stamp=FLEET_NEWEST):
        self.stamp = stamp
        self.reads = 0

    async def execute(self, _stmt):
        self.reads += 1
        return SimpleNamespace(scalar_one_or_none=lambda: self.stamp)


@pytest.fixture
def five_arms_refuse_nothing(monkeypatch):
    """The helper's answer on this board, as production served it.

    Search printed Darnold/Maye/Smith-Njigba at 45/27/15, so the five-arm union
    refused none of the headlined legs. Stubbed to the empty set so the only arm
    under test is the one this ship adds.
    """

    async def _none(_db, _market):
        return set()

    monkeypatch.setattr(events_module, "_withheld_price_outcome_ids", _none)


@pytest.mark.asyncio
async def test_the_specimen_board_is_refused_whole(five_arms_refuse_nothing):
    db = _FleetDB()
    withheld = await _search_withheld_price_ids(db, _market())
    assert withheld == {leg[0] for leg in SPECIMEN_LEGS}
    assert HEADLINED <= withheld
    assert db.reads == 1


@pytest.mark.asyncio
async def test_the_specimen_card_is_withdrawn_not_dashed(five_arms_refuse_nothing):
    market = _market()
    withheld = await _search_withheld_price_ids(_FleetDB(), market)
    # The builder alone would have drawn a ranked ladder of nulls — #6327's defect.
    top = _build_search_top_outcomes(market, limit=5, withheld=withheld)
    assert top and all(o["probability"] is None for o in top)
    # So the card is withdrawn, by the one predicate both call sites ask.
    assert _futures_card_has_no_answer(market, withheld) is True
    assert _futures_market_prices_all_withheld(market, withheld) is True


def test_without_the_refusal_set_the_old_question_keeps_the_card():
    """The defect as shipped: the four row arms alone keep this card."""
    assert _futures_card_has_no_answer(_market()) is False
    assert _futures_card_has_no_answer(_market(), set()) is False


def test_a_partial_refusal_keeps_the_card():
    """One refused leg is #6993's case: nulled in place, the card stays."""
    market = _market()
    assert _futures_market_prices_all_withheld(market, {6958}) is False
    assert _futures_card_has_no_answer(market, {6958}) is False


@pytest.mark.asyncio
async def test_a_graded_board_keeps_its_result(five_arms_refuse_nothing):
    """Settled means settled: a verdict on the board spares every leg (#6532)."""
    db = _FleetDB()
    market = _market(_legs(graded_id=6968))
    withheld = await _search_withheld_price_ids(db, market)
    assert withheld == set()
    assert _futures_card_has_no_answer(market, withheld) is False
    assert db.reads == 0


@pytest.mark.asyncio
async def test_a_live_board_pays_no_read_and_keeps_its_prices(five_arms_refuse_nothing):
    """Priced this minute and touched this minute: the gate never asks the fleet."""
    db = _FleetDB()
    market = _market(_legs(stamp=FLEET_NEWEST), touched=FLEET_NEWEST)
    withheld = await _search_withheld_price_ids(db, market)
    assert withheld == set()
    assert db.reads == 0


@pytest.mark.asyncio
async def test_a_fleet_wide_stall_withholds_nothing(five_arms_refuse_nothing):
    """If ingestion froze with this board, the fleet stamp froze too (#7537)."""
    db = _FleetDB(stamp=datetime.fromisoformat("2026-02-04T04:45:07.938434+00:00"))
    withheld = await _search_withheld_price_ids(db, _market())
    assert withheld == set()


@pytest.mark.asyncio
async def test_the_five_arms_still_reach_the_answer(monkeypatch):
    """The sixth arm is a UNION onto the helper, never a replacement for it."""

    async def _one(_db, _market):
        return {6958}

    monkeypatch.setattr(events_module, "_withheld_price_outcome_ids", _one)
    market = _market(_legs(stamp=FLEET_NEWEST), touched=FLEET_NEWEST)
    assert await _search_withheld_price_ids(_FleetDB(), market) == {6958}


def _route_source() -> str:
    return textwrap.dedent(inspect.getsource(events_module.search_events))


def test_the_route_asks_before_it_filters_and_slices():
    """Withdrawn BEFORE the slice so the page refills (#6327's filter-then-slice)."""
    src = _route_source()
    ask = src.index("_withheld_by_market = {")
    flat = src.index("m for m in deduped_futures if not _futures_card_has_no_answer(")
    assert ask < flat
    # #8851 put the same-question fold between the filter and the slice, so the
    # slice is found from the filter onward rather than inside a fixed window.
    rest = src[flat:]
    assert rest.index("m, _withheld_by_market.get(m.id)") < rest.index(
        "][:_SEARCH_FUTURES_PAGE]"
    )


def test_every_reader_list_passes_the_refusal_set():
    """The flat bucket and the families both — a family is the back door."""
    src = _route_source()
    assert "_futures_card_has_no_answer(m)" not in src
    assert src.count("_withheld_by_market.get(m.id)") == 3  # flat, map, families
    assert "_futures_card_has_no_answer(m, _withheld_by_market.get(m.id))" in src
    # And a promoted headline contender cannot walk a refused board back in.
    assert "_futures_market_prices_all_withheld(m, _withheld_by_market[m.id])" in src
