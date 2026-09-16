"""#6590 — a settled market stops printing two winners because a Draw was sided as a team.

THE DEFECT. Both 2-outcome "team vs team" loops in `backfill_winners` decide a
leg by intersecting the whitespace tokens of its name with the home and away
team names, on the assumption that BOTH legs name a team:

* `_resolve_kalshi_from_scores` — the moneyline loop.
* `_resolve_kalshi_spread_total_from_scores` — the team-name fallback.

Neither candidate scan filters `fm.source` despite the names, so both grade
Polymarket rows too. A draw leg breaks the assumption, and a draw leg that
embeds the two club names breaks it SILENTLY, because `.split()` leaves
punctuation attached::

    home="SK Beveren" -> {sk, beveren};   away="Leuven" -> {leuven}
    "Draw (SK Beveren vs. Oud-Heverlee Leuven)"
        -> {draw, (sk, beveren, vs., oud-heverlee, leuven)}
        home hit = {beveren}    away hit = {}    <-- "leuven)" != "leuven"
        is_home=True, is_away=False   ->   won = home_won = True

So production served TWO WINNERS ON ONE `mutually_exclusive` MARKET.
`/futures/60015154` (SK Beveren vs. Oud-Heverlee Leuven, final **3–0**) printed
"Settled — SK Beveren won." above a Final Results card badging BOTH
`SK Beveren` and `Draw (…)` as `Won · 100% Settled`.

`game_score` is not in `OVERWRITABLE_WINNER_SOURCES_SQL` and the candidate scan
drops any market already holding one, so each wrong verdict is PERMANENT. At
filing: 15 draw legs crowned on games that did not finish level, and **8
two-leg draw markets still ungraded** and due to be crowned on the next run.

WHY A BARE DRAW IS GRADED AND A QUALIFIED ONE IS REFUSED. Both loops only reach
this code when the segment they hold a score for is NOT level, which DECIDES a
bare draw — so `False` is the honest answer and reads better than a withheld
row. But `tie 1st half`, `draw 2-2`, `draw 1h 1-1`, `tie 9th inning` and
`draw/no contest` are all real measured shapes that ask about a DIFFERENT
segment, and answering those from the score in hand is exactly #4923.

Guard discipline follows #4923's: every resolver guard drives the real loop and
reads the statements it actually executed, and each fix arm carries the control
that would fail if the guard simply switched the resolver off.
"""

from unittest.mock import MagicMock

import pytest

import app.tasks.backfill_winners as bw


# ==========================================================================
# 1. the classifier
# ==========================================================================

#: The production specimen, read 2026-09-16 from `futures_outcomes` on market
#: 60015154. The parenthetical is the MATCH NAME, not a qualifier — which is
#: why the bare form has to admit it.
SPECIMEN_DRAW = "Draw (SK Beveren vs. Oud-Heverlee Leuven)"


@pytest.mark.parametrize("name", ["Tie", "Draw", "draw", "TIE", SPECIMEN_DRAW])
def test_a_bare_draw_is_decided_by_a_segment_that_is_not_level(name):
    assert bw._draw_leg_verdict(name) is False


#: Every one of these is a real outcome name on production, read 2026-09-16
#: (56,122 draw/tie legs). Each asks about a segment the caller does not hold a
#: score for, so a verdict here would be a #4923 defect in a new suit.
@pytest.mark.parametrize(
    "name",
    [
        "tie 1st half",
        "tie 2nd half",
        "draw 2-2",
        "draw 1-1",
        "draw 0-0",
        "draw 1h 1-1",
        "tie 9th inning",
        "tie 4th quarter",
        "draw/no contest",
    ],
)
def test_a_qualified_draw_is_refused_never_sided(name):
    assert bw._draw_leg_verdict(name) == "refuse"


#: `\b` is the whole reason these stay on the team path. Both are real clubs.
@pytest.mark.parametrize("name", ["Tienen", "Drawsko", "SK Beveren", "Detroit"])
def test_a_club_whose_name_merely_starts_with_those_letters_is_still_a_team(name):
    assert bw._draw_leg_verdict(name) is None


def test_a_missing_name_is_not_a_draw():
    assert bw._draw_leg_verdict(None) is None
    assert bw._draw_leg_verdict("") is None


def test_the_old_token_arithmetic_really_did_side_the_specimen_home():
    """The negative control: prove the arms COULD have differed.

    Without this, every assertion above passes just as well against a resolver
    that never had the bug — and a guard that cannot fail on the defect it
    names is decoration.
    """
    home_tokens = set("SK Beveren".lower().split())
    away_tokens = set("Leuven".lower().split())
    toks = set(SPECIMEN_DRAW.lower().split())

    # The away-exclusion misses because the token carries the paren…
    assert "leuven)" in toks and "leuven" not in toks
    assert not (toks & away_tokens)
    # …while the home side matches cleanly, so the pre-fix branch said "home".
    assert toks & home_tokens == {"beveren"}
    is_home = bool(toks & home_tokens) and not bool(toks & away_tokens)
    assert is_home is True


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

#: SK Beveren vs. Oud-Heverlee Leuven, Belgian First Division, 2026-09-06.
#: Final 3–0; `futures_markets.external_id` is Polymarket's numeric event id,
#: which is how a market with no Kalshi ticker reaches a "kalshi" resolver.
MARKET_ID = 60015154
EVENT_ID = 15298068
POLY_TICKER = "948797"
HOME, AWAY = "SK Beveren", "Leuven"
HOME_SCORE, AWAY_SCORE = 3, 0

OID_TEAM, OID_DRAW = 223837848, 223837849


#: The moneyline loop additionally gates on `_score_gradeable_family`, which
#: refuses Polymarket's numeric id — so THAT loop never graded this specimen and
#: is driven below with a real Kalshi family instead (`KXMLSGAME` carries 392
#: draw legs on production). The hole is identical in both; only the population
#: that reaches it differs, which is why both are guarded.
KALSHI_TICKER = "KXMLSGAME-26SEP09CHIMIA"


def _candidate(ticker, **over):
    kw = dict(
        market_id=MARKET_ID,
        market_name="SK Beveren vs. Oud-Heverlee Leuven",
        ticker=ticker,
        event_id=EVENT_ID,
        home_team_name=HOME,
        away_team_name=AWAY,
        home_score=HOME_SCORE,
        away_score=AWAY_SCORE,
        n_outcomes=2,
    )
    kw.update(over)
    return _row(**kw)


def _outcome(oid, name, market_id=MARKET_ID):
    return _row(market_id=market_id, id=oid, name=name)


def _verdict_by_outcome(session):
    """`{outcome_id: is_winner}` for every row the run actually stamped."""
    out = {}
    for _sql, params in session.verdict_writes():
        if params and "oid" in params:
            out[params["oid"]] = params["won"]
    return out


class _DrivesAResolver:
    """Shared driver; subclasses name the resolver under test."""

    RESOLVER = None
    #: A ticker that actually reaches this resolver's grading branch.
    TICKER = None

    async def _run(self, monkeypatch, candidates, outcomes):
        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result(candidates)
            if _PREFETCH_MARKER in sql:
                return _Result(outcomes)
            return None

        session = _install(monkeypatch, _RecordingSession(responder))
        stats = await getattr(bw, self.RESOLVER)()
        return session, stats

    async def test_the_specimen_grades_the_team_won_and_the_draw_lost(
        self, monkeypatch
    ):
        """The photographed market: exactly one winner, and it is the club."""
        session, _stats = await self._run(
            monkeypatch,
            [_candidate(self.TICKER)],
            [
                _outcome(OID_TEAM, HOME),
                _outcome(OID_DRAW, SPECIMEN_DRAW),
            ],
        )
        verdicts = _verdict_by_outcome(session)
        assert verdicts == {OID_TEAM: True, OID_DRAW: False}
        # The reader-facing invariant, stated as itself: a mutually-exclusive
        # market never stamps two winners.
        assert sum(1 for won in verdicts.values() if won) == 1

    async def test_a_bare_tie_loses_too(self, monkeypatch):
        session, _stats = await self._run(
            monkeypatch,
            [_candidate(self.TICKER)],
            [_outcome(OID_TEAM, HOME), _outcome(OID_DRAW, "Tie")],
        )
        assert _verdict_by_outcome(session) == {OID_TEAM: True, OID_DRAW: False}

    async def test_a_qualified_draw_is_left_ungraded(self, monkeypatch):
        """`tie 1st half` is not decided by a full-time 3–0 (#4923)."""
        session, _stats = await self._run(
            monkeypatch,
            [_candidate(self.TICKER)],
            [_outcome(OID_TEAM, HOME), _outcome(OID_DRAW, "tie 1st half")],
        )
        verdicts = _verdict_by_outcome(session)
        assert OID_DRAW not in verdicts
        assert verdicts == {OID_TEAM: True}

    async def test_an_ordinary_two_team_market_is_untouched(self, monkeypatch):
        """The control. The guard must not switch the resolver off."""
        session, _stats = await self._run(
            monkeypatch,
            [_candidate(self.TICKER)],
            [_outcome(OID_TEAM, HOME), _outcome(OID_DRAW, "Oud-Heverlee Leuven")],
        )
        assert _verdict_by_outcome(session) == {OID_TEAM: True, OID_DRAW: False}

    async def test_the_away_side_still_wins_when_it_should(self, monkeypatch):
        """Both directions: the sided path keeps working when away wins."""
        session, _stats = await self._run(
            monkeypatch,
            [_candidate(self.TICKER, home_score=0, away_score=2)],
            [_outcome(OID_TEAM, HOME), _outcome(OID_DRAW, "Oud-Heverlee Leuven")],
        )
        assert _verdict_by_outcome(session) == {OID_TEAM: False, OID_DRAW: True}


class TestTheMoneylineLoop(_DrivesAResolver):
    RESOLVER = "_resolve_kalshi_from_scores"
    TICKER = KALSHI_TICKER


class TestTheTeamNameFallback(_DrivesAResolver):
    RESOLVER = "_resolve_kalshi_spread_total_from_scores"
    TICKER = POLY_TICKER
