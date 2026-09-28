"""#9267 follow-up: a dict literal in `sport_keys.py` must not name one key twice.

CERT-3681 found `"soccer_mexico_ligamx": 2` written twice in
`EXPECTED_GAME_STATE_INDICATORS` (#9267 added a copy of #5588's entry). Both
said 2, so nothing broke — but Python keeps the LAST value in silence, so the
next duplicate that disagrees changes behaviour with no error anywhere. This
reads the source, because the built dict has already thrown the evidence away.

Two rules. (1) No key in any dict literal carries two DIFFERENT values — that
is the silent last-wins hazard, file-wide. (2) The maps an ESPN league key is
added to (the #8675/#9267 shape) name each key once, full stop. Eleven agreeing
duplicates in `KALSHI_FUTURES_TICKER_TO_SPORT_KEY` predate this and are left to
rule 1: they cannot change behaviour.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

SPORT_KEYS = Path(__file__).resolve().parents[1] / "app" / "utils" / "sport_keys.py"

ESPN_LEAGUE_MAPS = {
    "SPORT_LEAGUE_MAP",
    "EXPECTED_GAME_STATE_INDICATORS",
    "ESPN_SPORT_MAPPING",
}


def _dict_literals(tree: ast.AST) -> list[tuple[str | None, ast.Dict]]:
    out: list[tuple[str | None, ast.Dict]] = []
    named: set[int] = set()
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target and isinstance(node.value, ast.Dict):
            out.append((target, node.value))
            named.add(id(node.value))
    out.extend((None, n) for n in ast.walk(tree) if isinstance(n, ast.Dict) and id(n) not in named)
    return out


def _entries(d: ast.Dict) -> dict[object, list[tuple[int, str]]]:
    seen: dict[object, list[tuple[int, str]]] = defaultdict(list)
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant):
            seen[k.value].append((k.lineno, ast.dump(v)))
    return seen


def _tree() -> ast.AST:
    return ast.parse(SPORT_KEYS.read_text())


def test_no_key_carries_two_different_values():
    conflicts = []
    for name, d in _dict_literals(_tree()):
        for key, hits in _entries(d).items():
            if len({dump for _, dump in hits}) > 1:
                conflicts.append((name, key, [line for line, _ in hits]))
    assert conflicts == []


def test_espn_league_maps_name_each_key_once():
    dupes = []
    found = set()
    for name, d in _dict_literals(_tree()):
        if name not in ESPN_LEAGUE_MAPS:
            continue
        found.add(name)
        for key, hits in _entries(d).items():
            if len(hits) > 1:
                dupes.append((name, key, [line for line, _ in hits]))
    assert found == ESPN_LEAGUE_MAPS
    assert dupes == []


def test_liga_mx_still_on_every_espn_map():
    from app.utils.sport_keys import (
        ESPN_SPORT_MAPPING,
        EXPECTED_GAME_STATE_INDICATORS,
        SPORT_LEAGUE_MAP,
    )

    assert SPORT_LEAGUE_MAP["soccer_mexico_ligamx"] == ("soccer", "mex.1")
    assert ESPN_SPORT_MAPPING["soccer_mexico_ligamx"] == "soccer/mex.1"
    assert EXPECTED_GAME_STATE_INDICATORS["soccer_mexico_ligamx"] == 2


def test_rule_one_bites_on_a_disagreeing_duplicate():
    tree = ast.parse('M = {"a": 1, "b": 2, "a": 3}\nN = {"a": 1, "a": 1}')
    by_name = {name: d for name, d in _dict_literals(tree)}
    m = {k: {dump for _, dump in h} for k, h in _entries(by_name["M"]).items()}
    n = {k: {dump for _, dump in h} for k, h in _entries(by_name["N"]).items()}
    assert len(m["a"]) == 2
    assert len(n["a"]) == 1
