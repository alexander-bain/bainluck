"""#4958 — every writer of `current_probability` maintains `price_changed_at`.

THE DEFECT THIS SCAN EXISTS FOR. `price_changed_at` (#2024) is maintained by one
shared helper, `app/utils/price_change_stamp.py`, because a second copy of a
change-detection predicate does not throw when it drifts — it just stops
stamping, and the column quietly becomes wrong for one provider while looking
healthy for the others. That is not the failure that happened. What happened is
simpler and the helper's own docstring names it: the rollout reached three poll
tasks and a fourth writer was never one of them. On 2026-09-11 production held
**57,103 DataGolf legs, 0 stamped, ever**, of which 52,031 had been written in
the previous 24 hours. Not a low rate — none.

WHY THIS IS A SCAN AND NOT A PER-WRITER TEST. The defect is an ABSENT CALL. A
unit test per writer passes on the writers that comply and cannot notice the one
that does not exist yet. Only a scan over the writer SET can say "this is all of
them", which is the claim the column's readers depend on.

AND WHY IT IS NOT THE CENSUS THAT ALREADY EXISTS. `test_futures_stamp_semantics.
py::PRICE_CHANGE_STAMPERS` counts how many times each file in `app/tasks` calls
`price_changed_at_value(`. That is the right question asked from the wrong end:
it can only see files that ALREADY call the helper, so a writer that calls it
zero times declares nothing and the tripwire has no count to drift. It missed
the WebSocket consumers (Q460) and then missed DataGolf. This file asks the
complementary question — which write SITES exist, and which of them stamp — and
therefore reports the absences. Both are kept: that census is the cheap
per-file ratchet, this is the site-level one. Updating one without the other
will red the build, which is the intended coupling.

WHY IT IS PER-SITE AND NOT PER-MODULE. #4958 specified the guard as "every
module writing `FuturesOutcome.current_probability` also references
`price_change_stamp`". That is one grep, and it would already be satisfied by
`app/tasks/futures.py` — which imports the helper, uses it in its upsert, and
still has TWO ORM branches (`existing.current_probability = prob` at the update,
`= 0` at the stale-zeroing) that write a price and stamp nothing. A module-level
scan calls that file clean. So the unit here is the WRITE SITE.

THE RULES, AND WHY EACH ONE IS THE SHAPE IT IS
──────────────────────────────────────────────
* An **UPDATE** — `update(FuturesOutcome).values(...)`, an `on_conflict_do_update`
  `set_` mapping, or an ORM attribute assignment — must maintain the stamp. A
  price going AWAY counts: `NULL` is a change, which is why the helper takes the
  new value rather than short-circuiting on `None`.
* An **INSERT** — `pg_insert(FuturesOutcome).values(...)`, `FuturesOutcome(...)`
  — is exempt. A row that has just been created has no earlier price to have
  moved from, and a stamp on it would read as a move that never happened. NULL
  is the honest value and every existing writer leaves it that way.
* An **ORM assignment** is satisfied by an assignment to `price_changed_at` on
  the SAME local name inside the SAME function. That is deliberately structural,
  not semantic: it cannot prove the expression is right (the sibling file
  `test_datagolf_price_changed_at_4958.py` does that against a real round trip),
  only that the write does not silently skip the column.
* `self.<column> = …` is not a site. Two plain wrapper classes in `app/`
  (`event_chart_backfill.py`, `utils/tennis_population.py`) and the model's own
  `probability` setter assign that attribute name on an object that is not a
  loaded row. `test_a_self_assignment_is_not_a_site` pins the exclusion.
* A shape the scan cannot READ is a failure, never a pass. An
  `on_conflict_do_update(set_=some_name)` whose dict cannot be resolved, or a
  `.values(**mapping)` splat, is reported as UNRECOGNISED — because both
  `kalshi.py` and `polymarket.py` build their `set_` dicts as annotated
  variables, and a scan that read those as "no columns named" would have quietly
  declared the two biggest writers compliant while seeing nothing at all.
* A `**helper(...)` splat is resolved by CALLING the helper (`SPLAT_HELPERS`),
  never by copying its column names into this file. #5246 introduced one — the
  shared settlement-price clause — precisely so that a settlement writer is a
  population with one definition rather than four copies, and a scan that
  hardcoded its keys would keep passing after somebody changed what it returns.
  A helper whose key set DEPENDS on its argument is left unreadable rather than
  resolved on whichever branch this file happened to list first.

THE LEDGER IS THE FINDING. Nine sites in six files still write a price without
maintaining the stamp; they are listed in `KNOWN_UNSTAMPED` with their reasons
and are tracked in #5192. They are NOT fixed here — three of them are in files
this lane does not own (D39), one is a route, and each needs its own reasoning
about whether a retirement or a display coercion is a "move". The ledger is
exact in both directions: a new unstamped site fails this test, and fixing a
listed one also fails it until the entry is removed. It can only shrink.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

PRICE = "current_probability"
STAMP = "price_changed_at"
MODEL = "FuturesOutcome"
INSERT_FUNCS = {"insert", "pg_insert"}
#: `update` is the SQLAlchemy builder; `sa_update` is the alias several task
#: modules import it under. Aliases are read from each module's imports too.
UPDATE_FUNCS = {"update", "sa_update"}

#: Write sites that do NOT maintain `price_changed_at`, measured 2026-09-11.
#: Keyed `(path, function, shape) -> count` so that both a new offender and a
#: repaired one fail this test. Every entry is a real gap; none is a decision.
#:
#:  * `admin_providers.py` — the admin "recompute from snapshots" path rewrites
#:    a price from stored snapshots. Owner: admin/ops.
#:  * `playoffs.py` — a GET coercing a crowned leg to 1.0 on a LOADED row. Not
#:    an ingest write and probably never persisted (the request session does not
#:    commit), but it is an assignment to a mapped attribute and this scan does
#:    not guess about autoflush.
#:  * `futures.py` — the dormant odds_api futures path (no writes since
#:    2026-03-23). Its upsert stamps; these two ORM branches do not. This is the
#:    likely explanation for the 57 odds_api legs #4958 left open.
#:  * `polymarket.py::_retire_unpriced_legs` — nulls a withdrawn leg's price.
#:    Its docstring reasons explicitly about `last_updated`, `opening_probability`
#:    and `is_winner`, and does not mention this column, so it reads as an
#:    omission rather than the deliberate exclusions beside it.
#:  * `prediction_market_matching.py` — the live price poll and the withdrawn-leg
#:    clear. lane1's file under D39; filed, not touched.
#:  * `tournament_price_refresh.py` — the Q428 ladder rail, which moves a price
#:    every ten minutes and is exactly the population a movement column is for.
KNOWN_UNSTAMPED: dict[tuple[str, str, str], int] = {
    ("app/routes/admin_providers.py", "normalize_futures_probabilities", "orm-assign"): 1,
    ("app/routes/playoffs.py", "get_playoff_grid", "orm-assign"): 1,
    ("app/tasks/futures.py", "_poll_futures_odds", "orm-assign"): 2,
    ("app/tasks/polymarket.py", "_retire_unpriced_legs", "update.values"): 1,
    ("app/tasks/prediction_market_matching.py", "_clear_withdrawn_outcome", "orm-assign"): 1,
    ("app/tasks/prediction_market_matching.py", "_poll_live_prediction_market_prices", "orm-assign"): 2,
    ("app/tasks/tournament_price_refresh.py", "_write_refreshed_prices", "update.values"): 1,
}


#: Helpers whose `**splat` into a `.values(...)`/`set_` mapping contributes a
#: statically known set of COLUMN NAMES, as `name -> (module, arg tuples)`.
#:
#: Resolved by importing and CALLING the helper rather than by listing its keys
#: here. A copied list is a second definition of the thing the helper exists to
#: be the only copy of: it would keep this scan green after someone changed what
#: the helper returns, which is the exact failure mode #4958 was filed for.
#:
#: Each helper is called once per argument tuple and the key sets must AGREE —
#: see `_keys_from_helper`.
SPLAT_HELPERS: dict[str, tuple[str, tuple]] = {
    # #5246 / CERT-2637. The shared settlement-price clause. The PRICE depends on
    # the argument (1.0 for a venue YES, 0.0 for a NO); the COLUMN SET does not,
    # so both branches are called and required to agree.
    "settled_price_values": ("app.utils.settled_price", (True, False)),
}


def _keys_from_helper(name: str) -> tuple[set[str], bool]:
    """(column names, readable) for a `**helper(...)` splat.

    Unknown callee => unreadable, so a new helper is a build failure that gets
    read by a person rather than a silent hole in the census.
    """
    spec = SPLAT_HELPERS.get(name)
    if spec is None:
        return set(), False
    import importlib

    module, arg_sets = spec
    func = getattr(importlib.import_module(module), name)
    per_call = [set(func(arg)) for arg in arg_sets]
    if any(keys != per_call[0] for keys in per_call):
        # An argument-dependent key set cannot be resolved at the call site
        # without evaluating the argument, which this scan does not do.
        return set(), False
    return per_call[0], True


def _splat_keys(value: ast.AST, tree: ast.AST | None, fn: str,
                owner: dict[int, str] | None) -> tuple[set[str], bool]:
    """(columns, readable) for one `**value` / `{**value}` element."""
    if isinstance(value, ast.Name) and tree is not None and owner is not None:
        return _resolve_named_mapping(value.id, tree, fn, owner)
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        return _keys_from_helper(value.func.id)
    return set(), False


def _aliases(tree: ast.AST, names: set[str]) -> set[str]:
    """Local names in this module bound to any of `names`, plus `names` itself.

    The bare spellings are always included: a module that never imports the name
    cannot use it, and keeping them makes the recogniser honest on the common
    unaliased case even if an import walk ever misses one (#4819's lesson from
    the sibling `is_winner` scan).
    """
    found = set(names)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in names:
                    found.add(alias.asname or alias.name)
    return found


def _is_model_ref(node: ast.AST, model_aliases: set[str]) -> bool:
    """Does this expression name `FuturesOutcome`, however it is spelled?

    Same two arms, and the same deliberate breadth, as the `is_winner` scan:
    a bare `Name` must be a known local alias; any `<x>.FuturesOutcome` is
    accepted on the attribute alone rather than by resolving `<x>` back to
    `app.models.models`, because every module spelling missed is a writer the
    guard cannot see.
    """
    if isinstance(node, ast.Name):
        return node.id in model_aliases
    if isinstance(node, ast.Attribute):
        return node.attr == MODEL
    return False


def _builder_kind(call: ast.Call, ins: set[str], upd: set[str]) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    else:
        return None
    if name in ins:
        return "insert"
    if name in upd:
        return "update"
    return None


def _chain_root(node: ast.AST, ins: set[str], upd: set[str]) -> ast.AST:
    """The base builder call of `X(...).values(...).on_conflict_do_update(...)`.

    The stop condition is "this call IS a builder", not "its func is a plain
    Name" — the latter walks straight past `sa.update(Model)` to the bare
    `Name('sa')` and loses the site entirely (#4819).
    """
    current: ast.AST = node
    while True:
        if isinstance(current, ast.Call):
            if _builder_kind(current, ins, upd):
                return current
            if isinstance(current.func, ast.Attribute):
                current = current.func.value
                continue
            return current
        if isinstance(current, ast.Attribute):
            current = current.value
            continue
        return current


def _mapping_keys(node: ast.AST, tree: ast.AST | None = None, fn: str = "",
                  owner: dict[int, str] | None = None) -> tuple[set[str], bool]:
    """(column names, readable) for a `.values(...)` call or a dict literal.

    A `**splat` is resolved when it names a local dict — `tournament_price_
    refresh.py` writes `.values(current_probability=v, **graded)`, where
    `graded` is a two-key dict built a few lines up, and refusing to read that
    would make a real site permanently unreadable. A splat this scan cannot
    follow leaves the mapping UNREADABLE, which is a failure, not a pass.
    """
    if isinstance(node, ast.Call):
        keys = {kw.arg for kw in node.keywords if kw.arg}
        readable = True
        for kw in node.keywords:
            if kw.arg is not None:
                continue
            found, ok = _splat_keys(kw.value, tree, fn, owner)
            keys |= found
            readable = readable and ok
        return keys, readable
    if isinstance(node, ast.Dict):
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        readable = True
        for key, value in zip(node.keys, node.values):
            if key is not None:
                continue
            found, ok = _splat_keys(value, tree, fn, owner)
            keys |= found
            readable = readable and ok
        return keys, readable
    return set(), False


def _function_of(tree: ast.AST) -> dict[int, str]:
    owner: dict[int, str] = {}
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(func):
                owner.setdefault(id(node), func.name)
    return owner


def _resolve_named_mapping(name: str, tree: ast.AST, fn: str,
                           owner: dict[int, str]) -> tuple[set[str], bool]:
    """Columns of a `set_=<local dict>`, gathered from that function.

    `kalshi.py` and `polymarket.py` both build the mapping as an ANNOTATED
    assignment (`update_set: dict = {...}`) and then add keys by subscript. Both
    forms are read; anything that leaves the name unresolved is reported as
    unreadable rather than as "names no columns", which would have declared the
    two largest writers in the codebase compliant on an empty reading.
    """
    keys: set[str] = set()
    resolved = False
    for node in ast.walk(tree):
        if owner.get(id(node), "<module>") != fn:
            continue
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            found, readable = _mapping_keys(node.value, tree, fn, owner)
            keys |= found
            resolved = resolved or readable
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            found, readable = _mapping_keys(node.value, tree, fn, owner)
            keys |= found
            resolved = resolved or readable
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == name
            and isinstance(node.slice, ast.Constant)
        ):
            keys.add(node.slice.value)
    return keys, resolved


def _sites_in_tree(rel: str, tree: ast.AST):
    """(stamped, unstamped, unrecognised) for one parsed module.

    Each site is a `(rel, lineno, function, shape)` tuple.
    """
    model_aliases = _aliases(tree, {MODEL})
    ins = _aliases(tree, INSERT_FUNCS) | INSERT_FUNCS
    upd = _aliases(tree, UPDATE_FUNCS) | UPDATE_FUNCS
    owner = _function_of(tree)

    stamped, unstamped, unrecognised = [], [], []

    for node in ast.walk(tree):
        # ── ORM attribute assignment ────────────────────────────────────────
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not (isinstance(target, ast.Attribute) and target.attr == PRICE):
                    continue
                base = target.value
                if isinstance(base, ast.Name) and base.id == "self":
                    continue
                fn = owner.get(id(node), "<module>")
                site = (rel, node.lineno, fn, "orm-assign")
                if not isinstance(base, ast.Name):
                    unrecognised.append(site)
                    continue
                if _stamps_same_local(tree, owner, fn, base.id):
                    stamped.append(site)
                else:
                    unstamped.append(site)

        # ── Core builders ───────────────────────────────────────────────────
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in ("values", "on_conflict_do_update"):
            continue
        root = _chain_root(node, ins, upd)
        if not (
            isinstance(root, ast.Call)
            and root.args
            and _is_model_ref(root.args[0], model_aliases)
        ):
            continue
        kind = _builder_kind(root, ins, upd)
        fn = owner.get(id(node), "<module>")

        if node.func.attr == "values":
            keys, readable = _mapping_keys(node, tree, fn, owner)
            site = (rel, node.lineno, fn, f"{kind}.values")
            if not readable:
                unrecognised.append(site)
            elif PRICE not in keys:
                continue
            elif kind == "insert" or STAMP in keys:
                stamped.append(site)
            else:
                unstamped.append(site)
            continue

        for kw in node.keywords:
            if kw.arg != "set_":
                continue
            site = (rel, node.lineno, fn, "on_conflict.set_")
            if isinstance(kw.value, ast.Name):
                keys, readable = _resolve_named_mapping(kw.value.id, tree, fn, owner)
            else:
                keys, readable = _mapping_keys(kw.value, tree, fn, owner)
            if not readable:
                unrecognised.append(site)
            elif PRICE not in keys:
                continue
            elif STAMP in keys:
                stamped.append(site)
            else:
                unstamped.append(site)

    return stamped, unstamped, unrecognised


def _stamps_same_local(tree: ast.AST, owner: dict[int, str], fn: str, local: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if owner.get(id(node), "<module>") != fn:
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == STAMP
                and isinstance(target.value, ast.Name)
                and target.value.id == local
            ):
                return True
    return False


def _scan_app():
    stamped, unstamped, unrecognised = [], [], []
    for path in sorted(APP_ROOT.rglob("*.py")):
        rel = str(path.relative_to(APP_ROOT.parent))
        s, u, x = _sites_in_tree(rel, ast.parse(path.read_text(), filename=str(path)))
        stamped += s
        unstamped += u
        unrecognised += x
    return stamped, unstamped, unrecognised


def _ledger(sites) -> Counter:
    return Counter((rel, fn, shape) for rel, _lineno, fn, shape in sites)


def test_the_scan_can_see_the_writers_it_is_scanning() -> None:
    """A recogniser that finds nothing reports green forever.

    Both shapes must be present, because the two rules are independent: the
    Core one is what `kalshi.py`/`polymarket.py` need, the ORM one is what
    `datagolf.py` needed and what no writer used before #4958.
    """
    stamped, unstamped, _ = _scan_app()
    shapes = {shape for _, _, _, shape in stamped + unstamped}
    assert "orm-assign" in shapes, "no ORM price assignment found — scan is blind"
    assert {"update.values", "on_conflict.set_"} & shapes, (
        "no Core price UPDATE found — scan is blind"
    )
    assert len(stamped) >= 10, f"only {len(stamped)} stamped sites — scan is blind"


def test_datagolf_maintains_the_stamp_at_every_write_site() -> None:
    """The subject of #4958, stated as the thing a reader can check.

    Four sites: the pre-tournament and in-play update branches, and the two
    stale loops that withdraw a player's price when they leave the field.
    """
    stamped, unstamped, _ = _scan_app()
    dg_stamped = [s for s in stamped if s[0] == "app/tasks/datagolf.py"]
    dg_unstamped = [s for s in unstamped if s[0] == "app/tasks/datagolf.py"]

    assert not dg_unstamped, (
        "DataGolf writes a price without maintaining `price_changed_at` at: "
        + ", ".join(f"{s[0]}:{s[1]}" for s in dg_unstamped)
    )
    assert len(dg_stamped) == 4, (
        "expected the four DataGolf update sites (two price refreshes, two "
        f"stale withdrawals); found {len(dg_stamped)}: {dg_stamped}"
    )


def test_no_new_writer_skips_the_stamp() -> None:
    """The ratchet, exact in both directions.

    A new unstamped site fails here; so does repairing a listed one without
    removing its entry. The list can only shrink, and it is never the place to
    add a site to make a build green — a price writer that cannot maintain the
    column needs the reason written down, in #5192, before the entry exists.
    """
    _, unstamped, _ = _scan_app()
    found = _ledger(unstamped)
    expected = Counter(KNOWN_UNSTAMPED)

    new = found - expected
    fixed = expected - found

    assert not new, (
        "These write `FuturesOutcome.current_probability` without maintaining "
        "`price_changed_at`, so the column reads as 'this price has never "
        "moved' on every row they touch:\n  "
        + "\n  ".join(f"{k[0]}::{k[2]} in {k[1]} ×{v}" for k, v in sorted(new.items()))
        + "\n\nUse `price_changed_at_value` from `app/utils/price_change_stamp.py` "
        "— on a Core UPDATE inside the `.values()`/`set_` mapping, on an ORM path "
        "as an assignment beside the price. Do not add an entry to "
        "KNOWN_UNSTAMPED to make this pass."
    )
    assert not fixed, (
        "These KNOWN_UNSTAMPED entries no longer match the code — remove them "
        "(the ledger is a debt list, not a config):\n  "
        + "\n  ".join(f"{k[0]}::{k[2]} in {k[1]} ×{v}" for k, v in sorted(fixed.items()))
    )


def test_every_write_shape_is_one_this_scan_can_read() -> None:
    """An unreadable shape is a failure, not a silent pass.

    `set_=<a local dict>` is the shape the two largest writers use; a `**splat`
    would hide any column at all. Either one reaching this list means the
    recogniser needs teaching, and the guard says so instead of shrinking.
    """
    _, _, unrecognised = _scan_app()
    assert not unrecognised, (
        "price write against FuturesOutcome in a shape this scan cannot read: "
        + ", ".join(f"{s[0]}:{s[1]} ({s[3]})" for s in unrecognised)
        + " — teach the scan this shape rather than deleting the check."
    )


# ── The recogniser, exercised on snippets rather than only on today's app/ ──
#
# A scan whose only test data is the code it already passes on cannot be shown
# to catch a spelling nobody has written yet. Every case below is a real shape
# from this codebase, reduced.

def _scan(source: str):
    return _sites_in_tree("snippet.py", ast.parse(source))


def test_an_unstamped_orm_assignment_is_caught() -> None:
    stamped, unstamped, _ = _scan(
        "def poll():\n"
        "    outcome.current_probability = prob\n"
        "    outcome.last_updated = now\n"
    )
    assert not stamped and len(unstamped) == 1


def test_a_stamped_orm_assignment_is_accepted() -> None:
    """The exact shape `datagolf.py` now writes."""
    stamped, unstamped, _ = _scan(
        "def poll():\n"
        "    outcome.price_changed_at = price_changed_at_value(a, b, prob)\n"
        "    outcome.current_probability = prob\n"
    )
    assert len(stamped) == 1 and not unstamped


def test_a_stamp_on_a_DIFFERENT_local_does_not_count() -> None:
    """Two rows in one function is the datagolf shape exactly: `outcome` and
    `stale`. Stamping one must not excuse the other."""
    stamped, unstamped, _ = _scan(
        "def poll():\n"
        "    outcome.price_changed_at = expr\n"
        "    outcome.current_probability = prob\n"
        "    stale.current_probability = None\n"
    )
    assert len(stamped) == 1 and len(unstamped) == 1


def test_a_stamp_in_a_DIFFERENT_function_does_not_count() -> None:
    stamped, unstamped, _ = _scan(
        "def a():\n"
        "    outcome.price_changed_at = expr\n"
        "def b():\n"
        "    outcome.current_probability = prob\n"
    )
    assert not stamped and len(unstamped) == 1


def test_a_self_assignment_is_not_a_site() -> None:
    """`event_chart_backfill.py`, `utils/tennis_population.py` and the model's
    own `probability` setter all assign this attribute on something that is not
    a loaded row."""
    stamped, unstamped, unrecognised = _scan(
        "class Wrapper:\n"
        "    def __init__(self, probability):\n"
        "        self.current_probability = probability\n"
    )
    assert (stamped, unstamped, unrecognised) == ([], [], [])


def test_an_insert_is_exempt_and_an_update_is_not() -> None:
    """A new row has no earlier price to have moved from; an UPDATE does."""
    stamped, unstamped, _ = _scan(
        "from sqlalchemy.dialects.postgresql import insert as pg_insert\n"
        "from sqlalchemy import update\n"
        "from app.models.models import FuturesOutcome\n"
        "def w():\n"
        "    pg_insert(FuturesOutcome).values(current_probability=p)\n"
        "    update(FuturesOutcome).values(current_probability=p)\n"
    )
    assert len(stamped) == 1 and len(unstamped) == 1
    assert stamped[0][3] == "insert.values" and unstamped[0][3] == "update.values"


def test_a_set_dict_built_as_an_annotated_local_is_read() -> None:
    """`kalshi.py`'s and `polymarket.py`'s actual shape. Before this arm the
    scan read those mappings as naming no columns at all."""
    stamped, unstamped, unrecognised = _scan(
        "from sqlalchemy.dialects.postgresql import insert as pg_insert\n"
        "from app.models.models import FuturesOutcome\n"
        "def w():\n"
        "    update_set: dict = {'current_probability': p, 'price_changed_at': e}\n"
        "    pg_insert(FuturesOutcome).values(x=1).on_conflict_do_update(\n"
        "        index_elements=['id'], set_=update_set)\n"
    )
    assert len(stamped) == 1 and not unstamped and not unrecognised
    assert stamped[0][3] == "on_conflict.set_"


def test_a_set_dict_that_omits_the_stamp_is_caught_through_the_local() -> None:
    _, unstamped, _ = _scan(
        "from sqlalchemy.dialects.postgresql import insert as pg_insert\n"
        "from app.models.models import FuturesOutcome\n"
        "def w():\n"
        "    update_set = {'current_probability': p}\n"
        "    pg_insert(FuturesOutcome).values(x=1).on_conflict_do_update(\n"
        "        index_elements=['id'], set_=update_set)\n"
    )
    assert len(unstamped) == 1


def test_an_unresolvable_set_mapping_is_UNRECOGNISED_not_compliant() -> None:
    """The fail-loud arm. A mapping arriving from elsewhere could name anything;
    reading it as "names no columns" is how a scan goes quietly blind."""
    _, unstamped, unrecognised = _scan(
        "from sqlalchemy.dialects.postgresql import insert as pg_insert\n"
        "from app.models.models import FuturesOutcome\n"
        "def w(mapping):\n"
        "    pg_insert(FuturesOutcome).values(x=1).on_conflict_do_update(\n"
        "        index_elements=['id'], set_=mapping)\n"
    )
    assert not unstamped and len(unrecognised) == 1


def test_a_values_splat_is_UNRECOGNISED() -> None:
    _, _, unrecognised = _scan(
        "from sqlalchemy import update\n"
        "from app.models.models import FuturesOutcome\n"
        "def w(cols):\n"
        "    update(FuturesOutcome).values(**cols)\n"
    )
    assert len(unrecognised) == 1


# ── `**helper(...)`, the #5246 shape ────────────────────────────────────────


def test_a_splat_of_a_KNOWN_helper_is_read_and_its_columns_counted() -> None:
    """The live shape at `backfill_winners.py::_backfill_kalshi_winners`.

    The helper contributes `current_probability`, so the site is a price write
    and the stamp beside it makes it a compliant one. Reading the splat is what
    makes that judgement possible at all — before this, the site was
    UNRECOGNISED and CI said so.
    """
    stamped, unstamped, unrecognised = _scan(
        "from sqlalchemy import update\n"
        "from app.models.models import FuturesOutcome\n"
        "from app.utils.settled_price import settled_price_values\n"
        "def w(is_winner):\n"
        "    update(FuturesOutcome).values(\n"
        "        is_winner=is_winner,\n"
        "        **settled_price_values(is_winner),\n"
        "        price_changed_at=expr,\n"
        "    )\n"
    )
    assert not unrecognised and not unstamped and len(stamped) == 1


def test_a_splat_of_a_KNOWN_helper_WITHOUT_the_stamp_is_still_caught() -> None:
    """Teaching the scan a shape must not excuse the shape.

    The whole risk of making an unreadable site readable is that it becomes
    readable AND compliant in one step. Same splat, no `price_changed_at`: the
    site must land in `unstamped`, which is what `test_no_new_writer_skips_the_
    stamp` ratchets on.
    """
    stamped, unstamped, unrecognised = _scan(
        "from sqlalchemy import update\n"
        "from app.models.models import FuturesOutcome\n"
        "from app.utils.settled_price import settled_price_values\n"
        "def w(is_winner):\n"
        "    update(FuturesOutcome).values(**settled_price_values(is_winner))\n"
    )
    assert not unrecognised and not stamped and len(unstamped) == 1


def test_a_splat_of_an_UNKNOWN_helper_stays_UNRECOGNISED() -> None:
    """The hole this could have opened. `_splat_keys` resolving any call at all
    would let a future `**whatever()` hide a price write; only the allowlist
    resolves, and everything else still fails loudly."""
    _, _, unrecognised = _scan(
        "from sqlalchemy import update\n"
        "from app.models.models import FuturesOutcome\n"
        "def w(x):\n"
        "    update(FuturesOutcome).values(**some_other_helper(x))\n"
    )
    assert len(unrecognised) == 1


def test_every_SPLAT_HELPER_is_importable_and_agrees_across_its_arguments() -> None:
    """The positive control on the allowlist itself.

    `_keys_from_helper` reports an argument-dependent key set as UNREADABLE,
    which is the safe direction but is indistinguishable from "resolved" at the
    call site once the entry exists. This asserts each listed helper really does
    resolve, so an entry cannot rot into a permanent silent refusal.
    """
    assert SPLAT_HELPERS, "the allowlist is empty — the resolver is unexercised"
    for name in SPLAT_HELPERS:
        keys, readable = _keys_from_helper(name)
        assert readable, f"{name} no longer resolves to a stable column set"
        assert keys, f"{name} resolved to no columns"


def test_the_settlement_helper_still_carries_the_price_column() -> None:
    """The coupling that makes #5246's guard and this one one system.

    If `settled_price_values` stopped naming `current_probability`, the
    settlement writers would silently leave `_scan_app`'s price-write set and
    this whole file would go green on them. The scan resolves the helper by
    calling it precisely so that change is visible here rather than nowhere.
    """
    keys, _ = _keys_from_helper("settled_price_values")
    assert PRICE in keys


def test_a_module_qualified_builder_resolves() -> None:
    """`sa.update(models.FuturesOutcome)` is the same write, and `_chain_root`'s
    stop condition is what keeps it visible."""
    _, unstamped, _ = _scan(
        "import sqlalchemy as sa\n"
        "from app.models import models\n"
        "def w():\n"
        "    sa.update(models.FuturesOutcome).values(current_probability=p)\n"
    )
    assert len(unstamped) == 1


def test_a_write_to_another_model_is_not_a_site() -> None:
    """The broad `attr == MODEL` arm must not swallow neighbouring tables."""
    stamped, unstamped, unrecognised = _scan(
        "from sqlalchemy import update\n"
        "from app.models.models import FuturesMarket\n"
        "def w():\n"
        "    update(FuturesMarket).values(current_probability=p)\n"
    )
    assert (stamped, unstamped, unrecognised) == ([], [], [])
