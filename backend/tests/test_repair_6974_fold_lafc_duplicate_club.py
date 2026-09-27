"""#6974 LAFC residual: the duplicate-club repair touches its pinned rows and nothing else.

The refusals and the manifest's shape are pure and driven here. The SQL — the
mapping repoint, the banked deletes, ``team_merge._apply_merge`` and the undo —
runs against a real PostgreSQL in
``tests/integration/test_repair_6974_fold_lafc_apply_restore_pg.py``.
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
        "repair_6974_lafc", _SCRIPTS / "repair_6974_fold_lafc_duplicate_club.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()
FOLD = m.FOLDS[0]


def _measured() -> tuple[dict[int, dict], dict[int, dict]]:
    """The rows exactly as the manifest says production holds them."""
    rows: dict[int, dict] = {
        FOLD.canon_id: {
            "id": FOLD.canon_id, "name": FOLD.canon_name, "sport_key": m.SPORT_KEY,
            "espn_id": FOLD.espn_id, "slug": "lafc", "alternate_names": ["Los Angeles FC"],
        },
        FOLD.dup_id: {
            "id": FOLD.dup_id, "name": FOLD.dup_name, "sport_key": m.SPORT_KEY,
            "espn_id": FOLD.espn_id, "slug": "los-angeles-fc",
            "alternate_names": list(FOLD.aliases),
        },
    }
    mappings: dict[int, dict] = {}
    for e in m.MAPPING_EDITS:
        rows[e.to_team] = {
            "id": e.to_team, "name": e.to_name, "sport_key": m.SPORT_KEY, "espn_id": "18267",
            "slug": "fc-cincinnati", "alternate_names": None,
        }
        mappings[e.mapping_id] = {
            "id": e.mapping_id, "source": e.source, "source_name": e.source_name,
            "sport_key": m.SPORT_KEY, "team_id": e.from_team,
        }
    for p in m.MAPPING_DELETES + m.MAPPING_KEEPS:
        mappings[p.mapping_id] = {
            "id": p.mapping_id, "source": p.source, "source_name": p.source_name,
            "sport_key": p.sport_key, "team_id": FOLD.dup_id,
        }
    return rows, mappings


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
    rows, maps = _measured()
    rows[FOLD.dup_id]["alternate_names"] = '["' + '", "'.join(FOLD.aliases) + '"]'
    assert m.rows_refusal(rows, maps) is None


def test_the_fold_refuses_a_renamed_missing_re_ided_or_re_aliased_row():
    for tid in (FOLD.dup_id, FOLD.canon_id):
        for field, value, word in (
            ("name", "Renamed", "named"),
            ("espn_id", "0", "espn_id"),
            ("sport_key", "soccer_concacaf_leagues_cup", "soccer_concacaf_leagues_cup"),
        ):
            rows, maps = _measured()
            rows[tid] = dict(rows[tid], **{field: value})
            assert word in m.rows_refusal(rows, maps), (tid, field)
        rows, maps = _measured()
        del rows[tid]
        assert "gone" in m.rows_refusal(rows, maps)
    # The dropped aliases are only safe to drop because they are the aliases read.
    rows, maps = _measured()
    rows[FOLD.dup_id]["alternate_names"] = list(FOLD.aliases) + ["Extra"]
    assert "aliases" in m.rows_refusal(rows, maps)


@pytest.mark.parametrize("edit", m.MAPPING_EDITS, ids=lambda e: e.source_name)
def test_every_mapping_edit_refuses_a_moved_mapping_or_target(edit):
    for field, value in (
        ("team_id", edit.to_team),
        ("source_name", "Los Angeles FC"),
        ("source", "kalshi"),
        ("sport_key", "soccer_epl"),
    ):
        rows, maps = _measured()
        maps[edit.mapping_id] = dict(maps[edit.mapping_id], **{field: value})
        assert "mapping" in m.rows_refusal(rows, maps), field
    rows, maps = _measured()
    del maps[edit.mapping_id]
    assert "gone" in m.rows_refusal(rows, maps)
    rows, maps = _measured()
    rows[edit.to_team] = dict(rows[edit.to_team], name="Cincinnati")
    assert "target" in m.rows_refusal(rows, maps)


@pytest.mark.parametrize(
    "pin", m.MAPPING_DELETES + m.MAPPING_KEEPS, ids=lambda p: f"{p.mapping_id}"
)
def test_every_pinned_mapping_refuses_when_it_moved_or_vanished(pin):
    label = "deleted" if pin in m.MAPPING_DELETES else "kept"
    for field, value in (
        ("team_id", FOLD.canon_id),
        ("source_name", pin.source_name + " (2)"),
        ("source", "espn"),
        ("sport_key", "soccer_mls_next_pro"),
    ):
        rows, maps = _measured()
        maps[pin.mapping_id] = dict(maps[pin.mapping_id], **{field: value})
        refusal = m.rows_refusal(rows, maps)
        assert refusal and label in refusal and str(pin.mapping_id) in refusal, field
    rows, maps = _measured()
    del maps[pin.mapping_id]
    assert "gone" in m.rows_refusal(rows, maps)


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


def test_every_mapping_on_the_duplicate_has_exactly_one_job():
    # With the pinned count, "every pinned id is on the duplicate" means the
    # pinned set IS the duplicate's whole mapping set: nothing rides the fold unread.
    edits = {e.mapping_id for e in m.MAPPING_EDITS}
    deletes = {d.mapping_id for d in m.MAPPING_DELETES}
    keeps = {k.mapping_id for k in m.MAPPING_KEEPS}
    assert not edits & deletes and not edits & keeps and not deletes & keeps
    mapping_col = m.FK_COLUMNS.index(("team_identity_mapping", "team_id"))
    assert len(edits | deletes | keeps) == FOLD.refs[mapping_col] == 17
    assert all(e.from_team == FOLD.dup_id for e in m.MAPPING_EDITS)


def test_a_mapping_the_fold_would_misbind_is_repointed_off_the_club():
    # The Odds API's MLS "FC Cincinnati" is FC Cincinnati (29); a plain fold hands
    # FC Cincinnati's sportsbook games to LAFC.
    for e in m.MAPPING_EDITS:
        assert e.to_team not in {f.canon_id for f in m.FOLDS} | {f.dup_id for f in m.FOLDS}


def test_nothing_the_fold_carries_is_another_league_or_a_market_title():
    for k in m.MAPPING_KEEPS:
        assert k.sport_key == m.SPORT_KEY
        assert " - " not in k.source_name
    for d in m.MAPPING_DELETES:
        assert d.sport_key != m.SPORT_KEY or " - " in d.source_name, d


def test_the_other_la_clubs_names_are_never_carried_onto_lafc():
    carried = {a.lower() for a in FOLD.aliases if a not in FOLD.drop_aliases}
    assert not carried & {"galaxy", "la galaxy"}
    assert set(FOLD.drop_aliases) <= set(FOLD.aliases)


def test_backups_are_backup_prefixed_and_do_not_reuse_the_mls_or_nhl_tables():
    assert m.BACKUP_TEAMS == "backup_6974lafc_teams"
    assert m.BACKUP_REFS == "backup_6974lafc_refs"
    assert m.BACKUP_MAPPINGS == "backup_6974lafc_mappings"
