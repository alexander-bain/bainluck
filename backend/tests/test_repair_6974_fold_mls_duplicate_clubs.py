"""#6974: the MLS duplicate-club repair touches its pinned rows and nothing else.

The refusals and the manifest's shape are pure and driven here. The SQL — the
strip, the alias edits, ``team_merge._apply_merge`` per fold, the delete's own
FK actions and the undo — runs against a real PostgreSQL in
``tests/integration/test_repair_6974_fold_mls_apply_restore_pg.py``.
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
        "repair_6974", _SCRIPTS / "repair_6974_fold_mls_duplicate_clubs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _measured_rows() -> dict[int, dict]:
    """The rows exactly as the manifest says production holds them."""
    rows: dict[int, dict] = {}
    for f in m.FOLDS:
        for tid, name in ((f.dup_id, f.dup_name), (f.canon_id, f.canon_name)):
            rows[tid] = {
                "id": tid, "name": name, "sport_key": m.SPORT_KEY, "espn_id": f.espn_id,
                "slug": f"s{tid}", "logo_url_small": None, "alternate_names": None,
            }
    for s in m.STRIPS:
        rows[s.team_id] = {
            "id": s.team_id, "name": s.name, "sport_key": m.SPORT_KEY, "espn_id": s.espn_id,
            "slug": f"s{s.team_id}", "logo_url_small": s.logo_url_small,
            "alternate_names": list(s.aliases),
        }
    for a in m.ALIAS_EDITS:
        rows[a.team_id] = {
            "id": a.team_id, "name": a.name, "sport_key": m.SPORT_KEY, "espn_id": None,
            "slug": f"s{a.team_id}", "logo_url_small": None,
            "alternate_names": None if a.before is None else list(a.before),
        }
    return rows


def test_refuses_off_the_heavy_app(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert "bainluck-heavy" in m.wrong_app_refusal()
    monkeypatch.delenv("HEROKU_APP_NAME")
    assert m.wrong_app_refusal() is not None
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert m.wrong_app_refusal() is None


def test_the_measured_rows_pass():
    assert m.rows_refusal(_measured_rows()) is None


def test_jsonb_arriving_as_text_reads_the_same():
    rows = _measured_rows()
    s = m.STRIPS[0]
    rows[s.team_id]["alternate_names"] = '["' + '", "'.join(s.aliases) + '"]'
    assert m.rows_refusal(rows) is None


@pytest.mark.parametrize("fold", m.FOLDS, ids=lambda f: f.dup_name)
def test_every_fold_refuses_a_renamed_missing_or_re_ided_row(fold):
    for tid in (fold.dup_id, fold.canon_id):
        rows = _measured_rows()
        rows[tid] = dict(rows[tid], name=rows[tid]["name"] + " X")
        assert "named" in m.rows_refusal(rows)
        rows = _measured_rows()
        rows[tid] = dict(rows[tid], espn_id="0")
        assert "espn_id" in m.rows_refusal(rows)
        rows = _measured_rows()
        rows[tid] = dict(rows[tid], sport_key="soccer_usa_mls_preseason")
        assert "soccer_usa_mls_preseason" in m.rows_refusal(rows)
        rows = _measured_rows()
        del rows[tid]
        assert "gone" in m.rows_refusal(rows)


@pytest.mark.parametrize("strip", m.STRIPS, ids=lambda s: s.name)
def test_every_strip_refuses_a_row_that_no_longer_wears_the_borrowed_identity(strip):
    for field, value, word in (
        ("espn_id", "999", "espn_id"),
        ("logo_url_small", None, "crest"),
        ("alternate_names", ["Something Else"], "aliases"),
        ("name", "Renamed", "now"),
    ):
        rows = _measured_rows()
        rows[strip.team_id] = dict(rows[strip.team_id], **{field: value})
        assert word in m.rows_refusal(rows), field


@pytest.mark.parametrize("edit", m.ALIAS_EDITS, ids=lambda a: a.name)
def test_every_alias_edit_refuses_a_row_whose_aliases_moved(edit):
    rows = _measured_rows()
    rows[edit.team_id] = dict(rows[edit.team_id], alternate_names=["Moved"])
    assert "aliases" in m.rows_refusal(rows)


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
    """A reference the fold forgets is a row the delete orphans or cascades away.
    Read from the models, so a new FK onto `teams` fails here until it is pinned —
    and ``team_merge._FK_STATEMENTS``, which does the repointing, is held to the
    same set by ``tests/test_team_merge.py::TestFkCoverage``."""
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
    dups = [f.dup_id for f in m.FOLDS]
    canons = {f.canon_id for f in m.FOLDS}
    strips = [s.team_id for s in m.STRIPS]
    edits = [a.team_id for a in m.ALIAS_EDITS]
    assert len(dups) == len(set(dups)) == 21
    # A club is never also folded away, stripped, or alias-edited behind the
    # fold's back (its aliases are the fold's to write).
    assert not canons & set(dups)
    assert not canons & set(strips)
    assert not canons & set(edits)
    assert not set(dups) & set(strips)
    assert not set(dups) & set(edits)
    assert not set(strips) & set(edits)


def test_a_club_and_its_duplicate_share_the_provider_id_that_makes_them_one():
    # Ruling 048: absorption needs an id-anchored correspondence. Every fold is
    # pinned to ONE espn_id that both rows carry (rows_refusal enforces it per row).
    by_canon: dict[int, set[str]] = {}
    for f in m.FOLDS:
        by_canon.setdefault(f.canon_id, set()).add(f.espn_id)
    assert all(len(ids) == 1 for ids in by_canon.values())


def test_the_strip_clears_every_field_a_borrowed_espn_match_writes():
    from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS

    assert set(ESPN_SOURCED_IDENTITY_FIELDS) <= set(m.STRIP_FIELDS)
    assert {"espn_id", "logo_url"} <= set(m.STRIP_FIELDS)
    # The name is the row's own and is never stripped.
    assert "name" not in m.STRIP_FIELDS and "slug" not in m.STRIP_FIELDS


def test_no_reserve_side_is_folded():
    # A club's second side is another club (the planner hole this commit closes);
    # the manifest strips them, it never folds them.
    from app.utils.team_merge import _is_reserve_side

    assert not any(_is_reserve_side(f.dup_name) for f in m.FOLDS)
    assert sum(_is_reserve_side(s.name) for s in m.STRIPS) == 4


def test_backups_are_backup_prefixed():
    assert m.BACKUP_TEAMS == "backup_6974_teams"
    assert m.BACKUP_REFS == "backup_6974_refs"
