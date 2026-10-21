"""#1529 phase-A acceptance accounting (`app/utils/capture_census_acceptance.py`).

PILLAR: TRUTH. SHIP: across sports, game pages put full-game winners in Game lines and
preserve player and segment questions in the correct sections. These tests pin how a
complete census is graded against #1529's original acceptance: moneyline >= 1/game and
'other' < 10% of markets for every CORE_TEAM_SPORTS cohort, on the full window, with
exact comparisons, union cohorts, NO_POPULATION never PASS, and NO_RESULT for any
missing, malformed or self-contradicting result set. Pure: no database, no clock.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from app.utils import capture_census as cc
from app.utils import capture_census_acceptance as acc

DAY = date(2026, 10, 10)
NFL_PRESEASON_DAY = date(2026, 8, 15)

# Names the shared classifier answers with each class (asserted in TestFixtureNames).
ML = 'Yankees vs Red Sox'
OTHER = 'Mystery market about nothing'
SPREAD = 'Yankees vs Red Sox: Spread'
SEGMENT = 'Phantom Academy vs. Noir Verse: Map 1'


def market(sport, name, *, ext=None, outcomes=2, well=1, vol_pos=1, vol_null=0, artifact=0,
           home='Home', away='Away', day=DAY, source='kalshi'):
    if outcomes == 0:
        well = vol_pos = artifact = 0
        vol_null = 1
    return dict(sport=sport, name=name, ext=ext, outcomes=outcomes, well=well, vol_pos=vol_pos,
                vol_null=vol_null, artifact=artifact, home=home, away=away, day=day, source=source)


class Census:
    """Builds the four result sets of one consistent census from a list of games and markets."""

    def __init__(self):
        self.games = {}        # (sport, day) -> n
        self.markets = []

    def add_games(self, sport, n, day=DAY):
        self.games[(sport, day)] = self.games.get((sport, day), 0) + n
        return self

    def add(self, *markets):
        self.markets.extend(markets)
        return self

    def rows(self):
        per_sport = {}
        for (sport, _day), n in self.games.items():
            per_sport[sport] = per_sport.get(sport, 0) + n
        games_rows = sorted(per_sport.items(), key=lambda kv: (-kv[1], str(kv[0])))
        fixture_rows = [(s, d, n) for (s, d), n in self.games.items()]
        market_rows = [(m['sport'], m['name'], m['ext'], m['outcomes'], m['well'], m['vol_pos'],
                        m['vol_null'], m['artifact'], m['home'], m['away'], m['day']) for m in self.markets]
        split = {}
        for m in self.markets:
            k = (m['sport'], m['source'])
            row = split.setdefault(k, [0, 0, 0, 0, 0])
            for i, f in enumerate(('outcomes', 'well', 'vol_pos', 'vol_null', 'artifact')):
                row[i] += m[f]
        source_rows = [(s, src, *v) for (s, src), v in split.items() if v[0] > 0]  # the HAVING
        return dict(games_rows=games_rows, market_rows=market_rows, source_rows=source_rows,
                    fixture_day_rows=fixture_rows)

    def grade(self, **override):
        kwargs = dict(window_days=30, **self.rows())
        kwargs.update(override)
        return acc.phase_a_acceptance(**kwargs)


def passing_core(exclude=()):
    """Every CORE sport: 10 games, 10 moneylines, 2 spreads, 0 other."""
    c = Census()
    for sport in sorted(cc.CORE_TEAM_SPORTS - set(exclude)):
        c.add_games(sport, 10)
        c.add(*[market(sport, ML) for _ in range(10)], market(sport, SPREAD), market(sport, SPREAD))
    return c


def _walk(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    else:
        yield value


class TestFixtureNames:
    @pytest.mark.parametrize('name,sport,cls', [
        (ML, 'baseball_mlb', 'moneyline'), (OTHER, 'baseball_mlb', 'other'),
        (SPREAD, 'baseball_mlb', 'spread'), (SEGMENT, 'esports', 'segment_winner'),
        (SEGMENT, 'soccer_epl', 'segment_winner'),
    ])
    def test_the_shared_classifier_answers_the_fixture_names_as_assumed(self, name, sport, cls):
        assert cc.classify_game_market_class(name, None, sport, sides=('Home', 'Away')) == cls

    def test_core_is_the_fourteen_keys_and_holds_no_esports(self):
        assert len(cc.CORE_TEAM_SPORTS) == 14
        assert not any(acc._is_esports(s) for s in cc.CORE_TEAM_SPORTS)


class TestThresholds:
    def test_control_every_core_cohort_clearing_both_bars_is_pass(self):
        out = passing_core().grade()
        assert out['verdict'] == 'PASS', out.get('reconciliation')
        assert set(out['core_verdicts'].values()) == {'PASS'}
        assert out['reconciliation'] == {'ok': True, 'failures': []}

    def test_moneyline_exactly_one_per_game_passes_and_one_short_fails(self):
        exact = passing_core().grade()['sports']['baseball_mlb']
        assert exact['moneyline_per_game'] == {'num': 10, 'den': 10} and exact['moneyline_check'] == 'PASS'
        short = passing_core(exclude=['baseball_mlb']).add_games('baseball_mlb', 10).add(
            *[market('baseball_mlb', ML) for _ in range(9)]).grade()
        assert short['sports']['baseball_mlb']['moneyline_check'] == 'FAIL'
        assert short['verdict'] == 'FAIL'

    def test_other_share_of_exactly_ten_percent_fails_and_just_under_passes(self):
        # 10 moneylines + 9 spreads + 1 other = 20 markets... 2 others of 20 = exactly 10%.
        base = passing_core(exclude=['soccer_epl']).add_games('soccer_epl', 10)
        exact = base.add(*[market('soccer_epl', ML) for _ in range(10)],
                         *[market('soccer_epl', SPREAD) for _ in range(8)],
                         market('soccer_epl', OTHER), market('soccer_epl', OTHER)).grade()
        epl = exact['sports']['soccer_epl']
        assert epl['other_share'] == {'num': 2, 'den': 20}
        assert epl['other_check'] == 'FAIL' and exact['verdict'] == 'FAIL'
        under = passing_core(exclude=['soccer_epl']).add_games('soccer_epl', 10).add(
            *[market('soccer_epl', ML) for _ in range(10)], *[market('soccer_epl', SPREAD) for _ in range(9)],
            market('soccer_epl', OTHER), market('soccer_epl', OTHER)).grade()
        assert under['sports']['soccer_epl']['other_share'] == {'num': 2, 'den': 21}
        assert under['sports']['soccer_epl']['other_check'] == 'PASS' and under['verdict'] == 'PASS'

    def test_the_sentinel_alarm_misses_exactly_ten_percent_which_is_why_this_gate_exists(self):
        by_sc = {'soccer_epl': {'moneyline': cc.MassCounts(markets=9), 'other': cc.MassCounts(markets=1)}}
        assert cc.capture_findings({'soccer_epl': 9}, by_sc, now=DAY) == []
        assert acc._grade(9, 10, 9, 1)['other_check'] == 'FAIL'

    def test_no_threshold_is_a_float_and_nothing_in_the_report_is_rounded(self):
        out = passing_core().grade()
        assert not any(isinstance(v, float) for v in _walk(out))
        json.dumps(out, allow_nan=False)


class TestEmptyCohorts:
    def test_games_with_no_markets_fail_moneyline_and_leave_the_other_share_undefined(self):
        out = passing_core(exclude=['icehockey_nhl']).add_games('icehockey_nhl', 7).grade()
        nhl = out['sports']['icehockey_nhl']
        assert (nhl['games'], nhl['markets']) == (7, 0)
        assert nhl['moneyline_check'] == 'FAIL' and nhl['other_check'] == 'UNDEFINED'
        assert nhl['other_share'] is None and nhl['moneyline_per_game'] == {'num': 0, 'den': 7}
        assert out['verdict'] == 'FAIL'

    def test_the_sentinel_never_sees_a_cohort_with_games_and_no_markets(self):
        # capture_findings iterates sports present in market rows only.
        assert cc.capture_findings({'icehockey_nhl': 50}, {}, now=DAY) == []

    def test_a_core_sport_with_no_games_is_no_population_and_never_pass(self):
        out = passing_core(exclude=['basketball_wnba']).grade()
        assert out['sports']['basketball_wnba']['verdict'] == 'NO_POPULATION'
        assert out['sports']['basketball_wnba']['games'] == 0
        assert out['verdict'] == 'NO_POPULATION'

    def test_a_fail_outranks_no_population(self):
        out = passing_core(exclude=['basketball_wnba', 'icehockey_nhl']).add_games('icehockey_nhl', 3).grade()
        assert out['core_verdicts']['basketball_wnba'] == 'NO_POPULATION'
        assert out['verdict'] == 'FAIL'

    def test_a_completely_empty_census_is_no_population_for_every_core_sport(self):
        out = Census().grade()
        assert out['verdict'] == 'NO_POPULATION'
        assert set(out['core_verdicts'].values()) == {'NO_POPULATION'}
        assert out['esports']['status'] == 'UNKNOWN'


class TestClassesAndUnion:
    def test_all_seven_classes_are_reported_for_every_cohort_zeros_included(self):
        out = passing_core().add_games('tennis_atp', 2).grade()
        for sport, entry in out['sports'].items():
            assert list(entry['classes'])[:7] == cc.CLASSES, sport
        assert out['sports']['tennis_atp']['classes']['segment_winner']['markets'] == 0

    def test_a_segment_winner_is_in_the_denominator_and_is_neither_moneyline_nor_other(self):
        c = passing_core(exclude=['soccer_epl']).add_games('soccer_epl', 10)
        c.add(*[market('soccer_epl', ML) for _ in range(10)], *[market('soccer_epl', SEGMENT) for _ in range(9)],
              market('soccer_epl', OTHER), market('soccer_epl', OTHER))
        epl = c.grade()['sports']['soccer_epl']
        assert epl['classes']['segment_winner']['markets'] == 9
        assert epl['classes']['moneyline']['markets'] == 10 and epl['classes']['other']['markets'] == 2
        assert epl['other_share'] == {'num': 2, 'den': 21} and epl['other_check'] == 'PASS'

    def test_the_cohort_set_is_the_union_of_core_games_and_markets(self):
        out = passing_core().add_games('tennis_atp', 4).add(market('tennis_atp', OTHER)).grade()
        assert set(cc.CORE_TEAM_SPORTS) | {'tennis_atp'} == set(out['sports'])
        assert out['sports']['tennis_atp']['verdict'] == 'NOT_GRADED_NOT_CORE'
        assert 'tennis_atp' not in out['core_verdicts']
        assert out['verdict'] == 'PASS'


    def test_an_answer_outside_the_seven_classes_is_counted_in_the_denominator_and_disclosed(self, monkeypatch):
        real = acc.classify_game_market_class
        monkeypatch.setattr(acc, 'classify_game_market_class',
                            lambda name, *a, **k: 'bogus' if name == 'Weird' else real(name, *a, **k))
        c = passing_core(exclude=['baseball_mlb']).add_games('baseball_mlb', 1)
        out = c.add(market('baseball_mlb', ML), market('baseball_mlb', 'Weird')).grade()
        mlb = out['sports']['baseball_mlb']
        assert mlb['markets'] == 2 and mlb['classes'][acc.UNCLASSIFIED]['markets'] == 1
        assert out['unknowns']['unclassified_markets'] == 1
        assert mlb['other_share'] == {'num': 0, 'den': 2}


class TestNoClassifierDrift:
    def test_class_counts_equal_the_census_libraries_own_tally(self):
        c = passing_core()
        c.add_games('esports', 3).add(market('esports', SEGMENT), market('esports', OTHER, ext='kxlolgame-x'),
                                      market('esports', None), market('esports', ML, outcomes=0))
        c.add(market('baseball_mlb', 'Yankees vs Red Sox: First 5 Innings', ext='KXMLBF5-26OCT10NYYBOS'))
        # The game's sides decide this one: a player ladder only when the subject is not a club.
        c.add(market('soccer_epl', 'Lyle Foster: 3+ goals', home='Burnley', away='Arsenal'),
              market('soccer_epl', 'Arsenal: 3+ goals', home='Burnley', away='Arsenal'))
        rows = c.rows()
        out = acc.phase_a_acceptance(window_days=30, **rows)
        mine = out['sports']
        assert mine['soccer_epl']['classes']['player_prop']['markets'] == 1
        assert out['totals']['markets'] == out['totals']['fetched_market_rows'] == len(rows['market_rows'])
        for sport, entry in mine.items():
            assert sum(c['markets'] for c in entry['classes'].values()) == entry['markets'], sport
        theirs, _ = cc.tally_market_rows(rows['market_rows'])
        for sport, classes in theirs.items():
            for cls, mc in classes.items():
                assert mine[sport]['classes'][cls]['markets'] == mc.markets, (sport, cls)
                assert mine[sport]['classes'][cls]['outcomes'] == mc.outcomes, (sport, cls)


class TestNullsAndZeroOutcomes:
    def test_null_name_id_side_day_and_zero_outcome_rows_are_counted_and_disclosed(self):
        c = passing_core(exclude=['baseball_mlb']).add_games('baseball_mlb', 2)
        c.add(market('baseball_mlb', ML), market('baseball_mlb', ML, outcomes=0),
              market('baseball_mlb', None, ext=None, home=None))
        out = c.grade()
        mlb = out['sports']['baseball_mlb']
        assert mlb['markets'] == 3
        assert mlb['classes']['other']['markets'] == 1          # the NULL name, as the census tallies it
        assert out['unknowns']['null_name_markets'] == 1
        assert out['unknowns']['null_side_markets'] == 1
        assert out['unknowns']['zero_outcome_markets'] == 1
        assert mlb['classes']['moneyline']['zero_outcome_markets'] == 1
        assert mlb['classes']['moneyline']['vol_null_raw'] == 1   # the census's own counter, kept
        assert mlb['classes']['moneyline']['vol_null_outcomes'] == 0
        assert mlb['other_check'] == 'FAIL'                     # 1 of 3: a NULL row is never dropped to pass

    def test_a_null_sport_key_is_its_own_cohort(self):
        out = passing_core().add_games(None, 2).add(market(None, ML)).grade()
        assert out['sports'][acc.NULL_KEY]['markets'] == 1
        assert out['unknowns']['null_sport_key_markets'] == 1 and out['unknowns']['null_sport_key_game_groups'] == 1

    def test_unknown_volume_is_not_untraded(self):
        c = passing_core(exclude=['basketball_nba']).add_games('basketball_nba', 1)
        c.add(market('basketball_nba', ML, outcomes=4, well=0, vol_pos=0, vol_null=4))
        ml = c.grade()['sports']['basketball_nba']['classes']['moneyline']
        assert (ml['vol_pos'], ml['vol_null_outcomes']) == (0, 4)


class TestEsports:
    def test_absent_esports_is_unknown_not_zero(self):
        out = passing_core().grade()
        assert out['esports']['status'] == 'UNKNOWN' and out['esports']['sport_keys'] == []
        assert out['verdict'] == 'PASS'   # CORE acceptance is reported apart from esports coverage

    def test_every_esports_key_is_listed_and_reported_ungraded(self):
        c = passing_core().add_games('esports', 2).add_games('esports_lol', 1)
        c.add(market('esports', SEGMENT), market('esports', OTHER), market('esports_lol', OTHER))
        out = c.grade()
        assert out['esports']['status'] == 'OBSERVED'
        assert out['esports']['sport_keys'] == ['esports', 'esports_lol']
        assert out['sports']['esports']['verdict'] == 'NOT_GRADED_NOT_CORE'
        assert out['sports']['esports']['other_share'] == {'num': 1, 'den': 2}
        assert out['verdict'] == 'PASS'


class TestSeasonIsSeparate:
    def test_a_preseason_shortfall_still_fails_the_full_window_and_the_split_is_reported_beside_it(self):
        c = passing_core(exclude=['americanfootball_nfl'])
        c.add_games('americanfootball_nfl', 10).add(*[market('americanfootball_nfl', ML) for _ in range(10)])
        c.add_games('americanfootball_nfl', 6, day=NFL_PRESEASON_DAY)   # preseason: no winner markets
        out = c.grade()
        nfl = out['sports']['americanfootball_nfl']
        assert nfl['moneyline_per_game'] == {'num': 10, 'den': 16} and nfl['verdict'] == 'FAIL'
        assert out['verdict'] == 'FAIL'
        split = out['season_breakdown']['sports']['americanfootball_nfl']
        assert (split['window_games'], split['in_season_games'], split['excluded_games']) == (16, 10, 6)
        assert split['in_season_markets_by_class']['moneyline'] == 10
        assert out['acceptance_population'] == 'full window'


class TestNoResult:
    @pytest.mark.parametrize('missing', ['games_rows', 'market_rows', 'source_rows', 'fixture_day_rows'])
    def test_a_missing_result_set_is_no_result(self, missing):
        out = passing_core().grade(**{missing: None})
        assert out['verdict'] == 'NO_RESULT'
        assert out['reconciliation']['failures'][0]['code'] == 'MISSING_RESULT'
        assert 'sports' not in out and 'core_verdicts' not in out

    def _rows(self):
        return passing_core().rows()

    def test_a_truncated_or_short_row_is_no_result(self):
        rows = self._rows()
        rows['market_rows'][3] = rows['market_rows'][3][:8]   # the pre-#1529 arity
        assert passing_core().grade(market_rows=rows['market_rows'])['verdict'] == 'NO_RESULT'

    @pytest.mark.parametrize('bad', [None, True, 1.0, -1, '2'])
    def test_a_non_integer_or_negative_counter_is_no_result(self, bad):
        rows = self._rows()
        row = list(rows['market_rows'][0])
        row[3] = bad
        rows['market_rows'][0] = tuple(row)
        out = passing_core().grade(market_rows=rows['market_rows'])
        assert out['verdict'] == 'NO_RESULT' and out['reconciliation']['failures'][0]['code'] == 'MALFORMED_COUNTER'

    def test_a_zero_outcome_row_whose_null_volume_is_not_exactly_one_is_no_result(self):
        rows = self._rows()
        row = list(rows['market_rows'][0])
        row[3:8] = [0, 0, 0, 0, 0]
        rows['market_rows'][0] = tuple(row)
        assert passing_core().grade(market_rows=rows['market_rows'])['verdict'] == 'NO_RESULT'

    def test_a_zero_outcome_row_with_no_null_volume_row_is_no_result_even_when_the_sums_agree(self):
        # Its own source group is dropped by the HAVING, so only the row invariant can see it.
        c = passing_core().add_games('baseball_mlb', 1).add(market('baseball_mlb', ML, outcomes=0, source='polymarket'))
        rows = c.rows()
        row = list(rows['market_rows'][-1])
        assert row[3] == 0 and row[6] == 1
        row[6] = 0
        rows['market_rows'][-1] = tuple(row)
        out = c.grade(market_rows=rows['market_rows'])
        assert out['verdict'] == 'NO_RESULT' and out['reconciliation']['failures'][0]['code'] == 'MALFORMED_COUNTER'

    def test_more_well_traded_than_outcomes_is_no_result_even_when_the_sums_agree(self):
        out = passing_core().add_games('baseball_mlb', 1).add(market('baseball_mlb', ML, outcomes=2, well=3)).grade()
        assert out['verdict'] == 'NO_RESULT' and out['reconciliation']['failures'][0]['code'] == 'MALFORMED_COUNTER'

    def test_a_vol_null_gap_wider_than_the_zero_outcome_markets_is_no_result(self):
        c = passing_core().add_games('baseball_mlb', 1).add(market('baseball_mlb', ML, outcomes=4, vol_pos=2, vol_null=2))
        rows = c.rows()
        i = next(i for i, r in enumerate(rows['source_rows']) if r[:2] == ('baseball_mlb', 'kalshi'))
        sport, source, outc, well, volp, voln, art = rows['source_rows'][i]
        rows['source_rows'][i] = (sport, source, outc, well, volp, voln - 1, art)
        out = c.grade(source_rows=rows['source_rows'])
        assert out['verdict'] == 'NO_RESULT'
        assert out['reconciliation']['failures'][0]['field'] == 'vol_null_raw'

    def test_duplicate_groups_are_no_result(self):
        rows = self._rows()
        out = passing_core().grade(games_rows=rows['games_rows'] + rows['games_rows'][:1])
        assert out['reconciliation']['failures'][0]['code'] == 'DUPLICATE_GROUP'

    @pytest.mark.parametrize('field,row', [
        ('games_rows', ('tennis_atp', 0)),
        ('fixture_day_rows', ('tennis_atp', DAY, 0)),
        ('source_rows', ('baseball_mlb', 'odds_api', 0, 0, 0, 0, 0)),
    ])
    def test_an_empty_group_the_statement_cannot_return_is_no_result(self, field, row):
        rows = self._rows()
        out = passing_core().grade(**{field: rows[field] + [row]})
        assert out['verdict'] == 'NO_RESULT' and out['reconciliation']['failures'][0]['code'] == 'EMPTY_GROUP'

    def test_fixture_days_that_do_not_sum_to_games_are_no_result(self):
        rows = self._rows()
        out = passing_core().grade(fixture_day_rows=rows['fixture_day_rows'][1:])
        assert out['verdict'] == 'NO_RESULT'
        assert out['reconciliation']['failures'][0]['code'] == 'FIXTURE_DAYS_DISAGREE_WITH_GAMES'

    def test_markets_for_a_sport_without_games_are_no_result(self):
        out = passing_core().add(market('tennis_atp', OTHER)).grade()
        assert out['verdict'] == 'NO_RESULT'
        assert {f['code'] for f in out['reconciliation']['failures']} >= {'MARKETS_WITHOUT_GAMES'}

    def test_a_market_on_a_day_the_fixture_days_never_list_is_no_result(self):
        out = passing_core().add(market('baseball_mlb', ML, day=date(2026, 10, 1))).grade()
        assert 'MARKET_DAY_NOT_IN_FIXTURE_DAYS' in {f['code'] for f in out['reconciliation']['failures']}

    def test_a_source_split_that_disagrees_with_the_markets_is_no_result(self):
        rows = self._rows()
        sport, source, outc, *rest = rows['source_rows'][0]
        rows['source_rows'][0] = (sport, source, outc + 1, *rest)
        out = passing_core().grade(source_rows=rows['source_rows'])
        assert out['verdict'] == 'NO_RESULT'
        assert out['reconciliation']['failures'][0]['field'] == 'outcomes'

    def test_the_vol_null_gap_is_allowed_only_for_zero_outcome_markets_the_having_dropped(self):
        # Control: one zero-outcome market from a source with no other outcomes - its
        # group is dropped by the HAVING, and its one NULL row is the whole gap.
        ok = passing_core().add(market('baseball_mlb', ML, outcomes=0, source='polymarket'))
        ok.add_games('baseball_mlb', 1)
        out = ok.grade()
        assert out['reconciliation']['ok'] is True, out['reconciliation']
        rows = passing_core().rows()
        sport, source, outc, well, volp, voln, art = rows['source_rows'][0]
        rows['source_rows'][0] = (sport, source, outc, well, volp, voln + 1, art)
        bad = passing_core().grade(source_rows=rows['source_rows'])
        assert bad['verdict'] == 'NO_RESULT'
        assert bad['reconciliation']['failures'][0]['field'] == 'vol_null_raw'

    def test_a_source_split_for_a_sport_without_games_is_no_result(self):
        rows = self._rows()
        out = passing_core().grade(source_rows=rows['source_rows'] + [('tennis_atp', 'kalshi', 3, 0, 0, 0, 0)])
        assert 'SOURCE_SPLIT_WITHOUT_GAMES' in {f['code'] for f in out['reconciliation']['failures']}

    @pytest.mark.parametrize('window', [0, -30, 30.0, True, None])
    def test_a_malformed_window_is_no_result(self, window):
        assert passing_core().grade(window_days=window)['verdict'] == 'NO_RESULT'

    def test_a_result_set_given_as_a_string_is_no_result(self):
        assert passing_core().grade(games_rows='baseball_mlb,10')['verdict'] == 'NO_RESULT'
