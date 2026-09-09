"""CERT-2245 follow-up `SOCCER-3366-IDLESS-REFUSAL-REACHABILITY`.

`flip_permitted` refuses a measurement population FIRST and unconditionally, so
every reason below that check is unreachable for one. `soccer` is a measurement
population, and the `PARSER-MINTS-NO-ID` reason below the check was written for
soccer, about soccer, carrying soccer's own census. An operator reading soccer's
agreement row was told there was nothing to flip and never told that the ingest
parser mints no id — the build step that comes first.

The repair moves the reasoning into `discovery_state`, which is asked
independently of the flip question and is published on every sport's row. These
tests pin the property that made the defect possible, not just today's strings:

  * a measurement population still gets a real discovery answer;
  * soccer's answer is specifically the id-less one, and names the census;
  * `flip_permitted`'s own refusal and the published reason are the SAME text,
    so the second copy cannot drift back into existence;
  * every sport the endpoint iterates has a reachable answer.
"""

import pytest

from app.config.authority_by_sport import (
    DISCOVERY_NO_BEAT,
    DISCOVERY_NO_BEAT_AND_PARSER_BLIND,
    DISCOVERY_PARSER_MINTS_NO_ID,
    DISCOVERY_PARSES_BUT_MINTS_NO_ID,
    DISCOVERY_SCHEDULED,
    DISCOVERY_SCHEDULED_SPORTS,
    discovery_state,
    flip_permitted,
)
from app.utils.authority_agreement import (
    MEASUREMENT_POPULATION_SCOPES,
    SHADOW_STAMPERS,
)


class TestTheReasonSoccerCouldNotReach:
    def test_soccer_is_still_a_measurement_population(self):
        """The premise. If this stops being true the defect is gone by another
        route, and the tests below would pass vacuously (memory: a guard that
        cannot fail is not a guard).
        """
        assert "soccer" in MEASUREMENT_POPULATION_SCOPES

    def test_flip_permitted_still_refuses_soccer_before_any_discovery_reason(self):
        """The short circuit is deliberate and stays — it is the reason the fix
        had to be a second door, not a reordering.
        """
        permitted, why = flip_permitted("soccer", [])
        assert permitted is False
        assert "MEASUREMENT POPULATION" in why
        # The bug, pinned: the flip refusal does NOT mention the parser.
        assert "mints no id" not in why

    def test_soccer_now_has_a_reachable_discovery_reason(self):
        code, why = discovery_state("soccer")
        assert code == DISCOVERY_PARSER_MINTS_NO_ID
        assert "mints no id" in why
        # It carries soccer's own census rather than a generic sentence — the
        # numbers are what make it actionable.
        assert "274 of 274" in why
        assert "195 of 195" in why

    def test_the_reason_says_parser_before_beat(self):
        """Order is the content here: told only to schedule a beat, a reader
        would schedule one over a parser that mints no id, and ruling 048 turns
        that into a duplicate of every row it reads.
        """
        _, why = discovery_state("soccer")
        assert why.index("mints no id") < why.index("scheduling a beat")


class TestTheDisclosureCannotDriftBackIntoTwoCopies:
    #: No sport in `SHADOW_STAMPERS` reaches `flip_permitted`'s discovery branch
    #: today — every one is either a measurement population (refused earlier) or
    #: already on the beat. Skipping on that basis is how this guard would come
    #: to assert nothing on the day it matters, so the branch is reached on
    #: purpose with a synthetic sport instead. The sport is stamped and not
    #: scheduled, which is exactly the state the branch exists for.
    @pytest.mark.parametrize(
        "idless_census",
        [
            None,  # plain "no beat"
            "a pinned payload carries 0 of 9 fixture ids",  # the id-less arm
        ],
    )
    def test_flip_permitted_quotes_discovery_state_verbatim(
        self, monkeypatch, idless_census
    ):
        """A sport that reaches the discovery branch of `flip_permitted` must
        get the SAME sentence the endpoint publishes. Two hand-written copies of
        one disclosure is what this repo's rails module exists to warn about,
        and re-growing the second copy is the only way this defect returns.
        """
        from app.config import authority_by_sport as cfg

        sport_key = "korfball_synthetic"
        monkeypatch.setitem(cfg.SHADOW_STAMPERS, sport_key, "stamp_korfball")
        if idless_census is not None:
            monkeypatch.setitem(
                cfg.DISCOVERY_PARSES_BUT_MINTS_NO_ID, sport_key, idless_census
            )

        code, detail = cfg.discovery_state(sport_key)
        permitted, why = cfg.flip_permitted(sport_key, [])

        assert permitted is False
        # The branch really was reached — not the shadow-stamper refusal above it.
        assert "no working StatPal discovery pass" in why
        assert detail in why
        if idless_census is None:
            assert code == DISCOVERY_NO_BEAT
        else:
            assert code == DISCOVERY_PARSER_MINTS_NO_ID
            assert idless_census in why


class TestEverySportTheEndpointIteratesHasAnAnswer:
    @pytest.mark.parametrize("sport_key", sorted(SHADOW_STAMPERS))
    def test_discovery_state_is_total_over_the_published_sports(self, sport_key):
        """The endpoint publishes this block for every `SHADOW_STAMPERS` key,
        including the measurement populations `flip_permitted` short-circuits.
        A `KeyError` here would be a 500 on the row an operator came to read.
        """
        code, why = discovery_state(sport_key)
        assert code in {
            DISCOVERY_SCHEDULED,
            DISCOVERY_PARSER_MINTS_NO_ID,
            # Added by #3193's follow-up: tennis was reading the bare
            # `NO-BEAT` because nothing consulted
            # `DISCOVERY_NO_BEAT_AND_NO_PARSE`. This closed set is what caught
            # the new code arriving — kept closed for that reason, and the
            # map→arm table in `test_a_refusal_reason_tennis_cannot_reach_3193`
            # is what stops the NEXT one being added with no arm at all.
            DISCOVERY_NO_BEAT_AND_PARSER_BLIND,
            DISCOVERY_NO_BEAT,
            "BEAT-WITHOUT-A-WORKING-PARSE",
        }
        assert why.strip()

    def test_an_unknown_sport_does_not_raise(self):
        code, why = discovery_state("quidditch_premier")
        assert code == DISCOVERY_NO_BEAT
        assert why.strip()

    def test_a_scheduled_sport_reads_scheduled(self):
        for sport_key in DISCOVERY_SCHEDULED_SPORTS:
            code, _ = discovery_state(sport_key)
            assert code == DISCOVERY_SCHEDULED, sport_key

    def test_the_idless_map_and_the_scheduled_set_are_disjoint(self):
        """A sport in both would read SCHEDULED and its census would go dark
        again — the same class of defect one list over.
        """
        assert not (
            set(DISCOVERY_PARSES_BUT_MINTS_NO_ID) & set(DISCOVERY_SCHEDULED_SPORTS)
        )
