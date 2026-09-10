"""#4711 — a mapped StatPal sport is either on a beat or recorded as deliberately not.

`STATPAL_SPORT_MAPPING` is a claim that the StatPal consumers can do something with
a sport. `_sync_statpal_schedules` is only ever invoked with the sport keys its four
beats pass, so **a key added to the map without a beat is silently never synced**:
nothing fails, nothing logs, no terminal goes non-green, because no pass ever names
it. #2907's `sports_unasked` does not catch it either — that names sports a *pass*
could not ask, and no pass ever reaches this one.

That is #2867's failure mode (a game that never reaches the site before a market
lists it) arriving through a config edit rather than an outage, and it is #4691's
class exactly: a key claiming coverage no code path delivers.

So the guard is between records the repo already keeps — the map, the beat schedule,
the endpoint table, and the `authority_by_sport` discovery dicts. It mints no fourth
list of sports, because a fourth list is the thing that drifts.

## The two readings of "askable", and why this file pins both

There are two records of which sports the schedule task can actually ask, and
**they do not agree**:

* `DAY_BOARD_SPORTS` = `{"tennis", "soccer"}` — a fact about StatPal's product.
* the marker the CODE gates on — `"{day}" in _SCHEDULE_ENDPOINTS[sport]`, which
  becomes `no_day_token` → `fetch.asked is False`.

Tennis (`daily/{day}`) trips both. **Soccer trips only the first**: its endpoint is
`matches/daily`, whose day token is a query parameter rather than a path segment, so
the code's marker misses it and `get_fixtures_result("soccer")` really does issue a
request. `DAY_BOARD_SPORTS`' own docstring warns about this ("a caller reaching for
that marker concludes soccer needs no token, which is the shape of #4320").

Measured 2026-09-10 on the post-#4691 map (13 keys): askable reads **4** under
`DAY_BOARD_SPORTS` and **11** under the code's marker, the seven soccer keys being
the difference. The 4-key reading is the one that equals the beat set, so a guard
that quietly picked it would go green while the disagreement it was standing next to
went unrecorded. `test_the_two_readings_of_askable_disagree_and_the_gap_is_soccer`
asserts the gap instead, so that closing it in either record has to be deliberate.
"""

import pytest

from app.config.authority_by_sport import (
    DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE,
    DISCOVERY_NO_BEAT_AND_NO_PARSE,
    DISCOVERY_PARSES_BUT_MINTS_NO_ID,
)
from app.services.statpal_api import (
    DAY_BOARD_SPORTS,
    StatPalAPIService,
    schedule_can_cover_today,
)
from app.utils.sport_keys import RETIRED_STATPAL_SPORT_KEYS, STATPAL_SPORT_MAPPING

SCHEDULES_TASK = "app.tasks.sync_statpal_schedules"


def _schedule_beats() -> dict[str, dict]:
    """Every beat that runs the schedule task, read from the live schedule.

    Not a hard-coded list of four names: the point of this file is to notice when
    that set changes, which a copy of it here would prevent.
    """
    from app.tasks import celery_app

    return {
        name: spec
        for name, spec in celery_app.conf.beat_schedule.items()
        if spec.get("task") == SCHEDULES_TASK
    }


def _beat_sport_keys() -> dict[str, str]:
    """beat name → the `sport_key` it passes."""
    return {
        name: spec.get("kwargs", {}).get("sport_key")
        for name, spec in _schedule_beats().items()
    }


def _endpoint_for(statpal_sport: str) -> str:
    return StatPalAPIService._SCHEDULE_ENDPOINTS.get(statpal_sport, "season-schedule")


def _code_can_ask(statpal_sport: str) -> bool:
    """The predicate the TASK gates on, transcribed from `get_fixtures_result`.

    `"{day}" in endpoint` → `no_day_token` → `StatPalFixtureFetch.asked is False`.
    Deliberately NOT `schedule_can_cover_today`; the whole content of this file is
    that the two differ.
    """
    return "{day}" not in _endpoint_for(statpal_sport)


def _recorded_reason_for(statpal_sport: str) -> str | None:
    """The recorded reason this StatPal sport has no schedule beat, or None.

    The discovery dicts are keyed by measurement population (`tennis_singles`,
    `tennis_doubles`) or by the StatPal sport (`soccer`), never by our sport keys,
    so the join is by prefix. Union of all three so a sport moving between them —
    which is a real transition, soccer is one parser fix from
    `DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE` — does not read as the reason vanishing.
    """
    for record in (
        DISCOVERY_NO_BEAT_AND_NO_PARSE,
        DISCOVERY_PARSES_BUT_MINTS_NO_ID,
        DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE,
    ):
        for population, why in record.items():
            if population.startswith(statpal_sport) and why and why.strip():
                return why
    return None


class TestEveryBeatPointsAtSomethingReal:
    """The reverse direction: a beat may not name a key the map does not serve."""

    def test_the_schedules_task_still_has_beats(self):
        """Guard the guard.

        Every assertion below quantifies over the beat set, so an empty one would
        make this whole file vacuously green — the exact failure #4691 was: a check
        that stops measuring without going red.
        """
        assert _schedule_beats(), (
            "no beat runs %s — the schedule sync is unscheduled, or the task was "
            "renamed and this file is now measuring nothing" % SCHEDULES_TASK
        )

    def test_every_beat_passes_an_explicit_sport_key(self):
        """The all-sports form must not be reachable from the schedule.

        It loops the whole map, so it reaches the seven soccer keys, which
        `DISCOVERY_PARSES_BUT_MINTS_NO_ID` says must not be ingested until the
        parser learns `fallback_id_3`. A beat with no `sport_key` switches that
        on by accident.
        """
        missing = sorted(n for n, k in _beat_sport_keys().items() if not k)
        assert missing == [], (
            f"schedule beats with no sport_key: {missing} — the all-sports form "
            "reaches every mapped key, soccer included"
        )

    def test_every_beat_sport_key_is_mapped(self):
        """A beat pointed at an unmapped key banks `no_work` forever, silently.

        `_sync_statpal_schedules` resolves `sport_keys = [sport_key] if sport_key
        in STATPAL_SPORT_MAPPING else []`, so the pass has nothing to iterate and
        terminates green.
        """
        unmapped = sorted(
            f"{n} -> {k}"
            for n, k in _beat_sport_keys().items()
            if k and k not in STATPAL_SPORT_MAPPING
        )
        assert unmapped == [], (
            f"beats naming keys absent from STATPAL_SPORT_MAPPING: {unmapped}"
        )

    def test_no_beat_points_at_a_retired_key(self):
        """#4691's retirement has to reach the schedule, not just the map.

        Deleting a key from the map while leaving its beat running is the same
        silent `no_work` as above, arrived at from the other side.
        """
        retired = sorted(
            f"{n} -> {k}"
            for n, k in _beat_sport_keys().items()
            if k in RETIRED_STATPAL_SPORT_KEYS
        )
        assert retired == [], f"beats naming RETIRED keys: {retired}"

    def test_no_beat_points_at_a_day_board_sport(self):
        """A day-board key on a beat cannot yield a schedule.

        Tennis would bank `no_day_token` hourly; soccer would ingest the live
        board wearing a schedule URL. Both are `sports_unasked`-or-worse forever.
        """
        day_board = sorted(
            f"{n} -> {k} ({STATPAL_SPORT_MAPPING.get(k)})"
            for n, k in _beat_sport_keys().items()
            if k in STATPAL_SPORT_MAPPING
            and STATPAL_SPORT_MAPPING[k] in DAY_BOARD_SPORTS
        )
        assert day_board == [], f"beats naming day-board sports: {day_board}"


class TestEveryAskableKeyIsScheduled:
    """The forward direction: the hole #4711 exists to close."""

    def test_every_non_day_board_mapped_key_has_a_beat(self):
        """A mapped, askable sport with no beat is never synced and never says so.

        This is the acceptance criterion of #4711. Today the two sets are equal
        (4 keys: nfl, mlb, nba, nhl); the assertion is what keeps them equal.
        """
        scheduled = {k for k in _beat_sport_keys().values() if k}
        askable = {
            our_key
            for our_key, statpal_sport in STATPAL_SPORT_MAPPING.items()
            if schedule_can_cover_today(statpal_sport)
        }
        unscheduled = sorted(askable - scheduled)
        assert unscheduled == [], (
            f"mapped and askable but on no beat: {unscheduled} — add a "
            "`sync-statpal-schedules-*` beat, or record why not in "
            "`authority_by_sport`"
        )

    def test_every_day_board_key_is_unscheduled_for_a_recorded_reason(self):
        """The nine are deliberately unscheduled, and the repo says why.

        Absence alone would also hold if someone simply forgot, which is what
        #4711 is about. The reason has to be findable from the sport.
        """
        scheduled = {k for k in _beat_sport_keys().values() if k}
        unrecorded = []
        for our_key, statpal_sport in sorted(STATPAL_SPORT_MAPPING.items()):
            if schedule_can_cover_today(statpal_sport):
                continue
            assert our_key not in scheduled  # covered by the reverse test above
            if _recorded_reason_for(statpal_sport) is None:
                unrecorded.append(f"{our_key} ({statpal_sport})")
        assert unrecorded == [], (
            f"day-board keys with no recorded reason for having no beat: "
            f"{unrecorded} — see DISCOVERY_* in app/config/authority_by_sport.py"
        )


class TestTheTwoReadingsOfAskableDisagree:
    """The trap this file refuses to paper over."""

    def test_the_two_readings_of_askable_disagree_and_the_gap_is_soccer(self):
        """`DAY_BOARD_SPORTS` says 4 askable; the code's marker says 11.

        Pinned rather than resolved, because resolving it is not this guard's
        ship and either resolution is a real decision:

        * teach `get_fixtures_result` that `matches/daily` needs an offset, and
          soccer starts reporting `no_day_token` (the two readings converge at 4);
        * or leave it, and the all-sports form keeps issuing a real soccer request.

        If this test fails, one of those happened — re-read
        `test_every_non_day_board_mapped_key_has_a_beat`, whose 4-key reading is
        the one that currently equals the beat set.
        """
        by_day_board = {
            k for k, sp in STATPAL_SPORT_MAPPING.items() if schedule_can_cover_today(sp)
        }
        by_code_marker = {
            k for k, sp in STATPAL_SPORT_MAPPING.items() if _code_can_ask(sp)
        }

        assert by_day_board <= by_code_marker, (
            "the code's marker now refuses a sport `DAY_BOARD_SPORTS` calls "
            "askable — that inverts the known direction of the disagreement"
        )

        gap = sorted(by_code_marker - by_day_board)
        assert gap, (
            "the two readings of askable now agree. If soccer learned "
            "`no_day_token`, delete this test and say so; do not widen the map."
        )
        off_soccer = [
            k for k in gap if STATPAL_SPORT_MAPPING[k] != "soccer"
        ]
        assert off_soccer == [], (
            f"a NON-soccer sport joined the disagreement: {off_soccer} — its "
            "endpoint has no `{day}` marker but it is a day-board sport, so the "
            "all-sports form will issue a real request for it"
        )

    def test_the_disagreeing_sports_are_recorded_as_unsafe_to_schedule(self):
        """Soccer is asked by the code and has no beat — on purpose, in writing.

        The gap above is only benign because `DISCOVERY_PARSES_BUT_MINTS_NO_ID`
        rules that a soccer schedule beat "must not be [switched on]" until the
        ingest parser reads `fallback_id_3`. Without that record, seven askable
        keys with no beat would be exactly the defect #4711 describes.
        """
        gap = sorted(
            k
            for k, sp in STATPAL_SPORT_MAPPING.items()
            if _code_can_ask(sp) and not schedule_can_cover_today(sp)
        )
        assert gap, "no disagreement to check — see the test above"
        missing = [
            k for k in gap if _recorded_reason_for(STATPAL_SPORT_MAPPING[k]) is None
        ]
        assert missing == [], (
            f"askable-by-the-code, unscheduled, and unrecorded: {missing}"
        )


class TestTheGuardReadsRecordsRatherThanCopyingThem:
    """#4691's own pattern: pin the records the repo keeps, never mint another."""

    @pytest.mark.parametrize(
        "sport", sorted(DAY_BOARD_SPORTS)
    )
    def test_day_board_sports_have_an_endpoint_entry(self, sport):
        """A day-board sport missing from `_SCHEDULE_ENDPOINTS` defaults to
        `season-schedule`, which would make it read as askable by the code marker
        for no better reason than a missing dict key."""
        assert sport in StatPalAPIService._SCHEDULE_ENDPOINTS, (
            f"{sport} is day-board but has no _SCHEDULE_ENDPOINTS entry, so it "
            "falls back to `season-schedule` and silently reads as askable"
        )

    def test_schedule_can_cover_today_is_day_board_membership(self):
        """The helper and the constant must not drift apart.

        Everything above uses `schedule_can_cover_today`; this is what entitles
        it to stand for `DAY_BOARD_SPORTS`.
        """
        for sport in set(STATPAL_SPORT_MAPPING.values()) | set(DAY_BOARD_SPORTS):
            assert schedule_can_cover_today(sport) == (sport not in DAY_BOARD_SPORTS), (
                f"schedule_can_cover_today({sport!r}) disagrees with DAY_BOARD_SPORTS"
            )
