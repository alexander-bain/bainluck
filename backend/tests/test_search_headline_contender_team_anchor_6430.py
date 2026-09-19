"""#6430 — a CORRECTLY ANCHORED club reaches its championship market by its name.

🔴 THE SCOPE IS THE FIRST LINE ON PURPOSE (CERT-3128). This ship rescues every club
whose outcome is anchored to the club it names — 28 of the 30 anchored rows in market
114584. It does NOT rescue the other two: `New York Mets` is anchored to NEW YORK
YANKEES and `Los Angeles Angels` to LOS ANGELES DODGERS, so a fan typing "mets" still
gets no championship card at row 1 and "angels" gets none at all. That is a live,
reader-visible gap, it is carried on **#7233**, and its fix is #7188's ordered data
repair (lane1's by D39), not a change in this file. An earlier draft of this docstring
called the ship "the whole club field"; it was 28 of 30 then too, and CERT-3128 blocked
it for the difference. Do not restore the wider wording without the data repair.

THE DEFECT, measured on production 2026-09-19 via `GET /api/events/search`:

    q=dodgers   -> row 1 is "MLB World Series Champion 2026"   (0.3050)
    q=yankees   -> row 1 is "MLB World Series Champion 2026"   (0.1050)
    q=red sox   -> ten tier-5 "… Inning Winner" rows, no championship market

The single failing clause is `MIN_CONTENDER_PROBABILITY`: the Red Sox sit at
0.0455 in market 114584 (tier 1 ✓, volume 40,784,846 ✓, status open ✓).

WHY THE REPAIR IS AN IDENTITY ANCHOR AND NOT A FIELD-RELATIVE FLOOR. Replaying
`min(0.05, 1/field)` over the live tier-1 volume>=10k corpus admits
`Presidential Election Winner 2028` (128 outcomes) and `Pro Football
Championship Game Matchup` (256 outcomes, top price 0.035) — clause 3's own
LeBron case at scale. Both carry ZERO `team_id`; market 114584 carries 30 of 31.
`TestTheControl` is that measurement, frozen.

WHY THERE IS NO ANCHORED PRICE FLOOR — CERT-3125. The first version of this fix
kept a 0.005 sub-floor and this file sampled only the twelve clubs ABOVE it, so
the field test could not see that sixteen clubs were still refused. That is the
vacuous-guard trap: a fixture drawn from the passing side of a threshold cannot
test the threshold. `WORLD_SERIES_FIELD` below is now the whole thirty-row
anchored field as production serves it, dust included — the fixture is the whole
field precisely so that the two rows this ship does NOT rescue are visible in it
rather than filtered out of it.

WHAT REPLACED THE FLOOR. Price cannot separate a real longshot from a bad
anchor: the Diamondbacks (0.0015, against a real two-sided book of 0.0010/0.0020)
and "Mike Brown" on `Coach of the Year Winner` (0.000000, anchored to NEW
ENGLAND PATRIOTS) sit on the same side of every threshold. CORRESPONDENCE
separates them — the outcome's own name must agree with the name of the team it
is anchored to. Measured the same minute on 114584: 28 of 30 agree; the two that
do not are "New York Mets" anchored to NEW YORK YANKEES and "Los Angeles Angels"
anchored to LOS ANGELES DODGERS, which is #7188's team-identity poison and is
refused here rather than papered over.
"""

import ast
import pathlib

import pytest

from app.utils.search_headline_contender import (
    MIN_CONTENDER_PROBABILITY,
    MIN_CONTENDER_VOLUME,
    is_contender_outcome,
)

# THE WHOLE ANCHORED FIELD of market 114584 ("MLB World Series Champion 2026",
# tier 1, volume 40,784,846), read from production 2026-09-19 — all thirty rows
# carrying a `team_id`, in served order. The 31st outcome ("Other") has no
# `team_id` and is not part of this field.
#
# `corresponds` is "the outcome's own name agrees with the name of the team row
# it is anchored to", measured in the same query. It is False for exactly two
# rows, and both are mis-anchors, not longshots.
WORLD_SERIES_FIELD = [
    # (club, probability, corresponds)
    ("Los Angeles Dodgers", 0.3050, True),
    ("Milwaukee Brewers", 0.1525, True),
    ("New York Yankees", 0.1050, True),
    ("Tampa Bay Rays", 0.0935, True),
    ("San Diego Padres", 0.0575, True),
    ("Atlanta Braves", 0.0565, True),
    ("Chicago Cubs", 0.0555, True),
    ("Philadelphia Phillies", 0.0495, True),
    ("Boston Red Sox", 0.0455, True),
    ("Cleveland Guardians", 0.0315, True),
    ("Houston Astros", 0.0285, True),
    ("Chicago White Sox", 0.0225, True),
    ("Texas Rangers", 0.0205, True),
    ("Toronto Blue Jays", 0.0125, True),
    # --- everything below here was REFUSED by the 0.005 floor CERT-3125 blocked
    ("Arizona Diamondbacks", 0.0015, True),
    ("Cincinnati Reds", 0.0010, True),
    ("Athletics", 0.0010, True),
    ("New York Mets", 0.0010, False),  # anchored to NEW YORK YANKEES (#7188)
    ("Washington Nationals", 0.0010, True),
    ("Kansas City Royals", 0.0010, True),
    ("San Francisco Giants", 0.0010, True),
    ("Los Angeles Angels", 0.0010, False),  # anchored to LOS ANGELES DODGERS
    ("Colorado Rockies", 0.0010, True),
    ("Baltimore Orioles", 0.0005, True),
    ("Detroit Tigers", 0.0005, True),
    ("Seattle Mariners", 0.0005, True),
    ("Minnesota Twins", 0.0005, True),
    ("Miami Marlins", 0.0000, True),
    ("St. Louis Cardinals", 0.0000, True),
    ("Pittsburgh Pirates", 0.0000, True),
]
WORLD_SERIES_VOLUME = 40_784_846

CORRESPONDING = [row for row in WORLD_SERIES_FIELD if row[2]]
MIS_ANCHORED = [row for row in WORLD_SERIES_FIELD if not row[2]]


def _admitted(club_rows):
    return [
        club
        for club, probability, corresponds in club_rows
        if is_contender_outcome(
            probability, WORLD_SERIES_VOLUME, team_anchored=corresponds
        )
    ]


class TestTheDefect:
    """RED on clean master: these are the clubs the price floors delete."""

    def test_red_sox_reach_the_world_series_market(self):
        """#6430's reported specimen, at its measured live price."""
        assert is_contender_outcome(0.0455, WORLD_SERIES_VOLUME, team_anchored=True), (
            "the Boston Red Sox are refused a reserved slot in their own "
            "championship market at 4.55% — this is the reported defect"
        )

    def test_every_correctly_anchored_club_reaches_it_not_just_the_favourites(
        self,
    ):
        """CERT-3125's finding: the ship is the FIELD, not the priced cohort.

        This is the test that was vacuous before — it sampled twelve rows that
        all sat above the floor being tested. It now carries every anchored row
        production serves, so a floor reintroduced anywhere reddens it.

        CERT-3128: the claim is "every CORRECTLY ANCHORED club", and the
        arithmetic below is asserted out loud so the scope cannot be misread as
        the whole field. 28 reach it, 2 do not, 30 exist — and the 2 are named
        on #7233, not silently filtered away.
        """
        admitted = _admitted(CORRESPONDING)
        assert len(admitted) == len(CORRESPONDING), (
            f"only {len(admitted)} of {len(CORRESPONDING)} corresponding clubs "
            f"reach their own championship market; missing: "
            f"{[c for c, _, _ in CORRESPONDING if c not in admitted]}"
        )
        # The ship's exact reach, stated as arithmetic. If #7188's data repair
        # lands and these numbers move to 30/0, this assertion is the thing that
        # tells you to widen the claim in the docstring and close #7233.
        assert (len(CORRESPONDING), len(MIS_ANCHORED)) == (28, 2), (
            "the anchored field changed shape: "
            f"{len(CORRESPONDING)} corresponding + {len(MIS_ANCHORED)} "
            f"mis-anchored = {len(WORLD_SERIES_FIELD)}. If the mis-anchors are "
            "gone, #7188 landed — widen the ship claim and close #7233."
        )

    @pytest.mark.parametrize(
        "club,probability",
        [
            # The cheapest real book in the field: bid 0.0010 / ask 0.0020.
            ("Arizona Diamondbacks", 0.0015),
            # Priced at zero — the market saying this club cannot win. Still a
            # true answer to "is this market about you", which is the only
            # question this lane asks.
            ("Pittsburgh Pirates", 0.0000),
        ],
    )
    def test_a_club_below_the_old_dust_floor_reaches_its_market(
        self, club, probability
    ):
        """CERT-3125 named the Diamondbacks at 0.0015 by hand. Pinned."""
        assert is_contender_outcome(
            probability, WORLD_SERIES_VOLUME, team_anchored=True
        ), f"{club} is refused its own championship market at {probability}"

    def test_the_favourites_still_reach_it(self):
        """The arm is additive — it must not cost Dodgers/Yankees their row."""
        for club, probability in (
            ("Los Angeles Dodgers", 0.3050),
            ("New York Yankees", 0.1050),
        ):
            assert is_contender_outcome(probability, WORLD_SERIES_VOLUME), (
                f"{club} lost the slot it already had on a NAME-only verdict"
            )


class TestTheControl:
    """The rows a looser rule would have admitted, and must not."""

    @pytest.mark.parametrize(
        "market,probability",
        [
            # 112897 Presidential Election Winner 2028 — 128 outcomes, 0 team_id
            ("Presidential Election Winner 2028", 0.0100),
            # 56775566 Pro Football Championship Game Matchup — 256, 0 team_id
            ("Pro Football Championship Game Matchup", 0.0350),
        ],
    )
    def test_an_unanchored_longshot_is_still_refused(self, market, probability):
        """No `team_id` ⇒ the 0.05 floor is untouched. Clause 3 still governs."""
        assert not is_contender_outcome(probability, 10_000_000), (
            f"{market} earned a reserved slot at {probability} on a bare name "
            "match — this is the LeBron case clause 3 exists to prevent"
        )

    @pytest.mark.parametrize(
        "outcome,anchored_to",
        [
            ("Mike Brown", "New England Patriots"),
            ("Will Hardy", "North Carolina Tar Heels"),
        ],
    )
    def test_a_mis_anchored_person_is_refused(self, outcome, anchored_to):
        """`Coach of the Year Winner` (416), both rows live at 0.000000.

        This is the whole reason the price floor could not simply be deleted:
        a bare `team_id IS NOT NULL` makes a coach's name a headline contender
        on an anchor that is wrong. Correspondence is what refuses it.
        """
        assert not is_contender_outcome(
            0.0, 12_179_061, team_anchored=False
        ), (
            f'"{outcome}" earned a reserved slot on a mis-anchor to '
            f"{anchored_to} — clause 3's poison arriving through the anchor"
        )

    def test_the_two_mis_anchored_clubs_in_the_live_field_are_refused(self):
        """Mets→Yankees and Angels→Dodgers, #7188's poison, on the ship's own
        specimen market.

        🔴 THIS TEST PINS A READER-VISIBLE GAP, NOT JUST A RULE (CERT-3128). While
        it is green, a fan typing "mets" gets no championship card at row 1 and
        "angels" gets none at all — measured on production 2026-09-19. It is green
        because the rule fails CLOSED on bad data: loosening it to rescue these two
        re-admits `Mike Brown` → NEW ENGLAND PATRIOTS, which is the trade CERT-3125
        blocked. The gap is carried on **#7233** and closes when #7188's ordered
        data repair lands (lane1's by D39) — then these become corresponding rows
        and the field reads 30 of 30 with no change to the rule.
        """
        assert _admitted(MIS_ANCHORED) == [], (
            "a mis-anchored club reached a headline slot: "
            f"{_admitted(MIS_ANCHORED)}"
        )

    def test_the_anchor_does_not_relax_the_volume_floor(self):
        """Identity answers 'about you', never 'does anyone trade it'."""
        assert not is_contender_outcome(
            0.9, MIN_CONTENDER_VOLUME - 1, team_anchored=True
        )

    def test_an_unpriced_outcome_is_refused_on_both_arms(self):
        """`current_probability IS NULL` is not a quote. The SQL agrees."""
        assert not is_contender_outcome(None, WORLD_SERIES_VOLUME, team_anchored=True)
        assert not is_contender_outcome(None, WORLD_SERIES_VOLUME)

    def test_the_default_is_the_previous_behaviour_byte_for_byte(self):
        """Every existing caller and replay-corpus row keeps its old verdict."""
        below = MIN_CONTENDER_PROBABILITY - 0.001
        assert not is_contender_outcome(below, MIN_CONTENDER_VOLUME)
        assert is_contender_outcome(MIN_CONTENDER_PROBABILITY, MIN_CONTENDER_VOLUME)

    def test_the_anchored_arm_is_strictly_looser_never_tighter(self):
        """The arm can only ever ADD a market, which bounds the blast radius.

        Stated over the rule rather than over a constant: for every price, an
        anchored verdict is at least as permissive as the name-only one.
        """
        for probability in (0.0, 0.0005, 0.0015, 0.0455, 0.05, 0.5, 1.0):
            name_only = is_contender_outcome(probability, WORLD_SERIES_VOLUME)
            anchored = is_contender_outcome(
                probability, WORLD_SERIES_VOLUME, team_anchored=True
            )
            assert anchored or not name_only, (
                f"at {probability} the anchored arm REFUSED what the name-only "
                "arm admitted — the arm must only ever widen"
            )


class TestTheTwoLanesCannotDrift:
    """#3394's lesson: `/search` and `/typeahead` are textual copies.

    That fix landed on the dropdown, the identical arm in the results endpoint
    was left alone, and the same query broke the same way the day after it was
    declared fixed. Both lanes now share ONE helper; this asserts they still do.

    AMENDED by #7243, which moved the whole statement into one builder. This test
    counted "exactly 2 call sites of `_headline_contender_outcome_clause`" — one per
    lane — and that count is now 1, because the lanes no longer spell the predicate
    at all: they call `_headline_contender_statement`, which spells it once. The
    INVARIANT is unchanged and the assertion is strictly stronger (one shared
    spelling rather than two identical ones); only the thing it counts moved. The
    clause ORDER inside that builder is now load-bearing too — see
    `test_search_headline_contender_clause_order_7243.py`.
    """

    def _lane_callers(self, name):
        source = (
            pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "events.py"
        ).read_text()
        tree = ast.parse(source)
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == name
                ):
                    out.append(node.name)
        return out

    def test_the_clause_helper_is_spelled_in_exactly_one_place(self):
        assert set(self._lane_callers("_headline_contender_outcome_clause")) == {
            "_headline_contender_statement"
        }, (
            "the clause helper is called outside the one builder — a lane given "
            "its own inline predicate is how the two drift, which is #3394"
        )

    def test_both_headline_lanes_reach_that_place(self):
        callers = self._lane_callers("_headline_contender_statement")
        assert len(callers) == 2, (
            "expected the search and typeahead headline lanes to both reach the "
            f"shared builder, found {callers}"
        )

    def test_the_sql_clause_carries_the_correspondence_and_no_price_floor(self):
        """The SQL half must express the SAME rule as `is_contender_outcome`.

        A pure unit test cannot see the query, and the query is what production
        runs — so the correspondence join is asserted here by name.
        """
        from app.routes.events import _headline_contender_outcome_clause

        compiled = str(
            _headline_contender_outcome_clause(r"\mred\s+sox\M").compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "team_id IS NOT NULL" in compiled
        assert str(MIN_CONTENDER_PROBABILITY) in compiled
        # The anchored arm must test the TEAM's name, not just hold an id.
        assert "teams" in compiled.lower(), (
            "the anchored arm no longer joins `teams`, so a mis-anchored row "
            "(Mike Brown -> New England Patriots) can reach a headline slot"
        )
        assert compiled.lower().count("~*") >= 2, (
            "the pattern is applied to only one name — the correspondence "
            "requires it on BOTH the outcome and the team it is anchored to"
        )
        # The sub-floor CERT-3125 blocked must not come back by accident.
        assert "0.005" not in compiled, (
            "an anchored price floor is back in the SQL; CERT-3125 blocked "
            "exactly this — 16 of 30 clubs are refused by it"
        )
