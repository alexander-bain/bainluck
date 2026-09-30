"""#9277: `alcs` / `alds` must not card Alcorn State / Aldosivi.

Production, 2026-09-28 03:00Z, `/search` at 390px:

    alcs  -> TEAMS Alcorn State Braves, Alcorn St Braves, GD Alcochetense
             + four Alcorn football finals, above the ALCS answers card
    alds  -> TEAMS Aldosivi Mar del Plata + six Aldosivi games, and no ALDS
             market on the page (politics led the futures)
    nlds / nlcs -> teams 0, games 0, NLDS/NLCS markets first (the control)

Cause: the Teams prefix arm (#4126) compiles `to_tsquery('english', 'alcs:*')`,
and the stemmer reduces it to `alc:*` before the prefix applies. The empty-rail
rescue then fills the games rail through the same `_build_team_search_filter`.
So refusing the prefix arm for these tokens clears the card and the games.

These are compiled-SQL checks: they need no Postgres and run in every CI job.
"""

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.events import (
    _TEAM_PREFIX_REFUSED_TOKENS,
    _build_team_search_filter,
    _last_token_prefix_tsquery,
    _team_prefix_tsquery,
    _team_search_rank,
)


def _sql(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


STAGES = ["alcs", "alds", "nlcs", "nlds"]


class TestStageAcronymsGetNoTeamPrefixArm:
    @pytest.mark.parametrize("q", STAGES)
    def test_no_prefix_tsquery(self, q):
        assert _team_prefix_tsquery(q) is None

    @pytest.mark.parametrize("q", ["ALCS", "Alds", " nlds "])
    def test_case_and_whitespace_do_not_escape_the_refusal(self, q):
        assert _team_prefix_tsquery(q) is None

    @pytest.mark.parametrize("q", STAGES)
    def test_team_filter_carries_no_prefix_arm(self, q):
        sql = _sql(_build_team_search_filter(q))
        assert ":*" not in sql, sql
        # The whole-lexeme arms still run: this removes recall only from the
        # stemmed prefix, never from a team that owns the word.
        assert "websearch_to_tsquery" in sql

    @pytest.mark.parametrize("q", STAGES)
    def test_team_rank_carries_no_prefix_score(self, q):
        assert ":*" not in _sql(_team_search_rank(q))

    def test_refused_as_the_last_token_of_a_longer_query(self):
        assert _team_prefix_tsquery("yankees alcs") is None

    def test_the_set_is_exactly_the_four_measured_tokens(self):
        """Adding a token here is a recall decision for the Teams card; it needs
        its own measurement, not a quiet edit."""
        assert _TEAM_PREFIX_REFUSED_TOKENS == frozenset(STAGES)


class TestControlsKeepTheirPrefixArm:
    """The stem-prefix arm is what reaches these clubs today (measured on
    production: `nugs` -> Denver Nuggets, `cards` -> St. Louis Cardinals,
    `pels` -> New Orleans Pelicans, `caps` -> Washington Capitals, none via a
    word start). Their SQL must be unchanged."""

    @pytest.mark.parametrize(
        "q, expected",
        [
            ("yank", "'yank:*'"),
            ("yanks", "'yanks:*'"),
            ("nugs", "'nugs:*'"),
            ("cards", "'cards:*'"),
            ("pels", "'pels:*'"),
            ("caps", "'caps:*'"),
            ("red sox", "'red & sox:*'"),
            ("alcs yank", "'alcs & yank:*'"),
        ],
    )
    def test_prefix_arm_still_built(self, q, expected):
        assert expected in _sql(_team_prefix_tsquery(q))
        assert expected in _sql(_build_team_search_filter(q))

    @pytest.mark.parametrize("q", ["alcsx", "nldsa", "alc", "ald"])
    def test_only_whole_tokens_are_refused(self, q):
        assert _team_prefix_tsquery(q) is not None

    @pytest.mark.parametrize("q", STAGES)
    def test_futures_ordering_prefix_is_untouched(self, q):
        """The refusal is the Teams arm's. The futures ORDER BY shares the
        underlying builder, and there `alcs:*` ranks the ALCS markets. It must
        still get its prefix key."""
        assert f"'{q}:*'" in _sql(_last_token_prefix_tsquery(q))
