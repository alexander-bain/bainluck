"""#7501 — the slug ladder, and the token rung 2 mints against.

The ship is "a club with no `teams.slug` gets its page back". A fill that writes
a slug no URL composes delivers none of it while making the census read as
delivered — non-NULL is not reachable. So the assertions that matter here are
about rung 2, the collision rung, and specifically about which token it suffixes.

`f1a2b3c4d5e6` (the May migration, the only other writer this column has ever
had) used `sport_key.split("_")[-1]`. `buildTeamPageUrl` in
`frontend/lib/teamUrls.ts` uses an explicit map with a `parts[1:]` fallback. The
two agree on two-part keys and disagree on every three-part one, which is 221
tennis rows and every non-top-flight soccer competition. Copying the migration
was the available mistake; these are the rows that would have caught it.
"""

import pytest

from app.utils.team_slug import slug_candidates, url_league_segment


class TestTheURLSegment:
    """What the frontend actually puts in the path."""

    @pytest.mark.parametrize(
        "sport_key,segment",
        [
            # Mapped: the map's value, which is not derivable from the key.
            ("soccer_uefa_champs_league", "ucl"),
            ("soccer_spain_la_liga", "laliga"),
            ("mma_mixed_martial_arts", "ufc"),
            ("soccer_usa_mls", "mls"),
            # Unmapped, two-part: the fallback and the map agree.
            ("americanfootball_ncaaf", "ncaaf"),
            ("soccer_epl", "epl"),
            # Unmapped, three-part: `parts[1:]` joined, NOT the last token.
            ("soccer_efl_champ", "efl_champ"),
            ("tennis_atp_us_open", "atp_us_open"),
        ],
    )
    def test_the_segment_is_the_one_the_frontend_composes(self, sport_key, segment):
        assert url_league_segment(sport_key) == segment

    @pytest.mark.parametrize(
        "sport_key,migration_token",
        [
            ("soccer_uefa_champs_league", "league"),
            ("soccer_efl_champ", "champ"),
            ("tennis_atp_us_open", "open"),
        ],
    )
    def test_the_segment_is_not_the_migrations_token(self, sport_key, migration_token):
        """The whole reason this map exists rather than one `split` call.

        Asserted as a NON-equality on purpose: the positive cases above would
        still pass if someone reintroduced `split("_")[-1]` for the unmapped
        keys, because it is right for the two-part ones.
        """
        assert url_league_segment(sport_key) != migration_token

    @pytest.mark.parametrize("sport_key", [None, "", "   ", "golf"])
    def test_a_key_the_frontend_builds_no_url_for_gets_no_segment(self, sport_key):
        """`buildTeamPageUrl` returns null for these, so no suffix is reachable.

        Rung 2 is skipped rather than invented; the ladder falls to the id rungs,
        which compose a page under whatever path the reader arrived by.
        """
        assert url_league_segment(sport_key) is None

    def test_the_key_is_matched_case_and_whitespace_insensitively(self):
        assert url_league_segment("  SOCCER_UEFA_CHAMPS_LEAGUE ") == "ucl"


class TestTheLadder:
    def test_the_three_rungs_in_order_then_the_terminal(self):
        assert slug_candidates("Manchester City", "soccer_uefa_champs_league", 42) == [
            "manchester-city",
            "manchester-city-ucl",
            "manchester-city-42",
            "team-42",
        ]

    def test_rung_two_never_mints_the_unreachable_suffix(self):
        """`manchester-city-league` is what the migration wrote and what
        `/sport/soccer/ucl/team/...` cannot reach. It is exactly the row this
        ship exists to stop producing."""
        assert "manchester-city-league" not in slug_candidates(
            "Manchester City", "soccer_uefa_champs_league", 42
        )

    def test_georgia_the_specimen(self):
        """The reader's own case: team 15263, `americanfootball_ncaaf`, whose
        page read "We don't have a football page for Georgia Bulldogs." while
        `GET /api/teams/15263` served a 3-0 record."""
        assert slug_candidates("Georgia Bulldogs", "americanfootball_ncaaf", 15263)[
            :2
        ] == ["georgia-bulldogs", "georgia-bulldogs-ncaaf"]

    def test_a_key_with_no_league_half_skips_rung_two(self):
        assert slug_candidates("Some Club", "golf", 7) == [
            "some-club",
            "some-club-7",
            "team-7",
        ]

    @pytest.mark.parametrize("name", ["", "   ", "!!!", "—", None])
    def test_a_name_that_slugifies_to_nothing_still_gets_a_page(self, name):
        """A reachable ugly URL beats no page. The list is never empty, because
        an empty ladder would be a row the filler silently skips forever."""
        assert slug_candidates(name, "soccer_epl", 99) == ["team-99"]

    def test_the_terminal_rungs_carry_the_primary_key(self):
        """Two of the four rungs are unique by construction, which is what makes
        `unresolved` a report rather than the normal case."""
        ladder = slug_candidates("Arsenal", "soccer_epl", 1234)
        assert ladder[-2:] == ["arsenal-1234", "team-1234"]

    def test_a_name_already_ending_in_its_segment_does_not_repeat_a_rung(self):
        """Dedup is not cosmetic: a duplicated candidate spends a rung on a
        string the row was just refused, and the ladder is only four long."""
        ladder = slug_candidates("Epl", "soccer_epl", 5)
        assert ladder == ["epl", "epl-epl", "epl-5", "team-5"]
        assert len(ladder) == len(set(ladder))

    def test_every_candidate_fits_the_column(self):
        """`teams.slug` is `String(200)`. A suffix truncated away is a collision
        with the rung above it — the one failure the ladder cannot recover from,
        because both rungs would then be the same refused string."""
        ladder = slug_candidates("Q" * 400, "soccer_uefa_champs_league", 987654)
        assert all(len(c) <= 200 for c in ladder)
        assert len(ladder) == len(set(ladder))
        assert ladder[-1] == "team-987654"
