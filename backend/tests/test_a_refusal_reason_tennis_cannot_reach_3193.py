"""CERT-2310/2316 follow-up `3366-TENNIS-DISCOVERY-STATE-PRESERVES-PARSER-BLINDNESS`.

The second instance of the defect CERT-2245's follow-up fixed for soccer, one
list over. `discovery_state` consulted three of the four discovery maps.
`DISCOVERY_NO_BEAT_AND_NO_PARSE` — which carries tennis's census, 0 of 7 and 0
of 11 fixtures parsed on pinned real payloads from two independent causes in two
different functions (#3193) — was read by nothing. Both tennis populations fell
through to the bare `NO-BEAT` ending.

That ending is TRUE and it is the wrong instruction. It says "this is a build
step (a `sync_statpal_schedules` beat)", and a beat is the one build step that
cannot pay here: scheduled over a parser that reads nothing, it creates nothing
while the ticket reads closed. The config file spends three paragraphs saying so
and the operator reading the agreement row saw none of them.

These tests pin the property that made the defect possible, not today's strings:

  * tennis's map is non-empty and tennis is stamped, so the arm is reachable
    (the premise — without it every assertion below passes vacuously);
  * tennis's published state is specifically the parser-blind one, and it
    carries the map's own census rather than a generic sentence;
  * the census is stated BEFORE the beat is prescribed, which is the whole
    content of the fix;
  * every discovery map has an arm that publishes it, derived rather than
    hand-listed — a FIFTH map added beside a four-way check is not covered by
    it, and that miss is exactly how this one shipped.
"""

import pytest

from app.config import authority_by_sport as cfg
from app.config.authority_by_sport import (
    DISCOVERY_NO_BEAT,
    DISCOVERY_NO_BEAT_AND_NO_PARSE,
    DISCOVERY_NO_BEAT_AND_PARSER_BLIND,
    DISCOVERY_SCHEDULED_SPORTS,
    discovery_state,
)
from app.utils.authority_agreement import SHADOW_STAMPERS


class TestTheReasonTennisCouldNotReach:
    def test_tennis_is_still_stamped_and_still_filed_as_parser_blind(self):
        """The premise. If tennis leaves this map — because someone taught the
        parser, or scheduled a beat — the defect is gone by another route and
        the tests below would assert nothing (memory: a guard that cannot fail
        is not a guard).
        """
        assert set(DISCOVERY_NO_BEAT_AND_NO_PARSE) == {
            "tennis_singles",
            "tennis_doubles",
        }
        for sport_key in DISCOVERY_NO_BEAT_AND_NO_PARSE:
            assert sport_key in SHADOW_STAMPERS, (
                f"{sport_key} is filed as parser-blind but is not stamped, so "
                "the endpoint never publishes a row for it and this arm is dead"
            )

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_NO_BEAT_AND_NO_PARSE))
    def test_tennis_now_has_a_reachable_parser_blind_state(self, sport_key):
        code, why = discovery_state(sport_key)
        assert code == DISCOVERY_NO_BEAT_AND_PARSER_BLIND
        # The bug, pinned from the other side: it must NOT read as the bare
        # "no beat" state, which is what shipped and what prescribes the wrong
        # work.
        assert code != DISCOVERY_NO_BEAT

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_NO_BEAT_AND_NO_PARSE))
    def test_the_published_reason_carries_the_maps_own_census(self, sport_key):
        """Not a generic "the parser is blind" sentence. The numbers and the
        function names are what make it actionable, and they live in the map.
        """
        _, why = discovery_state(sport_key)
        assert DISCOVERY_NO_BEAT_AND_NO_PARSE[sport_key] in why

    def test_the_singles_reason_still_carries_the_measured_counts(self):
        """One string assertion on purpose: 0 of 7 and 0 of 11 are the census
        the whole refusal rests on, and a repair that dropped them while
        keeping the shape would pass every structural test above.
        """
        _, why = discovery_state("tennis_singles")
        assert "0 of the 7 fixtures" in why
        assert "0 of 11" in why

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_NO_BEAT_AND_NO_PARSE))
    def test_the_reason_says_parser_before_beat(self, sport_key):
        """Order is the content here, exactly as it is for soccer's id-less
        arm: told to schedule a beat first, a reader would schedule one over a
        parser measured at zero, and the beat would create nothing while the
        ticket read closed.
        """
        _, why = discovery_state(sport_key)
        census = DISCOVERY_NO_BEAT_AND_NO_PARSE[sport_key]
        assert why.index(census) < why.index("scheduling a beat"), (
            "the beat is prescribed before the blindness is named — which is "
            "the defect, reintroduced"
        )


class TestFlipPermittedInheritsTheRepair:
    """`flip_permitted` quotes `discovery_state` verbatim, so the repair reaches
    both surfaces or neither. Tennis cannot demonstrate this itself — it is a
    measurement population and is refused earlier — so the arm is reached on
    purpose with a synthetic sport, the same technique CERT-2245's follow-up
    used and for the same reason.
    """

    def test_a_parser_blind_sport_that_reaches_the_flip_branch_gets_the_census(
        self, monkeypatch
    ):
        sport_key = "korfball_synthetic"
        census = "a pinned payload parses 0 of 9 fixtures"
        monkeypatch.setitem(cfg.SHADOW_STAMPERS, sport_key, "stamp_korfball")
        monkeypatch.setitem(cfg.DISCOVERY_NO_BEAT_AND_NO_PARSE, sport_key, census)

        code, detail = cfg.discovery_state(sport_key)
        permitted, why = cfg.flip_permitted(sport_key, [])

        assert code == DISCOVERY_NO_BEAT_AND_PARSER_BLIND
        assert permitted is False
        # The discovery branch really was reached, not a refusal above it.
        assert "no working StatPal discovery pass" in why
        assert detail in why
        assert census in why

    def test_the_same_sport_without_the_map_entry_still_reads_bare_no_beat(
        self, monkeypatch
    ):
        """The control. `NO-BEAT` is a real state and must survive the repair —
        a sport with no beat and a parser nobody has measured is not the same
        claim as one measured at zero, and collapsing the two would trade this
        defect for its mirror image.
        """
        sport_key = "korfball_synthetic"
        monkeypatch.setitem(cfg.SHADOW_STAMPERS, sport_key, "stamp_korfball")

        code, _ = cfg.discovery_state(sport_key)
        assert code == DISCOVERY_NO_BEAT


class TestEveryDiscoveryMapHasAnArmThatPublishesIt:
    """The generalisation, and the only test here that would have caught the
    original defect BEFORE a reader hit it.

    Adding a state to the config and adding the arm that publishes it are two
    changes. Four maps exist; the fourth shipped with its arm and the third
    shipped without one, silently, because every guard enumerated maps by hand.
    This derives the check from the maps themselves, so a fifth map with no arm
    reds this test on the day it is added.
    """

    #: Each discovery map, with the code its arm must publish. Derived checks
    #: below; this table is the one hand-written thing and it is the thing a
    #: new map must be added to.
    MAP_TO_CODE = {
        "DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE": cfg.DISCOVERY_BEAT_PARSES_NOTHING,
        "DISCOVERY_NO_BEAT_AND_NO_PARSE": cfg.DISCOVERY_NO_BEAT_AND_PARSER_BLIND,
        "DISCOVERY_PARSES_BUT_MINTS_NO_ID": cfg.DISCOVERY_PARSER_MINTS_NO_ID,
    }

    def test_every_discovery_map_in_the_module_is_in_the_table(self):
        """The table cannot go stale silently. Any module-level name matching
        the discovery-map shape must be accounted for here.
        """
        discovered = {
            name
            for name in dir(cfg)
            if name.startswith("DISCOVERY_") and isinstance(getattr(cfg, name), dict)
        }
        assert discovered == set(self.MAP_TO_CODE), (
            "a discovery map was added or renamed without giving it an arm and "
            f"a row here: {sorted(discovered ^ set(self.MAP_TO_CODE))}"
        )

    @pytest.mark.parametrize("map_name", sorted(MAP_TO_CODE))
    def test_each_map_reaches_its_own_code(self, monkeypatch, map_name):
        """A synthetic stamped sport placed in one map must come back with that
        map's code. A map nothing consults fails here.
        """
        sport_key = "korfball_synthetic"
        census = "a pinned payload proves the state this map names"
        monkeypatch.setitem(cfg.SHADOW_STAMPERS, sport_key, "stamp_korfball")
        monkeypatch.setitem(getattr(cfg, map_name), sport_key, census)

        code, why = cfg.discovery_state(sport_key)

        assert code == self.MAP_TO_CODE[map_name], (
            f"{map_name} has no arm in `discovery_state` — a sport filed there "
            f"publishes {code!r} and its reason goes dark"
        )
        assert census in why, (
            f"{map_name}'s arm publishes its own code but drops the map's text, "
            "so the evidence a reader needs never reaches them"
        )

    @pytest.mark.parametrize("map_name", sorted(MAP_TO_CODE))
    def test_no_map_overlaps_the_scheduled_set(self, map_name):
        """`SCHEDULED` is tested first and returns unconditionally, so a sport
        in both reads SCHEDULED and its census goes dark — the same class of
        defect, reached from the other end. Guarded for every map rather than
        the one pair that had a check.
        """
        both = set(getattr(cfg, map_name)) & set(DISCOVERY_SCHEDULED_SPORTS)
        assert not both, (
            f"{map_name} overlaps DISCOVERY_SCHEDULED_SPORTS on {sorted(both)}; "
            "the SCHEDULED arm wins and the reason is unreachable"
        )
