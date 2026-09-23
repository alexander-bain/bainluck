"""#8084 arm B — winning a grid key does not mean having anything to put in it.

Arm A (PR #8085) is about the FETCH: `_get_team_metadata` asks Postgres for
`Team.name ILIKE '%<raw venue name>%'` and then keys the answers with a
normalizer that strips diacritics, so the accented clubs were never loaded at
all. This is the other half of the same reader complaint, and it is a different
mechanism with no code in common: these rows ARE loaded, they DO match, and
they still render as bare text. The two arms are independent — this file's
harness hands the function its rows directly, so nothing here depends on #8085
landing, and the diffs touch different regions of the same function.

`_rank` orders candidates `(in_scope, id)` and the write loop is last-one-wins.
Nothing in that order asks whether the winning row carries a crest. So a row
minted by a poller with nothing but a name outranks the real row purely for
being newer. Measured on production 2026-09-22 with the grid's own SQL:

    145   Manchester United  soccer_epl                          espn 360  crest ✓  1-2-2
    11861 Manchester United  soccer_uefa_champs_league_women     espn -    crest ✗  -

Both are out of scope for `champions-league` (its `sport_keys` is exactly
`["soccer_uefa_champs_league"]`), so the tie falls to `id`, 11861 wins, and a
reader on `/playoffs/champions-league` sees Manchester United as bare text.
`Real Betis` (5670 `soccer_uefa_europa_league` over 2194 `soccer_spain_la_liga`)
and `BYU Cougars` (2408 `basketball_wncaab` over 890/183) are the same shape.

THE FIX FILLS FIELDS, IT DOES NOT RE-PICK THE WINNER, and the two are not
interchangeable. Re-ranking on "whichever row has more in it" would hand the
Champions League grid Manchester United's ENGLISH PREMIER LEAGUE record, which
is precisely the defect #6230 was opened for — a spring-training record served
on an MLB grid. So a crest and colours are inherited, because they are true of
the club; a record, conference, division, seed and `espn_id` never are, because
they are true of a club in ONE competition. Half these tests exist to hold that
line, not to prove the fill works.

WHY IT CANNOT WIDEN THE MATCH. The donor is whatever already sits under the key,
so it is by construction a row `_alias_may_claim` and `_alias_contest_winner`
already admitted — a refused row never wrote and so can never donate. The crest
this serves is one the function would have served for that key anyway had the
winning row not existed.
"""

import pytest

from app.routes.playoffs import _get_team_metadata

CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/360.png"
OTHER_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/2633.png"


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeTeam:
    """Only the attributes `_get_team_metadata` reads."""

    def __init__(
        self,
        team_id,
        name,
        sport_key,
        espn_id=None,
        abbreviation=None,
        alternate_names=None,
        record=None,
        logo=None,
        primary_color=None,
        secondary_color=None,
        standings_data=None,
    ):
        self.id = team_id
        self.name = name
        self.sport = _FakeSport(sport_key)
        self.espn_id = espn_id
        self.abbreviation = abbreviation
        self.alternate_names = list(alternate_names or [])
        self.current_record = record
        self.logo_url_small = logo
        self.logo_url_large = None
        self.primary_color = primary_color
        self.secondary_color = secondary_color
        self.standings_data = standings_data


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


async def _lookup(rows, league_slug, names):
    return await _get_team_metadata(
        _FakeSession(rows), set(names), league_slug=league_slug
    )


# --- The production specimens, as production holds them ---------------------


def _man_utd_epl():
    """Row 145 — the real club: crest, colours, anchor, an EPL record."""
    return _FakeTeam(
        145,
        "Manchester United",
        "soccer_epl",
        espn_id="360",
        abbreviation="MAN",
        record="1-2-2",
        logo=CREST,
        primary_color="#DA291C",
        secondary_color="#FBE122",
    )


def _man_utd_womens_ucl():
    """Row 11861 — a name and nothing else, and the higher `id`."""
    return _FakeTeam(11861, "Manchester United", "soccer_uefa_champs_league_women")


def _byu_baseball():
    return _FakeTeam(
        890,
        "BYU Cougars",
        "baseball_ncaa",
        espn_id="127",
        abbreviation="BYU",
        record="28-28",
        logo=OTHER_CREST,
        primary_color="#002E5D",
    )


def _byu_womens_hoops():
    return _FakeTeam(
        2408, "BYU Cougars", "basketball_wncaab", abbreviation="BYU", record="22-10"
    )


# --- The ship ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_manchester_united_keeps_its_crest_when_an_empty_row_wins_the_key():
    """THE SPECIMEN. Revert the fill and `logo_url` is None — the bare row."""
    meta = await _lookup(
        [_man_utd_epl(), _man_utd_womens_ucl()],
        "champions-league",
        {"Manchester United"},
    )
    row = meta["manchester united"]

    assert row["logo_url"] == CREST, (
        "the Champions League grid serves Manchester United as bare text: the "
        "empty women's-CL row won the key on `id` and took the crest with it"
    )
    assert row["primary_color"] == "#DA291C"
    assert row["secondary_color"] == "#FBE122"


@pytest.mark.asyncio
async def test_the_empty_row_still_wins_the_key_scope_order_is_untouched():
    """The fill is not a re-rank. #6230's ordering decides `team_id` exactly as
    before; only the empty visual fields move."""
    meta = await _lookup(
        [_man_utd_epl(), _man_utd_womens_ucl()],
        "champions-league",
        {"Manchester United"},
    )

    assert meta["manchester united"]["team_id"] == 11861


@pytest.mark.asyncio
async def test_the_english_record_does_not_follow_the_crest_onto_the_ucl_grid():
    """THE LINE THIS FIX MUST NOT CROSS (#6230).

    `1-2-2` is Manchester United's ENGLISH PREMIER LEAGUE record. A rule that
    preferred "whichever row has more in it" would print it under a Champions
    League column, which is the spring-training defect wearing a different
    shirt. A club's crest is the club's; its record belongs to a competition.
    """
    meta = await _lookup(
        [_man_utd_epl(), _man_utd_womens_ucl()],
        "champions-league",
        {"Manchester United"},
    )
    row = meta["manchester united"]

    assert (
        row["record"] is None
    ), "an EPL record has been inherited onto the Champions League grid"
    assert row["espn_id"] is None, (
        "espn_id is per-sport and is the clinch overlay's join key (#7663); "
        "inheriting it across competitions joins the wrong standings row"
    )


@pytest.mark.asyncio
async def test_conference_division_and_seed_are_never_inherited():
    """The same line, for the three standings fields. A donor row carrying a
    conference from ANOTHER competition must not populate this grid's column."""
    donor = _FakeTeam(
        145,
        "Manchester United",
        "soccer_epl",
        logo=CREST,
        standings_data={
            "conference": "Premier League",
            "division": "None",
            "position": 4,
        },
    )
    meta = await _lookup(
        [donor, _man_utd_womens_ucl()], "champions-league", {"Manchester United"}
    )
    row = meta["manchester united"]

    assert row["logo_url"] == CREST
    assert row["conference"] is None
    assert row["seed"] is None


@pytest.mark.asyncio
async def test_a_school_crest_crosses_sports_but_its_baseball_record_does_not():
    """BYU on `/playoffs/ncaa-football`: the NCAAF grid has no BYU football row
    at all, so every candidate is another sport. The crest is the university's
    and is right anywhere; `28-28` is a BASEBALL record and belongs nowhere near
    a football grid. The honest outcome is a crested row with no record.

    ARM B COULD NOT DELIVER THAT SENTENCE AND #8131 DOES. This test used to
    assert `record == "22-10"` — the winning row's own women's-basketball
    season — because arm B's reach was the INHERITANCE fill, which may only
    write fields that were empty and so was never entitled to clear one. The
    docstring above named the right answer anyway, and a reader duly found
    `BYU Cougars 22-10` on the College Football Playoff grid. `_crosses_sport_
    boundary` closes that gap, so the assertion now matches the paragraph it
    always sat under.

    Arm B's own claim — that the fill never DONATES a record across rows — is
    untouched and is still pinned by
    `test_the_english_record_does_not_follow_the_crest_onto_the_ucl_grid`,
    where donor and winner are both soccer and the suppression cannot fire.
    """
    meta = await _lookup(
        [_byu_baseball(), _byu_womens_hoops()], "ncaa-football", {"BYU Cougars"}
    )
    row = meta["byu cougars"]

    assert row["logo_url"] == OTHER_CREST, (
        "the university's crest is right on any of its teams' grids and must "
        "survive the season being dropped"
    )
    assert row["record"] is None, (
        "22-10 is a women's basketball season (32 games) on a football grid; "
        "28-28 is a baseball one. Neither belongs here and there is no BYU "
        "football row to prefer instead (#8131)"
    )


@pytest.mark.asyncio
async def test_an_in_scope_empty_row_inherits_from_an_out_of_scope_crest():
    """East Tennessee St on `/playoffs/ncaa-basketball`: 1083 is `basketball_ncaab`
    and therefore IN scope, so #6230's preference hands it the key ahead of the
    crested `baseball_ncaa` row — and hands the reader bare text. Scope decides
    who the row IS; it does not have to decide what the club LOOKS like."""
    in_scope_empty = _FakeTeam(1083, "East Tennessee St Buccaneers", "basketball_ncaab")
    out_of_scope_crest = _FakeTeam(
        3607,
        "East Tennessee St Buccaneers",
        "baseball_ncaa",
        espn_id="304",
        abbreviation="ETSU",
        logo=OTHER_CREST,
    )
    meta = await _lookup(
        [in_scope_empty, out_of_scope_crest],
        "ncaa-basketball",
        {"East Tennessee St Buccaneers"},
    )
    row = meta["east tennessee st buccaneers"]

    assert row["team_id"] == 1083, "scope preference must still pick the row"
    assert row["logo_url"] == OTHER_CREST


# --- The refusals -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_row_that_already_has_a_crest_is_never_touched():
    """THE ADDITIVE CLAIM, stated as a test. The fill can only write a field
    that is empty, so no row a reader can see today changes. Here the winner
    carries its own crest and the loser carries a different one."""
    winner = _FakeTeam(
        11861,
        "Manchester United",
        "soccer_uefa_champs_league_women",
        logo=OTHER_CREST,
        primary_color="#111111",
    )
    meta = await _lookup(
        [_man_utd_epl(), winner], "champions-league", {"Manchester United"}
    )
    row = meta["manchester united"]

    assert row["logo_url"] == OTHER_CREST
    assert row["primary_color"] == "#111111"


@pytest.mark.asyncio
async def test_with_no_crested_candidate_the_row_stays_bare_rather_than_guessing():
    """Grambling St Tigers, unfixed on purpose: rows 1129, 2405 and 3046 are all
    empty, and the crested `Grambling Tigers` (13746) is a DIFFERENT NAME and so
    a different key. A bare row is a far smaller harm than a wrong crest, so
    the rule declines rather than reaching for a name that is merely similar."""
    meta = await _lookup(
        [
            _FakeTeam(1129, "Grambling St Tigers", "basketball_ncaab"),
            _FakeTeam(2405, "Grambling St Tigers", "baseball_ncaa"),
            _FakeTeam(13746, "Grambling Tigers", "baseball_ncaa", logo=OTHER_CREST),
        ],
        "ncaa-basketball",
        {"Grambling St Tigers"},
    )

    assert meta["grambling st tigers"]["logo_url"] is None
    assert meta["grambling tigers"]["logo_url"] == OTHER_CREST


@pytest.mark.asyncio
async def test_a_refused_impostor_cannot_donate_the_crest_it_was_refused():
    """#7727 HOLDS THROUGH THE FILL, which is the whole safety argument.

    `Auburn Tigers` carrying the alias `Texas Tech Red Raiders` is the
    production specimen #7727 was opened on. `_alias_may_claim` refuses it
    because the two rows are anchored to different ESPN teams, so it never
    writes the key — and a row that never wrote can never be the `previous`
    the fill reads. If the fill had been implemented over "every candidate
    row" instead of "whatever already holds the key", Auburn's crest would
    arrive under Texas Tech's name.
    """
    texas_tech = _FakeTeam(
        2641, "Texas Tech Red Raiders", "basketball_ncaab", espn_id="2641"
    )
    auburn = _FakeTeam(
        271,
        "Auburn Tigers",
        "basketball_ncaab",
        espn_id="2",
        alternate_names=["Texas Tech Red Raiders"],
        logo=OTHER_CREST,
    )
    meta = await _lookup(
        [texas_tech, auburn], "ncaa-basketball", {"Texas Tech Red Raiders"}
    )

    assert meta["texas tech red raiders"]["team_id"] == 2641
    assert (
        meta["texas tech red raiders"]["logo_url"] is None
    ), "Auburn's crest reached Texas Tech's key through the fill"


@pytest.mark.asyncio
async def test_a_crest_inherited_under_one_key_does_not_leak_to_the_rows_others():
    """THE COPY, NOT THE MUTATION. One `meta` object is shared by every key a
    row writes — its own name and each alias. Filling it in place would carry a
    crest inherited under the alias key across to the row's own name, inventing
    a crest for a club that has none."""
    crested_incumbent = _FakeTeam(10, "Fulham", "soccer_epl", logo=CREST)
    bare_row_with_alias = _FakeTeam(
        99, "Fulham Reserves", "soccer_epl", alternate_names=["Fulham"]
    )
    meta = await _lookup(
        [crested_incumbent, bare_row_with_alias],
        "epl",
        {"Fulham", "Fulham Reserves"},
    )

    assert meta["fulham"]["logo_url"] == CREST
    assert (
        meta["fulham reserves"]["logo_url"] is None
    ), "the alias key's inherited crest leaked onto the row's own name"
