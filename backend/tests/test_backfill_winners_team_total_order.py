"""CERT-495: a team-total market must grade the same way in every outcome order.

The blocked finding, in one sentence: the team-total branch of
``_resolve_kalshi_spread_total_from_scores`` took the FIRST matching
``{Team} over N`` leg, derived one boolean from that leg's team and line, and
wrote it to every sibling — so a real 14-leg market landed half-wrong, and WHICH
half depended on iteration order.

The shape is not hypothetical. ``docs/mockups/data/reds.json`` carries three
``KXMLBTEAMTOTAL`` markets; ``KXMLBTEAMTOTAL-26JUN052015CINSTL`` has fourteen
outcomes and **every one of them is an "over" leg**:

    St. Louis over 1.5 … 7.5 runs scored     (7 legs)
    Cincinnati over 1.5 … 7.5 runs scored    (7 legs)

There is no "under" sibling to complement, so the old code's
``won = over if is_over_outcome else not over`` wrote the SAME boolean to all
fourteen. With Cincinnati 3 – St. Louis 5 the correct answer is six True and
eight False; the old code produced fourteen True or fourteen False.

Why these guards are shaped the way they are
--------------------------------------------
``TestTeamTotalGrader`` pins the pure grader. ``TestTeamTotalWritesAreOrder
Independent`` drives the REAL resolver and records the UPDATEs it actually
issues, because the defect lives in the write loop and a pure-function test
cannot see it (this lane's standing lesson: the thing under test must be the
thing that RUNS — and never assert against ``inspect.getsource``, because the
docstring quotes the very thing you are asserting).

Both classes red against the graded bytes of ``04e12063``:

    git checkout 04e12063 -- backend/app/tasks/backfill_winners.py
"""

import itertools
import random

import pytest

# The market exactly as captured, id-ordered as `_prefetch_outcomes` returns it.
# ids are deliberately NOT contiguous with the semantic order.
_LINES = (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5)
_HOME = "Cincinnati Reds"
_AWAY = "St. Louis Cardinals"
_HOME_SCORE = 3
_AWAY_SCORE = 5

_LEGS = tuple(
    (100 + i, f"{team} over {line} runs scored")
    for i, (team, line) in enumerate(
        [("Cincinnati", ln) for ln in _LINES] + [("St. Louis", ln) for ln in _LINES]
    )
)

# Truth: each leg on its OWN team and its OWN line. Cincinnati scored 3,
# St. Louis scored 5 — so 6 winners and 8 losers, never 14 of either.
_EXPECTED = {}
for _oid, _name in _LEGS:
    _team, _rest = _name.split(" over ")
    _line = float(_rest.split()[0])
    _score = _HOME_SCORE if _team == "Cincinnati" else _AWAY_SCORE
    _EXPECTED[_oid] = _score > _line


class TestTeamTotalGrader:
    """The pure grader: one leg in, that leg's verdict out."""

    def test_every_leg_of_the_real_market_grades_on_its_own_team_and_line(self):
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        got = {
            oid: _team_total_outcome_is_winner(
                name, _HOME, _AWAY, _HOME_SCORE, _AWAY_SCORE
            )
            for oid, name in _LEGS
        }
        assert got == _EXPECTED

    def test_the_market_is_not_all_one_verdict(self):
        """The defect's signature. If this ever passes trivially the fixture is
        wrong, not the code — a 14-leg two-team market MUST split."""
        vals = set(_EXPECTED.values())
        assert vals == {True, False}
        assert sum(_EXPECTED.values()) == 6

    def test_spread_names_are_refused_so_the_spread_branch_gets_them(self):
        """#947: the greedy '(.+?) over N' also matches a SPREAD name, which
        would grade a margin market by the team's raw score."""
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        assert (
            _team_total_outcome_is_winner(
                "Carolina wins by over 1.5 goals", "Carolina", "Boston", 4, 1
            )
            is None
        )

    def test_unmatched_team_is_flagged_unresolved_rather_than_guessed(self):
        """CERT-499: an unattributable leg must NOT return the same `None` that
        means "not a team-total leg". The caller has to be able to tell them
        apart — one is none of its business, the other is a refusal it must
        count and act on."""
        from app.tasks.backfill_winners import (
            _TEAM_TOTAL_UNRESOLVED,
            _team_total_outcome_is_winner,
        )

        assert (
            _team_total_outcome_is_winner(
                "Toronto over 1.5 runs scored", _HOME, _AWAY, _HOME_SCORE, _AWAY_SCORE
            )
            is _TEAM_TOTAL_UNRESOLVED
        )

    def test_missing_score_returns_none(self):
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        assert (
            _team_total_outcome_is_winner(
                "Cincinnati over 1.5 runs scored", _HOME, _AWAY, None, _AWAY_SCORE
            )
            is None
        )

    def test_accented_team_name_still_matches(self):
        """#939's lesson, which the replaced branch had not learned: the old
        team-total code used a raw .lower().split(), so 'Montréal' never
        token-matched the ASCII outcome name."""
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        assert (
            _team_total_outcome_is_winner(
                "Montreal over 2.5 goals", "Montréal Canadiens", "Boston Bruins", 4, 1
            )
            is True
        )

    def test_under_leg_uses_the_same_semantic_as_the_game_total_grader(self):
        from app.tasks.backfill_winners import (
            _team_total_outcome_is_winner,
            _total_outcome_is_winner,
        )

        assert (
            _team_total_outcome_is_winner(
                "Cincinnati under 4.5 runs scored", _HOME, _AWAY, 3, 5
            )
            is True
        )
        # the sibling grader must agree about what "under" means
        assert _total_outcome_is_winner("Under 9.5 runs scored", 3, 5) is True
        assert _total_outcome_is_winner("Under 7.5 runs scored", 3, 5) is False


class _Recorder:
    """A session that answers the outcome prefetch and records every UPDATE."""

    def __init__(self, legs):
        self._legs = legs
        self.writes = {}

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if params and "oid" in params:
            self.writes[params["oid"]] = params["won"]
            return _Result([])
        if "FROM futures_outcomes" in sql:
            return _Result(
                [_Row(market_id=7, id=oid, name=name) for oid, name in self._legs]
            )
        return _Result([])

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def scalar(self):
        return None


class _CM:
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


def _candidate_row():
    return _Row(
        market_id=7,
        ticker="KXMLBTEAMTOTAL-26JUN052015CINSTL",
        market_name="Cincinnati vs St. Louis team totals",
        event_id=42,
        home_team_name=_HOME,
        away_team_name=_AWAY,
        home_score=_HOME_SCORE,
        away_score=_AWAY_SCORE,
    )


async def _writes_for(legs, monkeypatch):
    """Run the REAL resolver over `legs` and return the writes it issued."""
    import app.tasks.backfill_winners as bw

    rec = _Recorder(legs)
    monkeypatch.setattr(bw, "get_task_session", lambda: _CM(rec))
    stats = await bw._resolve_kalshi_spread_total_from_scores(
        {"candidates": [_candidate_row()], "locked_market_ids": frozenset()}
    )
    return rec.writes, stats


@pytest.mark.asyncio
class TestTeamTotalWritesAreOrderIndependent:
    """The guard the cert asked for: two teams, seven thresholds, scrambled
    order, identical writes every time."""

    async def test_captured_order_grades_every_leg_correctly(self, monkeypatch):
        writes, _ = await _writes_for(list(_LEGS), monkeypatch)
        assert writes == _EXPECTED

    async def test_writes_are_identical_under_every_rotation(self, monkeypatch):
        """A rotation puts a DIFFERENT leg first — which is exactly the axis the
        old code was sensitive to, and exactly what LAT-P154's ORDER BY changed."""
        base = list(_LEGS)
        for k in range(len(base)):
            rotated = base[k:] + base[:k]
            writes, _ = await _writes_for(rotated, monkeypatch)
            assert writes == _EXPECTED, f"rotation by {k} changed the verdicts"

    async def test_writes_are_identical_under_scrambled_order(self, monkeypatch):
        """Deterministic scrambles (seeded, so a failure reproduces)."""
        base = list(_LEGS)
        for seed in range(8):
            shuffled = list(base)
            random.Random(seed).shuffle(shuffled)
            writes, _ = await _writes_for(shuffled, monkeypatch)
            assert writes == _EXPECTED, f"seed {seed} changed the verdicts"

    async def test_the_two_orders_the_cert_named_disagreed_before_the_fix(
        self, monkeypatch
    ):
        """Cert-495's own reproduction axis, minimised: put a Cincinnati leg
        first, then a St. Louis leg first, and require the same answer. Before
        the fix these two produced all-False and all-True respectively."""
        cin_first = [leg for leg in _LEGS if leg[1].startswith("Cincinnati")] + [
            leg for leg in _LEGS if leg[1].startswith("St. Louis")
        ]
        stl_first = list(reversed(cin_first))
        a, _ = await _writes_for(cin_first, monkeypatch)
        b, _ = await _writes_for(stl_first, monkeypatch)
        assert a == b == _EXPECTED

    async def test_every_leg_is_written_exactly_once(self, monkeypatch):
        writes, _ = await _writes_for(list(_LEGS), monkeypatch)
        assert set(writes) == {oid for oid, _ in _LEGS}
        assert len(writes) == 14

    async def test_the_market_is_never_graded_all_one_way(self, monkeypatch):
        """The direct signature of the defect: 14 identical booleans."""
        for perm in itertools.islice(itertools.permutations(list(_LEGS)[:4]), 6):
            writes, _ = await _writes_for(list(perm) + list(_LEGS)[4:], monkeypatch)
            assert set(writes.values()) == {True, False}

    async def test_stats_total_stays_a_per_market_count(self, monkeypatch):
        """Behaviour preserved on purpose: the phase summary's counter must not
        silently change units from markets to outcomes."""
        _, stats = await _writes_for(list(_LEGS), monkeypatch)
        assert stats["total"] == 1

    async def test_an_unparseable_leg_is_left_alone_not_given_a_complement(
        self, monkeypatch
    ):
        """Assigning a leg the complement of some OTHER leg's verdict is the bug
        itself. An unreadable leg must keep its existing value."""
        legs = list(_LEGS) + [(999, "Yes")]
        writes, _ = await _writes_for(legs, monkeypatch)
        assert 999 not in writes
        assert writes == _EXPECTED


class TestSharedCityIdentity:
    """CERT-498 [P1]: two clubs in one city must not share a score.

    A bare token intersection with home-first precedence gave every AWAY leg the
    HOME score whenever the city tokens matched. ``SHARED_CITY_DIFFERENT_CLUB``
    in ``test_names_match_authority_2046.py`` catalogues the class; the
    production-derived fixture
    ``fixtures/related_futures_15200831_identity_20260819.json`` shows Kalshi
    writes the club as a single letter (``Los Angeles D``, ``Los Angeles A``).

    Both reproductions below are the cert's own, verbatim, and both red on
    ``aaf7a523``.
    """

    def test_mets_ladder_is_not_graded_off_the_yankees_score(self):
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        # Yankees (home) 2 – Mets (away) 6. The Mets scored 6, so "over 4.5" wins.
        assert (
            _team_total_outcome_is_winner(
                "New York M over 4.5 runs scored",
                "New York Yankees",
                "New York Mets",
                2,
                6,
            )
            is True
        )
        # …and the Yankees' own leg at the same line must still lose.
        assert (
            _team_total_outcome_is_winner(
                "New York Y over 4.5 runs scored",
                "New York Yankees",
                "New York Mets",
                2,
                6,
            )
            is False
        )

    def test_angels_ladder_is_not_graded_off_the_dodgers_score(self):
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        # Dodgers (home) 2 – Angels (away) 6, spelled out…
        assert (
            _team_total_outcome_is_winner(
                "Los Angeles Angels over 4.5 runs scored",
                "Los Angeles Dodgers",
                "Los Angeles Angels",
                2,
                6,
            )
            is True
        )
        # …and abbreviated the way the captured fixture actually spells it.
        assert (
            _team_total_outcome_is_winner(
                "Los Angeles A over 4.5 runs scored",
                "Los Angeles Dodgers",
                "Los Angeles Angels",
                2,
                6,
            )
            is True
        )
        assert (
            _team_total_outcome_is_winner(
                "Los Angeles D over 4.5 runs scored",
                "Los Angeles Dodgers",
                "Los Angeles Angels",
                2,
                6,
            )
            is False
        )

    def test_the_bare_shared_city_is_refused_rather_than_guessed(self):
        from app.tasks.backfill_winners import (
            _TEAM_TOTAL_UNRESOLVED,
            _team_total_outcome_is_winner,
        )

        assert (
            _team_total_outcome_is_winner(
                "New York over 4.5 runs scored",
                "New York Yankees",
                "New York Mets",
                2,
                6,
            )
            is _TEAM_TOTAL_UNRESOLVED
        )

    def test_an_unresolvable_abbreviation_is_refused_not_assigned(self):
        """'Chicago WS' has no remaining token starting with 'ws'. Refusing is
        the designed outcome — an ungraded row beats a wrong one."""
        from app.tasks.backfill_winners import (
            _TEAM_TOTAL_UNRESOLVED,
            _team_total_outcome_is_winner,
        )

        assert (
            _team_total_outcome_is_winner(
                "Chicago WS over 4.5 runs scored",
                "Chicago Cubs",
                "Chicago White Sox",
                2,
                6,
            )
            is _TEAM_TOTAL_UNRESOLVED
        )

    def test_every_catalogued_shared_city_pair_resolves_or_refuses_but_never_flips(
        self,
    ):
        """Across the whole catalogued class, the AWAY club's leg must never be
        graded off the HOME club's score. Home 0, away 9: an away leg at 4.5 is
        True or None, and can never be False."""
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        pairs = [
            ("New York Mets", "New York Yankees"),
            ("New York Giants", "New York Jets"),
            ("Los Angeles Angels", "Los Angeles Dodgers"),
            ("Los Angeles Chargers", "Los Angeles Rams"),
            ("Los Angeles Clippers", "Los Angeles Lakers"),
            ("New York Islanders", "New York Rangers"),
            ("Boston College", "Boston University"),
        ]
        for home, away in pairs:
            got = _team_total_outcome_is_winner(
                f"{away} over 4.5 points", home, away, 0, 9
            )
            assert got is not False, f"{away} away leg graded off {home}'s score"
            assert got is True, f"{away} should resolve exclusively"

    def test_distinct_cities_are_unaffected(self):
        """The exclusivity rule must not cost recall on the ordinary case."""
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        assert (
            _team_total_outcome_is_winner(
                "Cincinnati over 2.5 runs scored", _HOME, _AWAY, 3, 5
            )
            is True
        )
        assert (
            _team_total_outcome_is_winner(
                "St. Louis over 5.5 runs scored", _HOME, _AWAY, 3, 5
            )
            is False
        )


class TestAthleticsAliasAndDeferral:
    """CERT-499: the 56 production `A's` legs, and the silence that hid them.

    `normalize_team_name("A's")` is `"a's"` by design (its own docstring says so)
    while the event side spells the club `Athletics`, so the exclusivity rule
    refused every one of them — and the refusal was invisible, because a parsed
    sibling marked the market resolved. Since `game_score` is not in
    `OVERWRITABLE_WINNER_SOURCES_SQL` and the candidate scan drops markets that
    already carry a non-overwritable winner, that did not defer those legs, it
    stranded them permanently.
    """

    def test_the_athletics_alias_resolves_against_its_real_opponents(self):
        """21 of the 56 legs face Houston. `Astros` also begins with 'a', which
        is why a generic possessive-strip-and-prefix rule cannot do this job and
        an explicit alias can."""
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        for opponent in (
            "Houston Astros",
            "Philadelphia Phillies",
            "Chicago White Sox",
            "New York Mets",
            "New York Yankees",
        ):
            assert (
                _team_total_outcome_is_winner(
                    "A's over 0.5 runs scored", "Athletics", opponent, 3, 5
                )
                is True
            ), opponent
            assert (
                _team_total_outcome_is_winner(
                    "A's over 7.5 runs scored", "Athletics", opponent, 3, 5
                )
                is False
            ), opponent

    def test_the_opponents_own_leg_is_still_graded_off_the_opponent(self):
        from app.tasks.backfill_winners import _team_total_outcome_is_winner

        assert (
            _team_total_outcome_is_winner(
                "Houston over 4.5 runs scored", "Athletics", "Houston Astros", 3, 5
            )
            is True
        )


@pytest.mark.asyncio
class TestDeferralWritesNothingOnAnUnattributableLeg:
    """CERT-499: all-or-nothing, driven through the REAL resolver."""

    async def test_an_unattributable_leg_defers_the_WHOLE_market(self, monkeypatch):
        """All-or-nothing. A partial `game_score` grade is permanent, so writing
        the readable legs would strand the unreadable one forever."""
        legs = list(_LEGS) + [(999, "Toronto over 4.5 runs scored")]
        writes, stats = await _writes_for(legs, monkeypatch)
        assert writes == {}, "no leg may be written when one is unattributable"
        assert stats["team_total_unresolved_legs"] == 1
        assert stats["team_total_deferred_markets"] == 1
        assert stats["total"] == 0

    async def test_a_clean_market_is_unaffected_by_the_deferral_rule(self, monkeypatch):
        writes, stats = await _writes_for(list(_LEGS), monkeypatch)
        assert writes == _EXPECTED
        assert stats["team_total_unresolved_legs"] == 0
        assert stats["team_total_deferred_markets"] == 0
        assert stats["total"] == 1

    async def test_a_non_team_total_leg_does_NOT_defer_the_market(self, monkeypatch):
        """ "Yes" is not a team total, so it is none of this branch's business and
        must not be confused with a refusal. This is the whole reason the
        sentinel exists instead of a second `None`."""
        writes, stats = await _writes_for(list(_LEGS) + [(999, "Yes")], monkeypatch)
        assert writes == _EXPECTED
        assert stats["team_total_deferred_markets"] == 0
        assert stats["total"] == 1
