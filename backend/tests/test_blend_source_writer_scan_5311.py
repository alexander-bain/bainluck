"""#5311 / CU-4 — every writer of `Event.win_probability_sources` is accounted for.

THE COMMENT THIS FILE REPLACES. `stamp_source_reading`'s docstring ends: *"if you
add a seventh writer of this column, add it here too"*. That is a sentence, not a
guard. It is addressed to a person who has already decided to read the docstring
of the function they are not calling — which is precisely the person who does not
exist in the failure it describes. There are more than seven writers now.

WHY THE COLUMN NEEDS A POPULATION GUARD AT ALL. Two different defects live here
and they need two different questions asked.

  1. **A reading that never came through the stamper.** `stamp_source_reading` is
     the writer half of #1829 and the only thing that makes the hero's recency
     decay do anything: an entry with no `updated_at` keeps full weight forever.
     Correct as a default and invisible as a bug — nothing goes red, the number
     on the page is just quietly the wrong average.
  2. **A reading with no eligibility record.** CU-4's whole argument
     (`probability_eligibility.py`) is that an entry written by a gated writer
     and one written by an ungated one are INDISTINGUISHABLE after the fact. The
     record is what makes "zero ineligible probability inputs in the served
     payload" answerable. A market-derived writer that does not pass one grades
     `UNVERIFIED` forever, and the census cannot tell it from a genuine gap.

TWO POPULATIONS, BECAUSE ONE CANNOT SEE THE OTHER. This is the structural point
of the file and the reason it is not a single scan:

  * A **WRITE SITE** is where the column is PERSISTED — `update(Event).values(...)`,
    an ORM attribute assignment, a raw `UPDATE events SET ...`. Question 1 is
    asked here: does the value being persisted derive from the stamper?
  * A **MINT SITE** is where a reading is MADE — a call to `stamp_source_reading`.
    Question 2 is asked here: does it pass an eligibility record?

Neither population contains the other. `espn_sync._apply_final_pm_win_prob` mints
two readings (`kalshi`, `polymarket`) and RETURNS the dict for its caller to
persist — it contains no write site at all, so a write-site scan is structurally
blind to it, and it is one of the two real gaps this file reports. Conversely
`statpal_sync` persists this column three times and mints nothing, because what
it writes are sidecar keys and not readings.

WHY THE SOURCE KEY IS RESOLVED, AND WHY "UNKNOWN" MEANS "REQUIRED".
`MARKET_DERIVED_SOURCES` is `{kalshi, polymarket}` and the module is explicit
that the absence of a record on `betting` / `espn` / `stat_model` / `mlb` /
`final_result` is EXPECTED and not a finding — those five do not select among
sibling questions, so there is no wrong sibling to pick. Requiring a record from
them would bury the two sources that matter under five that never had the defect.
So this scan resolves each mint site's source argument, and grades:

    literal or module constant in MARKET_DERIVED_SOURCES  -> record REQUIRED
    literal or module constant, any other value           -> record not required
    anything it cannot resolve (`self.source`, a loop var) -> record REQUIRED

The last line is the load-bearing one and it is deliberately the conservative
direction. Three of the four live market-derived writers spell their source as a
variable (`self.source`, `anchor.source`); a scan that treated "unresolved" as
"probably fine" would exempt exactly the population the record exists for.

A SHAPE THIS SCAN CANNOT READ IS A FAILURE, NEVER A PASS. Inherited whole from
the sibling `test_price_stamp_writer_scan_4958.py`, which learned it the hard
way: a `.values(**mapping)` it could not resolve would have declared the biggest
writers compliant while seeing nothing. It matters more here than there, because
this column is written in FIVE syntactic shapes and one of them was found only by
reading the file:

    update(Event).values(win_probability_sources=x)   Core kwarg
    update(Event).values(**local_dict)                named-mapping splat
    event.win_probability_sources = x                 ORM assignment
    UPDATE events SET win_probability_sources = :wps  raw SQL in a string
    self.win_probability_sources = x                  NOT a site (see below)

`espn_helpers._sync_espn_win_probability` uses the second: it builds
`_update_vals: dict = {"win_probability_sources": _wps, ...}`, adds a key by
subscript, and splats it. A recogniser whose vocabulary is `win_probability_sources=`
scores that file zero and calls the ESPN writer absent. That is the silent-zero
failure this file is shaped around, and `test_every_write_shape_is_one_this_scan_can_read`
plus the per-shape red-checks below are what stop it recurring.

`self.<column> = ...` is NOT a site. `proven_duplicates.FoldedBlendView` assigns
that attribute name on a read-only proxy whose docstring is an argument for why
it must never write ("ruling 048 permits reading a ghost's content onto the page
and does not permit `UPDATE events SET win_probability_sources`"). It matches
every regex anyone would write and is the one construction here that is correct
BECAUSE it is not a write. `test_a_self_assignment_is_not_a_site` pins it.

THE LEDGERS ARE THE FINDING. Both are exact in both directions: a new offender
fails, and repairing a listed one also fails until its entry is removed. They can
only shrink. Nothing is fixed here — `espn_sync.py` and `backfill_combat_wps.py`
are outside the change this rides, `admin_matching.py` is a route, and each needs
its own reasoning about whether a record is even meaningful for what it writes.
Filed, not touched.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

COLUMN = "win_probability_sources"
MODEL = "Event"
STAMP = "stamp_source_reading"
PRUNE = "prune_blend_source"
UPDATE_FUNCS = {"update", "sa_update"}

#: The five sources whose readings are minted by choosing one market from
#: several. Imported rather than re-listed: a second copy of this set is the
#: #1951 drift failure, and the module that owns it is pure and safe to import.
from app.utils.probability_eligibility import MARKET_DERIVED_SOURCES  # noqa: E402

# ── Ledger 1: WRITE SITES whose persisted value does not come from the stamper ─
#
# Keyed `(path, function, shape) -> reason-class`. These are not readings, which
# is why they are permitted; the ledger records WHICH non-reading class each one
# is, so that a genuine reading appearing in one of these files still fails.
#
#  * `statpal_sync.py` — SIDECAR. Writes `statpal_fixture_id`,
#    `statpal_end_time` and the injuries block into this column "for backward
#    compatibility during migration". Non-probability keys; the stamper would be
#    the wrong function to call. (Two of the three are ORM assignment on a JSONB
#    column, which gotcha #4 says can silently fail — a separate defect from this
#    file's question, and not one this file asserts about.)
#  * `espn_sync.py::_process_live_sport` — SIDECAR, and the same shape as
#    `statpal_end_time` one bullet up. #5324/CERT-2777: when the authority
#    positively reports that a game we are serving as `live` has not begun, the
#    row is demoted to `scheduled` — and `_transition_event_statuses_impl`, on
#    the same 60s beat, would promote it straight back. That task makes zero API
#    calls by design, so the authority's statement has to reach it ON THE ROW.
#    It rides this column under the non-probability key `espn_not_started_at`
#    and is cleared by the next anchored pass that reports play. No probability
#    is written or read, so the stamper is the wrong function: there is no
#    source, no market and no reading to weight. Both shapes are listed because
#    the site does what `write_espn_win_prob` does — one Core update, then the
#    ORM object mirrored so in-session reads agree (gotcha #4/#5).
#  * `prediction_market_matching.py` / `admin_matching.py` / `source_intelligence.py`
#    — PRUNE. Each REMOVES a source key rather than writing a value: the two
#    `prune_blend_source` callers, the admin "clear kalshi" repair, and the raw
#    SQL that deletes `stat_model`/`espn`. A deletion mints no reading, so it has
#    no observation time and no market to name.
#  * `futures_price_refresh.py::_KALSHI_WITHDRAW_EVENT_HERO_SQL` — PRUNE, #5771.
#    When the venue has declared a result for a match that has not kicked off,
#    the leg is withdrawn from `futures_outcomes` AND the `kalshi` key is removed
#    from this column in the same transaction, because the hero and the chart
#    read this column and not those rows. It only ever removes a key: a
#    settlement is not a price, and no value we could write in its place is one
#    we have. Keyed by the CONSTANT rather than by `<module>` — see
#    `_module_constant_of` for why the file-wide key would be a hole.
KNOWN_NON_READING_WRITES: dict[tuple[str, str, str], str] = {
    ("backend/app/routes/admin_matching.py", "sawtooth_fix", "update.values"):
        "prune",
    ("backend/app/routes/source_intelligence.py", "cleanup_oscillation", "raw-sql"):
        "prune",
    ("backend/app/tasks/prediction_market_matching.py",
     "_cleanup_orphaned_blend_sources", "update.values"): "prune",
    ("backend/app/tasks/prediction_market_matching.py",
     "_prune_orphaned_blend_source", "update.values"): "prune",
    ("backend/app/tasks/prediction_market_matching.py",
     "_retire_unbacked_blend_source", "update.values"): "prune",
    ("backend/app/tasks/espn_sync.py", "_process_live_sport", "orm-assign"):
        "sidecar",
    ("backend/app/tasks/espn_sync.py", "_process_live_sport", "update.values"):
        "sidecar",
    ("backend/app/tasks/futures_price_refresh.py",
     "_KALSHI_WITHDRAW_EVENT_HERO_SQL", "raw-sql"): "prune",
    ("backend/app/tasks/statpal_sync.py", "_set_statpal_id", "orm-assign"):
        "sidecar",
    ("backend/app/tasks/statpal_sync.py", "_sync_statpal_injuries", "update.values"):
        "sidecar",
    ("backend/app/tasks/statpal_sync.py", "_sync_statpal_schedules", "orm-assign"):
        "sidecar",
}

# ── Ledger 2: MINT SITES that write a market-derived source with no record ────
#
# Keyed `(path, function, source-as-written) -> reason`. Every entry is a real
# census hole under CU-4, tracked on the issue named beside it. None is a
# decision that a record is unnecessary.
#
#  * `backfill_combat_wps.py` — stamps a literal `"kalshi"` reading for combat
#    sports. The clearest instance of the class: a market-derived source, minted
#    by choosing a market, with nothing naming which one.
#  * `espn_sync.py::_apply_final_pm_win_prob` — on settlement, overwrites the
#    `kalshi` and `polymarket` entries with the resolved result. Two things are
#    true and neither is decidable here: the value no longer comes from a market
#    price at all (so `verified` may be the wrong grade rather than a missing
#    one), and because a `None` record never CLEARS one, whatever record a prior
#    poll wrote survives beside a value that writer did not produce.
#  * `admin_matching.py::relink_*` — an admin repair whose `source` is a runtime
#    argument, so it can be either market-derived source. Unresolvable by
#    construction, and graded REQUIRED for that reason.
#
# REPAIRED and removed, #5273 CU-1 clause (1): `admin_matching.py::
# backfill_win_probability_sources`. Its `source` is still a runtime argument —
# that was never the reason it could not carry a record. It could not carry one
# because it did not ASK the gate: it selected a market by title and resolved an
# outcome by containment, so it had no admission to name. It now calls
# `admissible_as_blend_speaker` and mints from that, which is why this ledger is
# a ratchet in both directions — the entry's own removal is the proof.
KNOWN_UNRECORDED_MINTS: dict[tuple[str, str, str], str] = {
    ("backend/app/tasks/backfill_combat_wps.py", "_backfill_combat_wps", "kalshi"):
        "combat-sports backfill, literal kalshi, no market named",
    ("backend/app/tasks/espn_sync.py", "_apply_final_pm_win_prob", "<dynamic>"):
        "settlement overwrite of kalshi/polymarket with the resolved result",
}


# ── recogniser ────────────────────────────────────────────────────────────────


def _aliases(tree: ast.AST, names: set[str]) -> set[str]:
    """Local names bound to any of `names`, plus the bare spellings.

    The bare spellings are always included for the sibling scan's reason: a
    module that never imports the name cannot use it, so keeping them costs
    nothing and keeps the recogniser honest if an import walk ever misses one.
    """
    found = set(names)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in names:
                    found.add(alias.asname or alias.name)
    return found


def _is_model_ref(node: ast.AST, model_aliases: set[str]) -> bool:
    """Does this expression name `Event`, however it is spelled?

    Deliberately broad on the attribute arm: any `<x>.Event` is accepted without
    resolving `<x>` back to `app.models.models`, because every spelling missed is
    a writer the guard cannot see.
    """
    if isinstance(node, ast.Name):
        return node.id in model_aliases
    if isinstance(node, ast.Attribute):
        return node.attr == MODEL
    return False


def _builder_call(call: ast.Call, upd: set[str]) -> bool:
    func = call.func
    name = func.id if isinstance(func, ast.Name) else (
        func.attr if isinstance(func, ast.Attribute) else None
    )
    return name in upd


def _chain_root(node: ast.AST, upd: set[str]) -> ast.AST:
    """The base builder call of `update(Event).where(...).values(...)`.

    The stop condition is "this call IS a builder", not "its func is a plain
    Name": the latter walks past `sa.update(Model)` to the bare `Name('sa')` and
    loses the site entirely (#4819's lesson, inherited).
    """
    current: ast.AST = node
    while True:
        if isinstance(current, ast.Call):
            if _builder_call(current, upd):
                return current
            if isinstance(current.func, ast.Attribute):
                current = current.func.value
                continue
            return current
        if isinstance(current, ast.Attribute):
            current = current.value
            continue
        return current


def _function_of(tree: ast.AST) -> dict[int, str]:
    owner: dict[int, str] = {}
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(func):
                owner.setdefault(id(node), func.name)
    return owner


def _module_constant_of(tree: ast.AST) -> dict[int, str]:
    """Node id -> the MODULE-LEVEL constant whose assignment encloses it.

    `_function_of` can only answer for nodes inside a `def`. A raw-SQL statement
    hoisted to a module constant — `_KALSHI_WITHDRAW_EVENT_HERO_SQL = text(...)`,
    the shape `futures_price_refresh.py` uses — has no enclosing function, so it
    would be attributed to `<module>` and its ledger entry would read
    `(path, "<module>", "raw-sql")`. That key is the whole file: a SECOND
    module-level statement in the same module, one that did mint a reading,
    would match an entry written for this one and never be seen. Naming the
    constant keeps ledger 1 as exact as its docstring claims.
    """
    const: dict[int, str] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        else:
            continue
        if not targets:
            continue
        for child in ast.walk(node):
            # Only string constants, which is all `_raw_sql_sites` ever looks
            # up. Recording every node would put the `ast.Load`/`ast.Store`
            # CONTEXT SINGLETONS in here — CPython reuses one instance of each
            # across the whole tree — so this map would appear to own nodes
            # inside functions and any reasoning about its domain would be
            # wrong. They are never looked up, but a map that lies about what
            # it covers is a trap for the next reader.
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                const.setdefault(id(child), targets[0].id)
    return const


def _named_mapping_value(name: str, tree: ast.AST, fn: str,
                         owner: dict[int, str]) -> tuple[ast.AST | None, bool]:
    """(value expression for COLUMN, readable) for a `.values(**<local>)`.

    Reads both a plain and an ANNOTATED assignment (`_update_vals: dict = {...}`),
    because `espn_helpers` uses the annotated form and refusing to read it would
    make a live writer permanently invisible. A name that cannot be resolved is
    reported UNREADABLE rather than "writes no column" — the latter is the
    silent zero.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if owner.get(id(node)) != fn:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            return None, False
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value == COLUMN:
                return value, True
        # The dict resolves and simply does not name this column.
        return None, True
    return None, False


def _values_write(call: ast.Call, tree: ast.AST, fn: str,
                  owner: dict[int, str]) -> tuple[bool, ast.AST | None, bool]:
    """(writes COLUMN, value expression, readable) for one `.values(...)` call."""
    for kw in call.keywords:
        if kw.arg == COLUMN:
            return True, kw.value, True
    for kw in call.keywords:
        if kw.arg is not None:
            continue
        if isinstance(kw.value, ast.Name):
            value, ok = _named_mapping_value(kw.value.id, tree, fn, owner)
            if not ok:
                return True, None, False
            if value is not None:
                return True, value, True
        else:
            # A splat of anything other than a local name — a call, a
            # comprehension — is not resolved. Unreadable, not absent.
            return True, None, False
    return False, None, True


def _derivation(value: ast.AST | None, tree: ast.AST, fn: str,
                owner: dict[int, str], stamp_aliases: set[str],
                prune_aliases: set[str], depth: int = 0) -> str:
    """Where the persisted value came from: 'stamp', 'prune' or 'other'.

    Follows one local name back to its assignment in the SAME function — the
    common shape is `_wps = stamp_source_reading(...)` a few lines above the
    update. Tuple unpacking is read because `prune_blend_source` returns
    `(new_wps, changed)`.
    """
    if value is None or depth > 2:
        return "other"
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None
        )
        if name in stamp_aliases:
            return "stamp"
        if name in prune_aliases:
            return "prune"
        return "other"
    if isinstance(value, ast.Name):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            if owner.get(id(node)) != fn:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            hit = False
            for target in targets:
                if isinstance(target, ast.Name) and target.id == value.id:
                    hit = True
                elif isinstance(target, ast.Tuple):
                    if any(isinstance(e, ast.Name) and e.id == value.id
                           for e in target.elts):
                        hit = True
            if hit and node.value is not None:
                return _derivation(node.value, tree, fn, owner,
                                   stamp_aliases, prune_aliases, depth + 1)
    return "other"


def _module_constants(tree: ast.AST) -> dict[str, str]:
    """Module-level `NAME = "literal"` bindings, for source-key resolution."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _source_key(node: ast.AST, constants: dict[str, str]) -> str:
    """The source key a mint site writes, or `<dynamic>` when unresolvable."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    return "<dynamic>"


def _call_argument_strings(tree: ast.AST) -> set[int]:
    """Ids of string constants that are PASSED to a call.

    The discriminator between SQL and prose ABOUT SQL, and it has to be
    structural. The first draft of this file matched any string constant holding
    the column name beside `UPDATE`/`SET`, and six of its fourteen "write sites"
    were docstrings — including, exactly, the `FoldedBlendView` docstring whose
    sentence is *"ruling 048 ... does not permit ``UPDATE events SET
    win_probability_sources``"*. A guard that reads the comment explaining why a
    class must never write, and files it as a writer, is not a guard.

    A real statement is an ARGUMENT (`text("UPDATE ...")`, `execute("UPDATE ...")`);
    a docstring is a bare expression statement. Nothing in `app/` builds one of
    these by concatenation, and if something ever does, it reads as prose and is
    caught by the population floor rather than being silently classified.
    """
    used: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                used.add(id(arg))
    return used


def _raw_sql_sites(rel: str, tree: ast.AST, owner: dict[int, str],
                   const: dict[int, str] | None = None):
    """Write sites expressed as SQL text rather than as a builder.

    `source_intelligence.py` runs `UPDATE events SET win_probability_sources`
    through `text()`. No builder node exists, so every AST recogniser above is
    blind to it by construction — which is the entire argument for looking at
    string constants too.
    """
    passed = _call_argument_strings(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) not in passed:
            continue
        text_value = node.value
        if COLUMN not in text_value:
            continue
        upper = text_value.upper()
        if "UPDATE" in upper and "SET" in upper:
            where = owner.get(id(node)) or (const or {}).get(id(node), "<module>")
            yield (rel, where, "raw-sql", "other", None)


def _sites_in_tree(rel: str, tree: ast.AST):
    """Every WRITE site of the column in one module.

    Yields `(path, function, shape, derivation, value-node)`.
    """
    owner = _function_of(tree)
    model_aliases = _aliases(tree, {MODEL})
    upd = _aliases(tree, UPDATE_FUNCS)
    stamp_aliases = _aliases(tree, {STAMP})
    prune_aliases = _aliases(tree, {PRUNE})

    for node in ast.walk(tree):
        # Shape 1 + 2: a Core `update(Event)...values(...)` chain.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "values":
            root = _chain_root(node, upd)
            if not (isinstance(root, ast.Call) and _builder_call(root, upd)
                    and root.args and _is_model_ref(root.args[0], model_aliases)):
                continue
            fn = owner.get(id(node), "<module>")
            writes, value, readable = _values_write(node, tree, fn, owner)
            if not writes:
                continue
            if not readable:
                yield (rel, fn, "update.values", "UNRECOGNISED", None)
                continue
            derivation = _derivation(value, tree, fn, owner,
                                     stamp_aliases, prune_aliases)
            yield (rel, fn, "update.values", derivation, value)

        # Shape 3: ORM attribute assignment. `self.<column>` is not a site.
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Attribute) or target.attr != COLUMN:
                    continue
                if isinstance(target.value, ast.Name) and target.value.id == "self":
                    continue
                fn = owner.get(id(node), "<module>")
                derivation = _derivation(node.value, tree, fn, owner,
                                         stamp_aliases, prune_aliases)
                yield (rel, fn, "orm-assign", derivation, node.value)

    # Shape 4: raw SQL.
    yield from _raw_sql_sites(rel, tree, owner, _module_constant_of(tree))


def _mints_in_tree(rel: str, tree: ast.AST):
    """Every call to `stamp_source_reading` in one module.

    Yields `(path, function, source-key, has-record)`. This population is
    disjoint from the write sites on purpose: a mint whose result is returned
    rather than persisted is invisible to a write-site scan, and one of the two
    real gaps in the tree is exactly that shape.
    """
    owner = _function_of(tree)
    stamp_aliases = _aliases(tree, {STAMP})
    constants = _module_constants(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None
        )
        if name not in stamp_aliases:
            continue
        # `sources, source, value` — the key is the second positional, or the
        # `source=` keyword if a caller ever spells it out.
        key_node: ast.AST | None = None
        if len(node.args) >= 2:
            key_node = node.args[1]
        else:
            for kw in node.keywords:
                if kw.arg == "source":
                    key_node = kw.value
        key = _source_key(key_node, constants) if key_node is not None else "<dynamic>"
        has_record = any(
            kw.arg == "eligibility"
            and not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
            for kw in node.keywords
        )
        yield (rel, owner.get(id(node), "<module>"), key, has_record)


def _record_required(key: str) -> bool:
    """A record is required for a market-derived source, and when in doubt.

    The conservative direction is the point: three of the four live
    market-derived writers spell their source as a variable, so treating
    unresolved as exempt would exempt the population the record exists for.
    """
    return key == "<dynamic>" or key in MARKET_DERIVED_SOURCES


def _walk_app():
    for path in sorted(APP_ROOT.rglob("*.py")):
        text_value = path.read_text(encoding="utf-8")
        if COLUMN not in text_value and STAMP not in text_value:
            continue
        rel = str(path.relative_to(APP_ROOT.parent.parent))
        yield rel, ast.parse(text_value)


def _scan_writes():
    out = []
    for rel, tree in _walk_app():
        out.extend(_sites_in_tree(rel, tree))
    return out


def _scan_mints():
    out = []
    for rel, tree in _walk_app():
        out.extend(_mints_in_tree(rel, tree))
    return out


# ── the guards ────────────────────────────────────────────────────────────────


def test_the_scan_can_see_the_writers_it_is_scanning() -> None:
    """Anti-vacuity: a recogniser regression that zeroes a shape must fail LOUD.

    Every one of the four shapes is live in the tree today, so a floor of one
    each is a real floor. Without this, a change that broke `_chain_root` or the
    named-mapping resolver would empty the census and every assertion below
    would pass on nothing — the failure mode the sibling scan was written for.
    """
    sites = _scan_writes()
    shapes = {shape for _, _, shape, _, _ in sites}
    assert {"update.values", "orm-assign", "raw-sql"} <= shapes, shapes
    assert len(sites) >= 15, f"scan found only {len(sites)} write sites"

    mints = _scan_mints()
    assert len(mints) >= 14, f"scan found only {len(mints)} mint sites"
    # The named-mapping splat specifically: this file exists partly because a
    # kwarg-only recogniser scores it zero.
    assert any(
        path.endswith("espn_helpers.py") and derivation == "stamp"
        for path, _, _, derivation, _ in sites
    ), "the espn_helpers `.values(**_update_vals)` writer went unseen"


def test_every_write_shape_is_one_this_scan_can_read() -> None:
    """An unresolvable mapping is reported, never silently treated as clean."""
    unreadable = [s for s in _scan_writes() if s[3] == "UNRECOGNISED"]
    assert not unreadable, (
        "write sites whose value expression this scan cannot resolve — read them "
        "and either teach the scan the shape or ledger them:\n  "
        + "\n  ".join(f"{p}::{f} ({shape})" for p, f, shape, _, _ in unreadable)
    )


def test_no_new_writer_persists_a_reading_without_the_stamper() -> None:
    """Question 1, over the WRITE sites, pinned in both directions."""
    found = {
        (path, fn, shape): derivation
        for path, fn, shape, derivation, _ in _scan_writes()
        if derivation != "stamp"
    }
    unledgered = {k: v for k, v in found.items() if k not in KNOWN_NON_READING_WRITES}
    assert not unledgered, (
        "write sites that persist this column without going through "
        f"`{STAMP}`. A reading written here keeps full weight forever (#1829). "
        "If it is not a reading, add it to KNOWN_NON_READING_WRITES with its "
        f"class:\n  {unledgered}"
    )
    repaired = set(KNOWN_NON_READING_WRITES) - set(found)
    assert not repaired, (
        "KNOWN_NON_READING_WRITES names sites that no longer match — the ledger "
        f"is exact in both directions, so remove them:\n  {repaired}"
    )


def test_no_new_market_derived_reading_is_minted_without_a_record() -> None:
    """Question 2, over the MINT sites, pinned in both directions.

    This is the CU-4 assertion: a `kalshi` or `polymarket` reading with no
    eligibility record is indistinguishable from a gated one after the fact, so
    the census can never answer "zero ineligible inputs".
    """
    found = {
        (path, fn, key)
        for path, fn, key, has_record in _scan_mints()
        if _record_required(key) and not has_record
    }
    unledgered = found - set(KNOWN_UNRECORDED_MINTS)
    assert not unledgered, (
        "market-derived readings minted with no eligibility record. Pass "
        "`eligibility=` from the gate that admitted the speaker (see "
        "`live_blend.py`), or ledger it in KNOWN_UNRECORDED_MINTS with a "
        f"reason:\n  {unledgered}"
    )
    repaired = set(KNOWN_UNRECORDED_MINTS) - found
    assert not repaired, (
        "KNOWN_UNRECORDED_MINTS names mints that now carry a record (or moved) "
        f"— remove them:\n  {repaired}"
    )


def test_the_live_market_derived_writers_still_pass_a_record() -> None:
    """The three that DO comply, named, so a silent regression is not a shrink.

    Without this, deleting `eligibility=` from all three would move them into
    the "unrecorded" set and the ledger test would fail — but so would ADDING
    three ledger entries, which is a diff a hurried reader can wave through.
    Naming the compliant sites makes the regression need an explicit deletion
    here as well.
    """
    recorded = {
        (path, fn)
        for path, fn, key, has_record in _scan_mints()
        if has_record
    }
    expected = {
        ("backend/app/tasks/live_blend_refresh.py", "_refresh_batch"),
        ("backend/app/tasks/prediction_market_matching.py",
         "_phase2_persist_group_reading"),
        ("backend/app/tasks/prediction_market_matching.py",
         "_poll_live_prediction_market_prices"),
    }
    missing = {e for e in expected if e not in {(p, f) for p, f in recorded}}
    assert not missing, (
        f"a writer that used to pass an eligibility record stopped: {missing}"
    )


def test_every_ledgered_source_key_is_one_the_doctrine_recognises() -> None:
    """A ledger entry naming a source that is not market-derived is a mistake.

    `MARKET_DERIVED_SOURCES` is the reason these entries are findings at all. An
    entry for `betting` or `espn` would be noise under the module's own rule
    that their absence is expected — so it would mean the ledger, not the tree,
    is wrong.
    """
    for path, fn, key in KNOWN_UNRECORDED_MINTS:
        assert _record_required(key), (
            f"{path}::{fn} is ledgered for source {key!r}, which is not "
            "market-derived and needs no record"
        )


# ── red-checks: the recogniser is tested as a function, not assumed ───────────
#
# A scan that asserts its findings against the tree proves only that the tree
# looks the way the author thought today. Each shape below is fed to the
# recogniser directly, so a change that stops it SEEING a shape fails here even
# while the tree happens to contain no instance of it.


def _writes(source: str):
    return list(_sites_in_tree("t.py", ast.parse(source)))


def _mints(source: str):
    return list(_mints_in_tree("t.py", ast.parse(source)))


def test_a_core_values_kwarg_is_seen_and_its_stamper_followed() -> None:
    sites = _writes(
        "from app.utils.aggregation import stamp_source_reading\n"
        "async def f(s, e):\n"
        "    w = stamp_source_reading(e.win_probability_sources, 'espn', 0.5)\n"
        "    await s.execute(update(Event).where(Event.id == 1)"
        ".values(win_probability_sources=w))\n"
    )
    assert [(x[2], x[3]) for x in sites] == [("update.values", "stamp")]


def test_a_core_values_kwarg_with_an_unstamped_value_is_caught() -> None:
    sites = _writes(
        "async def f(s, e):\n"
        "    w = {'espn': 0.5}\n"
        "    await s.execute(update(Event).values(win_probability_sources=w))\n"
    )
    assert [(x[2], x[3]) for x in sites] == [("update.values", "other")]


def test_a_named_mapping_splat_is_resolved() -> None:
    """The shape a kwarg-only recogniser scores zero on."""
    sites = _writes(
        "from app.utils.aggregation import stamp_source_reading\n"
        "async def f(s, e):\n"
        "    w = stamp_source_reading(e.win_probability_sources, 'espn', 0.5)\n"
        "    vals: dict = {'win_probability_sources': w, 'espn_win_prob_home': 1}\n"
        "    await s.execute(update(Event).values(**vals))\n"
    )
    assert [(x[2], x[3]) for x in sites] == [("update.values", "stamp")]


def test_an_unresolvable_splat_is_UNRECOGNISED_not_clean() -> None:
    sites = _writes(
        "async def f(s, e):\n"
        "    await s.execute(update(Event).values(**build_it()))\n"
    )
    assert [(x[2], x[3]) for x in sites] == [("update.values", "UNRECOGNISED")]


def test_a_splat_of_a_mapping_without_the_column_is_not_a_site() -> None:
    sites = _writes(
        "async def f(s, e):\n"
        "    vals: dict = {'status': 'live'}\n"
        "    await s.execute(update(Event).values(**vals))\n"
    )
    assert sites == []


def test_an_orm_assignment_is_a_site_and_a_self_assignment_is_not() -> None:
    sites = _writes(
        "class V:\n"
        "    def __init__(self, e, s):\n"
        "        self.win_probability_sources = s\n"
        "def g(event, s):\n"
        "    event.win_probability_sources = s\n"
    )
    assert [(x[1], x[2]) for x in sites] == [("g", "orm-assign")]


def test_a_module_qualified_builder_resolves() -> None:
    """`sa.update(Event)` must not walk past the builder to the bare name."""
    sites = _writes(
        "async def f(s, w):\n"
        "    await s.execute(sa.update(models.Event)"
        ".values(win_probability_sources=w))\n"
    )
    assert [(x[2],) for x in sites] == [("update.values",)]


def test_a_write_to_another_model_is_not_a_site() -> None:
    sites = _writes(
        "async def f(s, w):\n"
        "    await s.execute(update(Team).values(win_probability_sources=w))\n"
    )
    assert sites == []


def test_raw_sql_is_a_site() -> None:
    sites = _writes(
        "async def f(db, wps, eid):\n"
        "    await db.execute(text('UPDATE events SET win_probability_sources"
        " = :wps WHERE id = :eid'), {'wps': wps, 'eid': eid})\n"
    )
    assert [(x[2], x[3]) for x in sites] == [("raw-sql", "other")]


def test_a_module_level_sql_constant_is_keyed_by_its_own_name() -> None:
    """A hoisted statement must not be ledgered as the whole file.

    `<module>` would let a SECOND module-level writer in the same file — one
    that did mint a reading — match an entry written for a prune and never be
    seen. The key is the constant, so the ledger stays exact in both directions.
    """
    sites = _writes(
        "_WITHDRAW_SQL = text('UPDATE events SET win_probability_sources"
        " = :wps WHERE id = :eid')\n"
    )
    assert [(x[1], x[2]) for x in sites] == [("_WITHDRAW_SQL", "raw-sql")]


def test_a_constant_inside_a_function_still_names_the_function() -> None:
    """The module-level attributor must not outrank `_function_of`."""
    sites = _writes(
        "async def f(db, wps, eid):\n"
        "    stmt = text('UPDATE events SET win_probability_sources = :wps')\n"
        "    await db.execute(stmt, {'wps': wps})\n"
    )
    assert [(x[1], x[2]) for x in sites] == [("f", "raw-sql")]


def test_a_select_of_the_column_is_not_a_raw_sql_site() -> None:
    sites = _writes(
        "async def f(db):\n"
        "    await db.execute(text('SELECT win_probability_sources FROM events'))\n"
    )
    assert sites == []


def test_a_prune_is_recognised_through_a_tuple_unpack() -> None:
    sites = _writes(
        "from app.utils.prediction_market_matching import prune_blend_source\n"
        "async def f(s, cur):\n"
        "    new_wps, changed = prune_blend_source(cur, 'kalshi', 0)\n"
        "    await s.execute(update(Event).values(win_probability_sources=new_wps))\n"
    )
    assert [(x[2], x[3]) for x in sites] == [("update.values", "prune")]


def test_an_aliased_stamper_import_is_followed() -> None:
    sites = _writes(
        "from app.utils.aggregation import stamp_source_reading as _stamp\n"
        "async def f(s, e):\n"
        "    w = _stamp(e.win_probability_sources, 'stat_model', 0.4)\n"
        "    await s.execute(update(Event).values(win_probability_sources=w))\n"
    )
    assert [(x[3],) for x in sites] == [("stamp",)]


def test_a_stamp_in_a_DIFFERENT_function_does_not_count() -> None:
    """Provenance is per-function; a stamper elsewhere must not launder a write."""
    sites = _writes(
        "from app.utils.aggregation import stamp_source_reading\n"
        "def other(e):\n"
        "    w = stamp_source_reading(e.win_probability_sources, 'espn', 0.5)\n"
        "async def f(s, w):\n"
        "    await s.execute(update(Event).values(win_probability_sources=w))\n"
    )
    assert [(x[3],) for x in sites] == [("other",)]


def test_a_mint_with_a_literal_market_derived_source_needs_a_record() -> None:
    mints = _mints(
        "from app.utils.aggregation import stamp_source_reading\n"
        "def f(w):\n"
        "    return stamp_source_reading(w, 'kalshi', 0.6)\n"
    )
    assert mints == [("t.py", "f", "kalshi", False)]
    assert _record_required("kalshi")


def test_a_mint_with_a_record_is_compliant() -> None:
    mints = _mints(
        "from app.utils.aggregation import stamp_source_reading\n"
        "def f(w, r):\n"
        "    return stamp_source_reading(w, 'kalshi', 0.6, eligibility=r.eligibility)\n"
    )
    assert mints == [("t.py", "f", "kalshi", True)]


def test_an_explicit_None_record_is_not_a_record() -> None:
    """`eligibility=None` is the shape a half-done rollout leaves behind."""
    mints = _mints(
        "from app.utils.aggregation import stamp_source_reading\n"
        "def f(w):\n"
        "    return stamp_source_reading(w, 'polymarket', 0.6, eligibility=None)\n"
    )
    assert mints == [("t.py", "f", "polymarket", False)]


def test_a_non_market_derived_literal_needs_no_record() -> None:
    mints = _mints(
        "from app.utils.aggregation import stamp_source_reading\n"
        "def f(w):\n"
        "    return stamp_source_reading(w, 'betting', 0.6)\n"
    )
    assert mints == [("t.py", "f", "betting", False)]
    assert not _record_required("betting")


def test_a_module_constant_source_key_is_resolved() -> None:
    """`mlb_sync` spells its key as `WIN_PROB_SOURCE_KEY`; unresolved would
    make a compliant writer look like a finding."""
    mints = _mints(
        "from app.utils.aggregation import stamp_source_reading\n"
        "KEY = 'mlb'\n"
        "def f(w):\n"
        "    return stamp_source_reading(w, KEY, 0.6)\n"
    )
    assert mints == [("t.py", "f", "mlb", False)]
    assert not _record_required("mlb")


def test_an_unresolvable_source_key_requires_a_record() -> None:
    """The conservative direction, and the one that covers the live writers."""
    mints = _mints(
        "from app.utils.aggregation import stamp_source_reading\n"
        "def f(w, anchor):\n"
        "    return stamp_source_reading(w, anchor.source, 0.6)\n"
    )
    assert mints == [("t.py", "f", "<dynamic>", False)]
    assert _record_required("<dynamic>")


def test_a_mint_that_is_never_persisted_here_is_still_a_mint() -> None:
    """The `espn_sync` shape: minted, returned, written by the caller.

    A write-site scan cannot see this function at all, which is the reason the
    two populations are scanned separately.
    """
    source = (
        "from app.utils.aggregation import stamp_source_reading\n"
        "def f(wps, resolved):\n"
        "    for k in ('kalshi', 'polymarket'):\n"
        "        wps = stamp_source_reading(wps, k, resolved)\n"
        "    return wps\n"
    )
    assert _writes(source) == []
    assert _mints(source) == [("t.py", "f", "<dynamic>", False)]
