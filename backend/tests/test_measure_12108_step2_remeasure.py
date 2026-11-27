"""Unit tests for Decision 448: A Step 2 calibration re-measurement script (#12108)."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import measure_12108_step2_remeasure as step2

UTC = timezone.utc


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _snap(
    *,
    snap_id: int,
    raw_source: str,
    league: str,
    captured_at: datetime,
    prob: float,
    commence_time: datetime,
    completed_at: datetime | None = None,
    valid_until: datetime | None = None,
    game_state: dict | None = None,
    max_cap: datetime | None = None,
) -> dict:
    flags = step2.classify_snapshot_exclusions(
        raw_source=raw_source,
        league=league,
        captured_at=captured_at,
        valid_until=valid_until,
        prob=prob,
        game_state=game_state,
        commence_time=commence_time,
        completed_at=completed_at,
        max_captured_at_for_source=max_cap if max_cap is not None else captured_at,
    )
    return {
        "snap_id": snap_id,
        "raw_source": raw_source,
        "captured_at": captured_at,
        "valid_until": valid_until,
        "prob": prob,
        "game_state": game_state,
        "flags": flags,
        "excluded": any(flags.values()),
    }


def _build_synthetic_obs() -> dict:
    """Build deterministic multi-cluster Option B synthetic dataset (100% in-memory)."""
    # 4 NBA clusters (2 events/cluster -> 8) + 2 MLB clusters (1 event/cluster -> 2) = 10 events.
    base = _dt(2026, 10, 15, 23, 0)
    wp_events = []
    esm_rows_by_eid_src: dict[int, dict[str, list[dict]]] = {}
    wp_by_eh: dict[tuple[int, str], dict[str, dict]] = {}
    odds_by_eh: dict[tuple[int, str], list[dict]] = {}
    wrong_start_by_eid: dict[int, dict[str, bool]] = {}

    for i in range(10):
        eid = 1000 + i
        start = base + timedelta(days=i * 5)
        is_mlb = i >= 8
        league = "baseball_mlb" if is_mlb else "basketball_nba"
        sport_group = "Baseball" if is_mlb else "Basketball"
        # Alternate outcomes cleanly so both classes have support.
        home_won = (i % 2 == 0) if i < 6 else (i % 3 == 0)
        home_team = f"HomeTeam{i % 4}" if not is_mlb else f"MLBHome{i}"
        away_team = f"AwayTeam{i % 4}" if not is_mlb else f"MLBAway{i}"
        # Give event 1002 wrong start (`score_observed_at < start`), leave others clean.
        score_obs = start - timedelta(minutes=25) if i == 2 else start + timedelta(minutes=45)
        completed_at = start + timedelta(hours=3)
        ev = {
            "event_id": eid,
            "start": start,
            "completed_at": completed_at,
            "score_observed_at": score_obs,
            "home_team_name": home_team,
            "away_team_name": away_team,
            "home_score": 105 if home_won else 94,
            "away_score": 94 if home_won else 105,
            "league": league,
            "sport_group": sport_group,
        }
        wp_events.append(ev)
        wrong_start_by_eid[eid] = step2.classify_wrong_start(
            ev, has_prestart_inplay_wp=(i == 4)
        )

        # True signal strength: Blend slightly sharper than PM Avg cleanly.
        p_pm_k = 0.62 if home_won else 0.38
        p_pm_p = 0.60 if home_won else 0.40
        p_espn_clean = 0.68 if home_won else 0.32
        p_book = 0.70 if home_won else 0.30

        esm_rows_by_eid_src[eid] = {}
        t_clean_espn = start - timedelta(hours=25)
        t_clean_espn_1h = start - timedelta(hours=2)
        if i == 0:
            # Latest pre-T-1h ESPN row is E3 estimated backfill; earlier clean row exists -> fallback!
            e3_time = start - timedelta(minutes=70)
            espn_list = [
                _snap(
                    snap_id=10,
                    raw_source="espn",
                    league=league,
                    captured_at=t_clean_espn,
                    prob=p_espn_clean,
                    commence_time=start,
                    completed_at=completed_at,
                    max_cap=start + timedelta(hours=2),
                ),
                _snap(
                    snap_id=11,
                    raw_source="espn",
                    league=league,
                    captured_at=e3_time,
                    prob=0.95,
                    commence_time=start,
                    completed_at=completed_at,
                    game_state={"backfilled": True, "seconds_left": 1800},
                    max_cap=start + timedelta(hours=2),
                ),
            ]
        elif i == 1:
            # All ESPN rows before T-1h are E3 -> dropped at T-1h and earlier.
            espn_list = [
                _snap(
                    snap_id=20,
                    raw_source="espn",
                    league=league,
                    captured_at=start - timedelta(hours=26),
                    prob=0.90,
                    commence_time=start,
                    completed_at=completed_at,
                    game_state={"backfilled": True, "seconds_left": 1200},
                    max_cap=start + timedelta(hours=2),
                ),
            ]
        else:
            espn_list = [
                _snap(
                    snap_id=100 + i,
                    raw_source="espn",
                    league=league,
                    captured_at=t_clean_espn,
                    prob=p_espn_clean,
                    commence_time=start,
                    completed_at=completed_at,
                    max_cap=start + timedelta(hours=2),
                ),
                _snap(
                    snap_id=200 + i,
                    raw_source="espn",
                    league=league,
                    captured_at=t_clean_espn_1h,
                    prob=p_espn_clean,
                    commence_time=start,
                    completed_at=completed_at,
                    max_cap=start + timedelta(hours=2),
                ),
            ]
        esm_rows_by_eid_src[eid]["espn"] = espn_list

        # Event 3 carries a stat_model < start (E5b) at T-1h, excluded from Panel B.
        if i == 3:
            sm_time = start - timedelta(hours=2)
            sm_row = _snap(
                snap_id=300 + i,
                raw_source="stat_model",
                league=league,
                captured_at=sm_time,
                prob=0.80,
                commence_time=start,
                completed_at=completed_at,
                max_cap=sm_time,
            )
            esm_rows_by_eid_src[eid]["stat_model"] = [sm_row]

        # MLB game 8 uses MLB Stats API; MLB game 9 has E5a clamped mlb + clean fangraphs fallback.
        if is_mlb:
            if i == 8:
                mlb_row = _snap(
                    snap_id=400 + i,
                    raw_source="mlb",
                    league=league,
                    captured_at=start - timedelta(hours=2),
                    prob=0.66 if home_won else 0.34,
                    commence_time=start,
                    completed_at=completed_at,
                    max_cap=start + timedelta(hours=2),
                )
                esm_rows_by_eid_src[eid]["mlb"] = [mlb_row]
            else:
                mlb_bad = _snap(
                    snap_id=410 + i,
                    raw_source="mlb",
                    league=league,
                    captured_at=start - timedelta(hours=2),
                    prob=0.9999,
                    commence_time=start,
                    completed_at=completed_at,
                    valid_until=start + timedelta(hours=4),
                    max_cap=start - timedelta(hours=2),
                )
                fg_good = _snap(
                    snap_id=420 + i,
                    raw_source="fangraphs",
                    league=league,
                    captured_at=start - timedelta(hours=3),
                    prob=0.65 if home_won else 0.35,
                    commence_time=start,
                    completed_at=completed_at,
                    max_cap=start + timedelta(hours=2),
                )
                esm_rows_by_eid_src[eid]["mlb"] = [mlb_bad]
                esm_rows_by_eid_src[eid]["fangraphs"] = [fg_good]

        for h_name, _ in step2.HORIZONS:
            h_map: dict[str, dict] = {
                "kalshi": {
                    "prob": p_pm_k,
                    "captured_at": start - timedelta(hours=25),
                    "valid_until": None,
                },
                "polymarket": {
                    "prob": p_pm_p,
                    "captured_at": start - timedelta(hours=25),
                    "valid_until": None,
                },
                # Raw `wp_by_eh` stores latest raw row at cutoff.
                "espn": {
                    "prob": espn_list[-1]["prob"]
                    if not (i == 0 and h_name in ("t_minus_6h", "t_minus_24h"))
                    else espn_list[0]["prob"],
                    "captured_at": espn_list[-1]["captured_at"]
                    if not (i == 0 and h_name in ("t_minus_6h", "t_minus_24h"))
                    else espn_list[0]["captured_at"],
                    "valid_until": None,
                },
            }
            if i == 3:
                h_map["stat_model"] = {
                    "prob": 0.80,
                    "captured_at": start - timedelta(hours=2),
                    "valid_until": None,
                }
            if is_mlb:
                h_map["mlb"] = {
                    "prob": esm_rows_by_eid_src[eid]["mlb"][-1]["prob"],
                    "captured_at": esm_rows_by_eid_src[eid]["mlb"][-1]["captured_at"],
                    "valid_until": esm_rows_by_eid_src[eid]["mlb"][-1]["valid_until"],
                }
            wp_by_eh[(eid, h_name)] = h_map
            odds_by_eh[(eid, h_name)] = [
                {
                    "bookmaker": "draftkings",
                    "captured_at": start - timedelta(hours=25),
                    "valid_until": None,
                    "home_win_probability": p_book,
                }
            ]

    cluster_by_eid = step2.assign_series_clusters(wp_events)
    cutoffs_by_eid = {
        ev["event_id"]: [(h, ev["start"] - delta) for h, delta in step2.HORIZONS]
        for ev in wp_events
    }
    all_eids = {ev["event_id"] for ev in wp_events}
    # Simulate 411: A sample containing only events 1000..1007 while Option B has all 1000..1009.
    odds_411a_eids = set(range(1000, 1008))

    return {
        "timed_out": False,
        "stopped_early": False,
        "stop_reason": None,
        "stop_stage": None,
        "database": "synthetic_unit_test",
        "ceiling": step2._PRE_NOV6_ISO,
        "wp_statement_timeout_s": 120,
        "odds_statement_timeout_s": 30,
        "batch_pause_s": 0.0,
        "max_read_duration_s": 3600.0,
        "odds_max_single_batch_s": 15.0,
        "odds_first_n_avg_count": 0,
        "odds_first_n_avg_max_s": 3.0,
        "odds_batch_max_s": 0.1,
        "odds_batch_median_s": 0.1,
        "odds_first_5_avg_s": 0.1,
        "events_total": len(wp_events),
        "wp_events_read": len(wp_events),
        "wp_batches_done": 1,
        "wp_batches_total": 1,
        "wrong_start_batches_done": 1,
        "wrong_start_batches_total": 1,
        "esm_detail_batches_done": 1,
        "esm_detail_batches_total": 1,
        "esm_events_count": len(wp_events),
        "odds_target_pm": len(wp_events),
        "odds_target_non_pm_pool": 0,
        "odds_target_non_pm_sample": 0,
        "odds_events_read": len(wp_events),
        "odds_batches_done": 1,
        "odds_batches_total": 1,
        "events_read": len(wp_events),
        "clusters_read": len(set(cluster_by_eid.values())),
        "batches_total": 2,
        "statements_executed": 4,
        "elapsed_s": 0.5,
        "wp_events": wp_events,
        "cluster_by_eid": cluster_by_eid,
        "cutoffs_by_eid": cutoffs_by_eid,
        "wp_by_eh": wp_by_eh,
        "esm_rows_by_eid_src": esm_rows_by_eid_src,
        "odds_fetched_eids": all_eids,
        "odds_411a_eids": odds_411a_eids,
        "odds_by_eh": odds_by_eh,
        "wrong_start_by_eid": wrong_start_by_eid,
    }


class TestSnapshotExclusions:
    def test_e1_and_e2_espn_date_cutoffs(self) -> None:
        start = _dt(2026, 10, 1, 0, 0)
        r_before_e1 = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="baseball_mlb",
            captured_at=_dt(2026, 9, 16, 23, 59),
            valid_until=None,
            prob=0.55,
            game_state=None,
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert r_before_e1["E1"] is True
        assert r_before_e1["E2"] is True

        r_between_e1_e2 = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="baseball_mlb",
            captured_at=_dt(2026, 9, 17, 0, 0),
            valid_until=None,
            prob=0.55,
            game_state=None,
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert r_between_e1_e2["E1"] is False
        assert r_between_e1_e2["E2"] is True

        r_after_e2 = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="baseball_mlb",
            captured_at=_dt(2026, 9, 20, 6, 0),
            valid_until=None,
            prob=0.55,
            game_state=None,
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert r_after_e2["E1"] is False
        assert r_after_e2["E2"] is False

        r_non_espn = step2.classify_snapshot_exclusions(
            raw_source="mlb",
            league="baseball_mlb",
            captured_at=_dt(2026, 9, 15, 0, 0),
            valid_until=None,
            prob=0.55,
            game_state=None,
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert not any(r_non_espn.values())

    def test_e3_espn_estimated_backfill_vs_play_wallclock(self) -> None:
        start = _dt(2026, 10, 5, 20, 0)
        cap = _dt(2026, 10, 5, 19, 0)
        bad = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="basketball_nba",
            captured_at=cap,
            valid_until=None,
            prob=0.60,
            game_state={"backfilled": True, "seconds_left": 1800},
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert bad["E3"] is True

        good_wallclock = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="basketball_nba",
            captured_at=cap,
            valid_until=None,
            prob=0.60,
            game_state={"backfilled": True, "seconds_left": 1800, "time_basis": "play_wallclock"},
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert good_wallclock["E3"] is False

        good_no_secs = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="basketball_nba",
            captured_at=cap,
            valid_until=None,
            prob=0.60,
            game_state={"backfilled": True, "period": "pregame"},
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert good_no_secs["E3"] is False

    def test_e4_mlb_stat_model_cutoff(self) -> None:
        start = _dt(2026, 9, 26, 0, 0)
        bad = step2.classify_snapshot_exclusions(
            raw_source="stat_model",
            league="baseball_mlb",
            captured_at=_dt(2026, 9, 25, 15, 59),
            valid_until=None,
            prob=0.52,
            game_state=None,
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert bad["E4"] is True
        assert bad["E5b"] is True

        nba_same_ts = step2.classify_snapshot_exclusions(
            raw_source="stat_model",
            league="basketball_nba",
            captured_at=_dt(2026, 9, 25, 15, 59),
            valid_until=None,
            prob=0.52,
            game_state=None,
            commence_time=start,
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert nba_same_ts["E4"] is False

        after_cutoff = step2.classify_snapshot_exclusions(
            raw_source="stat_model",
            league="baseball_mlb",
            captured_at=_dt(2026, 9, 25, 16, 0),
            valid_until=None,
            prob=0.52,
            game_state=None,
            commence_time=_dt(2026, 9, 25, 16, 0),
            completed_at=None,
            max_captured_at_for_source=None,
        )
        assert after_cutoff["E4"] is False
        assert after_cutoff["E5b"] is False

    def test_e5a_terminal_clamp_and_e5b_stat_model_prestart(self) -> None:
        start = _dt(2026, 10, 10, 20, 0)
        completed = _dt(2026, 10, 10, 23, 0)
        # Held past start with terminal clamp -> E5a.
        clamped_vu = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="basketball_nba",
            captured_at=start - timedelta(minutes=30),
            valid_until=start + timedelta(hours=2),
            prob=0.9995,
            game_state=None,
            commence_time=start,
            completed_at=completed,
            max_captured_at_for_source=start + timedelta(hours=1),
        )
        assert clamped_vu["E5a"] is True

        # Latest terminal clamp on completed event -> E5a even without valid_until.
        clamped_last = step2.classify_snapshot_exclusions(
            raw_source="mlb",
            league="baseball_mlb",
            captured_at=start - timedelta(minutes=10),
            valid_until=None,
            prob=0.0008,
            game_state=None,
            commence_time=start,
            completed_at=completed,
            max_captured_at_for_source=start - timedelta(minutes=10),
        )
        assert clamped_last["E5a"] is True

        # Earlier pre-start clamp NOT latest and valid_until <= start -> clean (not terminal leak).
        non_terminal_clamp = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="basketball_nba",
            captured_at=start - timedelta(hours=3),
            valid_until=start - timedelta(hours=2),
            prob=0.0008,
            game_state=None,
            commence_time=start,
            completed_at=completed,
            max_captured_at_for_source=start + timedelta(hours=1),
        )
        assert non_terminal_clamp["E5a"] is False

        # Genuine post-start clamp -> clean.
        post_start_clamp = step2.classify_snapshot_exclusions(
            raw_source="espn",
            league="basketball_nba",
            captured_at=start + timedelta(minutes=30),
            valid_until=start + timedelta(hours=2),
            prob=0.9999,
            game_state=None,
            commence_time=start,
            completed_at=completed,
            max_captured_at_for_source=start + timedelta(minutes=30),
        )
        assert post_start_clamp["E5a"] is False

        # stat_model captured at commence_time -> E5b False; before commence_time -> True.
        sm_at_start = step2.classify_snapshot_exclusions(
            raw_source="stat_model",
            league="basketball_nba",
            captured_at=start,
            valid_until=None,
            prob=0.60,
            game_state=None,
            commence_time=start,
            completed_at=completed,
            max_captured_at_for_source=start,
        )
        assert sm_at_start["E5b"] is False


class TestSelectionWrongStartAndSql:
    def test_pick_key_source_snapshot_fallback_and_fangraphs(self) -> None:
        start = _dt(2026, 10, 10, 20, 0)
        completed = start + timedelta(hours=3)
        cutoff = start - timedelta(hours=1)
        clean_espn = _snap(
            snap_id=1,
            raw_source="espn",
            league="baseball_mlb",
            captured_at=start - timedelta(hours=4),
            prob=0.61,
            commence_time=start,
            completed_at=completed,
            max_cap=start + timedelta(hours=2),
        )
        bad_espn = _snap(
            snap_id=2,
            raw_source="espn",
            league="baseball_mlb",
            captured_at=start - timedelta(hours=2),
            prob=0.99,
            commence_time=start,
            completed_at=completed,
            game_state={"backfilled": True, "seconds_left": 900},
            max_cap=start + timedelta(hours=2),
        )
        bad_mlb = _snap(
            snap_id=3,
            raw_source="mlb",
            league="baseball_mlb",
            captured_at=cutoff,
            prob=0.0005,
            commence_time=start,
            completed_at=completed,
            valid_until=start + timedelta(hours=3),
            max_cap=cutoff,
        )
        clean_fg = _snap(
            snap_id=4,
            raw_source="fangraphs",
            league="baseball_mlb",
            captured_at=start - timedelta(hours=2),
            prob=0.58,
            commence_time=start,
            completed_at=completed,
            max_cap=start + timedelta(hours=2),
        )
        selected, audit = step2._pick_key_source_snapshot(
            {
                "espn": [clean_espn, bad_espn],
                "mlb": [bad_mlb],
                "fangraphs": [clean_fg],
            },
            cutoff,
            apply_exclusions=True,
        )
        assert selected["espn"]["snap_id"] == 1
        assert audit["espn"]["fell_back"] is True
        assert audit["espn"]["dropped"] is False
        assert audit["mlb"]["dropped"] is True
        assert selected["mlb"]["snap_id"] == 4

    def test_classify_wrong_start_and_sql_guards(self) -> None:
        start = _dt(2026, 10, 12, 19, 0)
        clean = step2.classify_wrong_start(
            {"start": start, "score_observed_at": start + timedelta(minutes=10), "completed_at": start + timedelta(hours=3)},
            has_prestart_inplay_wp=False,
        )
        assert clean["any_wrong_start"] is False

        by_score = step2.classify_wrong_start(
            {"start": start, "score_observed_at": start - timedelta(minutes=5), "completed_at": None},
            has_prestart_inplay_wp=False,
        )
        assert by_score["score_observed_before_start"] is True
        assert by_score["any_wrong_start"] is True

        by_completed = step2.classify_wrong_start(
            {"start": start, "score_observed_at": None, "completed_at": start - timedelta(minutes=1)},
            has_prestart_inplay_wp=False,
        )
        assert by_completed["completed_before_start"] is True
        assert by_completed["any_wrong_start"] is True

        by_inplay = step2.classify_wrong_start(
            {"start": start, "score_observed_at": None, "completed_at": None},
            has_prestart_inplay_wp=True,
        )
        assert by_inplay["inplay_wp_before_start"] is True
        assert by_inplay["any_wrong_start"] is True

        for sql_name, sql in [
            ("EVENTS_SQL", step2.EVENTS_SQL),
            ("WIN_PROB_BATCH_SQL", step2.WIN_PROB_BATCH_SQL),
            ("ESM_DETAIL_SQL", step2.ESM_DETAIL_SQL),
            ("WRONG_START_BATCH_SQL", step2.WRONG_START_BATCH_SQL),
            ("ODDS_BATCH_SQL", step2.ODDS_BATCH_SQL),
        ]:
            assert "2026-11-06T00:00:00Z" in sql, sql_name
            assert "probability_publications" not in sql, sql_name

        assert "backfilled" in step2.WRONG_START_BATCH_SQL
        assert "play_wallclock" not in step2.WRONG_START_BATCH_SQL
        assert "inning" in step2.WRONG_START_BATCH_SQL
        assert "home_score" in step2.WRONG_START_BATCH_SQL


class TestVerdictGateAndReport:
    def test_classify_verdict_from_ci(self) -> None:
        assert step2.classify_verdict_from_ci(None).startswith("cannot tell")
        assert step2.classify_verdict_from_ci([-0.015, -0.001]).startswith("helps")
        assert step2.classify_verdict_from_ci([0.002, 0.012]).startswith("hurts")
        assert step2.classify_verdict_from_ci([-0.005, 0.004]).startswith("cannot tell")

    def test_step2_report_411a_gate_table0_common_support_fairness_and_jsonl(
        self, tmp_path: Path
    ) -> None:
        obs = _build_synthetic_obs()
        no_gate = step2.compute_step2_report(obs, baseline_411a=None)
        assert no_gate["aborted"] is False

        # Construct exact matching 411: A baseline from Panel A + meta and confirm 0 mismatches.
        matching_baseline = {
            "meta": {
                k: no_gate["meta"][k]
                for k in (
                    "events_total",
                    "wp_events_read",
                    "odds_target_pm",
                    "odds_target_non_pm_pool",
                    "odds_target_non_pm_sample",
                    "clusters_read",
                )
            },
            "horizons": no_gate["panel_a_411"]["horizons"],
            "cutoff_gaps": no_gate["panel_a_411"]["cutoff_gaps"],
        }
        verified = step2.compute_step2_report(obs, baseline_411a=matching_baseline)
        assert verified["aborted"] is False
        assert verified["baseline_411a_check"]["mismatches"] == 0
        assert verified["baseline_411a_check"]["checked_cells"] > 0

        # Panel A masks to 411a_eids (8 NBA events); Option B unmasked Panel B/C sees all 10 events.
        assert verified["panel_a_411"]["horizons"]["t_minus_1h"]["n_events"] == 10
        assert (
            verified["panel_a_411"]["horizons"]["t_minus_1h"]["overall"]["multi_source"]["pairwise"][
                "espn"
            ]["n_games"]
            == 8
        )
        assert (
            verified["panel_c_common_raw"]["horizons"]["t_minus_1h"]["overall"]["multi_source"][
                "pairwise"
            ]["espn"]["n_games"]
            == 9
        )
        # Verify Table 0 captures E3 fallback/drop, E5b stat_model, E5a mlb, and wrong-start counts.
        t0 = verified["table0"]
        assert t0["snapshot_counts"]["espn"]["E3"] >= 2
        assert t0["snapshot_counts"]["stat_model"]["E5b"] == 1
        assert t0["snapshot_counts"]["mlb"]["E5a"] == 1
        assert t0["wrong_start"]["all_pre_nov6"]["wrong_start_any"] == 2
        assert t0["wrong_start"]["all_pre_nov6"]["score_observed_before_start"] == 1
        assert t0["wrong_start"]["all_pre_nov6"]["inplay_wp_before_start"] == 1

        # Panel B vs Panel C primary read uses identical Common Support `shared_ids`.
        prim_all = verified["pre_registered_primary"]["all_surviving"]["t_minus_1h"]
        prim_fair = verified["pre_registered_primary"]["excluding_wrong_start"]["t_minus_1h"]
        assert prim_all["n_games"] == 10
        assert prim_fair["n_games"] == 8
        assert verified["pm_standalone_all_wp"]["t_minus_1h"]["all_wp"]["n_games"] == 10
        assert (
            verified["pm_standalone_all_wp"]["t_minus_1h"]["excluding_wrong_start"]["n_games"] == 8
        )

        # Mutate one 411: A baseline value and confirm abort happens BEFORE Panel B.
        bad_baseline = json.loads(json.dumps(matching_baseline))
        bad_baseline["meta"]["wp_events_read"] += 1
        aborted = step2.compute_step2_report(obs, baseline_411a=bad_baseline)
        assert aborted["aborted"] is True
        assert aborted["abort_reason"] == "411a_baseline_mismatch"
        assert aborted["baseline_411a_check"]["mismatches"] == 1
        assert "panel_b_clean" not in aborted
        aborted_md = step2.format_step2_markdown(aborted)
        assert "ABORTED BEFORE PANEL B" in aborted_md

        # Render full Markdown & write per-game JSONL.gz.
        full_md = step2.format_step2_markdown(verified)
        assert "Table 0" in full_md
        assert step2.WRITING_BASIS_STATEMENT in full_md
        assert "Addition 4" in full_md
        assert "Addition 3 Fairness Re-Run" in full_md

        raw_rec, clean_rec = verified["_per_game_records"]
        out_gz = tmp_path / "per_game.jsonl.gz"
        step2.write_per_game_jsonl_gz(out_gz, raw_rec, clean_rec)
        with gzip.open(out_gz, "rt", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        assert len(rows) == 40
        t1_e1001 = next(r for r in rows if r["horizon"] == "t_minus_1h" and r["event_id"] == 1001)
        assert "espn" in t1_e1001["raw_sources"]
        assert "espn" not in t1_e1001["clean_sources"]
