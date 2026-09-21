"""#7851 — the class controls: why the elegant rule was NOT shipped, executed.

THE SHIP (#7851) refuses a CFL market on a US-football event page: Duke Blue
Devils were served "2026 CFL Grey Cup Champion || Winnipeg Blue Bombers" because
`_team_name_patterns("Duke Blue Devils")` emits the bare token `Blue` and `Blue`
occupies whole tokens of `Winnipeg Blue Bombers`. That refusal, and its Duke and
real-CFL-page controls, are pinned in `test_market_label_normalization.py` and
`tests/integration/test_route_related_futures_cfl_7851.py`.

WHAT THIS FILE IS FOR. The obvious repair is not that one. It is:

    a label is claimed only when the team's own names cover EVERY token of it

— which kills the Grey Cup row, reads as a general truth fix, and is wrong. It
was replayed over real `/related-futures` payloads before it was believed, and
the replay is the only reason we know: it destroys `Miami (FL)` for the Miami
Hurricanes and every `NE Patriots …` prop label for New England, because the
extra token is not in the team's own name. **A rule that cannot tell `Miami (FL)`
from `Miami (OH)` is not a truth fix**, and both of those are served on the SAME
page by the SAME rule today (event `15315886`, Miami Hurricanes).

So this file is the durable form of a measurement that would otherwise be a
paragraph in a merged PR body: the next person who reaches for the coverage rule
gets a red test naming the rows it costs, instead of shipping it and finding out
from a reader. Acceptance refinement it answers (codex, 2026-09-21 13:03 PT,
#7851): shared colors, mascots, place fragments and display abbreviations may
RETRIEVE a candidate but never establish identity — and a fix must not "simply
remove valid paths", proven by class controls over exactly those classes.

PROVENANCE. Every row below was served by production on 2026-09-21 20:50Z, read
through `GET /api/events/{id}/related-futures` with the events named in the
table (replay: 318 kept / 216 lost / 0 gained over five payloads; the wider
12-payload run behind the ship measured 651 kept / 190 lost / 0 gained).
"""

import re

import pytest

from app.routes.events import _team_name_patterns
from app.utils.market_label_normalization import is_wrong_sport_leak
from app.utils.team_pattern_match import (
    any_pattern_matches_token,
    unescape_like_pattern,
)

# ── The rejected rule, executed rather than described ───────────────────────
# Copied from the #7851 replay harness. It is NOT imported from app code and
# must never be: app code does not contain it, which is the whole point. It
# lives here so every "this rule would have lost that row" claim below is run.

_MATCHUP_SPLIT = re.compile(r"\s+(?:vs\.?|v\.?|at|@|–|—|-)\s+", re.I)


def _tokens(label: str) -> list[str]:
    return [t for t in re.split(r"[^0-9A-Za-zÀ-ÿ]+", label) if t]


def _pattern_tokens(patterns: list[str]) -> set[str]:
    out: set[str] = set()
    for p in patterns:
        for t in _tokens(unescape_like_pattern(p)):
            out.add(t.lower())
    return out


def _side_is_covered(side: str, ptoks: set[str]) -> bool:
    toks = _tokens(side)
    if not toks:
        return False
    return all(t.lower() in ptoks for t in toks)


def the_rejected_coverage_rule(label: str, patterns: list[str]) -> bool:
    """"A label is claimed only when the team's own names cover all of its
    tokens." Retains the #6806 boundary rule and narrows it; one whole side of a
    matchup label being ours is enough."""
    if not label:
        return False
    if not any_pattern_matches_token(label, patterns):
        return False
    ptoks = _pattern_tokens(patterns)
    if _side_is_covered(label, ptoks):
        return True
    parts = _MATCHUP_SPLIT.split(label)
    if len(parts) >= 2:
        return any(_side_is_covered(p, ptoks) for p in parts)
    return False


# ── The measured casualties ─────────────────────────────────────────────────
# (event id, the event side's own team, market name, served outcome label, class)

CASUALTIES = [
    (
        15315886,
        "Miami Hurricanes",
        "College Football ACC Championship Winner",
        "Miami (FL)",
        "place fragment + parenthetical qualifier: `FL` is in no team name, "
        "but `Miami (FL)` IS the Hurricanes",
    ),
    (
        15315886,
        "Miami Hurricanes",
        "College Football National Championship Qualifiers",
        "Miami (FL)",
        "same label, the market a reader is likeliest to open",
    ),
    (
        15315886,
        "Miami Hurricanes",
        "ACC Conference Championship Matchup",
        "Miami (FL) vs Virginia Tech",
        "matchup label: the opponent's tokens are never ours",
    ),
    (
        14782706,
        "New England Patriots",
        "NE Patriots vs JAC Jaguars: Spread",
        "NE Patriots wins by over 5.5 points",
        "prop label: a market appends tokens (`wins`, `over`, `points`) that no "
        "team name contains",
    ),
    (
        14782706,
        "New England Patriots",
        "AFC East: Exact Order",
        "1: New England / 2: Miami / 3: Buffalo / 4: New York J",
        "ordered-list label: names every rival by construction",
    ),
]


class TestTodaysRuleKeepsEveryMeasuredCasualty:
    """The recall arm. These are rows a reader sees on the team's own page."""

    @pytest.mark.parametrize("eid,team,market,label,why", CASUALTIES)
    def test_the_row_is_still_claimed(self, eid, team, market, label, why):
        assert any_pattern_matches_token(label, _team_name_patterns(team)), (
            f"{label!r} ({market}, event {eid}) is no longer claimed by "
            f"{team!r} — {why}"
        )


class TestTheRejectedRuleWouldHaveDestroyedThem:
    """THE ARM THAT KEEPS THE TABLE HONEST (the #6806 sibling's convention).

    Without it, a later reader cannot tell a real casualty from a row that was
    never at risk, and the table would survive deleting the thing it documents.
    """

    @pytest.mark.parametrize("eid,team,market,label,why", CASUALTIES)
    def test_the_coverage_rule_refuses_it(self, eid, team, market, label, why):
        assert not the_rejected_coverage_rule(label, _team_name_patterns(team)), (
            f"{label!r} survives the coverage rule, so this row is not evidence "
            f"of its cost — remove it or fix it"
        )

    def test_the_rejected_rule_cannot_tell_miami_fl_from_miami_oh(self):
        """The one sentence that decided #7851's shape.

        `Miami (OH)` on the Hurricanes' page is a genuine collision (filed as
        the cross-entity token class, #7867). The coverage rule refuses it — and
        refuses `Miami (FL)`, which is the Hurricanes themselves, by the exact
        same arithmetic. It does not distinguish them; it cannot. Fixing the
        collision therefore has to happen on identity, never on token coverage.
        """
        pats = _team_name_patterns("Miami Hurricanes")
        assert not the_rejected_coverage_rule("Miami (FL)", pats)
        assert not the_rejected_coverage_rule("Miami (OH)", pats)


# ── Class controls: the shipped refusal is narrow ───────────────────────────


class TestTheShippedCflClauseRemovesNoValidPath:
    """codex's acceptance refinement, one control per collision class.

    The shipped clause refuses a CFL *competition* on a non-CFL football event.
    Each row below shares a color, a mascot, a place fragment, an abbreviation
    or a multiword name with some other entity — the retrieval signals the
    refinement says are not evidence of identity — and each is a legitimate path
    that must survive. A sport-family rule is not allowed to be the thing that
    quietly removes them.
    """

    # (market name, served outcome, event sport key, class)
    VALID_PATHS = [
        (
            "College Football ACC Championship Winner",
            "Miami (FL)",
            "americanfootball_ncaaf",
            "place fragment — the college page's own conference title",
        ),
        (
            "NCAAF Championship Winner",
            "Delaware Blue Hens",
            "americanfootball_ncaaf",
            "shared COLOR (`Blue`) — a wrong-team row is #7867's to fix on "
            "identity; a wrong-SPORT rule must not hide it",
        ),
        (
            "NCAAF Championship Winner",
            "Duke Blue Devils",
            "americanfootball_ncaaf",
            "the reporter's own team keeps its real championship path",
        ),
        (
            "NFL Super Bowl Winner",
            "New England Patriots",
            "americanfootball_nfl",
            "display abbreviation class (`NE Patriots` elsewhere in the same "
            "payload) — the NFL page keeps the NFL title",
        ),
        (
            "2026 CFL Grey Cup Champion",
            "Hamilton Tiger-Cats",
            "americanfootball_cfl",
            "shared MASCOT (`Tigers`/`Tiger-Cats`) — and the healthy CFL page, "
            "which the refusal is scoped to leave alone",
        ),
        (
            "Stanley Cup Winner",
            "New York Islanders",
            "icehockey_nhl",
            "MULTIWORD name — the clause is football-only and may not reach "
            "another sport's own championship",
        ),
        (
            "NHL Eastern Conference Winner",
            "Carolina Hurricanes",
            "icehockey_nhl",
            "shared mascot with a college team, on its own league's page",
        ),
    ]

    @pytest.mark.parametrize("market,outcome,sport_key,klass", VALID_PATHS)
    def test_it_is_not_refused(self, market, outcome, sport_key, klass):
        assert not is_wrong_sport_leak(market, outcome, sport_key), (
            f"{market!r} / {outcome!r} on {sport_key} is refused as a "
            f"wrong-sport leak — {klass}"
        )

    def test_and_the_leak_it_does_refuse_is_still_refused(self):
        """The non-vacuity arm: a table of things that pass is satisfied by a
        function that returns False for everything."""
        assert is_wrong_sport_leak(
            "2026 CFL Grey Cup Champion",
            "Winnipeg Blue Bombers",
            "americanfootball_ncaaf",
        )
