"""#1011 — soccer accuracy is graded on the home/draw/away question the market quoted.

Since release v4636 (2026-09-16T17:43:41Z) the sportsbook writer de-vigs a game
winner over every outcome the book quotes, so a soccer pair keeps the draw as
``1 - home - away``. The accuracy curve still treated every soccer moneyline row
as the pre-v4636 two-way pair and excluded all of it. These tests pin the three
places that now read the stored contract instead:

* the pure contract (``app/utils/soccer_three_way.py``), fed by the REAL writer
  (``odds_polling._parse_snapshot_values``) on provider-shaped boards, so the
  reader is tested against what the writer actually stores — not a hand-made
  pair that happens to sum to 0.74;
* the per-sportsbook writer, which grades soccer three-way in its own walk and
  stamps those buckets;
* the curve reader, which publishes a soccer bucket only when it carries the
  stamp — so a two-way bucket from an older writer can never be read as a
  three-way one.

The SQL is executed against real Postgres in
``tests/integration/test_calibration_soccer_three_way_1011_pg.py``.
"""
from __future__ import annotations

import asyncio
import json
import time as _real_time
from datetime import datetime, timedelta, timezone

import pytest

import app.tasks.backfill_winners as bw
import app.tasks.precompute_calibration as pc
from app.tasks.odds_polling import _parse_snapshot_values
from app.utils import soccer_three_way as stw

AFTER = stw.SOCCER_THREE_WAY_SINCE + timedelta(days=3)
BEFORE = stw.SOCCER_THREE_WAY_SINCE - timedelta(days=3)


def _board(home, away, outcomes):
    """One bookmaker's h2h board, in The Odds API's shape."""
    return (
        {"key": "draftkings",
         "markets": [{"key": "h2h", "outcomes": [
             {"name": name, "price": price} for name, price in outcomes]}]},
        {"home_team": home, "away_team": away, "sport_key": "soccer_epl"},
    )


#: FC St Gallen v FC Sion (live/163's specimen, 15305934): the venue's own
#: three-way block read St Gallen 45 / Sion 30 / Draw 26.
SOCCER_BOARD = _board("FC St Gallen", "FC Sion",
                      [("FC St Gallen", 120), ("FC Sion", 230), ("Draw", 250)])
#: Limited-overs cricket is a complete TWO-way market (production reads its raw
#: pair at ~1.057, live/333). It must never be graded three-way.
CRICKET_BOARD = _board("India", "Australia", [("India", -150), ("Australia", 125)])


def _stored(board):
    values = _parse_snapshot_values(*board)
    return values["home_win_probability"], values["away_win_probability"]


# --- the contract, against what the writer stores -------------------------


def test_the_writer_stores_a_soccer_pair_that_keeps_the_draw():
    home, away = _stored(SOCCER_BOARD)
    assert stw.pair_keeps_the_draw(home, away)
    # The venue's block read draw 26; the de-vigged remainder lands beside it.
    assert 0.25 < stw.draw_residual(home, away) < 0.29


@pytest.mark.parametrize("home_score,away_score,winner", [
    (2, 1, 0), (0, 3, 1), (1, 1, 2), (0, 0, 2),
])
def test_one_reading_grades_three_outcomes_and_exactly_one_wins(
        home_score, away_score, winner):
    home, away = _stored(SOCCER_BOARD)
    graded = stw.three_way_outcomes(home, away, home_score, away_score, AFTER,
                                    regulation_proven=True)
    assert graded is not None and len(graded) == 3
    assert sum(p for p, _ in graded) == pytest.approx(1.0)
    assert [won for _, won in graded] == [i == winner for i in range(3)]


def test_a_drawn_match_is_a_win_for_the_draw_not_two_losses():
    home, away = _stored(SOCCER_BOARD)
    graded = stw.three_way_outcomes(home, away, 1, 1, AFTER, regulation_proven=True)
    assert graded[2] == (pytest.approx(stw.draw_residual(home, away)), True)
    assert not graded[0][1] and not graded[1][1]


def test_a_two_way_board_is_never_graded_three_way():
    home, away = _stored(CRICKET_BOARD)
    assert home + away == pytest.approx(1.0, abs=1e-4)
    assert not stw.pair_keeps_the_draw(home, away)
    assert stw.three_way_outcomes(home, away, 250, 240, AFTER,
                                  regulation_proven=True) is None


def test_a_pre_v4636_renormalized_pair_is_not_three_way():
    # What the writer stored before v4636: the named pair divided by its own
    # sum and rounded to four places — the draw folded into both sides.
    h, a = 0.4545, 0.3030
    home, away = round(h / (h + a), 4), round(a / (h + a), 4)
    assert abs(stw.draw_residual(home, away)) <= 1e-4
    assert stw.three_way_outcomes(home, away, 1, 1, AFTER,
                                  regulation_proven=True) is None


def test_a_reading_from_before_the_cutoff_is_refused_even_if_it_keeps_the_draw():
    home, away = _stored(SOCCER_BOARD)
    assert stw.three_way_outcomes(home, away, 2, 0, BEFORE,
                                  regulation_proven=True) is None
    assert stw.three_way_outcomes(
        home, away, 2, 0, stw.SOCCER_THREE_WAY_SINCE,
        regulation_proven=True) is not None


def test_the_draw_remainder_floor_is_inclusive_and_separates_rounding():
    assert stw.pair_keeps_the_draw(0.50, 0.49)            # exactly 0.01
    assert not stw.pair_keeps_the_draw(0.50, 0.4901)
    assert not stw.pair_keeps_the_draw(0.0, 0.5)          # a missing leg
    assert not stw.pair_keeps_the_draw(None, 0.3)
    assert stw.three_way_outcomes(0.45, 0.30, None, 1, AFTER,
                                  regulation_proven=True) is None


def test_the_cutoff_is_the_v4636_release_minute():
    assert stw.SOCCER_THREE_WAY_SINCE == datetime(
        2026, 9, 16, 17, 43, 41, tzinfo=timezone.utc)
    assert stw.SOCCER_THREE_WAY_PARAMS == {
        "soccer_three_way_since": stw.SOCCER_THREE_WAY_SINCE,
        "soccer_draw_residual_min": stw.SOCCER_DRAW_RESIDUAL_MIN,
        "soccer_regulation_period": "FT",
        "soccer_regulation_status": "STATUS_FULL_TIME",
    }


# --- CERT-4066: the score graded is the 90-minute score ----------------------


def test_an_extra_time_final_is_not_graded_even_when_everything_else_holds():
    """Level 1-1 after 90, won 2-1 in extra time: the market's answer is the
    draw, the stored final says home. Without a full-time proof, no grade."""
    home, away = _stored(SOCCER_BOARD)
    assert stw.three_way_outcomes(home, away, 2, 1, AFTER,
                                  regulation_proven=False) is None
    with pytest.raises(TypeError):
        stw.three_way_outcomes(home, away, 2, 1, AFTER)  # the proof is required


@pytest.mark.parametrize("period,status,proven", [
    ("FT", None, True),
    (None, "STATUS_FULL_TIME", True),
    ("FT", "STATUS_FULL_TIME", True),
    ("AET", "STATUS_FINAL_AET", False),
    (None, "STATUS_FINAL_PEN", False),
    ("ft", None, False),            # exact: an unexpected spelling refuses
    ("FT ", None, False),
    ("90+4", None, False),          # a live token left behind
    (None, None, False),            # nothing says how the match ended
    ("2nd Half", "STATUS_IN_PROGRESS", False),
])
def test_only_the_rows_own_full_time_statement_proves_regulation(
        period, status, proven):
    assert stw.regulation_finish_proven(period, status) is proven


# --- the curve reader -------------------------------------------------------


class _Redis:
    def __init__(self, rows):
        self._value = json.dumps(rows)

    def get(self, key):
        return self._value


def _bucket(category, n, **extra):
    return {"bucket_idx": 3, "source": "odds_api_bookmaker", "category": category,
            "price_moved": None, "n": n, "winners": n // 3,
            "avg_prob": 0.33, "sum_prob": n * 0.33, "sum_sq_err": n * 0.2, **extra}


def test_the_reader_publishes_a_soccer_bucket_only_with_the_three_way_stamp():
    stamp = {stw.SOCCER_THREE_WAY_CONTRACT_KEY: stw.SOCCER_THREE_WAY_CONTRACT}
    raw = [
        _bucket("basketball_nba", 40),
        _bucket("soccer_epl", 90),                   # two-way reading
        _bucket("soccer_epl", 30, **stamp),          # three-way reading
        _bucket("soccer_spain_la_liga", 12, **{stw.SOCCER_THREE_WAY_CONTRACT_KEY:
                                               "soccer_three_way/v0"}),
    ]
    rows, excluded, degraded = pc.read_bookmaker_curve_rows(
        _Redis(raw), refuse=True)
    assert degraded is None
    assert sorted((r.category, r.n) for r in rows) == [
        ("basketball_nba", 40), ("soccer_epl", 30)]
    # The unstamped two-way bucket and the wrong-version stamp are excluded and
    # COUNTED, never silently dropped.
    assert excluded == 90 + 12


def test_an_old_writer_payload_publishes_no_soccer_at_all():
    """Rollout: a key written before this ship carries no stamps."""
    raw = [_bucket("soccer_epl", 90), _bucket("icehockey_nhl", 10)]
    rows, excluded, _ = pc.read_bookmaker_curve_rows(_Redis(raw), refuse=True)
    assert [r.category for r in rows] == ["icehockey_nhl"]
    assert excluded == 90


# --- the per-sportsbook writer ---------------------------------------------


class _Cell:
    def __init__(self, category, bucket_start):
        self.category = category
        self.bucket_start = bucket_start


class _Row:
    def __init__(self, idx, category, n, winners, sum_prob, sum_sq_err):
        self.bucket_idx, self.category, self.n = idx, category, n
        self.winners, self.sum_prob, self.sum_sq_err = winners, sum_prob, sum_sq_err


class _BankRedis:
    def __init__(self):
        self.curve = None
        self.hashes: dict[str, dict[str, str]] = {}

    def setex(self, key, ttl, value):
        self.curve = (key, ttl, value)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def expire(self, key, ttl):
        return None


SEPT = datetime(2026, 9, 1, tzinfo=timezone.utc)
AUG = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _run_writer(monkeypatch, *, main_grid, soccer_grid, redis):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(_real_time, "monotonic", lambda: clock["t"])
    calls = {"two_way": [], "three_way": [], "soccer_grid_params": None}

    class _Result:
        def __init__(self, payload):
            self._payload = payload

        def first(self):
            return None

        def all(self):
            return self._payload

    class _Session:
        async def execute(self, statement, params=None, *a, **k):
            sql = str(statement)
            if "SET LOCAL statement_timeout" in sql:
                return _Result([])
            # #1479: the per-transaction session tag, not a chunk.
            if "set_config('application_name'" in sql:
                return _Result([])
            if "date_trunc('month'" in sql:
                if "soccer_three_way_since" in sql:
                    calls["soccer_grid_params"] = params
                    return _Result(list(soccer_grid))
                return _Result(list(main_grid))
            clock["t"] += 1.0
            cat, lo = params["category"], params["lo"]
            if "soccer_draw_residual_min" in sql:
                assert params["soccer_three_way_since"] == stw.SOCCER_THREE_WAY_SINCE
                calls["three_way"].append((cat, lo))
                # 4 readings x 3 outcomes; one winner per reading.
                return _Result([_Row(3, cat, 12, 4, 4.0, 2.4)])
            calls["two_way"].append((cat, lo))
            return _Result([_Row(5, cat, 20, 11, 10.0, 4.0)])

        async def rollback(self):
            return None

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def _publish(envelope):
        return {"status": "ok", "identity": envelope.identity,
                "generation": envelope.generation}

    monkeypatch.setattr(
        "app.services.durable_snapshots.publish_snapshot_standalone", _publish)
    session = _Session()
    monkeypatch.setattr(bw, "get_task_session", lambda: session)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client",
                        lambda *a, **k: redis)
    summary = asyncio.run(bw._precompute_bookmaker_calibration())
    return summary, calls


def test_the_writer_grades_soccer_three_way_and_stamps_only_those_buckets(
        monkeypatch):
    redis = _BankRedis()
    summary, calls = _run_writer(
        monkeypatch,
        main_grid=[_Cell("soccer_epl", AUG), _Cell("soccer_epl", SEPT),
                   _Cell("basketball_nba", SEPT)],
        # A non-soccer row in the soccer grid must be ignored, never graded
        # three-way, whatever the statement returned.
        soccer_grid=[_Cell("soccer_epl", SEPT), _Cell("basketball_nba", SEPT)],
        redis=redis,
    )
    assert summary["terminal"] == "complete", summary["errors"]
    assert calls["three_way"] == [("soccer_epl", SEPT)]
    assert calls["soccer_grid_params"] == stw.SOCCER_THREE_WAY_PARAMS
    # The two-way walk is untouched: it still reads every grid cell.
    assert sorted(calls["two_way"]) == sorted(
        [("soccer_epl", AUG), ("soccer_epl", SEPT), ("basketball_nba", SEPT)])

    buckets = json.loads(redis.curve[2])
    stamped = [b for b in buckets if stw.SOCCER_THREE_WAY_CONTRACT_KEY in b]
    assert [(b["category"], b["bucket_idx"], b["n"], b["winners"])
            for b in stamped] == [("soccer_epl", 3, 12, 4)]
    assert stamped[0][stw.SOCCER_THREE_WAY_CONTRACT_KEY] == stw.SOCCER_THREE_WAY_CONTRACT
    # The two-way soccer reading (AUG + SEPT folded) is still emitted, unstamped
    # and kept apart — same (bucket, category) keys never merge across contracts.
    two_way_soccer = [b for b in buckets if b["category"] == "soccer_epl"
                      and stw.SOCCER_THREE_WAY_CONTRACT_KEY not in b]
    assert [(b["bucket_idx"], b["n"]) for b in two_way_soccer] == [(5, 40)]
    assert summary["soccer_three_way"]["outcomes"] == 12

    # And end to end: what the reader publishes for soccer is the stamped bucket.
    rows, excluded, _ = pc.read_bookmaker_curve_rows(_Redis(buckets), refuse=True)
    assert sorted((r.category, r.n) for r in rows) == [
        ("basketball_nba", 20), ("soccer_epl", 12)]
    assert excluded == 40


def test_soccer_cells_bank_under_their_own_statement_digest(monkeypatch):
    assert bw._BOOKMAKER_SOCCER_BANK_KEY != bw._BOOKMAKER_BANK_KEY
    redis = _BankRedis()
    old = datetime(2026, 9, 1, tzinfo=timezone.utc)
    # Pretend the clock is far enough on that September is settled and banked.
    monkeypatch.setattr(bw, "_bookmaker_cell_settled", lambda lo, now: True)
    _run_writer(monkeypatch, main_grid=[], soccer_grid=[_Cell("soccer_epl", old)],
                redis=redis)
    assert list(redis.hashes) == [bw._BOOKMAKER_SOCCER_BANK_KEY]
    # A second run carries the soccer cell from ITS bank and re-reads nothing.
    summary, calls = _run_writer(monkeypatch, main_grid=[],
                                 soccer_grid=[_Cell("soccer_epl", old)], redis=redis)
    assert calls["three_way"] == []
    assert summary["soccer_three_way"]["carried"] == 1
    assert summary["soccer_three_way"]["outcomes"] == 12


def test_a_soccer_cell_that_does_not_land_fails_the_whole_key_closed(monkeypatch):
    monkeypatch.setattr(bw, "_TRAVERSAL_BUDGET_S", 1.0)
    redis = _BankRedis()
    summary, calls = _run_writer(
        monkeypatch, main_grid=[_Cell("basketball_nba", SEPT)],
        soccer_grid=[_Cell("soccer_epl", SEPT)], redis=redis)
    assert calls["three_way"] == []
    assert summary["terminal"] == "failed" and summary["budget_exhausted"]
    assert redis.curve is None
    assert "soccer_epl" in " ".join(summary["errors"])


# --- the build's own inputs -------------------------------------------------


def test_the_build_fingerprint_moves_with_the_contract_values(monkeypatch):
    before = pc._main_input_fingerprint()
    monkeypatch.setattr(pc, "SOCCER_THREE_WAY_SINCE",
                        stw.SOCCER_THREE_WAY_SINCE + timedelta(hours=1))
    assert pc._main_input_fingerprint() != before
    monkeypatch.undo()
    monkeypatch.setattr(pc, "SOCCER_DRAW_RESIDUAL_MIN", 0.02)
    assert pc._main_input_fingerprint() != before


def test_the_events_curve_reads_soccer_only_through_the_three_way_branch():
    import inspect

    src = inspect.getsource(pc.compute_calibration_payload)
    events_sql = src.split('events_sql = text("""', 1)[1].split('""")', 1)[0]
    branch = events_sql.split("TRUE AS three_way", 1)[1]
    # The opening pair, never the closing one (its away leg is 1 - home).
    assert "opening_home_probability" in branch
    assert "closing_" not in branch.split(") outcomes", 1)[0]
    assert "WHERE (s.key NOT LIKE 'soccer_%' OR outcomes.three_way)" in events_sql
    assert '""").bindparams(**SOCCER_THREE_WAY_PARAMS)\n        events_rows' in src
