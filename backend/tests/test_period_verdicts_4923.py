"""#4923 — a question about PART of a game is never answered with the whole game's score.

Two fallback resolvers in `backfill_winners` grade from `events.home_score` /
`events.away_score` when Kalshi has purged its settlement data. Both let a
period-bounded market through and answered it with the full-time number:

* `_resolve_kalshi_from_scores` — the BTTS branch tests `"btts" in ticker` and
  `continue`s ~40 lines ABOVE the `_non_ml` guard that already knows about
  halves, so `KXMLS1HBTTS-…` was graded "did both teams score in the MATCH".
  Production, `/futures/60489789`: **"Yes ✅ WON — markets gave this just 1%"**
  over a first half that finished 1–0.
* `_resolve_kalshi_spread_total_from_scores` — `is_1h = "1h" in ticker_lower`.
  A test that knows one period treats every other period as the whole game, so
  `KXMLS2HTOTAL-…` served **"Over 1.5 2H goals scored — Won · 100% Settled"**
  on a second half with one goal.

Both statements are false and both are provable off Kalshi's OWN grades of the
sibling markets on the same event (15298466, final 1–1): `1st Half Correct
Score → Chicago Fire wins 1H 1-0` (`api_settlement`) and `First Half Total →
Over 1.5 1H goals` **LOST** (`clean_resolution`) pin the first half at 1–0,
which leaves the second half 0–1.

`game_score` is not in `OVERWRITABLE_WINNER_SOURCES_SQL` and the candidate scan
drops any market already holding one, so each wrong verdict is PERMANENT. That
is why the fix refuses rather than guesses: an ungraded row is a state every
surface already renders honestly, and it stays in the scan for the venue.

Guard discipline: nothing here asserts via `inspect.getsource` except the one
case where the thing under test IS a hand-written summary key list. Every other
guard drives the real resolver and reads the statements it actually executed.
"""

from unittest.mock import MagicMock

import pytest

# ONE import form for one module: `monkeypatch.setattr` needs the module
# object anyway, so binding the three helpers again by name would be a second
# spelling of the same dependency (CodeQL `py/import-and-import-from`).
import app.tasks.backfill_winners as bw


# ==========================================================================
# 1. the classifier, driven with REAL production series
# ==========================================================================

#: Every one of these is a live Kalshi series carried by an event-linked market
#: on production, read 2026-09-10 (899 distinct series). A period market whose
#: token this misses is a wrong verdict, so the list is deliberately wide.
PERIOD_SERIES = [
    # halves — four spellings of the same thing across five sports
    ("KXMLS1HBTTS", "1h"),
    ("KXMLS2HBTTS", "2h"),
    ("KXWC1HBTTS", "1h"),
    ("KXUSL1HBTTS", "1h"),
    ("KXNBA1HWINNER", "1h"),
    ("KXNBA2HWINNER", "2h"),
    ("KXNBA2HTOTAL", "2h"),
    ("KXNBA2HSPREAD", "2h"),
    ("KXNCAAMB1HWINNER", "1h"),
    ("KXNCAAF2HSPREAD", "2h"),
    ("KXWC2HTOTAL", "2h"),
    ("KXEPL1H", "1h"),
    ("KXBUNDESLIGA2H", "2h"),
    ("KXNFL1HTEAMTOTAL", "1h"),
    ("KXNCAAF1HFT", "1h"),
    # LIGUE 1's own digit sits immediately before the period's — "KXLIGUE11H"
    # is Ligue 1, first half.
    ("KXLIGUE11H", "1h"),
    # quarters — the family `_non_ml` never learned
    ("KXNBA1QWINNER", "1q"),
    ("KXNFL1QBTTS", "1q"),
    ("KXNFL2QBTTS", "2q"),
    ("KXNFL2QSPREAD", "2q"),
    ("KXNCAAF4QTOTAL", "4q"),
    ("KXWNBA3QSPREAD", "3q"),
    # MLB innings windows
    ("KXMLBF5", "f5"),
    ("KXMLBF5SPREAD", "f5spread"),
    ("KXMLBF5TOTAL", "f5total"),
    ("KXMLBF3", "f3"),
    ("KXMLBF7", "f7"),
    ("KXMLBRFI", "rfi"),
]

#: Whole-game families that must keep being graded. A false positive here does
#: not print a wrong verdict — it silently DELETES a correct one, which is the
#: harder bug to ever notice, so this list is the one that earns the regex its
#: lookbehind and its end anchors.
WHOLE_GAME_SERIES = [
    # THE CARVE-OUT: head-to-head, about the whole game, and it contains "2H".
    "KXEPLH2H",
    "KXEPLH2HFINISH",
    # the full-game sibling of the market that started this
    "KXMLSBTTS",
    "KXWCBTTS",
    "KXEPLBTTS",
    # plain game/spread/total families
    "KXMLBGAME",
    "KXMLBTOTAL",
    "KXMLBSPREAD",
    "KXMLBTEAMTOTAL",
    "KXNBASPREAD",
    "KXNBATOTAL",
    "KXNHLGAME",
    "KXMLSTOTAL",
    # a digit immediately before SPREAD, and it is the LEAGUE's digit
    "KXLIGUE1SPREAD",
    "KXLALIGA2GAME",
    "KXBUNDESLIGA2GAME",
    # player props whose stat name starts with a digit
    "KXNBA3PT",
    "KXNCAAF2PT",
    "KXNBA2D",
    "KXNBA3D",
    # out of scope by design: neither can reach either caller
    "KXATPSETWINNER",
    "KXCS2MAP",
    "KXUFCVICROUND",
]


@pytest.mark.parametrize("series,expected", PERIOD_SERIES)
def test_a_period_series_names_its_period(series, expected):
    assert bw._ticker_period(f"{series}-26SEP09CHIMIA") == expected


@pytest.mark.parametrize("series", WHOLE_GAME_SERIES)
def test_a_whole_game_series_names_no_period(series):
    assert bw._ticker_period(f"{series}-26SEP09CHIMIA") is None


def test_the_period_is_read_off_the_series_not_the_date():
    """282 event-linked markets carry an accidental "1h" in the SUFFIX.

    `KXWTAMATCH-26JUL11HODCHA` is Hodzic vs Chan on the 11th. The old
    `"1h" in ticker_lower` read the whole ticker and called all 282 of them
    first-half markets — the false-positive direction, silently costing
    verdicts rather than inventing them.
    """
    assert bw._ticker_period("KXWTAMATCH-26JUL11HODCHA") is None
    assert bw._ticker_period("KXWTASETWINNER-26JUL11HODCHA-2") is None
    assert bw._ticker_period("KXATPCHALLENGERMATCH-26MAY31HIBVAL") is None
    # …while the same date suffix under a real 1H series still reads 1H.
    assert bw._ticker_period("KXMLS1HBTTS-26SEP09CHIMIA") == "1h"


def test_a_missing_ticker_is_not_a_period():
    assert bw._ticker_period(None) is None
    assert bw._ticker_period("") is None


# ==========================================================================
# 2. the two resolvers, driven for real
# ==========================================================================

class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


def _row(**kw):
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class _RecordingSession:
    """Records (sql, params) for every execute and replays canned results."""

    def __init__(self, responder):
        self._responder = responder
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.statements.append((sql, params))
        out = self._responder(sql, params)
        return out if out is not None else MagicMock(rowcount=0)

    async def commit(self):
        return None

    async def rollback(self):
        return None

    def verdict_writes(self):
        """Every statement that would stamp an `is_winner` on a row."""
        return [
            (sql, params)
            for sql, params in self.statements
            if "UPDATE futures_outcomes" in sql and "is_winner" in sql
        ]


def _install(monkeypatch, session):
    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())
    return session


_CANDIDATE_MARKER = "HAVING SUM(CASE WHEN fo.is_winner"
_PREFETCH_MARKER = "WHERE market_id = ANY(:ids)"

#: Chicago Fire vs Inter Miami CF, 2026-09-09, MLS. Final 1–1; first half 1–0.
#: Both numbers are Kalshi's own, off the sibling markets on event 15298466.
FINAL_HOME, FINAL_AWAY = 1, 1


def _candidate(market_id, ticker, *, n_outcomes=1, event_id=15298466):
    return _row(
        market_id=market_id,
        market_name="Chicago Fire vs Miami: %s" % ticker,
        ticker=ticker,
        event_id=event_id,
        home_team_name="Chicago Fire",
        away_team_name="Inter Miami CF",
        home_score=FINAL_HOME,
        away_score=FINAL_AWAY,
        n_outcomes=n_outcomes,
    )


def _outcome(market_id, oid, name):
    return _row(market_id=market_id, id=oid, name=name)


class TestBttsBranch:
    """A half's BTTS is not the match's BTTS, however the match finished."""

    async def _run(self, monkeypatch, candidates, outcomes):
        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result(candidates)
            if _PREFETCH_MARKER in sql:
                return _Result(outcomes)
            return None

        session = _install(monkeypatch, _RecordingSession(responder))
        return session, await bw._resolve_kalshi_from_scores()

    async def test_a_first_half_btts_is_refused_not_graded(self, monkeypatch):
        # Both teams scored in the MATCH (1–1) — the exact input that made the
        # old branch write `is_winner = True` on a half that finished 1–0.
        session, stats = await self._run(
            monkeypatch,
            [_candidate(60489789, "KXMLS1HBTTS-26SEP09CHIMIA")],
            [_outcome(60489789, 226056790, "Yes")],
        )
        assert session.verdict_writes() == []
        assert stats["refused_period"] == 1
        assert stats["btts"] == 0

    async def test_a_second_half_btts_is_refused_too(self, monkeypatch):
        session, stats = await self._run(
            monkeypatch,
            [_candidate(60489777, "KXMLS2HBTTS-26SEP09CHIMIA")],
            [_outcome(60489777, 226056777, "Yes")],
        )
        assert session.verdict_writes() == []
        assert stats["refused_period"] == 1

    async def test_the_match_btts_is_still_graded(self, monkeypatch):
        """The control. The guard must not switch the resolver off."""
        session, stats = await self._run(
            monkeypatch,
            [_candidate(60489765, "KXMLSBTTS-26SEP09CHIMIA")],
            [_outcome(60489765, 226056765, "Yes")],
        )
        writes = session.verdict_writes()
        assert len(writes) == 1
        assert writes[0][1] == {"won": True, "mid": 60489765}
        assert stats["btts"] == 1
        assert stats["refused_period"] == 0

    async def test_a_quarter_winner_never_takes_the_moneyline_path(self, monkeypatch):
        """`_non_ml` names `1hwinner`/`2hwinner` and has never named a quarter.

        A 2-outcome quarter-winner market therefore reached the moneyline
        branch and was decided by the FINAL margin.
        """
        session, stats = await self._run(
            monkeypatch,
            [_candidate(70000001, "KXNBA1QWINNER-26SEP09BOSLAL", n_outcomes=2)],
            [
                _outcome(70000001, 1, "Chicago Fire"),
                _outcome(70000001, 2, "Inter Miami CF"),
            ],
        )
        assert session.verdict_writes() == []
        assert stats["refused_period"] == 1
        assert stats["moneyline"] == 0


class TestSpreadTotalResolver:
    """`is_1h` knew one period, so every other period was "the whole game"."""

    async def _run(self, monkeypatch, candidates, outcomes):
        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result(candidates)
            if _PREFETCH_MARKER in sql:
                return _Result(outcomes)
            return None

        session = _install(monkeypatch, _RecordingSession(responder))
        return session, await bw._resolve_kalshi_spread_total_from_scores()

    #: The three rungs production served. The match total is 2, so the old code
    #: graded the 0.5 and 1.5 rungs WON; the second half had one goal.
    SECOND_HALF_RUNGS = [
        "Over 0.5 2H goals scored",
        "Over 1.5 2H goals scored",
        "Over 2.5 2H goals scored",
    ]

    async def test_a_second_half_total_is_graded_on_the_second_half(self, monkeypatch):
        """#5052 turned this refusal into a verdict — on the RIGHT score.

        Refusing was #4923's first move ("a wrong verdict is replaced by no
        verdict first"), never its destination. What must never come back is
        the FULL-TIME answer, and this specimen is chosen so the two disagree:
        the match ended 1–1 (two goals), Kalshi's own sibling markets pin the
        first half at 1–0, so the second half had exactly ONE goal.

        The middle rung is the entire point. `Over 1.5` is WON on the match and
        LOST on the half, so a mutant that reaches for `row.home_score` /
        `row.away_score` here cannot pass — which is the property the old
        refusal-only assertion could not test, because a refusal looks the same
        whatever score you would have refused to use.
        """
        async def _halftime(session, event_id):
            return (1, 0)

        monkeypatch.setattr(bw, "_get_halftime_score", _halftime)
        session, stats = await self._run(
            monkeypatch,
            [_candidate(60489769, "KXMLS2HTOTAL-26SEP09CHIMIA", n_outcomes=3)],
            [
                _outcome(60489769, 226056760 + i, name)
                for i, name in enumerate(self.SECOND_HALF_RUNGS)
            ],
        )
        assert [w[1] for w in session.verdict_writes()] == [
            {"won": True, "oid": 226056760},   # 1 second-half goal > 0.5
            # the discriminator: the MATCH total (2) is over 1.5, the half is not
            {"won": False, "oid": 226056761},
            {"won": False, "oid": 226056762},  # 1 < 2.5
        ]
        assert stats["h2_total"] == 3
        assert stats["total"] == 0
        assert stats["refused_period"] == 0

    async def test_a_second_half_spread_is_graded_on_the_second_half_margin(
        self, monkeypatch
    ):
        """CERT-2603: the reconstructor finally has a parser to grade with.

        #5052 rebuilt the second-half score and left `_SPREAD_RE` unable to
        read a single one of production's 4,410 2H spread legs, so the ship
        moved 0 of them off blank. The widened pattern reads all three shapes
        that exist; this drives the resolver end to end on the hardest one.

        THE FIXTURE IS BUILT SO THE MATCH AND THE HALF DISAGREE ON EVERY LEG.
        Final 4–1 to the home side; halftime 4–0; so the second half is 0–1 and
        the AWAY side wins it. A grader that reached for `row.home_score` /
        `row.away_score` — #4923 — would invert every verdict below, and a
        grader that answered "who won the half" instead of "by how much" would
        get leg 3 wrong. Each leg is asserted individually because #939's defect
        was deriving one leg's answer and flipping the siblings.
        """
        async def _halftime(session, event_id):
            return (4, 0)

        monkeypatch.setattr(bw, "_get_halftime_score", _halftime)
        decided = _row(
            market_id=70000002,
            market_name="Chicago Fire vs Miami: 2H Spread",
            ticker="KXMLS2HSPREAD-26SEP09CHIMIA",
            event_id=15298466,
            home_team_name="Chicago Fire",
            away_team_name="Inter Miami CF",
            home_score=4,
            away_score=1,
            n_outcomes=4,
        )
        session, stats = await self._run(
            monkeypatch,
            [decided],
            [
                # home is +3 on the MATCH and −1 on the HALF
                _outcome(70000002, 31, "Chicago Fire wins the 2H by more than 0.5 goals"),
                # away is −3 on the match and +1 on the half
                _outcome(70000002, 32, "Inter Miami CF wins the 2H by more than 0.5 goals"),
                # ...but only by ONE, so the next rung up is lost: this is the
                # leg that separates a margin grader from a winner grader.
                _outcome(70000002, 33, "Inter Miami CF wins the 2H by more than 1.5 goals"),
                # the second production shape, no "the", on the same market
                _outcome(70000002, 34, "Chicago Fire wins 2H by over 0.5 goals"),
            ],
        )
        assert [w[1] for w in session.verdict_writes()] == [
            {"won": False, "oid": 31},
            {"won": True, "oid": 32},
            {"won": False, "oid": 33},
            {"won": False, "oid": 34},
        ]
        assert stats["h2_spread"] == 4
        # not the full-game counter, not the total one, and nothing refused
        assert stats["spread"] == 0
        assert stats["total"] == 0
        assert stats["no_parse"] == 0
        assert stats["refused_period"] == 0

    async def test_a_second_half_spread_leg_is_never_read_as_a_team_total(
        self, monkeypatch
    ):
        """CERT-2603: the second door into the same fabrication, measured shut.

        The team-total grader runs BEFORE the spread branch and refused margin
        legs only via `_SPREAD_RE` — as wide as the grader, not as wide as the
        hazard. So the 3,819 "wins 2H by over N points" legs, unreadable by the
        old pattern, walked into `_TEAM_TOTAL_RE`, whose `(.+?)` swallowed the
        margin clause into the TEAM name: "Chicago Bears wins the 2H by over
        9.5 points" parsed as a team called "Chicago Bears wins the 2H by" with
        a 9.5 line, and returned True on this very half (Bears scored 10).

        The half here is 10–3, so the Bears' 2H SCORE (10) and their 2H MARGIN
        (7) sit on opposite sides of the 9.5 line. Leg 2 is therefore True read
        as a team total and False read as the spread it is — and `game_score`
        is not overwritable, so the wrong one would have been permanent.
        """
        async def _halftime(session, event_id):
            return (20, 17)

        monkeypatch.setattr(bw, "_get_halftime_score", _halftime)
        nfl = _row(
            market_id=70000005,
            market_name="Bears vs Packers: 2H Spread",
            ticker="KXNFL2HSPREAD-26SEP09GBCHI",
            event_id=15298470,
            home_team_name="Chicago Bears",
            away_team_name="Green Bay Packers",
            home_score=30,
            away_score=20,
            n_outcomes=3,
        )
        session, stats = await self._run(
            monkeypatch,
            [nfl],
            [
                _outcome(70000005, 61, "Chicago Bears wins 2H by over 6.5 points"),
                _outcome(70000005, 62, "Chicago Bears wins the 2H by over 9.5 points"),
                _outcome(70000005, 63, "Green Bay Packers wins 2H by over 0.5 points"),
            ],
        )
        assert [w[1] for w in session.verdict_writes()] == [
            {"won": True, "oid": 61},    # 2H margin +7 > 6.5
            {"won": False, "oid": 62},   # +7 < 9.5 — the team-total read says True
            {"won": False, "oid": 63},   # away is −7 on the half
        ]
        assert stats["h2_spread"] == 3
        # the counter that proves WHICH branch answered: the team-total path
        # increments `total`, the spread path does not.
        assert stats["total"] == 0

    async def test_a_full_game_more_than_leg_is_graded_on_the_final_margin(
        self, monkeypatch
    ):
        """The same widening, off the full-time score — #4236's grading half.

        25,347 whole-game "wins by more than N goals" legs on 5,601 markets
        carry no `game_score` verdict at all today because the pattern could not
        read the phrasing (measured 2026-09-11). They are the same question as
        "by over N", and this asserts they are answered the same way: graded
        against Kalshi's own `api_settlement` verdicts on the 304 such legs that
        carry one, this grader agrees on 302.

        LEG 2 IS WHY THIS IS NOT A WINNER TEST. 3–1 is a two-goal margin, so
        "by more than 2.5" is LOST by the side that won the match — the answer a
        winner fallback cannot produce.
        """
        decided = _row(
            market_id=70000004,
            market_name="Chicago Fire vs Miami: Spread",
            ticker="KXMLSSPREAD-26SEP09CHIMIA",
            event_id=15298466,
            home_team_name="Chicago Fire",
            away_team_name="Inter Miami CF",
            home_score=3,
            away_score=1,
            n_outcomes=3,
        )
        session, stats = await self._run(
            monkeypatch,
            [decided],
            [
                _outcome(70000004, 51, "Chicago Fire wins by more than 1.5 goals"),
                _outcome(70000004, 52, "Chicago Fire wins by more than 2.5 goals"),
                _outcome(70000004, 53, "Inter Miami CF wins by more than 1.5 goals"),
            ],
        )
        assert [w[1] for w in session.verdict_writes()] == [
            {"won": True, "oid": 51},
            {"won": False, "oid": 52},
            {"won": False, "oid": 53},
        ]
        assert stats["spread"] == 3
        assert stats["no_parse"] == 0

    async def test_a_margin_claim_the_parser_cannot_read_is_still_blank(
        self, monkeypatch
    ):
        """The fail-closed control, and it must outlive every widening.

        `_MARGIN_CLAIM_RE` is deliberately wider than `_SPREAD_RE`: the guard
        asks "is this a margin question", the grader asks "can I read it". A
        phrasing outside the grader's vocabulary — a spelled-out period, a unit
        we have never seen — must stay blank rather than be answered by the
        winner fallback, which grades a different question.

        THE HALF HERE IS DECIDED (0–1), NOT DRAWN, and that is load-bearing. On
        a drawn segment the fallback declines on its own `h_score != a_score`
        test, so the guard is never consulted and this passes whether or not it
        exists — that vacuity read as green against a mutant that deleted the
        guard once already. With a decided half an unguarded fallback writes
        True for Miami, so the assertion on absent writes can actually fail.
        """
        async def _halftime(session, event_id):
            return (3, 0)

        monkeypatch.setattr(bw, "_get_halftime_score", _halftime)
        decided = _row(
            market_id=70000006,
            market_name="Chicago Fire vs Miami: 2H Spread",
            ticker="KXMLS2HSPREAD-26SEP09CHIMIA",
            event_id=15298466,
            home_team_name="Chicago Fire",
            away_team_name="Inter Miami CF",
            home_score=3,
            away_score=1,
            n_outcomes=2,
        )
        session, stats = await self._run(
            monkeypatch,
            [decided],
            [
                _outcome(70000006, 71,
                         "Chicago Fire wins the second half by more than 1.5 goals"),
                _outcome(70000006, 72,
                         "Inter Miami CF wins the second half by more than 1.5 goals"),
            ],
        )
        assert session.verdict_writes() == []
        assert stats["h2_spread"] == 0
        assert stats["spread"] == 0
        assert stats["total"] == 0
        assert stats["no_parse"] == 1

    async def test_a_second_half_with_no_halftime_score_is_still_refused(
        self, monkeypatch
    ):
        """The fail-closed half of #5052: no reconstruction, no verdict.

        `_get_halftime_score` returning `None` must land on `no_plays` and write
        nothing — never on the full-time score. This is the same guarantee 1H
        already had, and it is why adding 2H cannot invent a verdict: the
        failure mode is "still blank", which is what the reader already sees.
        """
        async def _no_halftime(session, event_id):
            return None

        monkeypatch.setattr(bw, "_get_halftime_score", _no_halftime)
        session, stats = await self._run(
            monkeypatch,
            [_candidate(60489769, "KXMLS2HTOTAL-26SEP09CHIMIA", n_outcomes=3)],
            [
                _outcome(60489769, 226056760 + i, name)
                for i, name in enumerate(self.SECOND_HALF_RUNGS)
            ],
        )
        assert session.verdict_writes() == []
        assert stats["no_plays"] == 1
        assert stats["h2_total"] == 0
        assert stats["refused_period"] == 0

    async def test_a_quarter_is_still_refused(self, monkeypatch):
        """#5052 widened the gate by exactly one token, and no more.

        Quarters and the MLB first-N windows have no reconstructor, so they
        must keep landing on `refused_period`. If this ever starts grading, it
        is grading against the full-game score — #4923 verbatim.
        """
        session, stats = await self._run(
            monkeypatch,
            [_candidate(70000003, "KXNCAAF4QTOTAL-26SEP09CHIMIA", n_outcomes=2)],
            [
                _outcome(70000003, 41, "Over 0.5 4Q goals scored"),
                _outcome(70000003, 42, "Over 1.5 4Q goals scored"),
            ],
        )
        assert session.verdict_writes() == []
        assert stats["refused_period"] == 1
        assert stats["total"] == 0

    async def test_the_full_game_total_is_still_graded(self, monkeypatch):
        """The control, and the one that proves the refusal is not a mute button.

        Same event, same arithmetic, a question the final score CAN answer.
        """
        session, stats = await self._run(
            monkeypatch,
            [_candidate(60489760, "KXMLSTOTAL-26SEP09CHIMIA", n_outcomes=2)],
            [
                _outcome(60489760, 11, "Over 1.5 goals scored"),
                _outcome(60489760, 12, "Over 2.5 goals scored"),
            ],
        )
        writes = session.verdict_writes()
        assert [w[1] for w in writes] == [
            {"won": True, "oid": 11},    # 2 goals > 1.5
            {"won": False, "oid": 12},   # 2 goals < 2.5
        ]
        assert stats["total"] == 2
        assert stats["refused_period"] == 0

    async def test_a_first_half_still_reaches_the_halftime_reconstruction(self, monkeypatch):
        """1H is the one period this function HAS a score for — it keeps it.

        With no halftime score available the existing refusal (`no_plays`)
        fires, and it must be THAT counter, not the new one: the two mean
        different things ("we have no reconstruction" vs "we will never have
        one") and collapsing them would hide the day 1H stops reconstructing.
        """
        async def _no_halftime(session, event_id):
            return None

        monkeypatch.setattr(bw, "_get_halftime_score", _no_halftime)
        session, stats = await self._run(
            monkeypatch,
            [_candidate(60489780, "KXMLS1HTOTAL-26SEP09CHIMIA", n_outcomes=2)],
            [
                _outcome(60489780, 21, "Over 0.5 1H goals scored"),
                _outcome(60489780, 22, "Over 1.5 1H goals scored"),
            ],
        )
        assert session.verdict_writes() == []
        assert stats["no_plays"] == 1
        assert stats["refused_period"] == 0


# ==========================================================================
# 3. the refusal is visible to an operator
# ==========================================================================

def test_the_refusal_reaches_the_phase_summary():
    """A refusal nobody can count is a refusal nobody finds (CERT-499).

    This is the one source-read in the file, and it is legitimate because the
    thing under test IS a hand-written key list: `stats["score"]` is the only
    place either counter reaches the task's own summary, and the class this
    ship removes was invisible for months precisely because a wrong grade
    looks exactly like a grade.
    """
    import inspect

    src = inspect.getsource(bw._resolve_winners_only)
    assert '"refused_period"' in src
    assert 'score_stats.get("refused_period", 0)' in src
    assert 'spread_total_stats.get("refused_period", 0)' in src
