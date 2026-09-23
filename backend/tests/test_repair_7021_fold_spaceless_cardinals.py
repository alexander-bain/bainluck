"""#7021: the Cardinals fold touches the one duplicate row and every reference to it.

The refusals are pure and driven with dicts here. The SQL itself — the
repoint, the fresher-board rule, the alias, the legacy slug, the delete and the
undo — runs against a real PostgreSQL in
``tests/integration/test_repair_7021_fold_apply_restore_pg.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_7021", _SCRIPTS / "repair_7021_fold_spaceless_cardinals.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _row(id_, name, sport_key="baseball_mlb", espn_id="24"):
    return {"id": id_, "name": name, "sport_key": sport_key, "espn_id": espn_id}


DUP = _row(m.DUP_ID, "St.Louis Cardinals")
CANON = _row(m.CANON_ID, "St. Louis Cardinals")


def test_refuses_off_the_heavy_app(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert "bainluck-heavy" in m.wrong_app_refusal()
    monkeypatch.delenv("HEROKU_APP_NAME")
    assert m.wrong_app_refusal() is not None
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert m.wrong_app_refusal() is None


def test_the_measured_rows_pass():
    assert m.rows_refusal(DUP, CANON) is None


def test_a_renamed_row_refuses():
    assert "named" in m.rows_refusal(dict(DUP, name="St. Louis Cardinals"), CANON)
    assert "named" in m.rows_refusal(DUP, dict(CANON, name="St. Louis Blues"))


def test_a_row_in_another_league_refuses():
    # The preseason row 2692 also carries espn_id 24 — it is not this fold.
    assert "baseball_mlb_preseason" in m.rows_refusal(
        DUP, dict(CANON, sport_key="baseball_mlb_preseason")
    )


def test_a_row_without_the_shared_espn_id_refuses():
    # The shared provider id is what makes these one club (ruling 048): without
    # it, two similar names are only a candidate.
    assert "espn_id" in m.rows_refusal(dict(DUP, espn_id=None), CANON)
    assert "espn_id" in m.rows_refusal(DUP, dict(CANON, espn_id="25"))


def test_a_missing_row_refuses():
    assert "gone" in m.rows_refusal(None, CANON)
    assert "gone" in m.rows_refusal(DUP, None)


def test_exact_counts_pass_and_any_drift_refuses():
    assert m.REPOINTS == {
        ("events", "home_team_id"): 13,
        ("events", "away_team_id"): 21,
        ("futures_outcomes", "team_id"): 1,
        ("entities", "source_team_id"): 1,
        ("user_favorites", "team_id"): 0,
        ("tournament_odds", "team_id"): 0,
        ("team_identity_mapping", "team_id"): 0,
    }
    pinned = dict(m.REPOINTS)
    assert m.counts_refusal(pinned) is None
    for key, n in pinned.items():
        for delta in (-1, 1):
            if n + delta < 0:
                continue
            assert f"{key[0]}.{key[1]}" in m.counts_refusal({**pinned, key: n + delta})
    assert m.counts_refusal({}) is not None


def test_every_foreign_key_onto_teams_is_repointed():
    """A reference the fold forgets is a row the delete orphans or cascades away.

    `/api/admin/teams/merge` is exactly this defect: it repoints five columns and
    misses `tournament_odds` and `entities.source_team_id`. The set is read from
    the models, so a new foreign key onto `teams` fails here until it is pinned.
    """
    from app.models.models import Base

    declared = {
        (table.name, fk.parent.name)
        for table in Base.metadata.sorted_tables
        for fk in table.foreign_keys
        if fk.column.table.name == "teams"
    }
    assert declared == set(m.REPOINTS)


def test_backups_are_backup_prefixed():
    assert m.BACKUP_TEAMS == "backup_7021_teams"
    assert m.BACKUP_REPOINTS == "backup_7021_repoints"


def test_the_alias_is_the_spelling_statpal_writes():
    # The alias is the whole durable half: StatPal's standings writer resolves
    # `team_name.lower()` against names AND alternate names, so this exact
    # string is what moves tomorrow's board onto the real club.
    assert m.DUP_NAME == "St.Louis Cardinals"
    assert m.LEGACY_SLUG == "stlouis-cardinals"
