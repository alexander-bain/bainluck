"""#9340 — a bare round's ANSWERS card holds the round's markets, not its namesakes.

WHAT THE READER SAW. Production `91183e5b`, 2026-09-28 14:4xZ, 390px LOOK of
`/search?q=championship%20series`. The flat futures list led with the ALCS/NLCS
markets (PR #9375's fix), and the ANSWERS card above it, "Championship Series"
(`entity:championship series`), read:

    MLB Championship Series Matchup
    NFL: Lions vs. Packers Season Series Winner
    NFL: Cardinals vs. Seahawks Season Series Winner
    NFL: Cowboys vs. Commanders Season Series Winner
    NFL: Bengals vs. Browns Season Series Winner

`championship` carries the `winner` synonym, so the NFL boards match every typed
word by NAME, and the entity card is built from name matches. The ALCS/NLCS rows
name the round only by abbreviation, so they never joined. Same class, second
specimen: `wild card`'s card was "Wild Card" headed by
`Set 1 Winner: Thiago Seyboth Wild vs Pedro Boscardin Dias` (tennis).

THE FIX. When `_postseason_round_lead_predicate` is armed (the query IS a round,
plus at most its league word), the entity card is the rows that predicate
accepts: the same rule the flat list and the dropdown lead with. A row that only
matches by name forms no card and keeps its rank in the flat list. The relevance
guard (">=1 member the query names") is satisfied by the predicate itself.
Unarmed queries (`alcs`, `yankees wild card`, `nfl championship series`) are
unchanged.

RED-FIRST. On master's composer 5 of these tests fail, reproducing production
exactly: the card is [2417016 + the four NFL boards], and `wild card`'s is the two
tennis sets. Severing only the relevance-guard bypass fails 3 (the round card is
dropped, not built).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.events import _compose_futures_families

UTC = timezone.utc
NOW = datetime(2026, 9, 28, 14, 45, tzinfo=UTC)  # the specimen's read, fixed


def _outcome(name, prob, oid):
    """Shaped to survive `_search_surviving_legs` (distinct id, real book)."""
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"leg-{oid}",
        current_probability=prob,
        current_odds=None,
        current_american_odds=None,
        current_yes_bid=max(0.01, prob - 0.02),
        current_yes_ask=min(0.99, prob + 0.02),
        previous_probability=None,
        is_winner=None,
        rank=None,
        team_id=None,
    )


def _market(mid, name, cat, legs, *, external_id=None, source="kalshi"):
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id or f"KX-{mid}",
        llm_sport_category=cat,
        category="championship",
        market_tier=2,
        market_type="futures",
        sport=None,
        sport_id=None,
        source=source,
        volume=0.0,
        status="open",
        mutually_exclusive=False,
        resolution_date=(NOW + timedelta(days=30)).date(),
        updated_at=NOW,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=None,
        outcomes=[_outcome(n, p, mid * 100 + i) for i, (n, p) in enumerate(legs)],
    )


def _fmt(m):
    return {"id": m.id, "name": m.name}


def _compose(markets, query):
    expanded = [(t, None) for t in query.split()]
    # `championship` carries the `winner` synonym on the real path; supply it so
    # the NFL boards name-match exactly as they do in production.
    expanded = [
        (t, "winner" if t == "championship" else None) for t, _ in expanded
    ]
    return _compose_futures_families(markets, expanded, _fmt, {m.id for m in markets})


def _shown_ids(fam):
    return [fam["headline"]["id"]] + [m["id"] for m in fam["members"]]


def _entity(fams, query):
    return next((f for f in fams if f["family_key"] == f"entity:{query}"), None)


# --- championship series -----------------------------------------------------
CS_MATCHUP = 2417016
NFL_LIONS = 56722514
NFL_CARDS = 56722551
NFL_COWBOYS = 56722496
NFL_BENGALS = 56722435
ALCS_ADVANCE = 60087229
ALCS_QUAL = 62383708
NLCS_QUAL = 62383707


def _championship_series_candidates():
    """The served family rows, in served (reranked) order: the card's rows first,
    as the composer received them, then the round's rows the list led with."""
    two = [("A", 0.55), ("B", 0.45)]
    return [
        _market(CS_MATCHUP, "MLB Championship Series Matchup", "baseball",
                [("Tampa Bay vs Los Angeles D", 0.11), ("New York Y vs Los Angeles D", 0.10)]),
        _market(NFL_LIONS, "NFL: Lions vs. Packers Season Series Winner", "football", two),
        _market(NFL_CARDS, "NFL: Cardinals vs. Seahawks Season Series Winner", "football", two),
        _market(NFL_COWBOYS, "NFL: Cowboys vs. Commanders Season Series Winner", "football", two),
        _market(NFL_BENGALS, "NFL: Bengals vs. Browns Season Series Winner", "football", two),
        _market(ALCS_ADVANCE, "MLB Playoffs: Team to advance to ALCS", "baseball",
                [("Tampa Bay Rays", 0.51), ("Chicago White Sox", 0.28)]),
        _market(ALCS_QUAL, "MLB ALCS Qualifiers", "baseball",
                [("Tampa Bay", 0.47), ("Cleveland", 0.38)]),
        _market(NLCS_QUAL, "MLB NLCS Qualifiers", "baseball",
                [("Los Angeles Dodgers", 0.68), ("Milwaukee", 0.56)]),
    ]


NFL_BOARDS = {NFL_LIONS, NFL_CARDS, NFL_COWBOYS, NFL_BENGALS}


class TestChampionshipSeriesSpecimen:
    def test_the_card_is_the_rounds_markets(self):
        fams = _compose(_championship_series_candidates(), "championship series")
        card = _entity(fams, "championship series")
        assert card is not None
        assert _shown_ids(card) == [ALCS_ADVANCE, ALCS_QUAL, NLCS_QUAL]
        assert card["member_count"] == 3
        assert card["label"] == "Championship Series"

    def test_no_nfl_board_rides_any_card(self):
        fams = _compose(_championship_series_candidates(), "championship series")
        shown = {i for f in fams for i in _shown_ids(f)}
        assert not (shown & NFL_BOARDS)

    def test_the_league_word_form_is_the_same_round(self):
        """`mlb championship series` arms the same predicate: same card."""
        cands = _championship_series_candidates()
        card = _entity(_compose(cands, "mlb championship series"), "mlb championship series")
        assert card is not None and _shown_ids(card) == [ALCS_ADVANCE, ALCS_QUAL, NLCS_QUAL]


class TestAnotherLeaguesRoundIsUnarmed:
    """`nfl championship series` is another league's question, so the round
    predicate is unarmed and the card is the name-match card exactly as before:
    the NFL boards name every typed word (`NFL:` included), so they form it.
    The fix must not reach this query. (The BEFORE of the armed specimen is the
    red-first run on master's composer: the card was [2417016 + the 4 boards].)"""

    def test_the_nfl_boards_still_form_the_nfl_query_card(self):
        cands = _championship_series_candidates()
        card = _entity(_compose(cands, "nfl championship series"), "nfl championship series")
        assert card is not None
        assert set(_shown_ids(card)) == NFL_BOARDS


# --- wild card ---------------------------------------------------------------
TENNIS_SET1 = 62900001
TENNIS_SET2 = 62900002
BOS_NYY = 62910001
PHI_ATL = 62910002
CWS_HOU = 62910003


def _wild_card_candidates():
    two = [("Home", 0.5), ("Away", 0.5)]
    return [
        _market(TENNIS_SET1, "Set 1 Winner: Thiago Seyboth Wild vs Pedro Boscardin Dias",
                "tennis", two, external_id="PM-set1", source="polymarket"),
        _market(TENNIS_SET2, "Set 2 Winner: Thiago Seyboth Wild vs Pedro Boscardin Dias",
                "tennis", two, external_id="PM-set2", source="polymarket"),
        _market(BOS_NYY, "Series Winner: Boston vs New York Y", "baseball",
                [("Boston", 0.46), ("New York Y", 0.54)], external_id="KXMLBSERIES-26BOSNYYWC"),
        _market(PHI_ATL, "Series Winner: Philadelphia vs Atlanta", "baseball",
                [("Philadelphia", 0.58), ("Atlanta", 0.42)], external_id="KXMLBSERIES-26PHIATLWC"),
        _market(CWS_HOU, "Series Winner: Chicago WS vs Houston", "baseball",
                [("Chicago WS", 0.40), ("Houston", 0.60)], external_id="KXMLBSERIES-26CWSHOUWC"),
    ]


class TestWildCardSpecimen:
    def test_the_card_is_the_wild_card_series(self):
        fams = _compose(_wild_card_candidates(), "wild card")
        card = _entity(fams, "wild card")
        assert card is not None
        assert _shown_ids(card) == [BOS_NYY, PHI_ATL, CWS_HOU]
        shown = {i for f in fams for i in _shown_ids(f)}
        assert TENNIS_SET1 not in shown and TENNIS_SET2 not in shown

    def test_a_clubs_wild_card_query_is_unarmed_and_unchanged(self):
        """`yankees wild card` asks for one club's series: no round card is built
        from the ticker, and the name-match rule decides as before."""
        cands = _wild_card_candidates()
        fams = _compose(cands, "yankees wild card")
        assert _entity(fams, "yankees wild card") is None  # nothing names `yankees`


class TestUnarmedQueriesAreByteIdentical:
    def test_alcs_card_is_built_from_name_matches_as_before(self):
        cands = _championship_series_candidates()
        card = _entity(_compose(cands, "alcs"), "alcs")
        assert card is not None
        assert _shown_ids(card) == [ALCS_ADVANCE, ALCS_QUAL]

    def test_a_round_with_one_row_forms_no_card(self):
        """A lone round row is still a lone answer: no card, as for any family."""
        only = [m for m in _championship_series_candidates() if m.id in {ALCS_QUAL, *NFL_BOARDS}]
        assert _compose(only, "championship series") == []
