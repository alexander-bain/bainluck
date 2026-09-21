"""#6806 — `app/utils/team_pattern_match.py`: a pattern counts only as whole tokens.

Pure-function controls for the boundary rule the related-futures route now
classifies with. The route-level proof (a foreign club's championship price
refused on the real request, legitimate rows kept by market/outcome id) is
`tests/integration/test_route_related_futures_identity_6806.py`; this file
pins the rule itself, the LIKE-escape round trip, and the exact
`_team_name_patterns` outputs the rule is applied to, so a change to either
side names the other.
"""

import pytest

from app.routes.events import _escape_like, _team_name_patterns
from app.utils.team_pattern_match import (
    any_pattern_matches_token,
    pattern_matches_token,
    unescape_like_pattern,
)


def _the_replaced_substring_rule(name: str, patterns: list[str]) -> bool:
    """The exact body of `_matches_any` BEFORE #6806, kept here so every claim
    of the form "the old rule did serve this" is executed rather than asserted.

    Copied verbatim from the removed hunk. If the route's escape convention ever
    changes, this goes stale and the sweep table below stops being evidence —
    which is why it lives beside the table and not in a comment.
    """
    name_lower = name.lower()
    for p in patterns:
        clean = p.replace("\\%", "%").replace("\\_", "_").replace("\\\\", "\\")
        if clean.lower() in name_lower:
            return True
    return False


# ── The specimen and its class ──────────────────────────────────────────────


class TestTheSpecimen:
    """`_team_name_patterns("Lech Poznań")` is `["Lech Poznań", "Poznań", "Lech"]`
    (asserted below, so a pattern-builder change is visible here)."""

    def test_the_patterns_are_what_the_route_searches_with(self):
        assert _team_name_patterns("Lech Poznań") == ["Lech Poznań", "Poznań", "Lech"]

    @pytest.mark.parametrize(
        "label",
        [
            "Anderlecht",  # interior — the #6806 specimen (Belgian Pro League)
            "Lechia Gdansk",  # prefix of a longer token — the 2026-09-18 payload
            "Lechia Gdańsk",
            "RSC Anderlecht",
            "Wałbrzych",  # no `lech` at all: unchanged refusal
        ],
    )
    def test_another_club_is_refused(self, label):
        assert not any_pattern_matches_token(label, _team_name_patterns("Lech Poznań"))

    @pytest.mark.parametrize(
        "label",
        [
            "Lech Poznan",  # Kalshi's unaccented spelling (outcome 4367)
            "Lech Poznań",
            "KKS Lech Poznań",  # club-type prefix
            "Lech",  # bare short name
            "Poznań",  # bare city label
            "LECH POZNAN",  # case
            "Lech Poznan (H)",
        ],
    )
    def test_the_club_itself_is_kept(self, label):
        assert any_pattern_matches_token(label, _team_name_patterns("Lech Poznań"))

    def test_the_old_rule_would_have_served_both_foreign_rows(self):
        """Names the defect: the substring test this replaces.

        live/363: this asserted `"lech" in "anderlecht"` — a property of two
        string LITERALS, true whatever this repo does, so it could not fail and
        proved nothing. CodeQL called it (`py/comparison-of-constants`, two
        warning-level alerts on PR #6856) and CodeQL was right. Rewritten to run
        the REAL replaced predicate over the REAL patterns the route builds, so
        it is evidence of the defect instead of an illustration of it.
        """
        patterns = _team_name_patterns("Lech Poznań")
        for foreign in ("Anderlecht", "Lechia Gdansk"):
            assert _the_replaced_substring_rule(foreign, patterns), foreign
            assert not any_pattern_matches_token(foreign, patterns), foreign


# ── The boundary rule, edge by edge ─────────────────────────────────────────


class TestTheBoundaryRule:
    @pytest.mark.parametrize(
        "label, pattern, expected",
        [
            # suffix / prefix / whole
            ("Boston Celtics", "Celtics", True),
            ("Boston Celtics", "Boston", True),
            ("Boston Celtics", "Boston Celtics", True),
            ("Celtics", "Celtics", True),
            # interior fragments, both sides
            ("Bostonians", "Boston", False),
            ("Celticsville", "Celtics", False),
            ("Anderlecht", "Lech", False),
            ("Lechia", "Lech", False),
            # digits are token characters too
            ("Philadelphia 76ers", "76ers", True),
            ("Philadelphia 176ers", "76ers", False),
            ("San Francisco 49ers", "49ers", True),
            # the short alias that used to claim another city
            ("LA Clippers", "LA", True),
            ("Atlanta Hawks", "LA", False),
            ("Atlanta", "LA", False),
            # punctuation is a boundary
            ("Boston at Golden State: Rebounds", "Boston", True),
            ("Boston at Golden State: Rebounds", "Golden State", True),
            ("Golden State vs. Boston", "Boston", True),
            ("Celtics-Heat Series", "Celtics", True),
            ("Jayson Tatum: 25+", "Jayson Tatum", True),
            # hyphen and apostrophe INSIDE the pattern
            ("AS Saint-Étienne", "Saint-Étienne", True),
            ("Saint-Étienne", "Saint-Étienne", True),
            ("Oakland A's", "Oakland A's", True),
            ("Oakland A's", "Oakland", True),
            ("Oaklandia FC", "Oakland", False),
            # a pattern whose EDGE is not a token character needs no boundary there
            ("Miami (OH) RedHawks", "Miami (OH)", True),
            ("Miami (OH)RedHawks", "Miami (OH)", True),
            ("St. Louis Cardinals", "St. Louis", True),
            ("St.Louis Cardinals", "St.", True),
            # a second occurrence can be the one that sits on a boundary
            ("Lechia Gdansk / Lech Poznan", "Lech", True),
            # a truncated label still answers through its whole tokens
            ("New York G", "New York", True),
            ("Los Angeles Clipp", "Los Angeles", True),
            # empties
            ("", "Lech", False),
            ("Lech", "", False),
            (None, "Lech", False),
        ],
    )
    def test_matrix(self, label, pattern, expected):
        assert pattern_matches_token(label, pattern) is expected

    def test_accented_letters_are_token_characters(self):
        """`Pozna` does not match `Poznań`: `ń` belongs to its token. No
        transliteration is added — `Poznań` against `Poznan` is refused in
        both directions, exactly as the substring rule refused it."""
        assert not pattern_matches_token("Poznań", "Pozna")
        assert pattern_matches_token("Poznań", "Poznań")
        assert not pattern_matches_token("Poznan", "Poznań")
        assert not pattern_matches_token("Poznań", "Poznan")
        assert pattern_matches_token("Beşiktaş JK", "Beşiktaş")
        assert not pattern_matches_token("Beşiktaşlı", "Beşiktaş")

    def test_case_is_folded_on_both_sides(self):
        assert pattern_matches_token("lech poznan", "LECH")
        assert pattern_matches_token("ISTANBUL BASAKSEHIR", "Istanbul")


# ── LIKE escapes round-trip ─────────────────────────────────────────────────


class TestLikeEscapes:
    @pytest.mark.parametrize(
        "raw",
        [
            "100% Club",
            "Under_Score FC",
            "a\\b",
            "\\%",
            "%\\_%",
            "\\\\",
            "plain name",
            "",
        ],
    )
    def test_unescape_inverts_escape_like(self, raw):
        assert unescape_like_pattern(_escape_like(raw)) == raw

    def test_an_unescaped_backslash_is_kept_literally(self):
        assert unescape_like_pattern("x\\y") == "x\\y"
        assert unescape_like_pattern("trailing\\") == "trailing\\"

    def test_a_single_pass_reads_backslash_then_wildcard_escape(self):
        # `\\\%` is (escaped backslash)(escaped percent) -> `\%`: the pass
        # consumes `\\` first, so the third backslash pairs with `%`, never
        # the second.
        assert unescape_like_pattern("\\\\\\%") == "\\%"
        # `\\\_x` likewise -> `\_x`
        assert unescape_like_pattern("\\\\\\_x") == "\\_x"

    @pytest.mark.parametrize(
        "team, label, expected",
        [
            ("100%ers", "100%ers", True),
            ("100%ers", "100Xers", False),  # `%` is literal, not a wildcard
            ("100%ers", "1100%ers", False),  # interior
            ("Under_Score FC", "Under_Score FC", True),
            ("Under_Score FC", "Under_Score", True),  # the city half
            ("Under_Score FC", "Underscore FC", False),  # `_` is literal
            ("Under_Score FC", "UnderXScore FC", False),
        ],
    )
    def test_escaped_patterns_match_the_literal_characters(self, team, label, expected):
        assert any_pattern_matches_token(label, _team_name_patterns(team)) is expected


# ── Existing pattern outputs, run through the rule ──────────────────────────


class TestRealPatternLists:
    """The pattern builder is unchanged (its contract is shared); these pin
    what its lists do under the new rule for the clubs the brief names."""

    def test_boston_celtics(self):
        pats = _team_name_patterns("Boston Celtics")
        assert pats == ["Boston Celtics", "Celtics", "Boston"]
        for kept in ("Boston Celtics", "Celtics", "Boston", "Boston Celtics (East)"):
            assert any_pattern_matches_token(kept, pats)
        for refused in (
            "Boston College",
            "Bostonians",
            "Celticsville",
            "Boston College Eagles",
        ):
            # Boston College is a different school: `College` is not in the
            # list and `Boston` IS a whole token — so it is still reached by
            # the city label, exactly as before. Only the invented fragments
            # are refused; the wrong-sport leak guard owns Boston College.
            if refused.startswith("Boston College"):
                assert any_pattern_matches_token(refused, pats)
            else:
                assert not any_pattern_matches_token(refused, pats)

    def test_multiword_city(self):
        pats = _team_name_patterns("Los Angeles Clippers")
        assert pats == ["Los Angeles Clippers", "Clippers", "Los Angeles", "Angeles"]
        assert any_pattern_matches_token("Los Angeles", pats)
        assert any_pattern_matches_token("LA Clippers", pats)  # via `Clippers`
        assert not any_pattern_matches_token("Los Angelesque", pats)

    def test_a_shared_city_token_is_still_shared(self):
        """Not fixed here, pinned so nobody reads this as a fix for it: two
        clubs of one city both answer to the city label (existing guards —
        sport, gender, league, fixture — are what separate them)."""
        pats = _team_name_patterns("Manchester United")
        assert any_pattern_matches_token("Manchester City", pats)  # via `Manchester`
        assert any_pattern_matches_token("Manchester United", pats)

    def test_the_generic_qualifier_gate_is_untouched(self):
        assert "State" not in _team_name_patterns("Arkansas State Red Wolves")
        assert _team_name_patterns("") == []


# ── live/363: THE COLLISIONS A PRODUCTION SWEEP ACTUALLY FOUND ──────────────


class TestEveryCollisionTheSweepFound:
    """The integration sweep, not the specimen — and it is the recall proof.

    Tightening a match predicate spends refusals, so the question this change
    owes is not "does Lech stop borrowing Lechia" but "what legitimate row does
    the new rule DROP". Answered by replaying both predicates over the SERVED
    payload: `/api/events/{id}/related-futures` for 60 events carrying related
    futures, drawn at random from a ±3/7-day window across every sport.

        3,743 served rows scanned
           55 change  (1.5%)
           55 of 55 are a DIFFERENT ENTITY being removed
            0 legitimate rows lost
            0 rows GAINED (the rule is a strict subset of the old test, and the
              sweep confirms it empirically as well as structurally)

    Every pair below is one of those 55, copied from the sweep with the team as
    the event's own side and the outcome as the row that was served under it.
    They are here because a unit table invented from the rule cannot tell you
    the rule is worth its cost; these can. The worst of them is not the Polish
    one: `Gent` was being served ARGENTINA's 41% FIFA World Cup price as its own
    championship path.
    """

    # (event side's team name, the foreign outcome it was claiming, why)
    COLLISIONS = [
        ("Gent", "Argentina", "`Gent` sits inside `ArGENTina` — served at 41.3%"),
        ("Jeugd KAA Gent B", "Argentina", "same token, longer club name"),
        ("Aston Villa FC", "Villarreal", "`Villa` prefixes `Villarreal`"),
        ("Aston Villa FC", "Sevilla", "`Villa`… inside `SeVILLA`"),
        ("TE", "Iga Swiatek", "a two-letter side matched every player with `te`"),
        ("TE", "Elise Mertens", "same"),
        ("TE", "Sorana Cirstea", "same"),
        ("TE", "Peyton Stearns", "same"),
        ("Liam Walsh", "William Zepeda", "`Liam` inside `WilLIAM`"),
        ("Liam Walsh", "Austin Williams", "same"),
        ("Buffalo Bulls", "Colorado Buffaloes", "`Buffalo` prefixes `Buffaloes`"),
        ("Cong An Ha Noi FC", "Congo DR", "`Cong` prefixes `Congo`"),
        ("CA Tigre BA", "Tigres", "`Tigre` prefixes `Tigres`"),
        ("St Patricks Athletic", "Athletico Paranaense", "`Athletic` prefixes it"),
        ("Telekom Baskets Bonn", "DeWanna Bonner", "`Bonn` prefixes `Bonner`"),
        ("Hamburg Towers", "Eli Stowers", "`Towers` inside `SdTOWERS`-shaped name"),
        ("Heck / Miyoshi", "Jiri Lehecka", "`Heck` inside `LeHECKa`"),
        ("San Martin de San Juan", "Tijuana de Caliente", "`Juan` inside `TiJUANa`"),
    ]

    @pytest.mark.parametrize("team,foreign,why", COLLISIONS)
    def test_the_foreign_outcome_is_refused(self, team, foreign, why):
        pats = _team_name_patterns(team)
        assert not any_pattern_matches_token(foreign, pats), (
            f"{foreign!r} is still claimed by {team!r} — {why}"
        )

    @pytest.mark.parametrize("team,foreign,why", COLLISIONS)
    def test_and_the_old_rule_did_claim_it(self, team, foreign, why):
        """THE ARM THAT KEEPS THE TABLE HONEST. Without it a later reader cannot
        tell a real collision from a pair that never matched anything, and the
        table would survive deleting the fix."""
        assert _the_replaced_substring_rule(foreign, _team_name_patterns(team)), (
            f"{foreign!r} was NOT claimed by {team!r} on base, so this row is "
            f"not evidence of anything — remove it or fix it"
        )

    def test_each_side_still_claims_its_own_name(self):
        """The recall arm: the same sweep found 0 legitimate losses, and this is
        that claim in miniature — every team above still matches itself."""
        for team, _foreign, _why in self.COLLISIONS:
            assert any_pattern_matches_token(team, _team_name_patterns(team)), team


class TestACollisionThisRuleNoLongerOwns:
    """`("Cheltenham Town", "Wuhan Three Towns", "`Town` prefixes `Towns`")` was
    row 13 of the sweep above until #7858, and it is moved here rather than
    deleted because it is a real production collision and the sweep's count of
    55 still includes it.

    What changed is WHICH rule refuses it. #7858 gated `town` as a club-type
    designator, so `_team_name_patterns("Cheltenham Town")` no longer emits the
    bare token at all — the pattern that reached `Towns` is gone before the
    boundary rule is consulted. That breaks the honesty arm above, which
    requires the pre-#6806 substring rule to still CLAIM the row: it cannot
    claim a pattern that is never built. Its instruction for that case is
    "remove it or fix it"; this is the fix, and it keeps both facts assertable.
    """

    TEAM = "Cheltenham Town"
    FOREIGN = "Wuhan Three Towns"

    def test_the_foreign_outcome_is_still_refused(self):
        assert not any_pattern_matches_token(
            self.FOREIGN, _team_name_patterns(self.TEAM)
        )

    def test_and_it_is_refused_upstream_now_not_by_the_boundary_rule(self):
        """The reason moved: no bare `Town` is emitted, so there is nothing for
        the boundary rule to adjudicate."""
        assert _team_name_patterns(self.TEAM) == ["Cheltenham Town", "Cheltenham"]
        assert not _the_replaced_substring_rule(
            self.FOREIGN, _team_name_patterns(self.TEAM)
        )

    def test_the_old_rule_did_claim_it_on_the_patterns_of_the_day(self):
        """The evidence the sweep banked, replayed against the pattern list that
        existed when it was banked — so the row still proves a real collision."""
        patterns_before_7858 = ["Cheltenham Town", "Town", "Cheltenham"]
        assert _the_replaced_substring_rule(self.FOREIGN, patterns_before_7858)

    def test_cheltenham_still_claims_its_own_name(self):
        assert any_pattern_matches_token(self.TEAM, _team_name_patterns(self.TEAM))
