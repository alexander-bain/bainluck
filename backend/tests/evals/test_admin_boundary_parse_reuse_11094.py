"""Actual file mutations must invalidate the bounded admin parser cache."""

import os

import pytest

from scripts.evals import admin_destructive_boundary_contract as contract

SOURCE = """@router.post("/erase")
def erase():
    _check_admin_destructive(secret)
    db.execute("DELETE FROM example")
"""
KEY = "admin_example.py:post:/erase"


@pytest.fixture
def routes(tmp_path, monkeypatch):
    contract._parse_handlers.cache_clear()
    monkeypatch.setattr(contract, "ROUTES", tmp_path)
    (tmp_path / "admin_example.py").write_text(SOURCE)
    yield tmp_path
    contract._parse_handlers.cache_clear()


@pytest.fixture
def parsed_sources(monkeypatch):
    original = contract.ast.parse
    calls = []

    def parse(source, *args, **kwargs):
        calls.append(source)
        return original(source, *args, **kwargs)

    monkeypatch.setattr(contract.ast, "parse", parse)
    return calls


def test_identical_contents_parse_once_and_return_equal_results(routes, parsed_sources):
    first = contract.handlers()
    assert first[KEY]["strong_gate_calls"] == 1
    assert contract.handlers() == first
    assert parsed_sources == [SOURCE]


def test_gate_mutation_with_same_size_and_mtime_is_observed(routes):
    pack = {
        "cases": [
            {
                "id": "example",
                "module": "admin_example.py",
                "method": "post",
                "route": "/erase",
            }
        ]
    }
    assert contract.evaluate_pack(pack)["passed"] == 1
    path = routes / "admin_example.py"
    before = path.stat()
    changed = SOURCE.replace("_check_admin_destructive(", "_check_admin_secret(")
    path.write_text(changed.ljust(len(SOURCE)))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    result = contract.evaluate_pack(pack)
    assert result["passed"] == 0
    assert result["rows"][0]["actual"]["weak_gate_calls"] == 1


def test_adding_and_removing_files_cannot_reuse_old_membership(routes):
    assert set(contract.handlers()) == {KEY}
    second = routes / "admin_other.py"
    second.write_text(SOURCE.replace("/erase", "/other"))
    assert set(contract.handlers()) == {KEY, "admin_other.py:post:/other"}
    (routes / "admin_example.py").unlink()
    assert set(contract.handlers()) == {"admin_other.py:post:/other"}
    second.unlink()
    assert contract.handlers() == {}


def test_new_root_is_reparsed_even_with_identical_contents(
    routes, parsed_sources, tmp_path_factory, monkeypatch
):
    expected = contract.handlers()
    other = tmp_path_factory.mktemp("other-routes")
    (other / "admin_example.py").write_text(SOURCE)
    monkeypatch.setattr(contract, "ROUTES", other)
    assert contract.handlers() == expected
    assert parsed_sources == [SOURCE, SOURCE]


def test_nested_caller_mutations_do_not_poison_future_results(routes):
    first = contract.handlers()
    first[KEY]["strong_gate_calls"] = 99
    first[KEY]["signals"].append("invented")
    first["extra"] = {}
    next_result = contract.handlers()
    assert set(next_result) == {KEY}
    assert next_result[KEY]["strong_gate_calls"] == 1
    assert next_result[KEY]["signals"] == ["delete from"]


def test_changed_classification_policy_invalidates_results(routes, monkeypatch):
    assert KEY in contract.handlers()
    monkeypatch.setattr(contract, "MUTATING_METHODS", {"get"})
    assert contract.handlers() == {}
    monkeypatch.setattr(contract, "MUTATING_METHODS", {"post"})
    monkeypatch.setattr(contract, "DESTRUCTIVE_SIGNALS", ("not present",))
    assert contract.handlers() == {}


def test_explicit_clear_reparses_and_cache_retains_only_one_snapshot(
    routes, parsed_sources
):
    contract.handlers()
    contract._parse_handlers.cache_clear()
    contract.handlers()
    assert parsed_sources == [SOURCE, SOURCE]
    path = routes / "admin_example.py"
    for suffix in ["\n# second", "\n# third"]:
        path.write_text(SOURCE + suffix)
        contract.handlers()
    assert contract._parse_handlers.cache_info().currsize == 1
