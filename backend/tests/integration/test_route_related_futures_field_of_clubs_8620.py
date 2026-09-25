"""#8620 — a league named after a country is not that country's market.

WHAT A READER SAW (production, 2026-09-25 13:04Z, shopper pass 0053):
`/events/15194389` Portugal 1–0 Wales, Bigger Picture → Portugal → CHAMPIONSHIP
PATH printed 18 rows all labelled "Liga Portugal Champion" — market 395
(`KXLIGAPORTUGAL-26`, last season's, resolved), one per club: FC Porto >99%,
Sporting Lisbon, SL Benfica, Rio Ave FC … Wales's card had none.

THE ARM. None of the 18 answers names Portugal, so the ticker, alias, `team_id`
and outcome-name paths all decline them. The market-name fallback ("game
props") then reads the TITLE, finds `Portugal` as a whole token of `Liga
Portugal Champion`, and admits every answer to Portugal's side.

THE RULE. A market any of whose answers IS a known club that is neither side of
this game is a field of clubs; it loses the market-name fallback, and only that.
Production `teams` carries 6 of the 18 answers exactly (FC Porto 2175, Sporting
Lisbon 2172, Rio Ave FC 2170, AVS Futebol SAD 2167, Moreirense FC 2164, SC Braga
5669) — any one of them marks the market. Ids below: production where the issue
or the read-only db-query gave them, constructed in the 86200xx range otherwise.

THE CONTROLS carry the weight: this game's own market (`Portugal vs Wales` with
a `Draw` answer — the opponent's label is never the evidence), a Yes/No market
about Portugal, a stage-of-elimination ladder, a player-prop market, an event
whose teams do not resolve, and Portugal's own row inside a field of clubs.

Harness: `test_route_related_futures_team_paths_7867.py` — the real handler
with the database answered by statement text.
"""

from tests.integration.test_route_related_futures import _make_market
from tests.integration.test_route_related_futures_team_paths_7867 import (
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)

# ── sport ids (constructed; the family prefix `soccer` is what matters) ──────
NATIONS, WORLD_CUP, PRIMEIRA, UCL = 862001, 862002, 862003, 862004

# (id, sport_id, name, abbreviation, location, alternate_names)
SOCCER = [
    (17792, NATIONS, "Portugal", "POR", "Portugal", None),          # production
    (17793, NATIONS, "Wales", "WAL", "Wales", None),                # production
    (12902, WORLD_CUP, "Portugal", "POR", "Portugal", None),        # production
    (862010, WORLD_CUP, "Colombia", "COL", "Colombia", None),
    (2175, PRIMEIRA, "FC Porto", "POR", None, None),                # production
    (2172, PRIMEIRA, "Sporting Lisbon", "SCP", None, None),         # production
    (2174, PRIMEIRA, "Benfica", "BEN", None, None),                 # production
    (2170, PRIMEIRA, "Rio Ave FC", "RIO", None, None),              # production
    (18822, UCL, "Porto", "POR", "Porto", None),                    # production
]

LIGA_PORTUGAL = 395            # production market, KXLIGAPORTUGAL-26
WC_WINNER = 862020
THIS_GAME = 862021
WILL_ADVANCE = 13783148        # production market
STAGE_OF_ELIM = 19529994       # production market, KXWCSTAGEOFELIM-26POR
SQUAD_PROPS = 16624255         # production market


def _liga_portugal():
    liga = _make_market(id=LIGA_PORTUGAL, name="Liga Portugal Champion", source="kalshi")
    return liga, [
        # production outcome ids and tickers (market 395)
        _outcome(4227, liga, "Sporting Lisbon", 0.12, ticker="KXLIGAPORTUGAL-26-SPO", team_id=6317),
        _outcome(4225, liga, "Vitoria SC Guimaraes", 0.01, ticker="KXLIGAPORTUGAL-26-VIT"),
        _outcome(4226, liga, "CD Tondela", 0.01, ticker="KXLIGAPORTUGAL-26-TON"),
        _outcome(4228, liga, "Santa Clara Azores", 0.01, ticker="KXLIGAPORTUGAL-26-SCL"),
        _outcome(4229, liga, "Rio Ave FC", 0.3, ticker="KXLIGAPORTUGAL-26-RAV"),
        _outcome(4230, liga, "Moreirense FC", 0.13, ticker="KXLIGAPORTUGAL-26-MOR"),
        _outcome(4235, liga, "Estrela Amadora", 0.2, ticker="KXLIGAPORTUGAL-26-ESA"),
        _outcome(8620001, liga, "FC Porto", 0.995, ticker="KXLIGAPORTUGAL-26-FCP"),
        _outcome(8620002, liga, "SL Benfica", 0.06, ticker="KXLIGAPORTUGAL-26-SLB"),
    ]


LIGA_IDS = {4227, 4225, 4226, 4228, 4229, 4230, 4235, 8620001, 8620002}


def _portugal_wales():
    return _event("Portugal", "Wales", sport_key="soccer_uefa_nations_league", sport_id=NATIONS, status="completed")


async def test_portugal_loses_the_liga_portugal_clubs_and_keeps_its_own_rows(monkeypatch):
    event = _portugal_wales()
    liga, liga_rows = _liga_portugal()
    wc = _make_market(id=WC_WINNER, name="FIFA World Cup Winner", source="kalshi")
    advance = _make_market(
        id=WILL_ADVANCE,
        name="Will Portugal advance to the knockout stages at the 2026 FIFA World Cup?",
        source="polymarket",
    )
    stage = _make_market(id=STAGE_OF_ELIM, name="Portugal: Stage of Elimination", source="kalshi")
    squad = _make_market(id=SQUAD_PROPS, name="World Cup: Player to make Portugal Squad", source="polymarket")
    outcomes = liga_rows + [
        # KEEP — Portugal's own answer in a field of clubs is the outcome arm
        _outcome(8620010, wc, "Portugal", 0.06),
        _outcome(8620011, wc, "Colombia", 0.02),                        # neither side — not served
        # KEEP — reached by MARKET name, answers are not clubs
        _outcome(8620012, advance, "Yes", 0.97),
        _outcome(8620013, advance, "No", 0.03),
        _outcome(8620014, stage, "Group Stage", 0.1, ticker="KXWCSTAGEOFELIM-26POR-GS"),
        _outcome(8620015, stage, "Round of 16", 0.3, ticker="KXWCSTAGEOFELIM-26POR-R16"),
        _outcome(8620016, squad, "Cristiano Ronaldo", 0.99),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=SOCCER, home_team_id=17792, away_team_id=17793,
                 sport_ids=[NATIONS]),
        event.id,
    )
    home = _ids(body, "home_team_futures")
    assert not LIGA_IDS & _ids(body)
    assert {8620010, 8620012, 8620013, 8620014, 8620015, 8620016} <= home
    assert 8620011 not in _ids(body)
    # Wales's card is untouched: it never had any of these.
    assert _ids(body, "away_team_futures") == set()


async def test_this_games_own_market_keeps_its_draw_because_the_opponent_is_ours(monkeypatch):
    """`Wales` is a known club and is not Portugal — but it is THIS game's other
    side, so it is never evidence of a field. The `Draw` answer still reaches
    Portugal's side through the market name, exactly as before."""
    event = _event("Portugal", "Wales", sport_key="soccer_uefa_nations_league", sport_id=NATIONS)
    game = _make_market(id=THIS_GAME, name="Portugal vs Wales: Totals and Result", source="polymarket")
    outcomes = [
        _outcome(8620020, game, "Portugal", 0.6),
        _outcome(8620021, game, "Wales", 0.15),
        _outcome(8620022, game, "Draw", 0.25),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=SOCCER, home_team_id=17792, away_team_id=17793,
                 sport_ids=[NATIONS]),
        event.id,
    )
    assert {8620020, 8620022} <= _ids(body, "home_team_futures")
    assert 8620021 in _ids(body, "away_team_futures")


async def test_an_opponent_that_did_not_resolve_is_still_not_the_evidence(monkeypatch):
    """Only Portugal resolves, so Wales is not in any `own` set — but its label
    matches the away side's own patterns, which is checked first."""
    event = _event("Portugal", "Wales", sport_key="soccer_uefa_nations_league", sport_id=NATIONS)
    game = _make_market(id=THIS_GAME, name="Portugal vs Wales: Totals and Result", source="polymarket")
    outcomes = [
        _outcome(8620030, game, "Wales", 0.15),
        _outcome(8620031, game, "Draw", 0.25),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=SOCCER, home_team_id=17792, away_team_id=None,
                 sport_ids=[NATIONS]),
        event.id,
    )
    assert 8620031 in _ids(body, "home_team_futures")


async def test_nothing_resolved_nothing_armed(monkeypatch):
    """With neither side in `teams` there is no `own`, so no answer can be
    foreign and the payload is what it was (the limitation, pinned)."""
    event = _portugal_wales()
    _, liga_rows = _liga_portugal()
    body = await _get(
        monkeypatch,
        _session(event, liga_rows, roster=SOCCER, home_team_id=None, away_team_id=None,
                 sport_ids=[NATIONS]),
        event.id,
    )
    assert LIGA_IDS <= _ids(body, "home_team_futures")
