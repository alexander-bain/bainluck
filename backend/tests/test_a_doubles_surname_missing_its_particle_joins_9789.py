"""A doubles surname one venue writes without its particle joins to StatPal. #9789.

SHIP (pillar: MATCHING): the Tokyo doubles match Galloway/Goransson v Tabilo/van
Assche shows once, as Thursday's match. Polymarket wrote the row `Tabilo/Assche`;
StatPal fixture 2638074 says `Tabilo/ van Assche`. The doubles join compared
surnames whole, so `assche` and `van assche` were two players, the fixture linked
nothing, and #9624 had no anchored row to move Kalshi 62952921 onto.

The fix forgives a run of `SURNAME_PARTICLES` in front of the surname on ONE side
of a doubles comparison. The controls below pin what it must still refuse.
"""

from __future__ import annotations

import json
from datetime import datetime
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.statpal_api import StatPalFixture
from app.tasks.link_tennis_statpal_fixtures import (
    VERDICT_LINK,
    VERDICT_UNMATCHED,
    classify_fixture,
    doubles_pair_matches,
)
from app.utils import authority_tennis_names as names
from app.utils.authority_tennis_names import (
    SURNAME_PARTICLES,
    doubles_key,
    doubles_side_keys,
    doubles_teams_agree,
    is_doubles_name,
    keys_agree,
    tennis_names_agree,
)

CORPUS = Path(__file__).parent / "fixtures" / "tennis_name_corpus_20260905.json"

#: StatPal fixture 2638074 as the d1 board served it at ~10:00Z on 2026-09-30.
FIXTURE = StatPalFixture(
    fixture_id="2638074",
    home_team="Galloway/ Goransson",
    away_team="Tabilo/ van Assche",
    start_time=datetime.fromisoformat("2026-10-01T01:00:00+00:00"),
)

#: The two production rows `/api/events/search?q=Galloway` returned (#9789).
#: Only the fields `classify_fixture` reads.
POLYMARKET_ROW = {
    "id": 15321373,
    "home": "Galloway/Goransson",
    "away": "Tabilo/Assche",
    "commence_time": datetime.fromisoformat("2026-10-01T01:00:00+00:00"),
}
#: Kalshi's row. Its start is Kalshi's close stamp, 44 h before StatPal's
#: (Hot List #14), so it sits outside `MATCH_WINDOW`.
KALSHI_ROW = {
    "id": 15320504,
    "home": "Galloway / Goransson",
    "away": "Tabilo / van Assche",
    "commence_time": datetime.fromisoformat("2026-09-29T05:00:00+00:00"),
}


def _old_rule(ours, theirs):
    """The pre-#9789 comparison: `keys_agree`, surname whole and equal."""
    return keys_agree(ours, theirs)


class TestTheSpecimen:
    def test_the_fixture_links_to_the_polymarket_row(self):
        verdict, matches = classify_fixture(FIXTURE, [POLYMARKET_ROW, KALSHI_ROW])
        assert verdict == VERDICT_LINK
        assert [m["id"] for m in matches] == [15321373]

    def test_it_was_unmatched_under_the_old_rule(self):
        # The strawman: put the old comparison back and the specimen must fail.
        with patch.object(names, "_doubles_keys_agree", _old_rule):
            verdict, _ = classify_fixture(FIXTURE, [POLYMARKET_ROW, KALSHI_ROW])
        assert verdict == VERDICT_UNMATCHED

    def test_the_pair_agrees_in_both_partner_orders(self):
        sp = (FIXTURE.home_team, FIXTURE.away_team)
        assert doubles_pair_matches(sp, ("Galloway/Goransson", "Tabilo/Assche"))
        assert doubles_pair_matches(sp, ("Assche/Tabilo", "Goransson/Galloway"))


class TestWhatItStillRefuses:
    @pytest.mark.parametrize(
        "ours, theirs",
        [
            # Two different particles are two surnames, not one spelling dropped.
            ("Tabilo/de Assche", "Tabilo/ van Assche"),
            # A bare particle is not a surname.
            ("Tabilo/Van", "Tabilo/ van Assche"),
            ("Tabilo/Der", "Tabilo/ van Der"),
            # A dropped token that is NOT a particle is a different surname.
            ("Tabilo/Aliassime", "Tabilo/ Auger Aliassime"),
            # Initials on both sides that differ still refuse.
            ("Tabilo/Assche A", "Tabilo/ van Assche B"),
            # One agreeing player is not an agreeing team.
            ("Tabilo/Assche", "Tabilo/ van Gogh"),
            # `le` and `do` are real surnames, so they are not particles.
            ("Tabilo/Minh", "Tabilo/ Le Minh"),
        ],
    )
    def test_refused(self, ours, theirs):
        assert not doubles_teams_agree(ours, theirs)

    @pytest.mark.parametrize(
        "ours, theirs",
        [
            ("Tabilo/Assche", "Tabilo/ van Assche"),
            ("Tabilo/van Assche", "Tabilo/ Assche"),
            ("Koolhof/Zandschulp", "Koolhof/ van de Zandschulp"),
            ("Koolhof/de Zandschulp", "Koolhof/ van de Zandschulp"),
            ("Tabilo/Assche T", "Tabilo/ van Assche"),
        ],
    )
    def test_accepted(self, ours, theirs):
        assert doubles_teams_agree(ours, theirs)

    def test_singles_are_out_of_scope(self):
        # Doubles only: the singles join has no second player to check against.
        assert not tennis_names_agree("Assche", "Z. Van Assche")

    def test_the_identity_did_not_move(self):
        # `doubles_key` is what the twin sweep and the agreement denominator
        # score on. The join widened; the identity must not.
        assert doubles_key("Tabilo/Assche") != doubles_key("Tabilo/ van Assche")


class TestOverThePinnedCorpus:
    """The widening measured over our whole doubles register, not the specimen."""

    @pytest.fixture(scope="class")
    def doubles(self):
        data = json.loads(CORPUS.read_text())
        pool = data if isinstance(data, list) else data["names"]
        return sorted({n for n in pool if isinstance(n, str) and is_doubles_name(n)})

    def test_the_corpus_holds_particle_surnames_to_test_on(self, doubles):
        # Non-vacuous: the sweep below means nothing without particle sides.
        sides = {
            k[0]
            for n in doubles
            for k in (doubles_side_keys(n) or ())
            if k[0].split()[0] in SURNAME_PARTICLES
        }
        assert len(doubles) == 1674
        assert len(sides) == 24

    def test_no_two_register_names_newly_agree(self, doubles):
        # A dropped particle keeps each side's last token, so grouping by the
        # pair of last tokens is a superset of every pair the change can join.
        blocks: dict[frozenset, list[str]] = {}
        for n in doubles:
            sides = doubles_side_keys(n)
            if sides:
                key = frozenset(k[0].split()[-1] for k in sides)
                blocks.setdefault(key, []).append(n)
        gained = []
        for block in blocks.values():
            for a, b in combinations(block, 2):
                if doubles_teams_agree(a, b):
                    with patch.object(names, "_doubles_keys_agree", _old_rule):
                        if not doubles_teams_agree(a, b):
                            gained.append((a, b))
        assert gained == []
