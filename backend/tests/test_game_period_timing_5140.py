"""#5140 — quarters, halftime and overtime belong where the game put them.

    cd backend && python3 -m pytest tests/test_game_period_timing_5140.py

THREE LAYERS, and which of them can fail on master matters:

A. `TestServedMarkers` drives the REAL route, `get_event_odds_history`, with the
   session stub pattern of `tests/test_events_history_period_markers.py` over
   replay fixtures of the two production specimens. Nothing here re-implements
   marker selection. On master the NFL cases FAIL on the reported defect itself
   (a wrong served timestamp); the MLB/tennis controls PASS on both sides, which
   is their job. Red-first re-run on master `f257af838`: 18 failed / 5 passed.
B. `TestWallClockHelper` / `TestBoxScoreWriter` call the two real production
   functions the defect passes through.
C. `TestTransitionRules` specifies `observed_transition_markers`, which does not
   exist on master. There they fail by ABSENCE (AttributeError) — that is not
   evidence of the defect, only layer A and B are. They are the acceptance rules
   for the proposed helper.

Not covered, said plainly: no real overtime payload was available (the OT rows
are synthetic and ESPN's OT status text is assumed from its quarter grammar); no
NCAAF fixture; nothing here renders a chart, so none of this is screen acceptance.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import _assign_wall_clock_timestamps, get_event_odds_history
from app.utils import period_markers as pm
from tests.test_series_fold_3810 import blend_fold_row, fold_row, is_blend_fold, is_series_fold

UTC = timezone.utc
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


# ── the route harness ───────────────────────────────────────────────────────
class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self.first()

    def scalar(self):
        return self.first()

    def __iter__(self):
        return iter(self._rows)


class _ReplaySession:
    """Hands each table's rows back; the ROUTE assembles series and markers."""

    def __init__(self, event, *, espn=(), win_prob=()):
        self.event, self.espn, self.win_prob = event, list(espn), list(win_prob)

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement)
        if is_series_fold(sql):
            return _Result([fold_row(self.event)])
        if is_blend_fold(sql):
            return _Result([blend_fold_row(self.event)])
        if "FROM events" in sql:
            return _Result([self.event])
        if "FROM espn_snapshots" in sql:
            return _Result(self.espn)
        if "FROM win_prob_snapshots" in sql:
            return _Result(self.win_prob)
        return _Result([])  # odds, scores, the tier-1 scoring_plays table: empty


def _dt(iso):
    return datetime.fromisoformat(iso)


def _session(*, event_id, sport_key, commence, completed, plays, espn_rows=(), wp_rows=()):
    event = SimpleNamespace(
        id=event_id, status="completed", commence_time=commence, completed_at=completed,
        home_team_name="Home", away_team_name="Away", home_score=None, away_score=None,
        sport=SimpleNamespace(key=sport_key), sport_id=1,
        box_score_data={"scoring_plays": plays} if plays else None,
        win_probability_sources=None,
    )
    espn = [
        SimpleNamespace(
            captured_at=_dt(r["timestamp"]), home_win_probability=r.get("home_probability"),
            away_win_probability=r.get("away_probability"), home_score=r.get("home_score"),
            away_score=r.get("away_score"), game_clock=r.get("game_clock"), period=r.get("period"),
        )
        for r in espn_rows
    ]
    win_prob = [
        SimpleNamespace(
            source=source, event_id=event_id, captured_at=_dt(p["timestamp"]),
            home_win_probability=p.get("home_probability"),
            away_win_probability=p.get("away_probability"),
            draw_probability=p.get("draw_probability"), game_state=p.get("game_state"),
        )
        for source, pts in wp_rows
        for p in pts
    ]
    win_prob.sort(key=lambda s: s.captured_at)
    return _ReplaySession(event, espn=espn, win_prob=win_prob)


async def _replay(name):
    fx = json.loads((FIXTURES / name).read_text())
    session = _session(
        event_id=fx["event_id"], sport_key=fx["sport_key"],
        commence=_dt(fx["commence_time"]), completed=_dt(fx["completed_at"]),
        plays=fx["scoring_plays_raw"], espn_rows=fx["espn_history"],
        wp_rows=fx["win_prob_history"].items(),
    )
    body = await get_event_odds_history(
        event_id=fx["event_id"], hours=720, response=MagicMock(headers={}), db=session
    )
    return fx, body


def _quarter(marker):
    """'2', '2nd Quarter' and '15:00 - 2nd Quarter' are all Q2 to both clients."""
    raw = str(marker["period"]).split(" - ")[-1].strip().lower()
    for n in "1234":
        if raw == n or raw.startswith(f"{n}st") or raw.startswith(f"{n}nd") \
                or raw.startswith(f"{n}rd") or raw.startswith(f"{n}th"):
            return int(n)
    return None


def _by_quarter(body):
    out = {}
    for m in body["period_markers"]:
        q = _quarter(m)
        if q is not None and q not in out:
            out[q] = _dt(m["timestamp"])
    return out


@pytest.mark.asyncio
class TestServedMarkers:
    async def test_the_harness_reproduces_what_production_served(self):
        """Guards the replay itself: on master the route, fed the fixture, must serve
        exactly the markers production served at fetch time — otherwise a red test
        below could be the harness's fault. Skipped once the correction exists."""
        if hasattr(pm, "observed_transition_markers"):
            pytest.skip("correction present; fidelity is a statement about master")
        for name in ("nfl_14638896_history_replay.json", "nfl_14780138_history_replay.json"):
            fx, body = await _replay(name)
            assert [(m["period"], m["timestamp"], m["source"]) for m in body["period_markers"]] == \
                   [(m["period"], m["timestamp"], m["source"]) for m in fx["served_period_markers_at_fetch"]]

    async def test_chiefs_broncos_q2_is_where_the_feed_said_q2_began_not_its_only_touchdown(self):
        """14638896. Recorded on the issue 2026-09-15 and STILL served 2026-09-17T04:06Z:
        Q2 at 01:33:43Z (1:39 left in the quarter). The same payload's state stream
        reads `End of 1st Quarter` 00:53:43Z then `15:00 - 2nd Quarter` 00:54:43Z."""
        _, body = await _replay("nfl_14638896_history_replay.json")
        q = _by_quarter(body)
        assert abs(q[2] - _dt("2026-09-15T00:54:43+00:00")) < timedelta(seconds=1), (
            f"Q2 served at {q[2].isoformat()} — 39 minutes late is its first SCORE"
        )
        assert abs(q[3] - _dt("2026-09-15T01:56:23+00:00")) < timedelta(seconds=1)
        assert abs(q[4] - _dt("2026-09-15T02:36:23+00:00")) < timedelta(seconds=1)

    async def test_patriots_seahawks_no_two_periods_share_an_instant(self):
        """14780138. Q2 and Q3 both at 00:24:28.214933Z, 4m28s after kickoff."""
        _, body = await _replay("nfl_14780138_history_replay.json")
        stamps = [m["timestamp"] for m in body["period_markers"]]
        assert len(stamps) == len(set(stamps)), f"stacked markers: {body['period_markers']}"

    async def test_patriots_seahawks_quarters_sit_on_their_observed_transitions(self):
        _, body = await _replay("nfl_14780138_history_replay.json")
        q = _by_quarter(body)
        assert abs(q[2] - _dt("2026-09-10T00:57:30+00:00")) < timedelta(seconds=1), q
        assert abs(q[3] - _dt("2026-09-10T01:53:41+00:00")) < timedelta(seconds=1), q
        assert abs(q[4] - _dt("2026-09-10T02:36:55+00:00")) < timedelta(seconds=1), q

    async def test_q1_is_not_backfilled_when_nobody_saw_it_start(self):
        """14780138's first state row is `14:55 - 1st Quarter` with nothing before
        it. That is a first sighting with no bracket: Q1 stays absent. It is NOT
        placed at kickoff and NOT placed at the first row."""
        _, body = await _replay("nfl_14780138_history_replay.json")
        assert 1 not in _by_quarter(body)

    async def test_a_silent_state_stream_leaves_the_carried_play_out_of_the_markers(self):
        """The one football path the observed transitions never reach: a game whose
        state stream says nothing (no period text anywhere), so the first-score tier
        is still what gets served. Mechanism A lives on there — an unresolvable play
        carries the FIRST SNAPSHOT's timestamp, and per-period min then reports
        kickoff as the start of that period. Skipped, so Q2 is absent rather than
        wrong, and what remains is labelled `first_score` so nobody reads a residual
        marker as a period start. (This is the arm `_observed` cannot cover: added
        after a mutation showed the tier-2 skip was not otherwise reachable.)"""
        t0 = datetime(2026, 9, 14, 20, 0, tzinfo=UTC)
        espn_rows = [
            {"timestamp": (t0 + timedelta(minutes=m)).isoformat(), "home_probability": p,
             "away_probability": 1 - p, "home_score": hs, "away_score": aws, "period": None}
            # #8501: the capture at 79 is what lets the 80-minute sighting place
            # the Q3 play; a sighting 40 minutes after the last capture would not.
            for m, p, hs, aws in [(0, 0.5, 0, 0), (40, 0.4, 0, 7), (79, 0.4, 0, 7), (80, 0.6, 3, 7)]
        ]
        session = _session(
            event_id=14999001, sport_key="americanfootball_nfl", commence=t0,
            completed=t0 + timedelta(hours=3), espn_rows=espn_rows,
            plays=[
                # unresolvable: ESPN stored this side as None, so no snapshot matches
                {"period": 2, "clock": "9:11", "home_score": None, "away_score": 7},
                {"period": 3, "clock": "3:13", "home_score": 3, "away_score": 7},
            ],
        )
        body = await get_event_odds_history(event_id=14999001, hours=720,
                                            response=MagicMock(headers={}), db=session)
        assert [(m["period"], m["timestamp"]) for m in body["period_markers"]] == [
            ("3", (t0 + timedelta(minutes=80)).isoformat())
        ], body["period_markers"]
        assert body["period_markers"][0]["precision"] == "first_score"
        # the play itself is still served, in order — only the MARKER was withheld
        assert len(body["scoring_plays"]) == 2

    async def test_a_non_football_game_reaches_tier_2_and_is_byte_identical(self):
        """#6718 finding 4 — THE CONTROL THE MLB AND TENNIS ONES COULD NOT BE.

        #5140 claimed "every other sport's marker chain is byte-identical" while
        the `timestamp_resolved` skip sat in the GENERIC tier-2 block, outside
        the football condition. Neither existing control could contradict that:
        measured, the MLB fixture carries ZERO scoring plays and tennis has
        none, so neither ever reaches the changed line — a control that cannot
        execute the statement it is vouching for.

        This one does. Same shape as the football silent-stream case above —
        basketball, one unresolvable play, one resolvable — so the skip WOULD
        fire here if it were still unscoped. Both periods must survive, the
        carried timestamp included, and no `precision` key may appear: outside
        football nothing about this chain moved.
        """
        t0 = datetime(2026, 9, 14, 20, 0, tzinfo=UTC)
        espn_rows = [
            {"timestamp": (t0 + timedelta(minutes=m)).isoformat(), "home_probability": p,
             "away_probability": 1 - p, "home_score": hs, "away_score": aws, "period": None}
            for m, p, hs, aws in [(0, 0.5, 0, 0), (40, 0.4, 0, 7), (80, 0.6, 3, 7)]
        ]
        session = _session(
            event_id=14999002, sport_key="basketball_nba", commence=t0,
            completed=t0 + timedelta(hours=3), espn_rows=espn_rows,
            plays=[
                {"period": 2, "clock": "9:11", "home_score": None, "away_score": 7},
                {"period": 3, "clock": "3:13", "home_score": 3, "away_score": 7},
            ],
        )
        body = await get_event_odds_history(event_id=14999002, hours=720,
                                            response=MagicMock(headers={}), db=session)
        assert [(m["period"], m["timestamp"]) for m in body["period_markers"]] == [
            ("2", t0.isoformat()),                              # the CARRIED one, kept
            ("3", (t0 + timedelta(minutes=80)).isoformat()),
        ], body["period_markers"]
        assert all("precision" not in m for m in body["period_markers"])
        assert {m["source"] for m in body["period_markers"]} == {pm.SOURCE_ESPN_BOX}

    async def test_halftime_is_its_own_marker_and_is_not_q3(self):
        _, body = await _replay("nfl_14638896_history_replay.json")
        ht = [m for m in body["period_markers"] if str(m["period"]).lower() == "halftime"]
        assert len(ht) == 1
        assert _dt("2026-09-15T01:41:00+00:00") < _dt(ht[0]["timestamp"]) < _dt("2026-09-15T01:42:00+00:00")
        assert _by_quarter(body)[3] - _dt(ht[0]["timestamp"]) > timedelta(minutes=10)

    async def test_every_corrected_marker_states_its_precision_and_bracket(self):
        _, body = await _replay("nfl_14780138_history_replay.json")
        by_label = {m["period"]: m for m in body["period_markers"]}
        # `15:00 - 2nd Quarter`, 80s after `End of 1st Quarter`: boundary at poll resolution
        assert by_label["2nd Quarter"]["precision"] == "boundary_observed"
        # `14:53 - 3rd Quarter` is NOT a start clock, and the clock is not used to
        # back-date it. It is "observed" because espn_snapshots polled `Halftime` 61s
        # earlier: the boundary is claimed only inside that one-poll bracket.
        q3 = by_label["3rd Quarter"]
        assert q3["precision"] == "boundary_observed"
        assert q3["not_before"].startswith("2026-09-10T01:52:40")
        assert q3["timestamp"].startswith("2026-09-10T01:53:41")

    async def test_nothing_else_in_the_payload_moved(self):
        """Missing marker evidence must not delete or shift real observations."""
        fx, body = await _replay("nfl_14780138_history_replay.json")
        assert [p["timestamp"] for p in body["espn_history"]][: len(fx["espn_history"]) - 1] == \
               [p["timestamp"] for p in fx["espn_history"]][:-1]
        assert len(body["scoring_plays"]) == len(fx["scoring_plays_raw"])
        for src, pts in fx["win_prob_history"].items():
            assert [p["home_probability"] for p in body["win_prob_history"][src]] == \
                   [p["home_probability"] for p in pts]

    # ── controls: must pass BEFORE and AFTER ──
    async def test_control_mlb_innings_are_untouched(self):
        t0 = datetime(2026, 9, 16, 1, 40, tzinfo=UTC)
        rows = [
            {"timestamp": (t0 + timedelta(minutes=20 * i)).isoformat(), "home_probability": 0.5,
             "away_probability": 0.5,
             "game_state": {"inning": 1 + i // 2, "inning_half": "top" if i % 2 == 0 else "bottom",
                            "home_score": 0, "away_score": 0}}
            for i in range(6)
        ]
        session = _session(event_id=15312659, sport_key="baseball_mlb", commence=t0,
                           completed=t0 + timedelta(hours=3), plays=None, wp_rows=[("mlb", rows)])
        body = await get_event_odds_history(event_id=15312659, hours=720,
                                            response=MagicMock(headers={}), db=session)
        assert [m["period"] for m in body["period_markers"]] == \
               ["Top 1st", "Bottom 1st", "Top 2nd", "Bottom 2nd", "Top 3rd", "Bottom 3rd"]
        assert all(m["source"] == "win_prob" and "precision" not in m for m in body["period_markers"])

    async def test_control_tennis_sets_are_not_quarters(self):
        t0 = datetime(2026, 9, 13, 18, 0, tzinfo=UTC)
        rows = [
            {"timestamp": (t0 + timedelta(minutes=40 * i)).isoformat(), "home_probability": 0.6,
             "away_probability": 0.4, "game_state": {"period": f"Set {i + 1}"}}
            for i in range(3)
        ]
        session = _session(event_id=15310688, sport_key="tennis_atp_us_open", commence=t0,
                           completed=t0 + timedelta(hours=3), plays=None, wp_rows=[("espn", rows)])
        body = await get_event_odds_history(event_id=15310688, hours=720,
                                            response=MagicMock(headers={}), db=session)
        assert [m["period"] for m in body["period_markers"]] == ["Set 1", "Set 2", "Set 3"]
        assert all("precision" not in m for m in body["period_markers"])


# ── B. the production functions the defect passes through ───────────────────
class TestWallClockHelper:
    SNAPS = [
        {"timestamp": "2026-09-10T00:24:28+00:00", "home_score": 0, "away_score": 0},
        {"timestamp": "2026-09-10T01:08:34+00:00", "home_score": 0, "away_score": 7},
        # #8501: a capture a minute before the 3–10 sighting, so that sighting
        # places its play rather than bounding it from after an 80-minute gap.
        {"timestamp": "2026-09-10T02:27:38+00:00", "home_score": 0, "away_score": 7},
        {"timestamp": "2026-09-10T02:28:38+00:00", "home_score": 3, "away_score": 10},
    ]

    def test_a_carried_timestamp_is_declared_not_passed_off_as_a_sighting(self):
        """14780138's first play arrives as home_score=None. The helper cannot look
        it up and hands it the FIRST snapshot's timestamp. Ordering needs that; the
        per-period minimum must be able to tell it is not an observation."""
        plays = [
            {"period": 2, "clock": "9:11", "home_score": None, "away_score": 7},
            {"period": 3, "clock": "3:13", "home_score": 3, "away_score": 10},
        ]
        out = _assign_wall_clock_timestamps(plays, self.SNAPS)
        assert len(out) == 2, "the play itself must survive"
        assert out[0]["timestamp"] == self.SNAPS[0]["timestamp"]  # still ordered, unchanged
        assert out[0].get("timestamp_resolved") is False
        assert out[1].get("timestamp_resolved") is True
        assert out[1]["timestamp"] == self.SNAPS[3]["timestamp"]


class TestBoxScoreWriter:
    def test_a_side_on_zero_is_zero_not_missing(self):
        """Why the lookup missed at all: `int(x) if x else None` reads an integer 0
        as absent. (That ESPN sent an int, not "0", is inferred from the stored
        None — the raw ESPN summary was not re-fetched.)"""
        from app.services.espn_api import ESPNAPIService

        plays = ESPNAPIService._parse_scoring_plays(None, {"scoringPlays": [{
            "text": "TD", "type": {"text": "Passing Touchdown"}, "period": {"number": 2},
            "clock": {"displayValue": "9:11"}, "homeScore": 0, "awayScore": 7,
            "team": {"displayName": "New England Patriots"},
        }]})
        assert plays and plays[0]["home_score"] == 0 and plays[0]["away_score"] == 7


# ── C. acceptance rules for the proposed helper (absent on master) ──────────
T0 = datetime(2026, 9, 10, 0, 20, tzinfo=UTC)


def _obs(minute, period, second=0):
    return {"timestamp": (T0 + timedelta(minutes=minute, seconds=second)).isoformat(), "period": period}


def _markers(rows, sport="americanfootball_nfl"):
    return pm.observed_transition_markers(sport, rows)


def _at(markers, label):
    hit = [m for m in markers if m["period"] == label]
    return hit[0] if hit else None


GAME = [
    _obs(0, "15:00 - 1st Quarter"), _obs(1, "14:20 - 1st Quarter"), _obs(34, "0:12 - 1st Quarter"),
    _obs(35, "End of 1st Quarter"), _obs(36, "15:00 - 2nd Quarter"), _obs(37, "14:31 - 2nd Quarter"),
    _obs(78, "0:05 - 2nd Quarter"), _obs(79, "Halftime"), _obs(92, "Halftime"),
    _obs(93, "15:00 - 3rd Quarter"), _obs(94, "14:40 - 3rd Quarter"), _obs(130, "End of 3rd Quarter"),
    _obs(131, "15:00 - 4th Quarter"), _obs(132, "14:12 - 4th Quarter"), _obs(175, "0:02 - 4th Quarter"),
]


class TestTransitionRules:
    def test_completed_game_replay(self):
        """#6718: Q1 IS ABSENT, and that is the correction, not a loss.

        `GAME` opens on `15:00 - 1st Quarter` with nothing before it, which is
        also what production holds — 14638896's `espn_history` begins at that
        exact row. Nothing in the stream says the game had not already started,
        so the first cut served Q1 at our first poll wearing
        `boundary_observed` and `not_before: null`: the tightest label the
        vocabulary has, on an unbounded claim. The `15:00` clock does not
        rescue it, because a start clock persists until play begins — on this
        very payload it reads `15:00` at 00:17:12 AND at 00:18:12, so the
        kickoff is somewhere after our first sighting, not on it.

        Absent is the honest answer and it is already known to render: 14780138
        has served no Q1 since #5140 and both of its charts read correctly at
        390px. The three quarters and the break that ARE bracketed are
        unchanged.
        """
        got = [(m["period"], m["timestamp"]) for m in _markers(GAME)]
        assert got == [
            ("2nd Quarter", _obs(36, "")["timestamp"]),
            ("Halftime", _obs(79, "")["timestamp"]), ("3rd Quarter", _obs(93, "")["timestamp"]),
            ("4th Quarter", _obs(131, "")["timestamp"]),
        ]
        assert all(m["not_before"] for m in _markers(GAME)), "no marker without a bracket"

    def test_delivery_order_and_duplicates_change_nothing(self):
        shuffled = list(reversed(GAME)) + GAME[3:9] + GAME[:2]
        assert _markers(shuffled) == _markers(GAME)

    def test_unchanged_score_across_a_boundary_is_irrelevant(self):
        """Transitions are keyed on STATE. 14780138 crossed Q1→Q2 at 0-0."""
        assert _at(_markers(GAME), "2nd Quarter")["precision"] == "boundary_observed"

    def test_a_score_correction_moves_no_marker(self):
        """A touchdown taken off the board changes scores, never the period rows."""
        with_scores = [dict(o, home_score=s) for o, s in zip(GAME, [0, 0, 7, 7, 0, 0, 0, 0, 0, 0, 7, 7, 7, 7, 7])]
        assert _markers(with_scores) == _markers(GAME)

    def test_start_clock_versus_mid_period_first_sighting(self):
        """#6718: THE START CLOCK NO LONGER UPGRADES THE PRECISION.

        The bracket here is nine minutes wide either way. The first cut let a
        `15:00` reading relabel it `boundary_observed` — the label that means
        "inside POLL_TOLERANCE", i.e. 150 seconds — so a nine-minute
        uncertainty was served as a tight one. A start clock says play has not
        advanced; it does not say when the period began, and it persists across
        polls. It may corroborate a bracket and may never replace or narrow
        one, so both halves of this pair are `first_seen`.
        """
        rows = [_obs(35, "End of 1st Quarter"), _obs(44, "10:41 - 2nd Quarter")]
        m = _at(_markers(rows), "2nd Quarter")
        assert m["precision"] == "first_seen"
        assert m["not_before"] == rows[0]["timestamp"]           # the claim is an interval
        assert m["timestamp"] == rows[1]["timestamp"]            # never moved by the clock
        rows[1] = _obs(44, "15:00 - 2nd Quarter")
        widened = _at(_markers(rows), "2nd Quarter")
        assert widened["precision"] == "first_seen"
        assert widened["timestamp"] == rows[1]["timestamp"]

        # And the tight bracket is still reachable — on evidence, not on a clock.
        tight = [_obs(35, "End of 1st Quarter"), _obs(36, "10:41 - 2nd Quarter")]
        assert _at(_markers(tight), "2nd Quarter")["precision"] == "boundary_observed"

    def test_a_period_first_seen_after_a_long_silence_is_absent_not_late(self):
        rows = [_obs(10, "9:00 - 1st Quarter"), _obs(75, "1:39 - 2nd Quarter"), _obs(76, "1:02 - 2nd Quarter")]
        assert _at(_markers(rows), "2nd Quarter") is None

    def test_missing_transitions_are_not_backfilled_at_kickoff(self):
        """Capture began in the third quarter. Q1 and Q2 were never seen."""
        rows = [_obs(120, "8:30 - 3rd Quarter"), _obs(121, "8:01 - 3rd Quarter"),
                _obs(140, "End of 3rd Quarter"), _obs(141, "15:00 - 4th Quarter")]
        assert [m["period"] for m in _markers(rows)] == ["4th Quarter"]

    def test_a_one_row_blip_into_the_next_period_is_not_its_start(self):
        rows = GAME[:6] + [_obs(50, "15:00 - 3rd Quarter")] + GAME[6:]
        q3 = _at(_markers(rows), "3rd Quarter")
        assert q3["timestamp"] == _obs(93, "")["timestamp"]
        assert q3["precision"] == "first_seen"  # once blipped, never claimed as observed

    def test_a_stale_old_state_row_delivered_late_resurrects_nothing(self):
        """A lagging source delivering an old state must change NOTHING.

        Asserted as a difference rather than as a count of `1st Quarter`
        markers: under #6718 that count is 0 either way, so the old form would
        now pass for the wrong reason — it would be satisfied by a helper that
        had stopped producing markers at all.
        """
        rows = GAME + [_obs(150, "3:00 - 1st Quarter")]
        assert _markers(rows) == _markers(GAME)
        assert _markers(GAME), "otherwise this passes vacuously"

    def test_a_stale_row_may_not_tighten_a_later_bracket(self):
        """#6718. The stale row sits one minute before a genuine 4th Quarter,
        so taking it as the lower bound would read as a one-poll observation.
        It regresses below the running maximum, which is the signature of a
        late delivery, so it is refused as a bound — and the honest bracket
        back to the real 3rd Quarter row is too wide to place Q4 at all."""
        rows = [_obs(0, "End of 2nd Quarter"), _obs(1, "15:00 - 3rd Quarter"),
                _obs(45, "5:00 - 2nd Quarter"), _obs(46, "15:00 - 4th Quarter")]
        got = _markers(rows)
        assert [m["period"] for m in got] == ["3rd Quarter"]
        assert got[0]["not_before"] == rows[0]["timestamp"]

    def test_two_overtimes_are_two_markers(self):
        """#6718. `(?:\\d\\w*\\s+)?` swallowed the ordinal, so every overtime
        ranked alike and the label dedupe kept only the first. College football
        reaches a second overtime routinely."""
        rows = [_obs(0, "End of 4th Quarter"), _obs(1, "10:00 - OT"),
                _obs(2, "End of OT"), _obs(3, "2nd OT"), _obs(4, "2nd OT")]
        assert [m["period"] for m in _markers(rows)] == ["Overtime", "2nd Overtime"]

    def test_one_instant_carrying_two_states_is_disagreement_not_a_transition(self):
        """#6718. Two sources contradicting each other at one capture time gave
        `not_before == timestamp` — a zero-width bracket wearing the tightest
        precision label. That instant is evidence of disagreement; it can
        neither carry a marker nor bound one."""
        t = _obs(10, "")["timestamp"]
        rows = [{"timestamp": t, "period": "1:00 - 1st Quarter"},
                {"timestamp": t, "period": "14:00 - 2nd Quarter"}]
        assert _markers(rows) == []

    def test_a_marker_names_the_series_that_saw_it(self):
        """#6718. Every marker was stamped `win_prob` whatever saw the
        transition, so the payload could not say which instrument observed it."""
        rows = [dict(_obs(35, "End of 1st Quarter"), source="espn_history"),
                dict(_obs(36, "15:00 - 2nd Quarter"), source="espn_history")]
        assert _at(_markers(rows), "2nd Quarter")["source"] == "espn_history"
        assert _at(_markers([{k: v for k, v in r.items() if k != "source"} for r in rows]),
                   "2nd Quarter")["source"] == pm.SOURCE_WIN_PROB

    def test_overtime_follows_regulation(self):
        """SYNTHETIC: no real OT payload was available; status text is assumed."""
        rows = GAME + [_obs(176, "End of 4th Quarter"), _obs(179, "10:00 - OT"), _obs(180, "9:21 - OT")]
        m = _markers(rows)
        assert [x["period"] for x in m][-2:] == ["4th Quarter", "Overtime"]
        assert _at(m, "Overtime")["timestamp"] == _obs(179, "")["timestamp"]

    def test_other_sports_get_nothing_from_this_helper(self):
        assert _markers(GAME, sport="basketball_nba") == []
        assert _markers([_obs(0, "Top 1st"), _obs(9, "Bottom 1st")], sport="baseball_mlb") == []
        assert _markers([_obs(0, "Set 1"), _obs(40, "Set 2")]) == []   # football key, foreign text
        assert _markers([_obs(0, "Final"), _obs(1, "Wed, September 9th at 8:20 PM EDT")]) == []
