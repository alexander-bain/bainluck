"""lane1/200 — #3981: every Athletics rung resolves, so the spread ladder stops
being built from the opponent's half alone.

**The defect.** `resolve_rung_side` matches a Kalshi rung's short team text
against `events.home_team_name`/`away_team_name` by a token rule: every token
but the last must match in place, and the last may be a prefix of the next word
(`G` -> `Giants`) or the initials of the words remaining (`WS` -> `White Sox`).

`A's` reaches neither arm. `_name_tokens("A's")` -> `["as"]`; the club is stored
as the single token `Athletics`; "athletics" does not start with "as" (it starts
"at"), and the initials arm compares "a" to "as". So the resolver refused, and
the caller — correctly, per its own contract — dropped the rung rather than
guess a side.

**What that costs a reader, measured rather than assumed** (production
2026-09-09 05:55Z). `A's wins by ...` rungs: **470 across 144 markets**. Of
those 144 markets, **0 are all-A's and 144 are mixed** — so the ladder is never
dropped *whole*: the opponent's rungs resolve, the A's rungs do not, and
**470 of the 1,266 rungs in those markets (37%) are silently discarded**. The
served ladder is then inferred from ONE side. Live specimen, event `15307209`
(Toronto Blue Jays @ Athletics, market `60405687`, 6 rungs = 3 A's + 3 Toronto):
`/api/events/15307209/history` serves exactly 3 contracts, all of them the
Toronto rungs negated and inverted (`-1.5 -> 0.01`, `-2.5 -> 0.97`,
`-3.5 -> 0.99`), and none of the three A's rungs.

That is the half of this defect worth naming: a one-sided ladder is not a
missing answer, it is a *confident* one built on half the evidence — the same
failure mode `margin_rung_on_home_axis`'s own docstring records for sign-only
handling.

**Why the fix is a table and not a branch.** The issue is explicit, and it is
right: a hard-coded `A's` inside `_rung_names_side` makes the general
prefix/initials contract untrue and hides the next miss. The alias is data,
consulted before the rule, keyed on the whole token sequence so it can never
fire inside a longer name.

🔴 **THE SAFETY PROPERTY THIS FILE EXISTS TO GUARD.** The refusal is the current
safety property and must not be traded away to gain coverage. A Kalshi spread
market names the AWAY team first in its title, so a wrong side does not lose a
rung — it inverts the whole projected scoreline. Every test below that asserts
a side asserts BOTH orientations, and `test_the_alias_never_resolves_a_genuinely_
ambiguous_rung` pins that widening coverage did not widen guessing.
"""

import pytest

from app.utils.binary_spread import (
    _aliased_rung_tokens,
    _name_tokens,
    parse_margin_rung,
    resolve_rung_side,
)

ATHLETICS = "Athletics"


class TestTheAliasItself:
    def test_the_as_token_is_rewritten_to_the_stored_club_name(self):
        assert _aliased_rung_tokens(_name_tokens("A's")) == ["athletics"]

    def test_an_unlisted_name_is_returned_unchanged(self):
        assert _aliased_rung_tokens(_name_tokens("Kansas City")) == ["kansas", "city"]
        assert _aliased_rung_tokens(_name_tokens("New York G")) == ["new", "york", "g"]

    def test_the_rewrite_cannot_fire_inside_a_longer_name(self):
        """Keyed on the whole sequence, so a stray `as` token is never rewritten.

        If the table were consulted per token this would come back
        `["athletics", "villa"]` and start matching a football club.
        """
        assert _aliased_rung_tokens(["as", "villa"]) == ["as", "villa"]
        assert _aliased_rung_tokens(["oakland", "as"]) == ["oakland", "as"]

    def test_the_alias_does_not_mutate_its_input(self):
        tokens = ["as"]
        _aliased_rung_tokens(tokens)
        assert tokens == ["as"]


class TestTheLadderResolves:
    """The ship: an Athletics rung resolves to a side, in both orientations."""

    def test_athletics_at_home_resolves_home(self):
        assert resolve_rung_side("A's", ATHLETICS, "Toronto Blue Jays") == "home"

    def test_athletics_away_resolves_away(self):
        assert resolve_rung_side("A's", "Toronto Blue Jays", ATHLETICS) == "away"

    def test_the_opponent_still_resolves_to_the_other_side(self):
        """The alias must not steal a rung that names the opponent."""
        assert resolve_rung_side("Toronto", ATHLETICS, "Toronto Blue Jays") == "away"
        assert resolve_rung_side("Toronto", "Toronto Blue Jays", ATHLETICS) == "home"

    def test_the_real_production_rung_text_parses_and_then_resolves(self):
        """End to end on a string taken verbatim from `futures_outcomes`.

        `parse_margin_rung` splits the team text out; the resolver is what was
        dropping it. Both halves have to work or the ladder stays empty.
        """
        parsed = parse_margin_rung("A's wins by over 1.5 runs")
        assert parsed is not None, "the margin phrasing itself stopped parsing"
        team_text, threshold = parsed
        assert (team_text, threshold) == ("A's", 1.5)
        assert resolve_rung_side(team_text, ATHLETICS, "Toronto Blue Jays") == "home"

    @pytest.mark.parametrize(
        "rung_text",
        [
            "A's wins by over 1.5 runs",
            "A's wins by over 2.5 runs",
            "A's wins by over 3.5 runs",
            "A's wins by over 4.5 runs",
            "A's wins by over 5.5 runs",
        ],
    )
    def test_every_rung_of_a_real_ladder_resolves(self, rung_text):
        """The five thresholds production actually carries for this club.

        One resolving rung is not a ladder — the projection needs the rungs to
        land on one axis together, so the guard is over the whole ladder.
        """
        parsed = parse_margin_rung(rung_text)
        assert parsed is not None
        assert resolve_rung_side(parsed[0], "Toronto Blue Jays", ATHLETICS) == "away"


class TestTheRefusalSurvives:
    """🔴 Coverage was bought without buying a guess."""

    def test_the_alias_never_resolves_a_genuinely_ambiguous_rung(self):
        """`New York` in Giants v Jets still refuses, as it must."""
        assert resolve_rung_side("New York", "New York Giants", "New York Jets") is None

    def test_a_rung_naming_neither_side_still_refuses(self):
        assert resolve_rung_side("Seattle", ATHLETICS, "Toronto Blue Jays") is None

    @pytest.mark.parametrize(
        "soccer_club",
        [
            "Charlton Athletic",
            "Athletic Club",
            "Dover Athletic FC",
            "Dunfermline Athletic FC",
            "Athletic Bilbao",
        ],
    )
    def test_the_alias_does_not_reach_a_football_club(self, soccer_club):
        """The one false-positive direction that matters.

        Production holds dozens of clubs whose name contains "Athletic", so the
        alias would be dangerous if it matched them. It cannot, and by
        construction rather than luck: the prefix arm asks whether the SIDE
        token starts with the RUNG token, and "athletic" does not start with
        "athletics". Pinned because a future widening of the alias — to a bare
        "athletic", say — would silently start resolving these.
        """
        assert resolve_rung_side("A's", soccer_club, "Real Madrid") is None
        assert resolve_rung_side("A's", "Real Madrid", soccer_club) is None

    def test_an_athletics_v_athletic_fixture_refuses_rather_than_guesses(self):
        """The adversarial case: if both sides could match, refuse.

        Contrived as a fixture, but it is the exact shape the refusal exists
        for, and it proves the alias runs through the both-match test rather
        than short-circuiting past it.
        """
        assert resolve_rung_side("A's", ATHLETICS, ATHLETICS) is None
