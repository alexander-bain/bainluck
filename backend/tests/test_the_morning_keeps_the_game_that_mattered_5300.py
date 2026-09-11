"""#5300 — the morning after keeps the game that MATTERED, not the closest two.

THE SPECIMEN, dated and measured on production rows. Friday 2026-09-11, the
morning after the NFL primetime game. `GET /api/feed?mode=sports&limit=250`
served three `tier:1` finals inside the 14h retention window:

| final | age at 15:30Z | EI |
|---|---|---|
| **San Francisco 49ers @ Los Angeles Rams** (NFL, `signal:blowout`) | 12.1h | **54** |
| Pittsburgh Pirates @ Chicago White Sox (MLB) | 13.3h | 82 |
| Colorado Rockies @ New York Yankees (MLB) | 13.2h | 60 |

`_DISCOVER_RECENT_FINAL_SLOTS` is 2 and the arm ranked by EI alone, so it kept
the two MLB games and dropped the NFL one. Three independent reads agree:

* **14:52Z** — #5100's own after-LOOK photographed exactly those two MLB games
  seated at ranks 11 and 12 of 20, the NFL game absent;
* **15:30Z** — the table above, replayed through the real function;
* **16:18Z** — the bus's day-1 ranking eval: "the 49ers-Rams result is ABSENT
  from Discover's top ... 2 dead cards of 20".

The card only became findable at ~16:15Z, once BOTH MLB games aged past 14h —
the last ~70 minutes before it expired too. The whole morning was lost.

═══ WHY EI ALONE CANNOT ANSWER THIS ═══

EI measures HOW CLOSE a game was, not HOW MUCH IT MATTERED. The 49ers game
carries `signal:blowout` and so scores 54; a tight Pirates-White Sox scores 82.
On any night one league plays a full slate, its best two close finishes beat the
one game the country actually watched. Two terms fix it and each does work the
other cannot:

* **a per-league slot** (`_DISCOVER_FINAL_LEAGUE_SLOTS`) — a nightly slate stops
  owning both slots. This is what admits the NFL game.
* **a freshness decay** (`_DISCOVER_FINAL_EI_HALF_LIFE_HOURS`) — Alex's "no
  fixed clock, a decay the eval can grade". A fresher final outranks a staler one
  of similar quality instead of the two being ordered by EI alone.

═══ WHAT THIS SHIP DOES NOT TOUCH ═══

RETENTION. The 14h cliff is D118 = B (Alex, 2026-09-10) and a CI-guarded mirror
of `frontend/lib/discover/feedFreshness.ts`; `test_marquee_final_stays_fourteen_
hours_d118.py` owns it. This ship changes only WHICH finals win the two slots.
`test_the_decay_cannot_resurrect_a_retired_card` pins that boundary from here.

`timing:primetime` LOOKS like the significance signal and is NOT one:
`event_taxonomy` derives it from the clock alone (19:00-23:59 Eastern), so a
7:05pm ET baseball game earns it and a 1pm playoff game does not. Today's two MLB
rows started 18:05 and 18:40 ET and missed it by minutes, so a rule resting on it
would have passed by luck and broken the first night the Yankees played an hour
later. `test_the_fix_does_not_rest_on_the_primetime_tag` pins that.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import (
    _DISCOVER_FINAL_EI_HALF_LIFE_HOURS,
    _DISCOVER_FINAL_LEAGUE_SLOTS,
    _DISCOVER_RECENT_FINAL_SLOTS,
    _discover_final_freshness_weight,
    _discover_final_league_key,
    _discover_final_rank_score,
    _recent_marquee_final_ids,
)

NOW = datetime(2026, 9, 11, 15, 30, tzinfo=timezone.utc)

#: "caller said nothing", distinct from an explicit `ended_at=None`.
_MISSING = object()


def _final(
    *,
    event_id: int,
    ei: int,
    hours_since_end: float,
    league: str | None = "mlb",
    sport: str = "baseball",
    extra_tags: tuple[str, ...] = (),
    media: bool = True,
    ended_at: object = _MISSING,
) -> dict:
    """A finished tier-1 card, shaped like the production rows above."""
    tags = ["tier:1", "status:completed", f"sport:{sport}", *extra_tags]
    if league is not None:
        tags.append(f"league:{league}")
    ended = NOW - timedelta(hours=hours_since_end)
    data = {
        "id": event_id,
        "sport": sport,
        "status": "completed",
        "event_tags": tags,
        "home_team": f"home {event_id}",
        "away_team": f"away {event_id}",
        # Kickoff sits well before the whistle so a test that accidentally ages
        # off `commence_time` reads a different number and fails loudly.
        "commence_time": (ended - timedelta(hours=3)).isoformat().replace(
            "+00:00", "Z"
        ),
        "ei": {"score": ei},
    }
    if ended_at is _MISSING:
        data["ended_at"] = ended.isoformat().replace("+00:00", "Z")
    elif ended_at is not None:
        data["ended_at"] = ended_at
    if media:
        data["home_team_data"] = {"logo": "h"}
        data["away_team_data"] = {"logo": "a"}
    return {"type": "event", "score": 67, "data": data}


def _the_measured_morning() -> list[dict]:
    """The three production rows, with their real EIs and real ages."""
    return [
        _final(event_id=1, ei=82, hours_since_end=13.3, league="mlb"),
        _final(event_id=2, ei=60, hours_since_end=13.2, league="mlb"),
        _final(
            event_id=3,
            ei=54,
            hours_since_end=12.1,
            league="nfl",
            sport="football",
            extra_tags=("signal:blowout", "timing:primetime"),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
class TestTheShip:
    """Each of these is FALSE on the parent commit."""

    def test_last_nights_nfl_game_is_one_of_the_two_finals_discover_keeps(self):
        kept = _recent_marquee_final_ids(self_rows := _the_measured_morning(), NOW)
        assert 3 in kept, (
            "the NFL primetime final must survive; ranked by EI alone it scores "
            "54 against 82 and 60 and is dropped"
        )
        assert len(kept) == _DISCOVER_RECENT_FINAL_SLOTS
        assert len(self_rows) == 3

    def test_the_best_other_final_keeps_the_second_slot(self):
        # The league cap must not cost the night its best other result: the
        # reader is owed the marquee game AND the night's best finish.
        kept = _recent_marquee_final_ids(_the_measured_morning(), NOW)
        assert kept == {1, 3}, "expected the best MLB final and the NFL final"

    def test_the_weaker_same_league_final_is_the_one_that_loses(self):
        # Rockies @ Yankees (EI 60) is the card that gives up its slot, not the
        # better MLB one — the cap picks the weakest of the repeat, never the
        # first one it happens to walk past.
        assert 2 not in _recent_marquee_final_ids(_the_measured_morning(), NOW)

    def test_it_holds_across_the_whole_morning_not_one_lucky_minute(self):
        # The defect self-corrected at ~16:15Z when both MLB rows aged out. A fix
        # that only works at one clock is the same nothing.
        for minutes in range(0, 90, 10):
            now = datetime(2026, 9, 11, 14, 52, tzinfo=timezone.utc) + timedelta(
                minutes=minutes
            )
            rows = [
                _final(event_id=1, ei=82, hours_since_end=13.3 - minutes / 60),
                _final(event_id=2, ei=60, hours_since_end=13.2 - minutes / 60),
                _final(
                    event_id=3,
                    ei=54,
                    hours_since_end=12.1 - minutes / 60,
                    league="nfl",
                    sport="football",
                ),
            ]
            # Re-age against this clock rather than NOW.
            for row, hours in ((rows[0], 13.3), (rows[1], 13.2), (rows[2], 12.1)):
                ended = now - timedelta(hours=hours)
                row["data"]["ended_at"] = ended.isoformat().replace("+00:00", "Z")
            assert 3 in _recent_marquee_final_ids(rows, now), (
                f"the NFL final fell off {minutes} minutes into the morning"
            )


# ─────────────────────────────────────────────────────────────────────────────
class TestTheCapNeverCostsASlot:
    """#1091's standing lesson: a cap that turns into a filter empties a surface."""

    def test_three_finals_from_one_league_still_fill_both_slots(self):
        rows = [
            _final(event_id=10, ei=90, hours_since_end=5.0),
            _final(event_id=11, ei=80, hours_since_end=5.0),
            _final(event_id=12, ei=70, hours_since_end=5.0),
        ]
        kept = _recent_marquee_final_ids(rows, NOW)
        assert kept == {10, 11}, (
            "with only one league on the board the cap must defer, not delete — "
            "the morning must not be emptier than the EI-only arm left it"
        )

    def test_a_single_league_night_is_unchanged_from_the_parent_behaviour(self):
        rows = [_final(event_id=20 + n, ei=90 - n, hours_since_end=4.0) for n in range(5)]
        assert _recent_marquee_final_ids(rows, NOW) == {20, 21}

    def test_the_slot_budget_is_never_exceeded(self):
        rows = [
            _final(event_id=30, ei=90, hours_since_end=4.0, league="mlb"),
            _final(event_id=31, ei=88, hours_since_end=4.0, league="nfl"),
            _final(event_id=32, ei=86, hours_since_end=4.0, league="nba"),
            _final(event_id=33, ei=84, hours_since_end=4.0, league="nhl"),
        ]
        assert len(_recent_marquee_final_ids(rows, NOW)) == _DISCOVER_RECENT_FINAL_SLOTS


# ─────────────────────────────────────────────────────────────────────────────
class TestTheDecay:
    """Alex's 'no fixed clock — a decay the eval can grade'."""

    def test_a_fresher_final_outranks_a_staler_one_of_equal_excitement(self):
        fresh = _final(event_id=40, ei=70, hours_since_end=2.0, league="nfl")
        stale = _final(event_id=41, ei=70, hours_since_end=12.0, league="mlb")
        assert _discover_final_rank_score(fresh, NOW) > _discover_final_rank_score(
            stale, NOW
        )

    def test_the_stale_final_loses_its_slot_the_moment_something_newer_arrives(self):
        stale = _final(event_id=50, ei=95, hours_since_end=13.5, league="mlb")
        alone = _recent_marquee_final_ids([stale], NOW)
        assert alone == {50}, "on a quiet night a stale final still holds a slot"

        newer = [
            _final(event_id=51, ei=60, hours_since_end=1.0, league="nfl"),
            _final(event_id=52, ei=58, hours_since_end=1.5, league="nba"),
        ]
        kept = _recent_marquee_final_ids([stale] + newer, NOW)
        assert kept == {51, 52}, (
            "EI 95 at 13.5h must lose to two fresh finals — this is 'the stale "
            "finals off page one'"
        )

    def test_the_half_life_actually_halves(self):
        row = _final(event_id=60, ei=100, hours_since_end=_DISCOVER_FINAL_EI_HALF_LIFE_HOURS)
        assert _discover_final_freshness_weight(row, NOW) == pytest.approx(0.5)

    def test_the_decay_is_continuous_not_a_second_cliff(self):
        # A cliff would let two requests minutes apart disagree. Every step down
        # must be strictly smaller than the last and never reach zero.
        weights = [
            _discover_final_freshness_weight(
                _final(event_id=70, ei=50, hours_since_end=h), NOW
            )
            for h in (0.5, 2.0, 6.0, 10.0, 13.9)
        ]
        assert weights == sorted(weights, reverse=True)
        assert len(set(weights)) == len(weights)
        assert weights[-1] > 0.0

    def test_the_decay_cannot_resurrect_a_retired_card(self):
        # Retention is D118's 14h cliff and is NOT this ship's. A card past it is
        # gone however fresh its decay term would look.
        retired = _final(event_id=80, ei=100, hours_since_end=14.5, league="nfl")
        assert _recent_marquee_final_ids([retired], NOW) == set()

    def test_the_decay_ages_off_the_whistle_not_the_kickoff(self):
        # `_final` puts kickoff 3h before the whistle, so ageing off
        # `commence_time` reads 3h more and gives a visibly smaller weight. The
        # anchor must be the same one `client_deletes_finished_card` retires on.
        row = _final(
            event_id=90, ei=100, hours_since_end=_DISCOVER_FINAL_EI_HALF_LIFE_HOURS
        )
        assert _discover_final_freshness_weight(row, NOW) == pytest.approx(0.5)

        kickoff_aged = 0.5 ** (
            (_DISCOVER_FINAL_EI_HALF_LIFE_HOURS + 3.0)
            / _DISCOVER_FINAL_EI_HALF_LIFE_HOURS
        )
        assert _discover_final_freshness_weight(row, NOW) != pytest.approx(
            kickoff_aged
        )

    def test_the_decay_breaks_near_ties_without_overruling_a_real_gap(self):
        # The calibration the half-life encodes. Over the 1.2h spread a real
        # morning has, a clearly better game must still win; only a near-tie
        # turns on freshness.
        better_but_older = _final(event_id=91, ei=82, hours_since_end=13.3)
        worse_but_newer = _final(event_id=92, ei=60, hours_since_end=12.1)
        assert _discover_final_rank_score(
            better_but_older, NOW
        ) > _discover_final_rank_score(worse_but_newer, NOW)

        near_tie_older = _final(event_id=93, ei=71, hours_since_end=13.3)
        near_tie_newer = _final(event_id=94, ei=70, hours_since_end=12.1)
        assert _discover_final_rank_score(
            near_tie_newer, NOW
        ) > _discover_final_rank_score(near_tie_older, NOW)

    def test_a_classic_five_hours_older_than_a_dud_still_wins(self):
        """The half-life pinned FROM BELOW, where nothing else pins it.

        Every other guard here passes at a six-hour half-life, which is the
        value that was measured and rejected for turning "last night's best
        games" into "last night's latest games". This is the case that separates
        them: both games are last night, five hours apart, and one was a classic
        (EI 96) while the other was a dud (EI 60). At ten hours the classic
        wins; at six the dud does. A reader opening Discover in the morning is
        owed the classic.
        """
        classic = _final(event_id=95, ei=96, hours_since_end=13.0, league="nfl")
        dud = _final(event_id=96, ei=60, hours_since_end=8.0, league="mlb")
        assert _discover_final_rank_score(classic, NOW) > _discover_final_rank_score(
            dud, NOW
        ), "the decay has become the ranking instead of a tie-break"

        # And it is the SELECTION that must come out that way, not just the score.
        assert _recent_marquee_final_ids([classic, dud], NOW) == {95, 96}
        ranked = sorted(
            (classic, dud), key=lambda r: -_discover_final_rank_score(r, NOW)
        )
        assert ranked[0]["data"]["id"] == 95


# ─────────────────────────────────────────────────────────────────────────────
class TestTheEdgesThatMustNotBecomePolicy:
    def test_two_league_less_finals_do_not_starve_each_other(self):
        # Folding untagged rows into one shared bucket would let the first one
        # silently block the second — a missing tag becoming a policy about games
        # that have nothing to do with each other.
        rows = [
            _final(event_id=100, ei=90, hours_since_end=4.0, league=None, sport=""),
            _final(event_id=101, ei=88, hours_since_end=4.0, league=None, sport=""),
        ]
        assert _recent_marquee_final_ids(rows, NOW) == {100, 101}

    def test_the_league_key_prefers_league_then_sport_then_the_event_itself(self):
        assert _discover_final_league_key(
            _final(event_id=110, ei=1, hours_since_end=1.0, league="nfl", sport="football")
        ) == "league:nfl"
        assert _discover_final_league_key(
            _final(event_id=111, ei=1, hours_since_end=1.0, league=None, sport="football")
        ) == "sport:football"
        assert _discover_final_league_key(
            _final(event_id=112, ei=1, hours_since_end=1.0, league=None, sport="")
        ) == "event:112"

    def test_a_sport_tagged_pair_is_still_capped(self):
        # Two rows of one sport with no league tag are still one slate.
        rows = [
            _final(event_id=120, ei=90, hours_since_end=4.0, league=None, sport="soccer"),
            _final(event_id=121, ei=88, hours_since_end=4.0, league=None, sport="soccer"),
            _final(event_id=122, ei=50, hours_since_end=4.0, league="nfl", sport="football"),
        ]
        assert _recent_marquee_final_ids(rows, NOW) == {120, 122}

    def test_an_unreadable_stamp_leaves_the_existing_ordering_alone(self):
        # Weight 1.0, not 0.0: a parse failure must not silently sort a card last.
        row = _final(event_id=130, ei=50, hours_since_end=4.0, ended_at="not a date")
        row["data"].pop("commence_time")
        assert _discover_final_freshness_weight(row, NOW) == 1.0

    def test_a_future_stamp_is_clamped_and_never_becomes_a_boost(self):
        ahead = (NOW + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        row = _final(event_id=131, ei=50, hours_since_end=1.0, ended_at=ahead)
        assert _discover_final_freshness_weight(row, NOW) == 1.0

    def test_the_fix_does_not_rest_on_the_primetime_tag(self):
        # `timing:primetime` is a clock bucket (19:00-23:59 ET), not significance.
        # Strip it from the NFL row and the ship must still hold.
        rows = _the_measured_morning()
        nfl = next(r for r in rows if r["data"]["id"] == 3)
        nfl["data"]["event_tags"] = [
            t for t in nfl["data"]["event_tags"] if t != "timing:primetime"
        ]
        assert "timing:primetime" not in nfl["data"]["event_tags"]
        assert 3 in _recent_marquee_final_ids(rows, NOW)

    def test_giving_the_mlb_rows_primetime_too_does_not_break_it(self):
        # The other direction: a 7:05pm ET baseball game DOES earn the tag.
        rows = _the_measured_morning()
        for row in rows:
            row["data"]["event_tags"] = list(row["data"]["event_tags"]) + [
                "timing:primetime"
            ]
        assert 3 in _recent_marquee_final_ids(rows, NOW)


# ─────────────────────────────────────────────────────────────────────────────
class TestTheConstantsAreWhatTheDocstringsClaim:
    def test_one_league_slot(self):
        assert _DISCOVER_FINAL_LEAGUE_SLOTS == 1

    def test_the_half_life_sits_under_the_retention_window(self):
        from app.utils.sports_first_page_rails import (
            CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS,
        )

        # A half-life at or above the window barely reorders anything, which is
        # the mutation that makes the decay inert while every other guard passes.
        assert 0 < _DISCOVER_FINAL_EI_HALF_LIFE_HOURS < CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS
