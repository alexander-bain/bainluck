"""Pin the reviewed cohort and its evidence, not a blanket legacy policy."""

import ast
import json

from scripts.evals.eval_registry_contract import validate
from scripts.evals.scoreboard import REPO, build_scoreboard


def test_all_47_individually_reviewed_artifacts_keep_their_named_parent():
    folder = REPO / "backend/scripts/evals"
    audit = json.loads((folder / "registry_audit_2026_11.json").read_text())
    registry = json.loads((folder / "eval_registry.json").read_text())
    assert len(audit["rows"]) == 47
    assert len({r["name"] for r in audit["rows"]}) == 47
    assert validate(registry, [r["name"] for r in audit["rows"]]) == {"verdict": "ALLOW", "errors": []}
    members = {m["name"]: m for d in registry["domains"] for m in d["members"]}
    for row in audit["rows"]:
        assert row["verdict"] in {"register", "fold", "legacy"}
        assert row["checks"] and row["canonical_coverage"] and row["bite_evidence"]
        assert row["history"] and row["case_sources"]
        if row["verdict"] == "register":
            assert members[row["name"]]["target"] == row["canonical"]
            source = ast.get_docstring(ast.parse((REPO / row["source"]).read_text()))
            assert f"Extends {row['canonical']} (ruling 002)" in source


def test_six_retro_catchers_remain_keepers_and_legacy_is_disjoint():
    folder = REPO / "backend/scripts/evals"
    registry = json.loads((folder / "eval_registry.json").read_text())
    known = {d["canonical"] for d in registry["domains"]}
    known.update(m["name"] for d in registry["domains"] for m in d["members"])
    retro = json.loads((REPO / "backend/tests/evals/fixtures/eval_bite_rate_audit.json").read_text())
    for row in retro["escaped_defect_retro"]:
        # cache_failure_resilience_fixtures is the case file for that canonical.
        assert row["canonical_catcher"].removesuffix("_fixtures") in known
    legacy = {r["name"] for r in registry.get("legacy", [])}
    assert not legacy & known
    board = build_scoreboard()
    assert board["registry"]["legacy"] == len(legacy)
    assert not ({r["name"] for r in json.loads((folder / "registry_audit_2026_11.json").read_text())["rows"]} & set(board["registry"]["unregistered_names"]))
