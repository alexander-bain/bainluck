"""#7355 — `warriors` stops heading its ANSWERS card with League of Legends.

Production 2026-09-25 12:45Z, `/search?q=warriors` at 390px: the card read
"Stephen Curry to leave Warriors?", then two LoL matches (Saigon Warriors) and
two Glasgow Warriors rugby games, with Golden State's own markets behind
"+4 more". #7259's wrong-sport demotion cannot arm: the query's games span seven
sport facets and that rule acts on unanimity or not at all.

The signal here is the teams table: a market from a sport in which NO matched
team plays is a nickname cousin. These tests pin the two helpers; the route arm
lives in `tests/integration/test_route_search_teamless_sport_7355.py`.

The team rows below are production's `name ILIKE '%warriors%'` rows, read
2026-09-25 (16 rows). New Zealand Warriors is `rugbyleague_nrl` — so rugby is
EVIDENCED and stays, and only esports sinks. #7355's own design note called rugby
teamless because it read the 5-row served bucket, which omits New Zealand; that
is why the helper reads the uncapped recall rows.

🔴 SCOPE, stated first so nobody widens it: this ship removes the ESPORTS cousins
(production 2026-09-25: `kings` 4 on its card, `falcons` 2, `warriors` 2, `lions`
1 — none of those queries recalls an esports club). It does NOT surface Golden
State on `warriors`: the Glasgow/Wigan rugby rows share a sport with a real club
(New Zealand), and `_demote_narrower_scope` sinks "Western Conference Finals" as
a sub-award. Both stay open on #7355; `test_rerank_applies_the_demotion` pins
the order as it really comes out, rugby included.
"""

from types import SimpleNamespace

import pytest

from app.routes import events as ev

WINDOW = ev._SEARCH_TEAM_WINDOW

WARRIORS_TEAMS = [
    ("Merrimack Warriors", "americanfootball_ncaaf"),
    ("Hawaii Rainbow Warriors", "americanfootball_ncaaf"),
    ("Merrimack Warriors", "americanfootball_ncaaf_fcs"),
    ("Merrimack Warriors", "baseball_ncaa"),
    ("Hawai'i Rainbow Warriors", "baseball_ncaa"),
    ("Golden State Warriors", "basketball_nba"),
    ("Golden State Warriors Blue", "basketball_nba_summer_league"),
    ("Merrimack Warriors", "basketball_ncaab"),
    ("Hawai'i Rainbow Warriors", "basketball_ncaab"),
    ("Hawai'i Rainbow Warriors", "basketball_wncaab"),
    ("Guyana Amazon Warriors", "cricket_caribbean_premier_league"),
    ("Merrimack Warriors", "lacrosse_ncaa"),
    ("New Zealand Warriors", "rugbyleague_nrl"),
    ("New Zealand Warriors", "rugbyleague_nrlw"),
    ("Golden Warriors", "soccer_usa_mls"),
    ("VC Warriors", "soccer_usa_mls"),
]


def _teams(pairs):
    return [SimpleNamespace(name=n, sport_key=k) for n, k in pairs]


def _m(mid, name, cat, volume=0.0):
    return SimpleNamespace(id=mid, name=name, llm_sport_category=cat, volume=volume)


# Production's open `%warriors%` markets, volume-ordered, 2026-09-25.
WARRIORS_MARKETS = [
    _m(13639204, "NBA: Stephen Curry to leave Warriors?", "basketball", 260538),
    _m(62072491, "LoL: ZSK vs Saigon Warriors (BO1)", "esports", 78220),
    _m(62072487, "LoL: Solary vs Saigon Warriors (BO1)", "esports", 63954),
    _m(62250341, "LoL: Saigon Warriors vs MVK Academy (BO5)", "esports", 1820),
    _m(60924180, "United Rugby Championship: Munster vs Glasgow Warriors", "rugby", 7),
    _m(62215099, "Honor of Kings: Kuaishou Gaming vs Rogue Warriors (BO5)", "esports", 5),
    _m(61380730, "Will Golden State Warriors advance to the Western Conference Finals", "basketball"),
    _m(61380762, "Will Golden State Warriors advance to the Western Conference Semifinals", "basketball"),
    _m(61619038, "United Rugby Championship: Glasgow Warriors vs Ulster", "rugby"),
    _m(61619036, "Super League: Wigan Warriors vs Wakefield Trinity", "rugby"),
]


def _ids(ms):
    return [m.id for m in ms]


class TestTheEvidence:
    def test_warriors_resolves_every_sport_its_clubs_play(self):
        cats = ev._team_evidence_sport_categories(_teams(WARRIORS_TEAMS), WINDOW)
        assert cats == {"football", "baseball", "basketball", "cricket",
                        "lacrosse", "rugby", "soccer"}

    def test_rugby_league_is_rugby_not_unknown(self):
        """The prefix `sport_keys.py` does not map. Unmapped would disarm the whole
        signal on `warriors`; mapped-to-nothing would call rugby teamless."""
        cats = ev._team_evidence_sport_categories(
            _teams([("New Zealand Warriors", "rugbyleague_nrl")]), WINDOW
        )
        assert cats == {"rugby"}

    def test_no_teams_disarms(self):
        """`trump`, `fed`: no team rows means nothing says which sports are real."""
        assert ev._team_evidence_sport_categories([], WINDOW) is None

    def test_a_full_window_disarms(self):
        """The 26th club could be in another sport; a full window is not a census."""
        rows = _teams([("City FC", "soccer_epl")] * WINDOW)
        assert ev._team_evidence_sport_categories(rows, WINDOW) is None
        assert ev._team_evidence_sport_categories(rows[:-1], WINDOW) == {"soccer"}

    @pytest.mark.parametrize("key", [None, "", "quidditch_world"])
    def test_an_untranslatable_team_disarms(self, key):
        rows = _teams([("Golden State Warriors", "basketball_nba"), ("X Warriors", key)])
        assert ev._team_evidence_sport_categories(rows, WINDOW) is None

    def test_every_team_prefix_on_production_translates(self):
        """The teams table's prefixes, measured 2026-09-25. A new one fails here
        instead of silently disarming every query that recalls it."""
        for prefix in ("tennis", "soccer", "mma", "boxing", "basketball", "baseball",
                       "americanfootball", "cricket", "icehockey", "lacrosse",
                       "aussierules", "rugbyleague", "handball", "rugbyunion"):
            got = ev._team_evidence_sport_categories(_teams([("T", f"{prefix}_x")]), WINDOW)
            assert got, prefix
            # and what it translates to is a category the demotion can compare
            assert got <= ev._SEARCH_SPORT_LLM_CATEGORIES, prefix


class TestTheDemotion:
    def test_warriors_sinks_esports_and_keeps_everything_else_in_order(self):
        cats = ev._team_evidence_sport_categories(_teams(WARRIORS_TEAMS), WINDOW)
        out = ev._demote_teamless_sport(list(WARRIORS_MARKETS), cats)
        assert _ids(out) == [
            13639204, 60924180, 61380730, 61380762,  # basketball + rugby, input order
            61619038, 61619036,
            62072491, 62072487, 62250341, 62215099,  # esports, input order
        ]

    def test_the_card_geometry_carries_no_esports(self):
        """The ship, in the card's own geometry: headline + four shown members."""
        cats = ev._team_evidence_sport_categories(_teams(WARRIORS_TEAMS), WINDOW)
        card = ev._demote_teamless_sport(list(WARRIORS_MARKETS), cats)[:5]
        assert [m.llm_sport_category for m in card].count("esports") == 0

    def test_giants_is_a_no_op(self):
        """Two real clubs in two sports: this signal never chooses between them."""
        cats = ev._team_evidence_sport_categories(
            _teams([("New York Giants", "americanfootball_nfl"),
                    ("San Francisco Giants", "baseball_mlb")]), WINDOW)
        ms = [_m(1, "Giants win the NL West", "baseball", 9),
              _m(2, "Giants to make the NFL playoffs", "football", 8)]
        assert ev._demote_teamless_sport(ms, cats) is ms

    def test_non_sport_and_unclaimed_categories_keep_their_place(self):
        cats = frozenset({"basketball"})
        ms = [_m(1, "Warriors trademark lawsuit", "legal", 9),
              _m(2, "Warriors documentary", None, 8),
              _m(3, "Warriors of Troy", "other", 7),
              _m(4, "Saigon Warriors vs X", "esports", 6),
              _m(5, "Golden State Warriors title", "basketball", 5)]
        assert _ids(ev._demote_teamless_sport(ms, cats)) == [1, 2, 3, 5, 4]

    def test_disarmed_evidence_changes_nothing(self):
        ms = list(WARRIORS_MARKETS)
        assert ev._demote_teamless_sport(ms, None) is ms
        assert ev._demote_teamless_sport(ms, frozenset()) is ms


class TestTheRerankCarriesIt:
    EXPANDED = [("warriors", None)]

    def test_rerank_applies_the_demotion(self):
        cats = ev._team_evidence_sport_categories(_teams(WARRIORS_TEAMS), WINDOW)
        out = ev._rerank_search_futures(list(WARRIORS_MARKETS), self.EXPANDED, None, cats)
        # The residual, pinned rather than hidden: the rugby cousins keep their
        # place and the two "Conference" markets sit below them (narrower scope).
        assert _ids(out) == [
            13639204, 60924180, 61619038, 61619036,
            61380730, 61380762,
            62072491, 62072487, 62250341, 62215099,
        ]

    def test_typeahead_shape_call_is_unchanged(self):
        """Typeahead passes no evidence; its order must not move."""
        before = ev._rerank_search_futures(list(WARRIORS_MARKETS), self.EXPANDED)
        assert _ids(before)[:3] == [13639204, 62072491, 62072487]

    def test_the_single_sport_rule_still_runs_last(self):
        """#7259 stays the stronger signal: with a resolved sport, a teamed but
        wrong-sport row still sinks below the right-sport ones."""
        cats = frozenset({"basketball", "rugby"})
        out = ev._rerank_search_futures(list(WARRIORS_MARKETS), self.EXPANDED, "basketball", cats)
        assert [m.llm_sport_category for m in out[:3]] == ["basketball"] * 3
        assert [m.llm_sport_category for m in out[3:6]] == ["rugby"] * 3
        assert [m.llm_sport_category for m in out[6:]] == ["esports"] * 4


class TestTheHandlerWiring:
    SRC = __import__("inspect").getsource(ev.search_events)

    def test_evidence_reads_the_uncapped_rows(self):
        assert "_team_evidence_sport_categories(\n        _team_result_rows," in self.SRC

    def test_teams_stage_runs_before_the_rerank(self):
        teams = self.SRC.index('_mark("teams")')
        rerank = self.SRC.index("_rerank_search_futures(\n        futures_markets_raw")
        assert teams < rerank

    def test_both_rerank_sites_carry_the_evidence(self):
        assert self.SRC.count("_team_sport_categories,\n") == 2

    def test_the_teams_shed_path_uses_a_savepoint_not_a_rollback(self):
        """It now runs while the futures rows are live; `_recover_search_session`
        rolls back the whole session and would expire them (gotcha #6)."""
        start = self.SRC.index("team_search_result = await db.execute(team_search_q)")
        stage = self.SRC[start - 600:self.SRC.index('_mark("teams")')]
        assert "_teams_savepoint = await db.begin_nested()" in stage
        assert "_recover_search_session" not in stage
