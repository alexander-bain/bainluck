"""The scoreboard reports evidence, including red and missing evidence."""

import json
import socket
import subprocess
import sys
from copy import deepcopy

from scripts.evals import scoreboard


def test_cli_is_offline_and_fits_one_screen(monkeypatch):
    def offline(*args, **kwargs):
        raise AssertionError("scoreboard attempted network access")

    monkeypatch.setattr(socket, "socket", offline)
    board = scoreboard.build_scoreboard()
    assert len(scoreboard.render(board).splitlines()) <= 24
    result = subprocess.run(
        [sys.executable, "-m", "scripts.evals.scoreboard", "--json"],
        cwd=scoreboard.REPO / "backend", capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == board
    plain = subprocess.run(
        [sys.executable, "-m", "scripts.evals.scoreboard"],
        cwd=scoreboard.REPO / "backend", capture_output=True, text=True, timeout=30,
    )
    assert plain.returncode == 0, plain.stderr
    assert plain.stdout.rstrip() == scoreboard.render(board)


def test_counts_and_pinned_results_come_from_their_files(tmp_path):
    board = scoreboard.build_scoreboard()
    baseline = json.loads((scoreboard.REPO / "backend/tests/fixtures/matching_golden_baseline.json").read_text())
    assert board["golden"] == {
        "passing": sum(v is True for v in baseline["pairs"].values()),
        "total": len(baseline["pairs"]),
        "floor": baseline["passing_count"],
        "declared_total": baseline["pair_count"],
    }
    # Snapshot pins, not pass thresholds. A later record may pin worse numbers.
    assert (board["golden"]["passing"], board["golden"]["total"]) == (666, 709)
    assert board["bite_rate"] == {"total": 40, "mutation_bites": 40, "real_boundaries": 0}
    registry = json.loads((scoreboard.REPO / scoreboard.EVALS / "eval_registry.json").read_text())
    names = {d["canonical"] for d in registry["domains"]}
    names.update(m["name"] for d in registry["domains"] for m in d["members"])
    assert board["registry"]["registered"] == len(names)
    assert board["registry"]["legacy"] == len(registry.get("legacy", []))
    assert [f["domain"] for f in board["families"]] == [d["domain"] for d in registry["domains"]]
    for family in board["families"]:
        for member in family["members"]:
            if member["case_sources"]:
                assert member["cases"] == sum(scoreboard._count(scoreboard.REPO, s) for s in member["case_sources"])
    record = json.loads((scoreboard.REPO / scoreboard.EVALS / "scoreboard_record.json").read_text())
    assert board["mutation_residue"] == record["mutation_residue"]
    # event_hero_duel_percent_mutations grows its resolver table with +=.
    (tmp_path / "cases.py").write_text("MUTANTS = [1, 2]\nMUTANTS += [3]\n")
    assert scoreboard._count(tmp_path, {"path": "cases.py", "kind": "ast_list", "key": "MUTANTS"}) == 3


def test_uncomfortable_results_print_without_becoming_a_gate(monkeypatch, capsys):
    board = deepcopy(scoreboard.build_scoreboard())
    board["golden"]["passing"] = 12
    board["bite_rate"].update(mutation_bites=3, real_boundaries=0)
    board["mutation_residue"]["verdict"] = "RESIDUE"
    board["families"][0]["members"][0]["last_result"].update(passed=0, failed=4)
    monkeypatch.setattr(scoreboard, "build_scoreboard", lambda: board)
    monkeypatch.setattr(sys, "argv", ["scoreboard"])
    assert scoreboard.main() == 0
    output = capsys.readouterr().out
    for fragment in ["12/709 passing", "3/40 bite", "0/40 real boundaries", "RESIDUE", "4 fail"]:
        assert fragment in output


def test_new_and_legacy_names_are_counted_visibly(tmp_path):
    import shutil

    source = scoreboard.REPO
    shutil.copytree(source / "backend/scripts/evals", tmp_path / "backend/scripts/evals")
    shutil.copytree(source / "backend/tests/evals", tmp_path / "backend/tests/evals")
    shutil.copytree(source / "backend/tests/fixtures", tmp_path / "backend/tests/fixtures")
    shutil.copy2(source / "backend/tests/test_mutation_guard.py", tmp_path / "backend/tests/test_mutation_guard.py")
    evals = tmp_path / scoreboard.EVALS
    (evals / "unregistered_canary.py").write_text("# unregistered\n")
    (evals / "legacy_canary.py").write_text("# reviewed legacy\n")
    path = evals / "eval_registry.json"
    registry = json.loads(path.read_text())
    # A second member reading exactly the same sample does not double the
    # family's case count. This is the four Search adapters' real shape.
    original = scoreboard.build_scoreboard()
    canonical = registry["domains"][0]["canonical"]
    registry["domains"][0]["members"].append({"name": "shared_corpus_canary", "relation": "extends", "target": canonical})
    record_path = evals / "scoreboard_record.json"
    record = json.loads(record_path.read_text())
    record["artifacts"]["shared_corpus_canary"] = record["artifacts"][canonical]
    record_path.write_text(json.dumps(record))
    registry.setdefault("legacy", []).append({"name": "legacy_canary", "reason": "test disposition"})
    path.write_text(json.dumps(registry))
    board = scoreboard.build_scoreboard(tmp_path)
    assert board["families"][0]["cases"] == original["families"][0]["cases"]
    assert "unregistered_canary" in board["registry"]["unregistered_names"]
    assert "legacy_canary" in board["registry"]["legacy_names"]
    assert "legacy_canary" not in board["registry"]["unregistered_names"]
