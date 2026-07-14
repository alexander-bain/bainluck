"""Queue #188 Item 2 (#1088): Kalshi golf round-leader date collapse.

A still-open tournament's round-leader / round-top markets all arrive stamped
with the same Kalshi list/close date (gotcha #14) — The Open Championship's
R1/R2/R3 leader markets were all dated 2026-07-13 instead of their true rounds
(Jul-16/17/18). Kalshi encodes the round only in the ticker (``KXPGAR{N}LEAD``)
and the market name ("Round N"), never in a per-round date, and DataGolf never
creates round markets, so the honest per-round date is:

    DataGolf tournament start + (round - 1) days.

The subtlety that made the collapse look tournament-specific: ``_normalize_
tournament``'s own round-stripper is DASH-anchored, but Kalshi names carry no
dash before the round tail, so a round-leader name slugifies WITH the round
suffix and never matches the tournament "…- Winner" key. ``_fix_golf_round_
leader_dates`` strips the round tail first, so every tournament (not just the
majors that match a hardcoded pattern) keys to its winner market.

These tests cover the pure round-extraction / round-strip / key-alignment /
date-offset logic that drives the DB fix — where the bug lived.
"""

from datetime import datetime, timedelta

from app.routes.golf import _normalize_tournament
from app.tasks.kalshi import _GOLF_ROUND_RE, _GOLF_ROUND_STRIP_RE


def _round_date(start: datetime, name: str) -> datetime | None:
    """Mirror of the per-market computation inside _fix_golf_round_leader_dates."""
    rnd_m = _GOLF_ROUND_RE.search(name)
    if not rnd_m:
        return None
    rnd = int(rnd_m.group(1))
    return start + timedelta(days=rnd - 1)


class TestRoundExtraction:
    def test_matches_end_of_round_leader(self):
        assert _GOLF_ROUND_RE.search("The Open Championship End of Round 1 Leader").group(1) == "1"
        assert _GOLF_ROUND_RE.search("Genesis Scottish Open End of Round 2 Leader").group(1) == "2"
        assert _GOLF_ROUND_RE.search("U.S. Open End of Round 3 Leader").group(1) == "3"

    def test_matches_round_top(self):
        assert _GOLF_ROUND_RE.search("Some Event Round 2 Top 10 Finishers").group(1) == "2"

    def test_non_round_markets_ignored(self):
        # Tournament-winner / top-N / make-cut are NOT round-specific.
        assert _GOLF_ROUND_RE.search("The Open Championship - Winner") is None
        assert _GOLF_ROUND_RE.search("The Open Championship Top 10 Finish") is None
        assert _GOLF_ROUND_RE.search("Hole in One During The Open") is None


class TestKeyAlignmentWithWinnerMarket:
    """The round-leader name, with the round tail stripped, must normalize to the
    SAME tournament key as the DataGolf "…- Winner" market — otherwise the start
    lookup misses and the round date can't be computed."""

    CASES = [
        ("The Open Championship End of Round 1 Leader", "The Open Championship - Winner"),
        ("Genesis Scottish Open End of Round 2 Leader", "Genesis Scottish Open - Winner"),
        ("U.S. Open End of Round 3 Leader", "U.S. Open - Winner"),
        ("RBC Canadian Open End of Round 2 Leader", "RBC Canadian Open - Winner"),
        ("BMW International Open End of Round 1 Leader", "BMW International Open - Winner"),
    ]

    def test_stripped_round_name_matches_winner_key(self):
        for round_name, winner_name in self.CASES:
            base = _GOLF_ROUND_STRIP_RE.sub("", round_name).strip()
            assert _normalize_tournament(base) == _normalize_tournament(winner_name), round_name

    def test_unstripped_name_would_NOT_match(self):
        # Regression: without the strip, a non-major tournament's round-leader
        # name slugifies with the round suffix and misses the winner key. (The
        # majors still match via the hardcoded pattern, so test a non-major.)
        round_name = "Genesis Scottish Open End of Round 2 Leader"
        winner_key = _normalize_tournament("Genesis Scottish Open - Winner")
        assert _normalize_tournament(round_name) != winner_key
        base = _GOLF_ROUND_STRIP_RE.sub("", round_name).strip()
        assert _normalize_tournament(base) == winner_key


class TestPerRoundDate:
    def test_the_open_rounds_get_distinct_true_dates(self):
        # Acceptance (#1088): DataGolf "The Open Championship - Winner" starts
        # 2026-07-16, so R1/R2/R3 leader markets must carry Jul-16/17/18, not the
        # collapsed Kalshi list date (2026-07-13).
        start = datetime(2026, 7, 16)
        r1 = _round_date(start, "The Open Championship End of Round 1 Leader")
        r2 = _round_date(start, "The Open Championship End of Round 2 Leader")
        r3 = _round_date(start, "The Open Championship End of Round 3 Leader")
        assert r1.date() == datetime(2026, 7, 16).date()
        assert r2.date() == datetime(2026, 7, 17).date()
        assert r3.date() == datetime(2026, 7, 18).date()
        # And they are three DISTINCT dates (the collapse is gone).
        assert len({r1, r2, r3}) == 3

    def test_round_one_equals_tournament_start(self):
        start = datetime(2026, 7, 16)
        assert _round_date(start, "Anything End of Round 1 Leader") == start
