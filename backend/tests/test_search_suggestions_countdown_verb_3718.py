"""#3718 — the "Right now" countdown says the right verb for the sport.

WHAT A USER SAW. On production `362f659d`, Saturday 2026-09-06 23:03Z, two of the
eight chips on the `/search` zero-state row read:

    Ole Miss Rebels        Tips off in 26 min
    Wisconsin Badgers      Tips off in 26 min

Both are `americanfootball_ncaaf` (events 1177062 and 416568, both 23:30Z).
Neither one tips off. `countdown_label` took no sport argument at all, so every
sport in section 2 got basketball's verb.

WHAT THESE TESTS PIN, and why each direction is needed (gotcha #43 — assert both
ways or the guard only catches half the class):

  1. the sports that were WRONG now read right — football kicks off, baseball
     has a first pitch, hockey drops a puck, tennis goes on court;
  2. the sport that was RIGHT is unchanged — basketball still tips off, because
     a copy fix that "fixes" the one correct case is a regression;
  3. an unmapped or missing sport degrades to the NEUTRAL wording rather than
     guessing a verb or raising — section 2 runs inside a bare `except` that
     logs and drops the whole section (the #2286 class), so a raise here would
     trade two wrong words for two missing chips;
  4. the mirror still agrees with the build. The verb is a second build-time
     input to a string the renderer rebuilds from the serving clock, so the
     SPORT has to travel in the stored payload beside the deadline. If it does
     not, a served mirror re-renders "Kicks off in 12 min" as "Starts in 12 min"
     and `test_render_is_a_no_op_on_a_payload_built_this_instant` is violated by
     a payload that still passes it — the deadline round-trips and the verb
     does not.
  5. the travelling field is STRIPPED on the way out, like the deadline, so the
     wire shape does not grow a key.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import search_suggestions_cache as ssc

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 9, 6, 23, 4, 0, tzinfo=timezone.utc)


class TestTheVerbMatchesTheSport:
    @pytest.mark.parametrize(
        "sport_key,expected",
        [
            # 🔴 THE TWO ROWS FROM THE PRODUCTION SHOT, BY THEIR REAL SPORT KEY.
            ("americanfootball_ncaaf", "Kicks off in 26 min"),
            ("americanfootball_nfl", "Kicks off in 26 min"),
            ("soccer_epl", "Kicks off in 26 min"),
            ("baseball_mlb", "First pitch in 26 min"),
            ("icehockey_nhl", "Puck drops in 26 min"),
            # Every tour spelling of tennis resolves through the PREFIX, which is
            # why the table is not keyed on the full sport key: #2552's lesson is
            # that `tennis_us_open` is not what any event carries.
            ("tennis_atp_us_open", "On court in 26 min"),
            ("tennis_wta_us_open", "On court in 26 min"),
            ("tennis_atp", "On court in 26 min"),
            ("cricket_test_match", "First ball in 26 min"),
        ],
    )
    async def test_a_sport_that_was_wrong_now_reads_right(self, sport_key, expected):
        assert ssc.countdown_label(T0 + timedelta(minutes=26), T0, sport_key) == expected

    @pytest.mark.parametrize(
        "sport_key", ["basketball_nba", "basketball_ncaab", "basketball_wnba"]
    )
    async def test_basketball_still_tips_off(self, sport_key):
        """The one sport the old constant was RIGHT for must not regress."""
        assert (
            ssc.countdown_label(T0 + timedelta(minutes=26), T0, sport_key)
            == "Tips off in 26 min"
        )

    async def test_no_football_game_can_print_the_basketball_verb(self):
        """The defect in its own words, as a negative — the shape #3718 filed."""
        for key in ("americanfootball_ncaaf", "americanfootball_nfl"):
            label = ssc.countdown_label(T0 + timedelta(minutes=26), T0, key)
            assert "Tips off" not in label, f"{key} still tips off: {label!r}"


class TestAnUnknownSportIsPlainAndNeverGuesses:
    @pytest.mark.parametrize(
        "sport_key",
        [
            None,
            "",
            "   ",
            "quidditch_premier",
            "politics",
            "esports_lol",
            "motorsport_f1",
            123,  # not a string at all
        ],
    )
    async def test_it_falls_back_to_the_neutral_wording(self, sport_key):
        assert (
            ssc.countdown_label(T0 + timedelta(minutes=26), T0, sport_key)
            == "Starts in 26 min"
        )

    async def test_the_neutral_wording_is_the_same_word_the_hours_branch_uses(self):
        """Plain, not a third vocabulary: "Starts" is already what >=1h prints."""
        assert ssc.countdown_label(T0 + timedelta(minutes=150), T0, None).startswith(
            "Starts in "
        )
        assert ssc.countdown_label(
            T0 + timedelta(minutes=150), T0, "americanfootball_ncaaf"
        ) == "Starts in 2h"

    async def test_an_unmapped_sport_does_not_raise(self):
        """Section 2's `except` logs and DROPS the section, so a raise costs chips."""
        for key in (None, "", "nonsense", object()):
            ssc.countdown_verb(key)  # must not raise

    async def test_the_expiry_contract_does_not_depend_on_the_sport(self):
        """A started game has no label whatever sport it is."""
        for key in (None, "basketball_nba", "americanfootball_ncaaf", "nonsense"):
            assert ssc.countdown_label(T0 - timedelta(seconds=1), T0, key) is None


class TestTheMirrorAgreesWithTheBuildOnTheVerb:
    """The renderer half — a verb that does not travel is a verb the mirror loses."""

    def _built(self, sport_key, deadline):
        """The stored artifact section 2 writes, in the shape the route writes it."""
        return {
            "suggestions": [
                {
                    "query": "Ole Miss Rebels",
                    "label": ssc.countdown_label(deadline, T0, sport_key),
                    "type": "event",
                    "event_id": 1177062,
                    ssc.COUNTDOWN_FIELD: deadline.isoformat(),
                    ssc.COUNTDOWN_SPORT_FIELD: sport_key,
                }
            ]
        }

    async def test_render_preserves_the_verb_on_a_payload_built_this_instant(self):
        payload = self._built("americanfootball_ncaaf", T0 + timedelta(minutes=26))
        out = ssc.render(payload, T0)
        assert out["suggestions"][0]["label"] == "Kicks off in 26 min"

    async def test_a_five_minute_old_mirror_still_kicks_off(self):
        """🔴 THE REGRESSION THIS CLASS EXISTS FOR.

        If the sport did not travel, the deadline would round-trip correctly and
        the minute count would be right — while the verb silently reverted to
        the neutral default. A mirror printing "Starts in 21 min" where the build
        printed "Kicks off in 26 min" is exactly the build/mirror disagreement
        the whole re-render design forbids, arriving through the field nobody
        added.
        """
        deadline = T0 + timedelta(minutes=26)
        payload = self._built("americanfootball_ncaaf", deadline)
        later = T0 + timedelta(minutes=5)
        out = ssc.render(payload, later)
        assert out["suggestions"][0]["label"] == "Kicks off in 21 min"

    async def test_every_sport_round_trips_through_the_renderer_unchanged(self):
        deadline = T0 + timedelta(minutes=26)
        for key in (
            "americanfootball_ncaaf",
            "baseball_mlb",
            "basketball_nba",
            "tennis_atp_us_open",
            "icehockey_nhl",
            None,
        ):
            payload = self._built(key, deadline)
            built = payload["suggestions"][0]["label"]
            assert ssc.render(payload, T0)["suggestions"][0]["label"] == built, key

    async def test_the_sport_field_is_stripped_from_the_served_payload(self):
        """Like the deadline: the wire shape must not grow a key."""
        payload = self._built("americanfootball_ncaaf", T0 + timedelta(minutes=26))
        item = ssc.render(payload, T0)["suggestions"][0]
        assert ssc.COUNTDOWN_SPORT_FIELD not in item
        assert ssc.COUNTDOWN_FIELD not in item
        # and the real content survives the strip
        assert item["query"] == "Ole Miss Rebels"
        assert item["event_id"] == 1177062

    async def test_a_stored_item_with_a_deadline_but_no_sport_still_renders(self):
        """Backward compatibility: a mirror written by the PREVIOUS build.

        A payload already in Redis when this ships carries `countdown_from` and
        no sport. It must render — plainly — not be dropped, or the first serve
        after deploy is a short row.
        """
        payload = {
            "suggestions": [
                {
                    "query": "Ole Miss Rebels",
                    "label": "Tips off in 26 min",
                    "type": "event",
                    "event_id": 1177062,
                    ssc.COUNTDOWN_FIELD: (T0 + timedelta(minutes=26)).isoformat(),
                }
            ]
        }
        out = ssc.render(payload, T0)
        assert out["suggestions"][0]["label"] == "Starts in 26 min"


class TestTheRouteHandsTheSportToTheRenderer:
    """AST, not grep: the fix is only live if section 2 actually passes a sport.

    `countdown_label`'s sport argument is OPTIONAL — it has to be, because the
    expiry contract does not vary by sport and the renderer calls it for items
    that predate the field. That optionality is exactly what lets a future edit
    drop the argument at the call site and print plain text forever with every
    unit test above still green. This reads the route.
    """

    async def test_section_two_passes_a_sport_key_to_countdown_label(self):
        import ast
        import inspect

        from app.routes import events as events_module

        src = inspect.getsource(events_module._build_search_suggestions)
        tree = ast.parse(src.lstrip())
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "countdown_label"
        ]
        assert calls, "section 2 no longer calls ssc.countdown_label at all"
        for call in calls:
            assert len(call.args) >= 3, (
                "ssc.countdown_label is called with fewer than 3 positional args, so "
                "the countdown reverted to the sport-neutral verb: #3718 regressed."
            )

    async def test_the_sport_travels_in_the_payload_the_route_stores(self):
        import inspect

        from app.routes import events as events_module

        src = inspect.getsource(events_module._build_search_suggestions)
        assert "COUNTDOWN_SPORT_FIELD" in src, (
            "section 2 stores no sport beside the deadline, so a served mirror "
            "cannot re-render the verb: #3718 regressed on the mirror path."
        )

    async def test_the_sport_key_is_selected_and_not_lazy_loaded(self):
        """🔴 `ev.sport.key` IS A LAZY LOAD AND WOULD DELETE THE SECTION.

        The section's query selects Event columns only. Reaching the sport
        through the relationship raises `MissingGreenlet` under async, inside
        this section's `try`, which logs and drops it — the chips would not have
        said "Kicks off", they would have been GONE. The key must come from the
        SELECT.
        """
        import ast
        import inspect

        from app.routes import events as events_module

        src = inspect.getsource(events_module._build_search_suggestions)
        tree = ast.parse(src.lstrip())

        # 🔴 AST, NOT A SOURCE GREP, AND THE FIRST DRAFT OF THIS TEST PROVED WHY:
        # a grep for `.sport.key` matched the COMMENT three lines above the query
        # that explains why the code must not say it. A comment is not a lazy
        # load. Only the parsed tree can tell the warning from the offence.
        lazy = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute)
            and n.attr == "key"
            and isinstance(n.value, ast.Attribute)
            and n.value.attr == "sport"
        ]
        assert not lazy, (
            "section 2 reaches the sport through the ORM relationship (`.sport.key`) "
            "— that is a lazy load under async and it drops the whole section"
        )

        # ...and the key really is in a `select(...)` alongside Event.
        selected = [
            call
            for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "select"
            and any(
                isinstance(a, ast.Attribute)
                and a.attr == "key"
                and isinstance(a.value, ast.Name)
                and a.value.id == "Sport"
                for a in call.args
            )
        ]
        assert selected, (
            "no `select(..., Sport.key, ...)` in the builder: the countdown's sport "
            "is not being loaded from the query, so it is either absent or lazy"
        )
