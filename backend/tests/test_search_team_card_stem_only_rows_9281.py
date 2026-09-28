"""#9281 — typing `pats`, `bucs` or `cats` cards the clubs, not Paterno or Bucknell.

Production 2026-09-28 03:24Z, `/search?q=pats` at 390px: the TEAMS card read
New England Patriots, Paterno (soccer), Patro Eisden Maasmechelen (soccer),
George Mason Patriots, Dallas Baptist Patriots. `bucs` added Milwaukee Bucks,
Bucknell Bison and Ohio State Buckeyes; `cats` added Western Carolina
Catamounts and Catania.

Cause: the Teams prefix arm (#4126) stems before the ``:*``, so ``pats:*`` is
``pat:*`` and recalls every `Pat…` name. #9277 measured the unconditional
"the typed word must start a name word" rule and refused it, because `nugs`,
`cards`, `pels` and `caps` reach their clubs only through that stem.

Fix (`_drop_stem_only_team_rows`, read by `_team_card_keyed`): the rule applies
only when some row already matches the whole word (MC0/MC1 — name, alias or
curated nickname). A row then survives if a word of it starts with what was
typed, or it carries the named club's own nickname word.

The windows below are production's 25-row Teams windows for each query,
compiled from `_team_search_rank` / `_build_team_search_filter` in the route's
own ORDER BY and read through db-query at 2026-09-28 03:3xZ, verbatim.
"""

from types import SimpleNamespace

from app.routes import events as ev

PATS_WINDOW = [
    (11, "New England Patriots", "americanfootball_nfl", "NE", ["pats", "Patriots"], 2.5),
    (12055, "Guilherme Pat", "mma_mixed_martial_arts", None, None, 1.5),
    (6159, "Pat Brown", "boxing_boxing", None, None, 1.5),
    (14167, "Pat Sabatini", "mma_mixed_martial_arts", None, None, 1.5),
    (12955, "Dallas Baptist", "baseball_ncaa", "DBU", ["Dallas Baptist Patriots", "Patriots"], 1.0),
    (894, "Dallas Baptist Patriots", "baseball_ncaa", "DBU", ["Dallas Baptist", "Patriots"], 1.0),
    (13149, "George Mason Patriots", "baseball_ncaa", "GMU", ["Patriots", "George Mason"], 1.0),
    (11230, "Connor Patterson", "mma_mixed_martial_arts", None, None, 0.5),
    (3509, "George Mason Patriots", "basketball_ncaab", "GMU", None, 0.5),
    (7764, "George Mason Patriots", "basketball_wncaab", None, None, 0.5),
    (17016, "Lenny Patrach", "boxing_boxing", None, None, 0.5),
    (17741, "New England Patriots", "americanfootball_nfl_preseason", None, None, 0.5),
    (5019, "Paterno", "soccer_other", None, None, 0.5),
    (12853, "Patricio Pitbull", "mma_mixed_martial_arts", None, None, 0.5),
    (15268, "Patrick Habirora", "mma_mixed_martial_arts", None, None, 0.5),
    (15512, "Patrick Kypson", "tennis_atp_french_open", None, None, 0.5),
    (13635, "Patrick Kypson", "tennis_atp_madrid_open", None, None, 0.5),
    (16782, "Patrick Kypson", "tennis_atp_wimbledon", None, None, 0.5),
    (14254, "Patrick Kypson", "tennis_atp_italian_open", None, None, 0.5),
    (10142, "Patrick Kypson", "tennis_atp_miami_open", None, None, 0.5),
    (17628, "Patrick O'Connor", "boxing_boxing", None, None, 0.5),
    (16889, "Patrik Kincl", "mma_mixed_martial_arts", None, None, 0.5),
    (16881, "Patrik Šebek", "mma_mixed_martial_arts", None, None, 0.5),
    (13922, "Patro Eisden Maasmechelen", "soccer_belgium_first_div", None, None, 0.5),
    (14157, "Patryk Grabowski", "mma_mixed_martial_arts", None, None, 0.5),
]

BUCS_WINDOW = [
    (554, "Tampa Bay Buccaneers", "americanfootball_nfl", "TB", ["Buccaneers", "bucs"], 2.5),
    (1439, "Bucknell Bison", "lacrosse_ncaa", "BUCKNELL", ["Bucknell", "Bison", "Bucknell Bison"], 2.0),
    (102, "Milwaukee Bucks", "basketball_nba", "MIL", ["Milwaukee", "Bucks", "Milwaukee Bucks"], 1.5),
    (19771, "Bucknell Bison", "americanfootball_ncaaf", "BUCK", ["Bison", "Bucknell"], 1.5),
    (3759, "Bucknell Bison", "baseball_ncaa", "BUCK", ["Bucknell", "Bison"], 1.5),
    (3607, "East Tennessee St Buccaneers", "baseball_ncaa", "ETSU", ["East Tennessee State Buccaneers", "Buccaneers", "ETSU"], 1.5),
    (17173, "Charleston Southern Buccaneers", "americanfootball_ncaaf", "CHSO", ["Charleston So", "Buccaneers"], 1.0),
    (3611, "Charleston Southern Buccaneers", "baseball_ncaa", "CHSO", ["Charleston So", "Buccaneers"], 1.0),
    (18615, "East Tennessee State Buccaneers", "americanfootball_ncaaf_fcs", "ETSU", ["ETSU", "Buccaneers"], 1.0),
    (14168, "East Tennessee State Buccaneers", "baseball_ncaa", "ETSU", ["ETSU", "Buccaneers"], 1.0),
    (14627, "Ohio State", "baseball_ncaa", "OSU", ["Ohio State Buckeyes", "Buckeyes"], 1.0),
    (879, "Ohio State Buckeyes", "baseball_ncaa", "OSU", ["Buckeyes", "Ohio State"], 1.0),
    (1424, "Ohio State Buckeyes", "lacrosse_ncaa", "OHIO STATE", ["Ohio State", "Buckeyes"], 1.0),
    (68, "Ohio State Buckeyes", "basketball_wncaab", "OSU", ["Ohio State", "Buckeyes"], 1.0),
    (198, "Ohio State Buckeyes", "basketball_ncaab", "OSU", ["Ohio State", "Buckeyes"], 1.0),
    (837, "Ohio State Buckeyes", "americanfootball_ncaaf", "OSU", ["Ohio State", "Buckeyes"], 1.0),
    (1773, "Atlético Bucaramanga", "soccer_conmebol_copa_sudamericana", None, None, 0.5),
    (16836, "Bucheon FC 1995", "soccer_korea_kleague1", None, None, 0.5),
    (18629, "Bucknell Bison", "americanfootball_ncaaf_fcs", None, None, 0.5),
    (2598, "Bucknell Bison", "basketball_wncaab", None, None, 0.5),
    (2655, "Bucknell Bison", "basketball_ncaab", None, None, 0.5),
    (393, "Charleston Southern Buccaneers", "basketball_ncaab", None, None, 0.5),
    (19153, "Charleston Southern Buccaneers", "americanfootball_ncaaf_fcs", None, None, 0.5),
    (7314, "Charleston Southern Buccaneers", "basketball_wncaab", None, None, 0.5),
    (18359, "Cristina Bucsa", "tennis_wta_monterrey_open", None, None, 0.5),
]

CATS_WINDOW = [
    (845, "Geelong Cats", "aussierules_afl", "GEEL", ["Cats"], 3.0),
    (17809, "Geelong Cats", "aussierules_aflw", None, None, 1.5),
    (15499, "Hamilton Tiger-Cats", "americanfootball_cfl", None, None, 1.5),
    (12762, "Sacramento River Cats", "baseball_milb", None, None, 1.5),
    (3746, "Vermont Catamounts", "lacrosse_ncaa", "VERMONT", ["Catamounts", "Vermont", "Vermont Catamounts"], 1.5),
    (16639, "Damoni Cato-Cain", "boxing_boxing", None, None, 1.0),
    (7303, "Vermont Catamounts", "basketball_wncaab", "UVM", ["Vermont", "Catamounts"], 1.0),
    (18632, "Western Carolina Catamounts", "americanfootball_ncaaf_fcs", "WCU", ["W Carolina", "Catamounts"], 1.0),
    (4071, "Western Carolina Catamounts", "baseball_ncaa", "WCU", ["W Carolina", "Catamounts"], 1.0),
    (19121, "Western Carolina Catamounts", "americanfootball_ncaaf", "WCU", ["Catamounts", "W Carolina"], 1.0),
    (4892, "Catania", "soccer_other", None, None, 0.5),
    (18106, "Catania FC", "soccer_italy_coppa_italia", None, None, 0.5),
    (4879, "Catanzaro", "soccer_other", None, None, 0.5),
    (1232, "Catherine Tacone Ramos", "boxing_boxing", None, None, 0.5),
    (18731, "Caty McNally", "tennis_wta_us_open", None, None, 0.5),
    (10668, "Caty McNally", "tennis_wta_miami_open", None, None, 0.5),
    (18069, "Caty McNally", "tennis_wta_cincinnati_open", None, None, 0.5),
    (13785, "Caty McNally", "tennis_wta_madrid_open", None, None, 0.5),
    (14306, "Caty McNally", "tennis_wta_italian_open", None, None, 0.5),
    (16690, "Caty McNally", "tennis_wta_wimbledon", None, None, 0.5),
    (6482, "Caty McNally", "tennis_wta_indian_wells", None, None, 0.5),
    (15541, "Caty McNally", "tennis_wta_french_open", None, None, 0.5),
    (17467, "Caty McNally", "tennis_wta_canadian_open", None, None, 0.5),
    (14747, "Jack Catterall", "boxing_boxing", None, None, 0.5),
    (11234, "Stefano Catacoli", "mma_mixed_martial_arts", None, None, 0.5),
]

NUGS_WINDOW = [
    (154, "Denver Nuggets", "basketball_nba", "DEN", ["Denver", "Nuggets"], 1.0),
    (16919, "Denver Nuggets", "basketball_nba_summer_league", None, None, 0.5),
]

CARDS_WINDOW = [
    (10740, "St. Louis Cardinals", "baseball_mlb", "STL", ["Cardinals", "St. Louis", "St.Louis Cardinals"], 1.5),
    (927, "Lamar Cardinals", "baseball_ncaa", "LAM", ["Lamar", "Cardinals", "Lamar Cardinals"], 1.5),
    (2394, "Stanford Cardinal", "basketball_wncaab", "ARK", ["Cardinal", "Stanford", "Stanford Cardinal"], 1.5),
    (2395, "Stanford Cardinal", "baseball_ncaa", "STAN", ["Stanford", "Cardinal", "Stanford Cardinal"], 1.5),
    (1179, "Stanford Cardinal", "basketball_ncaab", "STAN", ["Stanford", "Cardinal", "Stanford Cardinal"], 1.5),
    (541, "Arizona Cardinals", "americanfootball_nfl", "ARI", ["Cardinals"], 1.0),
    (15299, "Ball State Cardinals", "americanfootball_ncaaf", "BALL", ["Cardinals", "Ball State"], 1.0),
    (3904, "Ball State Cardinals", "baseball_ncaa", "BALL", ["Cardinals", "Ball State"], 1.0),
    (8989, "Ball State Cardinals", "basketball_wncaab", "BALL", ["Ball State", "Cardinals"], 1.0),
    (8727, "Incarnate Word Cardinals", "baseball_ncaa", "UIW", ["Cardinals", "Incarnate Word"], 1.0),
    (19715, "Incarnate Word Cardinals", "americanfootball_ncaaf", "UIW", ["Cardinals", "Incarnate Word"], 1.0),
    (8952, "Lamar Cardinals", "basketball_wncaab", "LAM", ["Lamar", "Cardinals"], 1.0),
    (18669, "Lamar Cardinals", "americanfootball_ncaaf_fcs", "LAM", ["Lamar", "Cardinals"], 1.0),
    (158, "Louisville Cardinals", "basketball_ncaab", "LOU", ["Cardinals", "Louisville"], 1.0),
    (73, "Louisville Cardinals", "basketball_wncaab", "LOU", ["Louisville", "Cardinals"], 1.0),
    (84, "Louisville Cardinals", "americanfootball_ncaaf", "LOU", ["Cardinals", "Louisville"], 1.0),
    (892, "Louisville Cardinals", "baseball_ncaa", "LOU", ["Cardinals", "Louisville"], 1.0),
    (15326, "Stanford Cardinal", "americanfootball_ncaaf", "STAN", ["Stanford", "Cardinal"], 1.0),
    (2692, "St. Louis Cardinals", "baseball_mlb_preseason", "STL", ["St. Louis", "Cardinals"], 1.0),
    (14472, "Arizona Cardinals", "americanfootball_nfl_preseason", None, None, 0.5),
    (2825, "Arturo Cardenas", "boxing_boxing", None, None, 0.5),
    (3114, "Ball State Cardinals", "basketball_ncaab", None, None, 0.5),
    (1848, "Cardiff City", "soccer_england_league1", None, None, 0.5),
    (5193, "Cardiff Draconians", "soccer_other", None, None, 0.5),
    (19163, "Incarnate Word Cardinals", "americanfootball_ncaaf_fcs", None, None, 0.5),
]

PELS_WINDOW = [
    (107, "New Orleans Pelicans", "basketball_nba", "NO", ["New Orleans", "Pelicans", "New Orleans Pelicans"], 1.5),
    (13034, "Andrea Pellegrino", "tennis_atp_monte_carlo_masters", None, None, 0.5),
    (16254, "Andrea Pellegrino", "tennis_atp_wimbledon", None, None, 0.5),
    (15099, "Andrea Pellegrino", "tennis_atp_french_open", None, None, 0.5),
    (14256, "Andrea Pellegrino", "tennis_atp_italian_open", None, None, 0.5),
    (13626, "Andrea Pellegrino", "tennis_atp_madrid_open", None, None, 0.5),
    (16892, "New Orleans Pelicans", "basketball_nba_summer_league", None, None, 0.5),
    (2869, "Pelicans", "icehockey_liiga", None, None, 0.5),
    (11232, "Tariq Pell", "mma_mixed_martial_arts", None, None, 0.5),
]

CAPS_WINDOW = [
    (65, "Washington Capitals", "icehockey_nhl", "WSH", ["Capitals", "Washington Capitals", "Washington"], 1.5),
    (5136, "Cape Town City", "soccer_other", None, None, 0.5),
    (1899, "Cape Verde", "soccer_fifa_world_cup", None, None, 0.5),
    (9381, "Delhi Capitals", "cricket_ipl", None, None, 0.5),
    (14135, "Dylan Capetillo", "boxing_boxing", None, None, 0.5),
    (19361, "Washington Capitals", "icehockey_nhl_preseason", None, None, 0.5),
]

BULL_WINDOW = [
    (34, "New York Red Bulls", "soccer_usa_mls", "RBNY", ["Red Bull New York", "NY Red Bulls", "New York", "Red Bull NY"], 6.0),
    (14534, "New York Red Bulls II", "soccer_other", None, ["Red Bulls", "Red Bull NY", "Red Bull New York"], 6.0),
    (36, "Chicago Bulls", "basketball_nba", "CHI", ["Bulls", "Chicago"], 3.0),
    (17120, "Buffalo Bulls", "americanfootball_ncaaf", "BUFF", ["Buffalo", "Bulls"], 3.0),
    (15294, "South Florida Bulls", "americanfootball_ncaaf", "USF", ["South Florida", "Bulls"], 3.0),
    (885, "South Florida Bulls", "baseball_ncaa", "USF", ["South Florida", "Bulls"], 3.0),
    (726, "South Florida Bulls", "basketball_ncaab", "USF", ["Bulls", "South Florida"], 3.0),
    (2705, "South Florida Bulls", "basketball_wncaab", "USF", ["South Florida", "Bulls"], 3.0),
    (1178, "Buffalo Bulls", "basketball_ncaab", None, None, 1.5),
    (6873, "Buffalo Bulls", "basketball_wncaab", None, None, 1.5),
    (9086, "Butler Bulldogs", "baseball_ncaa", "BUT", ["Butler", "Bulldogs", "Butler Bulldogs"], 1.5),
    (16917, "Chicago Bulls", "basketball_nba_summer_league", None, None, 1.5),
    (18672, "Citadel Bulldogs", "americanfootball_ncaaf_fcs", "CIT", ["The Citadel", "The Citadel Bulldogs", "Bulldogs"], 1.5),
    (12909, "Durham Bulls", "baseball_milb", None, None, 1.5),
    (2886, "Fresno St Bulldogs", "baseball_ncaa", "FRES", ["Fresno St", "Fresno State Bulldogs", "Bulldogs"], 1.5),
    (19117, "Gardner-Webb Runnin Bulldogs", "americanfootball_ncaaf", "GWEB", ["Runnin' Bulldogs", "Gardner-Webb Runnin' Bulldogs", "Gardner-Webb"], 1.5),
    (2878, "Georgia Bulldogs", "basketball_wncaab", "UGA", ["Georgia", "Lady Bulldogs", "Georgia Lady Bulldogs"], 1.5),
    (3247, "Mississippi St Bulldogs", "baseball_ncaa", "MSST", ["Mississippi State Bulldogs", "Mississippi St", "Bulldogs"], 1.5),
    (2555, "South Carolina St Bulldogs", "basketball_wncaab", "SCST", ["Lady Bulldogs", "SC State", "South Carolina State Lady Bulldogs"], 1.5),
    (10703, "The Citadel Bulldogs", "baseball_ncaa", "CIT", ["Bulldogs", "The Citadel Bulldogs", "The Citadel"], 1.5),
    (19288, "Yale University Bulldogs", "americanfootball_ncaaf_fcs", "YALE", ["Bulldogs", "Yale", "Yale Bulldogs"], 1.5),
    (728, "Alabama A&M Bulldogs", "basketball_ncaab", "AAMU", ["Bulldogs", "Alabama A&M"], 1.0),
    (8888, "Alabama A&M Bulldogs", "basketball_wncaab", "AAMU", ["Bulldogs", "Alabama A&M"], 1.0),
    (18651, "Alabama A&M Bulldogs", "americanfootball_ncaaf_fcs", "AAMU", ["Bulldogs", "Alabama A&M"], 1.0),
    (15243, "Bryant Bulldogs", "baseball_ncaa", "BRY", ["Bulldogs", "Bryant"], 1.0),
]


def _rows(window):
    return [
        SimpleNamespace(
            id=i, name=name, slug=None, abbreviation=abbr, logo_url_small=None,
            current_record=None, sport_key=sport_key, standings_updated_at=None,
            alternate_names=aliases, team_rank=rank,
        )
        for i, name, sport_key, abbr, aliases, rank in window
    ]


def _card(window, query):
    return [(c["name"], c["sport_key"]) for _k, c in ev._team_card_keyed(_rows(window), query)]


def _names(window, query):
    return [name for name, _ in _card(window, query)]


def _without_the_fix(monkeypatch):
    monkeypatch.setattr(ev, "_drop_stem_only_team_rows", lambda rows, _query: rows)


# --- the specimens -----------------------------------------------------------


def test_pats_cards_only_patriots_teams():
    assert _card(PATS_WINDOW, "pats") == [
        ("New England Patriots", "americanfootball_nfl"),
        ("George Mason Patriots", "basketball_ncaab"),
        ("Dallas Baptist Patriots", "baseball_ncaa"),
    ]


def test_bucs_cards_only_buccaneers_teams():
    assert _card(BUCS_WINDOW, "bucs") == [
        ("Tampa Bay Buccaneers", "americanfootball_nfl"),
        ("Charleston Southern Buccaneers", "americanfootball_ncaaf"),
        ("East Tennessee St Buccaneers", "baseball_ncaa"),
        ("East Tennessee State Buccaneers", "americanfootball_ncaaf_fcs"),
    ]


def test_cats_cards_only_cats_teams():
    assert _card(CATS_WINDOW, "cats") == [
        ("Geelong Cats", "aussierules_afl"),
        ("Hamilton Tiger-Cats", "americanfootball_cfl"),
        ("Sacramento River Cats", "baseball_milb"),
    ]


def test_strawman_without_the_fix_reproduces_production(monkeypatch):
    """The fixtures ARE the defect: with the filter neutralised, each card is
    exactly what production served, so the tests above fail for the right reason."""
    _without_the_fix(monkeypatch)
    assert _names(PATS_WINDOW, "pats") == [
        "New England Patriots", "Paterno", "Patro Eisden Maasmechelen",
        "George Mason Patriots", "Dallas Baptist Patriots",
    ]
    assert _names(BUCS_WINDOW, "bucs") == [
        "Tampa Bay Buccaneers", "Milwaukee Bucks", "Bucknell Bison",
        "Charleston Southern Buccaneers", "Ohio State Buckeyes",
    ]
    assert _names(CATS_WINDOW, "cats") == [
        "Geelong Cats", "Hamilton Tiger-Cats", "Sacramento River Cats",
        "Western Carolina Catamounts", "Catania",
    ]


# --- controls: the stem is the only way in, so nothing arms ------------------


def test_controls_with_no_whole_word_row_are_byte_identical(monkeypatch):
    """`nugs`/`cards`/`pels`/`caps` reach their clubs only through the stem —
    #9277's measured losses. No row matches the whole word, so the card is the
    same with and without the fix."""
    controls = [
        (NUGS_WINDOW, "nugs"), (CARDS_WINDOW, "cards"),
        (PELS_WINDOW, "pels"), (CAPS_WINDOW, "caps"),
    ]
    after = [_card(window, q) for window, q in controls]
    _without_the_fix(monkeypatch)
    assert after == [_card(window, q) for window, q in controls]
    assert [card[0][0] for card in after] == [
        "Denver Nuggets", "St. Louis Cardinals", "New Orleans Pelicans", "Washington Capitals",
    ]


def test_bull_keeps_bulldogs_because_they_start_with_what_was_typed(monkeypatch):
    """Armed (the Red Bulls match the whole word) and still unchanged: every
    `Bulldogs` row starts with the raw `bull`, so partial typing keeps working."""
    after = _card(BULL_WINDOW, "bull")
    _without_the_fix(monkeypatch)
    assert after == _card(BULL_WINDOW, "bull")
    assert ("Alabama A&M Bulldogs", "basketball_ncaab") in after


# --- the helper's own branches ------------------------------------------------


def test_multi_word_query_is_never_filtered():
    rows = _rows(PATS_WINDOW)
    assert ev._drop_stem_only_team_rows(rows, "new england pats") is rows


def test_no_whole_word_row_returns_the_rows_untouched():
    rows = _rows(NUGS_WINDOW)
    assert ev._drop_stem_only_team_rows(rows, "nugs") is rows


def test_the_whole_word_row_itself_always_survives():
    """A whole-word hit whose words do NOT start with the typed word (the `pats`
    alias on New England Patriots) is kept on the whole-word arm."""
    kept = ev._drop_stem_only_team_rows(_rows(PATS_WINDOW), "pats")
    assert "New England Patriots" in {r.name for r in kept}
    assert "Paterno" not in {r.name for r in kept}


def test_a_club_named_only_by_the_curated_map_is_a_whole_word_hit():
    """#9272 made the card score rows on the curated map's aliases too. A club
    whose STORED aliases lack the nickname (`rox` -> Colorado Rockies lives only
    in `team_aliases.py`) must still count as whole-word, or another row arming
    the filter would drop it. Synthetic window: `Roxborough Rox` stands in for
    any row that holds `Rox` as a stored alias."""
    window = [
        (10830, "Roxborough Rox", "soccer_other", None, ["Rox"], 1.0),
        (10737, "Colorado Rockies", "baseball_mlb", "COL", ["Rockies"], 1.0),
        (5020, "Roxana", "soccer_other", None, None, 0.5),
    ]
    kept = {r.name for r in ev._drop_stem_only_team_rows(_rows(window), "rox")}
    assert kept == {"Roxborough Rox", "Colorado Rockies", "Roxana"}


def test_strawman_stored_aliases_only_drops_the_map_named_club(monkeypatch):
    monkeypatch.setattr(
        ev, "_team_row_aliases",
        lambda row: [a for a in (row.alternate_names or []) if isinstance(a, str)],
    )
    window = [
        (10830, "Roxborough Rox", "soccer_other", None, ["Rox"], 1.0),
        (10737, "Colorado Rockies", "baseball_mlb", "COL", ["Rockies"], 1.0),
    ]
    kept = {r.name for r in ev._drop_stem_only_team_rows(_rows(window), "rox")}
    assert "Colorado Rockies" not in kept
