"""#6619 — a settled "Halftime Result" stops naming a winner from the FULL-TIME score.

THE DEFECT. `backfill_winners` asks "is this a period market?" with
`_ticker_period`, which reads the KALSHI TICKER SERIES::

    series = (ticker or "").split("-", 1)[0].lower()
    _PERIOD_SERIES_RE.search(series)

Polymarket's `external_id` is a bare integer — market 60040627 carries
`'977353'` — so there is no series and no period token to find. The classifier
answers `None`, which every caller reads as WHOLE GAME, and the segment marker
that does exist is in a field nobody consulted: `futures_markets.name`,
"Deportivo Alavés vs. Valencia CF - Halftime Result".

So production served, at `/futures/60040627` (LOOK banked 2026-09-16 20:58Z):

    Valencia CF  WON          "Markets gave this just 0%."
    Settled — Valencia CF won.
    Valencia CF · Won · 100% Settled   (opened 21%)
    Draw        · Lost                 (opened 45%)   <-- the priced favourite
    Deportivo Alavés · Lost            (opened 32%)

The match finished **0–1**. That is the full-time score. The event holds ZERO
`scoring_plays` rows and no `box_score_data` period linescore, so nothing in our
data says who led at half time — and `Draw`, the outcome the market itself
priced most likely, is graded `Lost` on evidence we do not hold.

Measured 2026-09-16 on production: **203** Polymarket half markets already carry
a `game_score` verdict, 203 legs crowned. `game_score` is not in
`OVERWRITABLE_WINNER_SOURCES_SQL` and the candidate scan drops any market
already holding one, so every one of them is PERMANENT.

THE REFUSAL ALREADY EXISTED AND WAS UNREACHABLE. `_period_scores` documents that
a half it cannot rebuild returns `None` and "the caller must refuse — never fall
back to the full-game score, which is the #4923 defect". `_get_halftime_score`
would have returned `None` for every specimen above. Neither ran, because the
question "which period?" was answered `None` one step earlier.

#4923 is this class and is CLOSED; its fix taught the ticker classifier. This is
its second arm — the venue with no ticker to teach. `_market_period` consults the
ticker FIRST, so every Kalshi row that already classified is untouched, and the
only behaviour that changes belongs to rows being graded against a score that
cannot answer their question.

Guard discipline follows #4923's and #6590's: the resolver guards drive the real
loop and read the statements it actually executed, and every refusal arm carries
the positive control that would fail if the guard merely switched the resolver
off. The sharpest of those controls makes the full-time score and the halftime
score DISAGREE, so a test that passed by grading from the wrong one cannot pass.
"""

import pytest

import app.tasks.backfill_winners as bw

# One harness, not two. #6590 built the rig that drives these same two resolvers
# and reads the statements they executed; a second copy of it here is a second
# reading of the same question, which is the failure `_market_period` exists to
# end. If that module is ever retired this import fails loudly, which is the
# correct outcome — these guards protect the same two loops.
from tests.test_a_draw_leg_is_never_graded_as_a_team_6590 import (  # noqa: E402
    _CANDIDATE_MARKER,
    _PREFETCH_MARKER,
    _RecordingSession,
    _Result,
    _install,
    _outcome,
    _row,
    _verdict_by_outcome,
)

# ==========================================================================
# 1. the classifier
# ==========================================================================

#: Read from `futures_markets.name` on production, 2026-09-16. The first is the
#: photographed specimen.
HALFTIME_NAMES = [
    "Deportivo Alavés vs. Valencia CF - Halftime Result",
    "Hitchin Town FC vs. Biggleswade Town FC - Halftime Result",
    "Norrby IF vs. Varbergs BoIS - Halftime Result",
    "Team A vs. Team B - 1st Half Result",
    "Team A vs. Team B - First Half Winner",
    "Team A vs. Team B - Half-time Result",
]

SECOND_HALF_NAMES = [
    "Boldmere St Michaels FC vs. Bourne Town FC - Second Half Result",
    "AE Kifisia FC vs. APO Levadiakos FC - Second Half Result",
    "Team A vs. Team B - 2nd Half Result",
]

#: Every non-segment use of the word "half" in `futures_markets.name`, measured
#: 2026-09-16: 19 markets, and this is all of them. A bare `half` token would
#: have swept in every one.
NOT_A_SEGMENT = [
    "Freestyle Skiing Men's Freeski Halfpipe: Gold Medal Winner",
    "Announcers at Olympics Women's Freeski Halfpipe: Qualifying",
    "Winter Games 2026: Ski Halfpipe - Men's",
    "New Half-Life game by December 31?",
    "Will Half-Life 3 be announced before 2027?",
    "Top Half: World Cup Semifinal Matchup",
    "Bottom Half: World Cup Semifinal Matchup",
    "EPL Top Half Finishers",
    "Will SCOTUS allow First Step Act halfway-house claims under §2241?",
    "SK Beveren vs. Oud-Heverlee Leuven",
    "CA Rosario Central vs. Gimnasia y Esgrima de La Plata",
]


@pytest.mark.parametrize("name", HALFTIME_NAMES)
def test_a_first_half_name_is_classified_1h(name):
    assert bw._name_period(name) == "1h"


@pytest.mark.parametrize("name", SECOND_HALF_NAMES)
def test_a_second_half_name_is_classified_2h(name):
    assert bw._name_period(name) == "2h"


@pytest.mark.parametrize("name", NOT_A_SEGMENT)
def test_a_name_that_merely_contains_half_is_not_a_segment(name):
    assert bw._name_period(name) is None


def test_a_missing_name_is_not_a_segment():
    assert bw._name_period(None) is None
    assert bw._name_period("") is None


# ==========================================================================
# 2. the defect's precondition, stated as itself
# ==========================================================================

#: Deportivo Alavés vs. Valencia CF, La Liga, settled 2026-09-15. Final 0–1.
#: `external_id` is Polymarket's numeric id — the reason the ticker classifier
#: has nothing to read.
MARKET_ID = 60040627
EVENT_ID = 15305823
POLY_TICKER = "977353"
SPECIMEN_NAME = "Deportivo Alavés vs. Valencia CF - Halftime Result"
HOME, AWAY = "Deportivo Alavés", "Valencia CF"
FT_HOME, FT_AWAY = 0, 1

OID_HOME, OID_AWAY, OID_DRAW = 9001, 9002, 9003


def test_the_ticker_classifier_really_is_blind_to_this_market():
    """The strawman. If this ever starts answering, the fix is moot — say so."""
    assert bw._ticker_period(POLY_TICKER) is None
    assert bw._name_period(SPECIMEN_NAME) == "1h"


def test_the_ticker_wins_when_both_fields_speak():
    """A no-op for every Kalshi row that already classified."""
    assert bw._market_period("KXNBA1HWINNER-26SEP16", "Some Second Half Result") == "1h"
    assert bw._market_period("KXNBA2QWINNER-26SEP16", "Halftime Result") == "2q"


def test_the_name_answers_when_the_ticker_cannot():
    assert bw._market_period(POLY_TICKER, SPECIMEN_NAME) == "1h"
    assert bw._market_period(POLY_TICKER, "Second Half Result") == "2h"


def test_a_whole_game_market_is_still_a_whole_game_market():
    """The control: `_market_period` must not classify everything."""
    assert bw._market_period(POLY_TICKER, "SK Beveren vs. Oud-Heverlee Leuven") is None
    assert bw._market_period("KXMLSGAME-26SEP09CHIMIA", "Chicago vs. Miami") is None


# ==========================================================================
# 3. the resolvers, driven for real
# ==========================================================================


def _candidate(ticker, name, **over):
    kw = dict(
        market_id=MARKET_ID,
        market_name=name,
        ticker=ticker,
        event_id=EVENT_ID,
        home_team_name=HOME,
        away_team_name=AWAY,
        home_score=FT_HOME,
        away_score=FT_AWAY,
        n_outcomes=2,
    )
    kw.update(over)
    return _row(**kw)


async def _run(monkeypatch, resolver, candidates, outcomes, halftime=None):
    """Drive one real resolver; `halftime` = what `_get_halftime_score` returns."""

    def responder(sql, params):
        if _CANDIDATE_MARKER in sql:
            return _Result(candidates)
        if _PREFETCH_MARKER in sql:
            return _Result(outcomes)
        return None

    session = _install(monkeypatch, _RecordingSession(responder))

    async def _fake_halftime(_session, _event_id):
        return halftime

    monkeypatch.setattr(bw, "_get_halftime_score", _fake_halftime)
    stats = await getattr(bw, resolver)()
    return session, stats


#: `_resolve_kalshi_from_scores` additionally gates on `_score_gradeable_family`,
#: which refuses Polymarket's numeric id outright — so the 203 production rows
#: reached the hole through the OTHER loop. The blind spot is in the shared
#: classifier, so both are guarded, and the moneyline arm is driven with a real
#: Kalshi family that the family allowlist admits.
KALSHI_TICKER = "KXMLSGAME-26SEP09CHIMIA"


class TestTheTeamNameFallback:
    """`_resolve_kalshi_spread_total_from_scores` — the loop the 203 came through."""

    RESOLVER = "_resolve_kalshi_spread_total_from_scores"

    async def test_the_specimen_is_refused_when_no_halftime_score_exists(
        self, monkeypatch
    ):
        """The photographed market: no verdict at all, rather than a wrong one."""
        session, _stats = await _run(
            monkeypatch,
            self.RESOLVER,
            [_candidate(POLY_TICKER, SPECIMEN_NAME)],
            [_outcome(OID_AWAY, AWAY, MARKET_ID), _outcome(OID_DRAW, "Draw", MARKET_ID)],
            halftime=None,
        )
        assert _verdict_by_outcome(session) == {}

    async def test_the_half_score_decides_it_when_we_have_one(self, monkeypatch):
        """The control that cannot be passed by grading from the wrong score.

        Full time is 0–1 (away won). Half time is 2–0 the OTHER way. A resolver
        still reading the full-time score crowns `Valencia CF`; one reading the
        half crowns `Deportivo Alavés`. Only the second is correct, and the two
        answers are distinguishable — which is the whole point of the arm.
        """
        session, _stats = await _run(
            monkeypatch,
            self.RESOLVER,
            [_candidate(POLY_TICKER, SPECIMEN_NAME)],
            [
                _outcome(OID_HOME, HOME, MARKET_ID),
                _outcome(OID_AWAY, AWAY, MARKET_ID),
            ],
            halftime=(2, 0),
        )
        assert _verdict_by_outcome(session) == {OID_HOME: True, OID_AWAY: False}

    async def test_a_whole_game_market_is_still_graded(self, monkeypatch):
        """The control. The guard must not switch the resolver off."""
        session, _stats = await _run(
            monkeypatch,
            self.RESOLVER,
            [_candidate(POLY_TICKER, "Deportivo Alavés vs. Valencia CF")],
            [
                _outcome(OID_HOME, HOME, MARKET_ID),
                _outcome(OID_AWAY, AWAY, MARKET_ID),
            ],
            halftime=None,
        )
        assert _verdict_by_outcome(session) == {OID_HOME: False, OID_AWAY: True}


class TestTheMoneylineLoop:
    """`_resolve_kalshi_from_scores` — same classifier, same blind spot."""

    RESOLVER = "_resolve_kalshi_from_scores"

    async def test_a_half_named_market_is_refused_as_a_period_market(
        self, monkeypatch
    ):
        session, stats = await _run(
            monkeypatch,
            self.RESOLVER,
            [_candidate(KALSHI_TICKER, SPECIMEN_NAME)],
            [
                _outcome(OID_HOME, HOME, MARKET_ID),
                _outcome(OID_AWAY, AWAY, MARKET_ID),
            ],
            halftime=None,
        )
        assert _verdict_by_outcome(session) == {}
        assert stats["refused_period"] == 1

    async def test_a_whole_game_market_is_still_graded(self, monkeypatch):
        """The control. Same ticker, same scores, only the name differs."""
        session, stats = await _run(
            monkeypatch,
            self.RESOLVER,
            [_candidate(KALSHI_TICKER, "Deportivo Alavés vs. Valencia CF")],
            [
                _outcome(OID_HOME, HOME, MARKET_ID),
                _outcome(OID_AWAY, AWAY, MARKET_ID),
            ],
            halftime=None,
        )
        assert _verdict_by_outcome(session) == {OID_HOME: False, OID_AWAY: True}
        assert stats["refused_period"] == 0
