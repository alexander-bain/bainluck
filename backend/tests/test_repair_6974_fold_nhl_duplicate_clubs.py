"""#6974 NHL residual: the duplicate-club repair touches its pinned rows and nothing else.

The refusals and the manifest's shape are pure and driven here. The SQL — the
strip, the mapping repoint, ``team_merge._apply_merge`` per fold and the undo —
runs against a real PostgreSQL in
``tests/integration/test_repair_6974_fold_nhl_apply_restore_pg.py``.
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
        "repair_6974_nhl", _SCRIPTS / "repair_6974_fold_nhl_duplicate_clubs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _measured() -> tuple[dict[int, dict], dict[int, dict]]:
    """The rows exactly as the manifest says production holds them."""
    rows: dict[int, dict] = {}
    for f in m.FOLDS:
        rows[f.canon_id] = {
            "id": f.canon_id, "name": f.canon_name, "sport_key": m.SPORT_KEY,
            "espn_id": f.espn_id, "slug": f"s{f.canon_id}", "logo_url_small": None,
            "alternate_names": None,
        }
        rows[f.dup_id] = {
            "id": f.dup_id, "name": f.dup_name, "sport_key": m.SPORT_KEY,
            "espn_id": f.espn_id, "slug": f"s{f.dup_id}", "logo_url_small": None,
            "alternate_names": list(f.aliases),
        }
    for s in m.STRIPS:
        rows[s.team_id] = {
            "id": s.team_id, "name": s.name, "sport_key": m.SPORT_KEY, "espn_id": s.espn_id,
            "slug": f"s{s.team_id}", "logo_url_small": s.logo_url_small,
            "alternate_names": list(s.aliases),
        }
    mappings: dict[int, dict] = {}
    for e in m.MAPPING_EDITS:
        rows[e.to_team] = {
            "id": e.to_team, "name": e.to_name, "sport_key": m.SPORT_KEY, "espn_id": "29",
            "slug": f"s{e.to_team}", "logo_url_small": None, "alternate_names": None,
        }
        mappings[e.mapping_id] = {
            "id": e.mapping_id, "source": e.source, "source_name": e.source_name,
            "sport_key": m.SPORT_KEY, "team_id": e.from_team,
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
    f = m.FOLDS[0]
    rows[f.dup_id]["alternate_names"] = '["' + '", "'.join(f.aliases) + '"]'
    assert m.rows_refusal(rows, maps) is None


@pytest.mark.parametrize("fold", m.FOLDS, ids=lambda f: f.dup_name)
def test_every_fold_refuses_a_renamed_missing_re_ided_or_re_aliased_row(fold):
    for tid in (fold.dup_id, fold.canon_id):
        for field, value, word in (
            ("name", "Renamed", "named"),
            ("espn_id", "0", "espn_id"),
            ("sport_key", "icehockey_nhl_preseason", "icehockey_nhl_preseason"),
        ):
            rows, maps = _measured()
            rows[tid] = dict(rows[tid], **{field: value})
            assert word in m.rows_refusal(rows, maps), (tid, field)
        rows, maps = _measured()
        del rows[tid]
        assert "gone" in m.rows_refusal(rows, maps)
    # The dropped alias is only safe to drop because it is the alias read.
    rows, maps = _measured()
    rows[fold.dup_id]["alternate_names"] = list(fold.aliases) + ["Extra"]
    assert "aliases" in m.rows_refusal(rows, maps)


@pytest.mark.parametrize("strip", m.STRIPS, ids=lambda s: s.name)
def test_every_strip_refuses_a_row_that_no_longer_wears_the_borrowed_identity(strip):
    for field, value, word in (
        ("espn_id", "999", "espn_id"),
        ("logo_url_small", None, "crest"),
        ("alternate_names", ["Something Else"], "aliases"),
        ("name", "Renamed", "now"),
    ):
        rows, maps = _measured()
        rows[strip.team_id] = dict(rows[strip.team_id], **{field: value})
        assert word in m.rows_refusal(rows, maps), field


@pytest.mark.parametrize("edit", m.MAPPING_EDITS, ids=lambda e: e.source_name)
def test_every_mapping_edit_refuses_a_moved_mapping_or_target(edit):
    for field, value in (
        ("team_id", edit.to_team),
        ("source_name", "Columbus Blue Jackets"),
        ("source", "odds_api"),
        ("sport_key", "icehockey_ahl"),
    ):
        rows, maps = _measured()
        maps[edit.mapping_id] = dict(maps[edit.mapping_id], **{field: value})
        assert "mapping" in m.rows_refusal(rows, maps), field
    rows, maps = _measured()
    del maps[edit.mapping_id]
    assert "gone" in m.rows_refusal(rows, maps)
    rows, maps = _measured()
    rows[edit.to_team] = dict(rows[edit.to_team], name="Columbus")
    assert "target" in m.rows_refusal(rows, maps)


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


def test_the_manifest_never_gives_one_row_two_jobs():
    dups = {f.dup_id for f in m.FOLDS}
    canons = {f.canon_id for f in m.FOLDS}
    strips = {s.team_id for s in m.STRIPS}
    targets = {e.to_team for e in m.MAPPING_EDITS}
    assert dups == {8293, 6181}
    assert not canons & dups and not canons & strips and not dups & strips
    # A mapping never lands on a row this repair deletes or strips.
    assert not targets & (dups | strips)


def test_the_new_jersey_row_is_stripped_never_folded():
    # 12716's events and legs split across the Islanders and the Devils; a fold
    # into either binds the other club's rows (#6974 comment 2026-09-19).
    assert 12716 not in {f.dup_id for f in m.FOLDS}
    assert 12716 in {s.team_id for s in m.STRIPS}


def test_a_mapping_the_fold_would_misbind_is_repointed_first():
    # Kalshi's NHL "Columbus" is the Blue Jackets. It sat on 6181, so a plain
    # fold would have handed it to the Islanders.
    folded_away = {f.dup_id for f in m.FOLDS}
    for e in m.MAPPING_EDITS:
        assert e.from_team in folded_away
        assert e.to_team not in {f.canon_id for f in m.FOLDS if f.dup_id == e.from_team}


def test_a_bare_city_is_never_carried_onto_a_club():
    for f in m.FOLDS:
        carried = [a for a in f.aliases if a not in f.drop_aliases]
        assert "New York" not in carried
        assert set(f.drop_aliases) <= set(f.aliases)


def test_a_club_and_its_duplicate_share_the_provider_id_that_makes_them_one():
    by_canon: dict[int, set[str]] = {}
    for f in m.FOLDS:
        by_canon.setdefault(f.canon_id, set()).add(f.espn_id)
    assert all(len(ids) == 1 for ids in by_canon.values())


def test_the_strip_clears_every_field_a_borrowed_espn_match_writes():
    from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS

    assert set(ESPN_SOURCED_IDENTITY_FIELDS) <= set(m.STRIP_FIELDS)
    assert {"espn_id", "logo_url"} <= set(m.STRIP_FIELDS)
    assert "name" not in m.STRIP_FIELDS and "slug" not in m.STRIP_FIELDS


def test_backups_are_backup_prefixed_and_do_not_reuse_the_mls_tables():
    assert m.BACKUP_TEAMS == "backup_6974nhl_teams"
    assert m.BACKUP_REFS == "backup_6974nhl_refs"
