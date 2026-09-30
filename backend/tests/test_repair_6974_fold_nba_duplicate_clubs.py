"""#6974 NBA residual: the duplicate-club repair touches its pinned rows and nothing else.

The refusals and the manifest's shape are pure and driven here. The SQL — the
mapping repoint, the banked deletes, the leg corrections, ``team_merge._apply_merge``
and the undo — runs against a real PostgreSQL in
``tests/integration/test_repair_6974_fold_nba_apply_restore_pg.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_6974_nba", _SCRIPTS / "repair_6974_fold_nba_duplicate_clubs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()
DUPS = {f.dup_id for f in m.FOLDS}
CLUBS = {f.canon_id for f in m.FOLDS}


def _measured() -> tuple[dict[int, dict], dict[int, dict], dict[int, dict]]:
    """The rows exactly as the manifest says production holds them."""
    rows: dict[int, dict] = {}
    for f in m.FOLDS:
        rows[f.canon_id] = {
            "id": f.canon_id, "name": f.canon_name, "sport_key": m.SPORT_KEY,
            "espn_id": f.espn_id, "slug": f"club-{f.canon_id}", "alternate_names": ["City"],
        }
        rows[f.dup_id] = {
            "id": f.dup_id, "name": f.dup_name, "sport_key": m.SPORT_KEY,
            "espn_id": f.espn_id, "slug": f"dup-{f.dup_id}", "alternate_names": list(f.aliases),
        }
    for t in m.TARGETS:
        rows[t.team_id] = {
            "id": t.team_id, "name": t.name, "sport_key": t.sport_key, "espn_id": "1",
            "slug": f"t-{t.team_id}", "alternate_names": None,
        }
    mappings: dict[int, dict] = {}
    for e in m.MAPPING_EDITS:
        mappings[e.mapping_id] = {
            "id": e.mapping_id, "source": e.source, "source_name": e.source_name,
            "sport_key": m.SPORT_KEY, "team_id": e.from_team,
        }
    for p in m.MAPPING_DELETES:
        mappings[p.mapping_id] = {
            "id": p.mapping_id, "source": p.source, "source_name": p.source_name,
            "sport_key": m.SPORT_KEY, "team_id": p.team_id,
        }
    legs = {g.outcome_id: {"id": g.outcome_id, "name": g.name, "team_id": g.from_team}
            for g in m.LEG_EDITS}
    return rows, mappings, legs


def test_refuses_off_the_heavy_app(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert "bainluck-heavy" in m.wrong_app_refusal()
    monkeypatch.delenv("HEROKU_APP_NAME")
    assert m.wrong_app_refusal() is not None
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert m.wrong_app_refusal() is None


def test_the_measured_rows_pass():
    assert m.rows_refusal(*_measured()) is None


def test_jsonb_arriving_as_text_reads_the_same():
    rows, maps, legs = _measured()
    f = m.FOLDS[0]
    rows[f.dup_id]["alternate_names"] = '["' + '", "'.join(f.aliases) + '"]'
    assert m.rows_refusal(rows, maps, legs) is None


@pytest.mark.parametrize("fold", m.FOLDS, ids=lambda f: f.dup_name)
def test_every_fold_refuses_a_renamed_missing_re_ided_or_re_aliased_row(fold):
    for tid in (fold.dup_id, fold.canon_id):
        for field, value, word in (
            ("name", "Renamed", "named"),
            ("espn_id", "0", "espn_id"),
            ("sport_key", "basketball_wnba", "basketball_wnba"),
        ):
            rows, maps, legs = _measured()
            rows[tid] = dict(rows[tid], **{field: value})
            assert word in m.rows_refusal(rows, maps, legs), (tid, field)
        rows, maps, legs = _measured()
        del rows[tid]
        assert "gone" in m.rows_refusal(rows, maps, legs)
    rows, maps, legs = _measured()
    rows[fold.dup_id]["alternate_names"] = list(fold.aliases) + ["Extra"]
    assert "aliases" in m.rows_refusal(rows, maps, legs)


@pytest.mark.parametrize("target", m.TARGETS, ids=lambda t: t.name)
def test_every_target_club_refuses_when_it_is_not_the_row_it_was(target):
    for field, value in (("name", "Renamed"), ("sport_key", "basketball_wnba")):
        rows, maps, legs = _measured()
        rows[target.team_id] = dict(rows[target.team_id], **{field: value})
        assert "target" in m.rows_refusal(rows, maps, legs), field
    rows, maps, legs = _measured()
    del rows[target.team_id]
    assert "target" in m.rows_refusal(rows, maps, legs)


@pytest.mark.parametrize(
    "pin", m.MAPPING_EDITS + m.MAPPING_DELETES, ids=lambda p: f"{p.mapping_id}"
)
def test_every_pinned_mapping_refuses_when_it_moved_or_vanished(pin):
    here = pin.from_team if isinstance(pin, m.MappingEdit) else pin.team_id
    for field, value in (
        ("team_id", here + 1),
        ("source_name", pin.source_name + " (2)"),
        ("source", "espn"),
        ("sport_key", "basketball_wnba"),
    ):
        rows, maps, legs = _measured()
        maps[pin.mapping_id] = dict(maps[pin.mapping_id], **{field: value})
        refusal = m.rows_refusal(rows, maps, legs)
        assert refusal and "mapping" in refusal and str(pin.mapping_id) in refusal, field
    rows, maps, legs = _measured()
    del maps[pin.mapping_id]
    assert "gone" in m.rows_refusal(rows, maps, legs)


@pytest.mark.parametrize("leg", m.LEG_EDITS, ids=lambda g: f"{g.outcome_id}")
def test_every_pinned_leg_refuses_when_it_moved_renamed_or_vanished(leg):
    for field, value in (("team_id", None), ("team_id", leg.from_team + 1), ("name", "Other")):
        rows, maps, legs = _measured()
        legs[leg.outcome_id] = dict(legs[leg.outcome_id], **{field: value})
        refusal = m.rows_refusal(rows, maps, legs)
        assert refusal and str(leg.outcome_id) in refusal, (field, value)
    rows, maps, legs = _measured()
    del legs[leg.outcome_id]
    assert "gone" in m.rows_refusal(rows, maps, legs)


def test_exact_counts_pass_and_any_drift_refuses():
    pinned = {f.dup_id: f.refs for f in m.FOLDS}
    assert m.counts_refusal(pinned) is None
    for f in m.FOLDS:
        for i, n in enumerate(f.refs):
            for delta in (-1, 1):
                if n + delta < 0:
                    continue
                moved = list(f.refs)
                moved[i] = n + delta
                refusal = m.counts_refusal({**pinned, f.dup_id: tuple(moved)})
                table, col = m.FK_COLUMNS[i]
                assert f"{table}.{col}" in refusal and str(f.dup_id) in refusal
    assert m.counts_refusal({}) is not None


def test_every_foreign_key_onto_teams_is_counted():
    from app.models.models import Base

    declared = {
        (table.name, fk.parent.name)
        for table in Base.metadata.sorted_tables
        for fk in table.foreign_keys
        if fk.column.table.name == "teams"
    }
    assert declared == set(m.FK_COLUMNS)
    assert all(len(f.refs) == len(m.FK_COLUMNS) for f in m.FOLDS)


def test_every_mapping_on_a_duplicate_is_repointed_or_deleted():
    # With the pinned count, the pinned ids ARE each duplicate's whole mapping
    # set: no mapping rides a fold onto a club unread.
    col = m.FK_COLUMNS.index(("team_identity_mapping", "team_id"))
    jobs: dict[int, list[int]] = {d: [] for d in DUPS}
    for e in m.MAPPING_EDITS:
        jobs[e.from_team].append(e.mapping_id)
    for p in m.MAPPING_DELETES:
        jobs[p.team_id].append(p.mapping_id)
    for f in m.FOLDS:
        assert len(set(jobs[f.dup_id])) == f.refs[col], f.dup_name
    assert len({*sum(jobs.values(), [])}) == len(m.MAPPING_EDITS) + len(m.MAPPING_DELETES)


def test_a_corrected_leg_or_mapping_never_lands_on_a_duplicate_or_the_folds_own_club():
    # Moving a leg onto the duplicate's own club is the fold's job; moving it onto
    # a duplicate would be deleted with it. Either means the manifest is wrong.
    by_dup = {f.dup_id: f.canon_id for f in m.FOLDS}
    targets = {t.team_id for t in m.TARGETS}
    for g in m.LEG_EDITS:
        assert g.from_team in DUPS
        assert g.to_team is None or (g.to_team in targets and g.to_team not in DUPS)
        assert g.to_team != by_dup[g.from_team], g
    for e in m.MAPPING_EDITS:
        assert e.from_team in DUPS and e.to_team in targets
    assert len({g.outcome_id for g in m.LEG_EDITS}) == len(m.LEG_EDITS)


def test_the_clippers_keep_exactly_their_own_legs_off_the_catch_all():
    # 12649 held 31 legs: 12 are Kalshi's "Los Angeles C" (the Clippers); the
    # rest are the Lakers', LAFC's and the Kings'. Only the 12 ride the fold.
    fold = next(f for f in m.FOLDS if f.dup_id == 12649)
    futures = m.FK_COLUMNS.index(("futures_outcomes", "team_id"))
    off = [g for g in m.LEG_EDITS if g.from_team == 12649]
    assert fold.refs[futures] - len(off) == 12
    assert {g.to_team for g in off} == {m.LAKERS, m.LAFC, m.KINGS}
    assert all("Los Angeles C" != g.name for g in off)


def test_college_legs_are_unlinked_not_guessed():
    unlinked = {g.outcome_id for g in m.LEG_EDITS if g.to_team is None}
    assert unlinked == {1610270, 1618071, 1618069, 1618201, 1618218, 1615657}


def test_backups_are_backup_prefixed_and_do_not_reuse_another_leagues_tables():
    assert m.BACKUP_TEAMS == "backup_6974nba_teams"
    assert m.BACKUP_REFS == "backup_6974nba_refs"
    assert m.BACKUP_MAPPINGS == "backup_6974nba_mappings"
