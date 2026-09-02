"""#2622 — the rekey rail: reachable, additive, idempotent, and bounded.

The producer fix only reaches markets as they are ingested again. The two US
Open winner boards are already in the table, so the ship needs a rail that walks
the standing population — and a rail that can do MORE than append would be an
unbounded reclassification wearing a narrow name.

RED-FIRST: this whole file fails on master, where
`app.tasks.repair_canonical_market_key` does not exist. Symbols are resolved
lazily so the failure is a COUNT of assertions rather than a collection error.
"""

import inspect
from importlib import import_module

import pytest


def _mod():
    try:
        module = import_module("app.tasks.repair_canonical_market_key")
    except ModuleNotFoundError:  # pragma: no cover - only on the pre-fix tree
        module = None
    assert module is not None, (
        "app.tasks.repair_canonical_market_key does not exist on this tree — "
        "#2622's rekey rail is not applied"
    )
    return module


class TestItIsReachable:
    def test_both_halves_are_registered_in_the_same_commit_that_builds_them(self):
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["canonical-key-rekey-census"] == (
            "app.tasks.repair_canonical_market_key",
            "census",
        )
        assert _REPAIRS["canonical-key-rekey"] == (
            "app.tasks.repair_canonical_market_key",
            "repair",
        )

    def test_the_docstring_catalog_did_not_drift_again(self):
        import app.routes.admin_repairs as mod

        assert "canonical-key-rekey" in (mod.__doc__ or ""), (
            "the docstring catalog has drifted from the registry again"
        )

    def test_the_dispatcher_can_forward_every_param_this_rail_declares(self):
        # FastAPI drops an unknown query param SILENTLY, so a cursor the
        # dispatcher cannot pass would re-read page one forever while the
        # response looked busy.
        import app.routes.admin_repairs as mod

        forwarded = set(
            inspect.signature(mod.run_repair).parameters
        )
        declared = set(inspect.signature(_mod().repair).parameters)
        declared -= {"session", "apply"}
        assert declared <= forwarded, declared - forwarded


class TestItCanOnlyAppend:
    def test_the_eligibility_predicate_counts_exactly_three_colons(self):
        # A pre-#2622 key has four segments. This is both the eligibility test
        # and the idempotence guarantee: a rekeyed row grows a fourth colon and
        # leaves the population for good.
        predicate = _mod().PRE_DISCIPLINE_PREDICATE
        assert "= 3" in predicate
        assert "canonical_market_key IS NOT NULL" in predicate

    def test_it_never_re_derives_league_or_season(self):
        # The whole design. Re-running `detect_league` / `detect_season` over
        # 861,809 rows would churn keys for reasons unrelated to #2622.
        #
        # Scanned as an AST rather than as text: this module's own docstring
        # NAMES all three functions while explaining why it does not call them,
        # so a substring search here is vacuous — it fails on the explanation
        # and would pass on a module that quietly deleted the paragraph and
        # called them anyway.
        import ast

        import app.tasks.repair_canonical_market_key as rail

        tree = ast.parse(inspect.getsource(rail))
        referenced = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        } | {
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) for alias in node.names
        }
        forbidden = {"detect_league", "detect_season", "compute_canonical_market_key"}
        assert not (referenced & forbidden), referenced & forbidden
        # And the one thing it IS allowed to derive.
        assert "market_discipline_axis" in referenced

    def test_the_only_write_is_an_append_guarded_by_the_key_it_read(self):
        import app.tasks.repair_canonical_market_key as rail

        source = inspect.getsource(rail.repair)
        # One UPDATE, and it is compare-and-set on the exact prior key.
        assert source.count("UPDATE futures_markets") == 1
        assert "AND canonical_market_key = :old_key" in source

    def test_the_default_population_is_open_and_all_is_spelled_out(self):
        # `population=all` reaches the resolved rows the calibration fair-fight
        # pairing joins on. That is a calibration decision, not a lane's.
        mod = _mod()
        assert set(mod.POPULATIONS) == {"open", "all"}
        assert mod.POPULATIONS["open"] == "status = 'open'"
        assert inspect.signature(mod.repair).parameters["population"].default == "open"
        assert inspect.signature(mod.census).parameters["population"].default == "open"

    def test_an_unknown_population_is_refused_by_name(self):
        mod = _mod()
        with pytest.raises(ValueError) as exc:
            mod._population_sql("resolved")
        assert "resolved" in str(exc.value)

    def test_the_limit_is_bounded_at_both_ends(self):
        mod = _mod()
        assert 0 < mod.DEFAULT_LIMIT <= mod.MAX_LIMIT


class TestItReportsWhatItDidNotDo:
    def test_the_repair_returns_a_keyset_cursor_not_an_offset(self):
        # CAL-P058 / C-CERT-1852: a page that rekeys its rows removes them from
        # its own population, so an OFFSET steps over as many untouched rows as
        # it just repaired.
        params = inspect.signature(_mod().repair).parameters
        assert "after_id" in params
        assert "offset" not in params

    def test_skipped_rows_leave_with_a_name(self):
        # Ruling 054 — a market this rail cannot change is COUNTED, never
        # silently dropped from the arithmetic.
        source = inspect.getsource(_mod().repair)
        assert "skipped_no_discipline_in_name" in source

    def test_the_census_cannot_write(self):
        source = inspect.getsource(_mod().census)
        for verb in ("UPDATE", "INSERT", "DELETE", "commit"):
            assert verb not in source, f"the census reached for {verb}"
