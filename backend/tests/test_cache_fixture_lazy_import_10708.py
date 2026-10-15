"""Cache cleanup must preserve isolation without importing unrelated apps."""

import builtins
import inspect
from pathlib import Path
import sys
from types import ModuleType

import pytest


TARGET = Path(__file__).with_name("conftest.py").resolve()
CACHES = (
    "app.tasks.live_blend_refresh",
    "app.utils.request_cache",
    "app.utils.candidate_base",
    "app.utils.principal_independent_cache",
    "app.utils.event_history_cache",
    "app.routes.calibration",
)


@pytest.fixture
def root_fixtures():
    return next(
        module
        for module in tuple(sys.modules.values())
        if getattr(module, "__file__", None)
        and Path(module.__file__).resolve() == TARGET
    )


def cache_modules(calls):
    modules = {name: ModuleType(name) for name in CACHES}
    modules[CACHES[0]]._pending_handoff = {"event": "old"}
    modules[CACHES[-1]]._staged_cache = {"data": "old", "timestamp": 100.0}
    for name, methods in (
        (
            CACHES[1],
            (
                "_reset_last_good_for_tests",
                "_reset_inflight_for_tests",
                "_reset_shared_client_for_tests",
            ),
        ),
        (CACHES[2], ("_reset_l0_for_tests",)),
        (CACHES[3], ("clear_shared_builds",)),
        (CACHES[4], ("_reset_for_tests",)),
    ):
        for method in methods:

            def reset(label=f"{name}.{method}"):
                calls.append(label)

            setattr(modules[name], method, reset)
    return modules


def install(monkeypatch, modules):
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def finish(generator):
    with pytest.raises(StopIteration):
        next(generator)


def test_every_existing_reset_runs_before_and_after(root_fixtures, monkeypatch):
    calls = []
    modules = cache_modules(calls)
    install(monkeypatch, modules)
    handoff = inspect.unwrap(root_fixtures._reset_live_blend_pending_handoff)()
    caches = inspect.unwrap(root_fixtures._reset_request_cache_state)()
    next(handoff)
    next(caches)
    assert modules[CACHES[0]]._pending_handoff == {}
    assert modules[CACHES[-1]]._staged_cache == {"data": None, "timestamp": 0.0}
    assert len(calls) == len(set(calls)) == 6
    modules[CACHES[0]]._pending_handoff["new"] = "debt"
    modules[CACHES[-1]]._staged_cache.update(data="new", timestamp=200.0)
    finish(handoff)
    finish(caches)
    assert modules[CACHES[0]]._pending_handoff == {}
    assert modules[CACHES[-1]]._staged_cache == {"data": None, "timestamp": 0.0}
    assert len(calls) == 12
    assert all(calls.count(name) == 2 for name in set(calls))


def test_modules_loaded_during_test_are_reset_at_teardown(root_fixtures, monkeypatch):
    # Remove cached parent attributes too; otherwise an evicted module may still
    # be genuinely live and should still be reset.
    for name in CACHES:
        monkeypatch.delitem(sys.modules, name, raising=False)
        parent, _, leaf = name.rpartition(".")
        if parent in sys.modules:
            monkeypatch.delattr(sys.modules[parent], leaf, raising=False)
    handoff = inspect.unwrap(root_fixtures._reset_live_blend_pending_handoff)()
    caches = inspect.unwrap(root_fixtures._reset_request_cache_state)()
    next(handoff)
    next(caches)
    calls = []
    modules = cache_modules(calls)
    install(monkeypatch, modules)
    finish(handoff)
    finish(caches)
    assert modules[CACHES[0]]._pending_handoff == {}
    assert modules[CACHES[-1]]._staged_cache["data"] is None
    assert len(calls) == 6


def test_cleanup_never_imports_routes_or_tasks(root_fixtures, monkeypatch):
    original = builtins.__import__

    def refuse_import(name, *args, **kwargs):
        if name.startswith(("app.tasks", "app.routes")):
            raise AssertionError("cleanup imported unrelated application: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_import)
    for function in (
        root_fixtures._reset_live_blend_pending_handoff,
        root_fixtures._reset_request_cache_state,
    ):
        generator = inspect.unwrap(function)()
        next(generator)
        finish(generator)


def test_evicted_module_with_live_parent_attribute_is_still_reset(
    root_fixtures, monkeypatch
):
    module = ModuleType("app.tasks.live_blend_refresh")
    module._pending_handoff = {1: "old"}
    package = ModuleType("app.tasks")
    package.live_blend_refresh = module
    monkeypatch.setitem(sys.modules, "app.tasks", package)
    monkeypatch.delitem(sys.modules, module.__name__, raising=False)
    root_fixtures._reset_loaded_live_blend_handoff()
    assert module._pending_handoff == {}


def test_module_lookup_does_not_execute_dynamic_package_loader(
    root_fixtures, monkeypatch
):
    package = ModuleType("app.routes")

    def dynamic(name):
        raise AssertionError("dynamic package loader ran")

    package.__getattr__ = dynamic
    monkeypatch.setitem(sys.modules, "app.routes", package)
    monkeypatch.delitem(sys.modules, "app.routes.calibration", raising=False)
    assert root_fixtures._loaded_cache_modules("app.routes.calibration") == ()


@pytest.mark.parametrize("name", [CACHES[0], CACHES[-1]])
def test_divergent_parent_and_registry_identities_both_reset(
    root_fixtures, monkeypatch, name
):
    registered = cache_modules([])[name]
    cached = cache_modules([])[name]
    parent, _, leaf = name.rpartition(".")
    package = ModuleType(parent)
    setattr(package, leaf, cached)
    monkeypatch.setitem(sys.modules, parent, package)
    monkeypatch.setitem(sys.modules, name, registered)
    if name == CACHES[0]:
        root_fixtures._reset_loaded_live_blend_handoff()
        assert registered._pending_handoff == cached._pending_handoff == {}
    else:
        root_fixtures._reset_loaded_request_caches()
        assert (
            registered._staged_cache
            == cached._staged_cache
            == {"data": None, "timestamp": 0.0}
        )


@pytest.mark.parametrize("name", CACHES)
def test_setup_identities_retained_after_complete_eviction(
    root_fixtures, monkeypatch, name
):
    calls = []
    modules = cache_modules(calls)
    install(monkeypatch, modules)
    parent, _, leaf = name.rpartition(".")
    if parent in sys.modules:
        monkeypatch.delattr(sys.modules[parent], leaf, raising=False)
    fixture = (
        root_fixtures._reset_live_blend_pending_handoff
        if name == CACHES[0]
        else root_fixtures._reset_request_cache_state
    )
    generator = inspect.unwrap(fixture)()
    next(generator)
    calls.clear()
    modules[CACHES[0]]._pending_handoff["later"] = "debt"
    modules[CACHES[-1]]._staged_cache.update(data="later", timestamp=10.0)
    monkeypatch.delitem(sys.modules, name)
    finish(generator)
    if name == CACHES[0]:
        assert modules[name]._pending_handoff == {}
    elif name == CACHES[-1]:
        assert modules[name]._staged_cache == {"data": None, "timestamp": 0.0}
    else:
        assert any(label.startswith(name + ".") for label in calls)
