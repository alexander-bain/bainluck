"""A soccer StatPal anchor is a SHADOW, and must not buy a LIVE badge. #4075.

`event_has_never_been_observed` let a `statpal_fixture_id` rescue a row from the
narrowed unobserved bound, on stated grounds:

    "an anchored row is one the authority knows about and can settle, so it
    keeps its sport's full maximum however quiet it happens to be right now."

For soccer that premise is false BY CONSTRUCTION. `statpal_api` fences soccer
off from live-score ingestion on purpose:

    LIVESCORES_INGESTION_DARK_SPORTS: frozenset[str] = frozenset({"soccer"})

…while the authority stamper (`dd753773`, 2026-09-08) writes soccer anchors
hourly. So a soccer `statpal_fixture_id` means "we hold a number for this row",
never "something is watching it play".

THE COST, measured on production 2026-09-08 21:35Z: 124 soccer rows carried a
`statpal_fixture_id`; **68** of them were otherwise completely silent — no score,
no period, no `espn_id` — so the stamp was the ONLY thing defeating the
predicate. Each was bounded at soccer's 4.0h `SPORT_MAX_DURATIONS` default
instead of the 2.5h `UNOBSERVED_MAX_HOURS["soccer"]` written for exactly that
row: **1.5 extra hours of a LIVE badge on a match nothing is reporting on**, and
that population is the one #3946 narrowed the bound for in the first place.

LATENT WHEN FILED, not live: 0 of the 68 were `live` at the time of measurement.
This is a rung that would fire and today find nothing — which is why it is
guarded here rather than demonstrated against a production row.

The SQL twin (`event_rails.never_observed_columns`) learns the same sport in the
same commit; their agreement is swept 2^5 × both sports in
`test_a_hollow_live_card_does_not_lead_the_rail_3946.py` §4, which is the test
that fails if a future change teaches one half and not the other.
"""

import pytest

from app.services.statpal_api import LIVESCORES_INGESTION_DARK_SPORTS
from app.tasks.config import SPORT_MAX_DURATIONS
from app.utils.event_completion import (
    UNOBSERVED_MAX_HOURS,
    event_has_never_been_observed,
    wall_clock_bound_hours,
)
from app.utils.sport_keys import (
    STATPAL_SHADOW_ANCHOR_SPORT_PREFIXES,
    STATPAL_SPORT_MAPPING,
    statpal_anchor_is_shadow,
)

#: Soccer has no `SPORT_MAX_DURATIONS` prefix of its own, so it takes `default`.
#: Read from the map rather than written as `4.0`, so a change to the default
#: moves this test's premise with it instead of leaving a stale literal.
SOCCER_MAX_HOURS = SPORT_MAX_DURATIONS["default"]


def _silent_row_with_only_an_anchor(sport_key):
    """The specimen: every play signal silent, one StatPal id, no snapshot."""
    return event_has_never_been_observed(
        None,  # home_score
        None,  # away_score
        None,  # period
        None,  # espn_id
        "9912345",  # statpal_fixture_id — the shadow
        None,  # last_snapshot
        sport_key,
    )


class TestTheBoundTheShadowAnchorWasBuying:
    """§1 — the user-visible half: 2.5h, not 4.0h."""

    def test_a_silent_soccer_row_with_only_a_shadow_anchor_is_unobserved(self):
        assert _silent_row_with_only_an_anchor("soccer_epl") is True

    def test_it_is_bounded_at_two_and_a_half_hours_not_four(self):
        never_observed = _silent_row_with_only_an_anchor("soccer_epl")
        bound = wall_clock_bound_hours("soccer_epl", SOCCER_MAX_HOURS, never_observed)

        assert bound == UNOBSERVED_MAX_HOURS["soccer"] == 2.5
        assert bound < SOCCER_MAX_HOURS

    def test_the_gap_this_closes_is_the_hour_and_a_half_that_was_filed(self):
        """The issue's headline number, asserted rather than described."""
        assert SOCCER_MAX_HOURS - UNOBSERVED_MAX_HOURS["soccer"] == 1.5

    def test_the_old_reading_is_what_bought_the_extra_time(self):
        """Pins the REGRESSION, not just the repair.

        With the anchor read as an observation — which is what the predicate did
        before #4075, and what it would do again if `sport_key` ever gained a
        default — the same row keeps the full 4.0h. This is the assertion that
        goes red if the fix is reverted, and it is deliberately phrased as the
        old behaviour rather than as a second copy of the new one.
        """
        as_if_the_anchor_spoke = wall_clock_bound_hours(
            "soccer_epl", SOCCER_MAX_HOURS, False
        )
        assert as_if_the_anchor_spoke == SOCCER_MAX_HOURS == 4.0

    @pytest.mark.parametrize(
        "field,value",
        [
            ("home_score", 0),
            ("away_score", 0),
            ("period", "2nd Half"),
            ("espn_id", "401778901"),
        ],
    )
    def test_a_soccer_row_something_really_reported_on_keeps_the_full_maximum(
        self, field, value
    ):
        """The narrowing reaches SILENT rows only.

        A `0-0` at half time is a REPORTED scoreline, not an absence — demoting
        it would take a real match off a real league page, which is the failure
        `test_a_hollow_live_card_does_not_lead_the_rail_3946.py` §3 owns. #4075
        removes one rescuer, and must not have removed the others with it.
        """
        kwargs = dict(
            home_score=None,
            away_score=None,
            period=None,
            espn_id=None,
            statpal_fixture_id="9912345",
            last_snapshot=None,
            sport_key="soccer_epl",
        )
        kwargs[field] = value

        never_observed = event_has_never_been_observed(**kwargs)
        assert never_observed is False
        assert (
            wall_clock_bound_hours("soccer_epl", SOCCER_MAX_HOURS, never_observed)
            == SOCCER_MAX_HOURS
        )

    def test_a_play_snapshot_still_rescues_a_silent_soccer_row(self):
        """The sixth conjunct is untouched — a play source that captured a
        post-commence snapshot has spoken, whatever the anchor means.
        """
        assert (
            event_has_never_been_observed(
                None, None, None, None, "9912345", "a-snapshot", "soccer_epl"
            )
            is False
        )


class TestEveryOtherSportsAnchorStillProtects:
    """§2 — the issue's second acceptance clause, one sport at a time."""

    @pytest.mark.parametrize(
        "sport_key",
        [
            "americanfootball_nfl",
            "basketball_nba",
            "baseball_mlb",
            "icehockey_nhl",
            "tennis_atp",
            "tennis_wta",
            "golf_pga",
        ],
    )
    def test_a_lit_sports_anchor_is_still_an_observation(self, sport_key):
        assert statpal_anchor_is_shadow(sport_key) is False
        assert _silent_row_with_only_an_anchor(sport_key) is False

    def test_the_tennis_bound_3946_shipped_is_unmoved(self):
        """#3946's own specimen, re-asserted through the changed function.

        A silent `tennis_atp` row with NO anchor still narrows to 3.0h — this
        ship must not have widened the bound it is standing on.
        """
        never_observed = event_has_never_been_observed(
            None, None, None, None, None, None, "tennis_atp"
        )
        assert never_observed is True
        assert wall_clock_bound_hours("tennis_atp", 6.0, never_observed) == 3.0


class TestTheShadowSetCannotDriftFromTheFence:
    """§3 — `sport_keys` and `statpal_api` hold one decision in two places.

    `LIVESCORES_INGESTION_DARK_SPORTS` is keyed by STATPAL's sport identifier and
    `STATPAL_SHADOW_ANCHOR_SPORT_PREFIXES` by OURS, so neither can import the
    other's meaning. This is the test that makes them one decision anyway: light
    soccer up (#3348) and it fails here, pointing at the prefix set, rather than
    silently leaving soccer rows bounded for a darkness that ended.
    """

    def test_every_dark_statpal_sport_has_its_our_keys_covered(self):
        dark_our_keys = {
            our_key
            for our_key, statpal_sport in STATPAL_SPORT_MAPPING.items()
            if statpal_sport in LIVESCORES_INGESTION_DARK_SPORTS
        }
        assert dark_our_keys, "the fence named a StatPal sport we map no key to"

        for our_key in sorted(dark_our_keys):
            assert statpal_anchor_is_shadow(our_key) is True, our_key

    def test_no_lit_statpal_sport_is_treated_as_a_shadow(self):
        for our_key, statpal_sport in sorted(STATPAL_SPORT_MAPPING.items()):
            if statpal_sport in LIVESCORES_INGESTION_DARK_SPORTS:
                continue
            assert statpal_anchor_is_shadow(our_key) is False, our_key

    @pytest.mark.parametrize(
        "sport_key",
        [
            "soccer_brazil_campeonato",
            "soccer_mexico_ligamx",
            "soccer_other",
            "soccer_uefa_champs_league",
        ],
    )
    def test_soccer_keys_the_schedule_map_never_names_are_covered_too(self, sport_key):
        """Why this is keyed by PREFIX and not by `STATPAL_SPORT_MAPPING`'s keys.

        That map lists seven soccer keys because those are the ones we pull
        schedules for, but most soccer events sit under keys it never names —
        105 of 168 in the attach window on 2026-09-06. Keying the shadow set to
        the schedule map would leave the majority of the population still
        reading its anchor as an observation, which is the same reasoning
        `statpal_sync._INJURY_EVENT_SPORT_PREFIX` records.
        """
        assert statpal_anchor_is_shadow(sport_key) is True

    def test_an_absent_sport_key_reads_as_not_a_shadow(self):
        """The default direction: unknown sport ⇒ the anchor keeps its ordinary
        protective meaning, matching how `wall_clock_bound_hours` treats a sport
        with no `UNOBSERVED_MAX_HOURS` entry. Narrowing is for sports we measured.
        """
        assert statpal_anchor_is_shadow(None) is False
        assert statpal_anchor_is_shadow("") is False
        assert statpal_anchor_is_shadow("handball_generic") is False

    def test_the_prefix_set_is_exactly_soccer_today(self):
        """A one-line census, so widening the set is a deliberate edit with a
        test to update rather than a silent change of blast radius.
        """
        assert STATPAL_SHADOW_ANCHOR_SPORT_PREFIXES == frozenset({"soccer"})
