"""CAL-P092 — the publisher→after-read rule, as an AST/callgraph analyser.

Why this module exists
----------------------
``C-APPLY-PRE-1912-R3-R3`` [P1] blocked on the guard that was supposed to close
this family for good:

    ``source = inspect.getsource(rail); publishes = source.count(...); proved =
    source.count("after-read proved"); assert proved == publishes``

    "Executing the real test against a scratch source string with a fifth
    ``publish_snapshot_standalone`` call and no read made it fail ``5 != 4``;
    adding only ``# after-read proved`` made the same test **PASS 5 == 5**. No
    control flow or read was added." … "the guard counts prose, not a
    publisher-to-reader relationship, so its claimed structural closure is
    false."

That is the self-oracle family this rail keeps producing: five acknowledgement-only
publishers arrived one at a time, each guarded after it was caught. A guard that a
COMMENT can satisfy does not fail on the sixth — it blesses it.

The rule, stated
----------------
**Every publisher call's enclosing function must show a consumer-facing read on
every successful return path.**

Unpacked into things an AST can decide:

1. *Publisher call* — a call whose callee name is in :data:`PUBLISHER_NAMES`,
   found anywhere in the module, however it was imported (the rail imports
   function-locally, so a module-level import census would see nothing).
2. *Enclosing function* — the INNERMOST ``def``/``async def``. Nested helpers get
   their own scope; ``_save_progress``' inner ``return int(v)`` is not one of
   ``_save_progress``' return paths and must not be read as one.
3. *Consumer-facing read* — a call to :data:`READER_NAMES`, or to a function
   defined in the same module that transitively reaches one. The transitive
   closure is what lets the rail keep its real shape: ``_save_plan`` does not
   call ``read_snapshot_standalone``, it calls ``_load_plan``, which does. A rule
   that demanded the literal reader would push the rail toward duplicating its
   reader inline, which is worse code and a weaker proof.
4. *Successful return path* — a ``return`` of ``True`` or of a tuple whose first
   element is the constant ``True``. That is this family's convention
   (``(ok, note)``).
5. *…on every path* — the read must DOMINATE the return: it must sit in a
   statement that unconditionally executes before it. See :func:`_dominates`.
   "Somewhere in the function" is not the rule, because a read inside the
   ``if`` the success path skips proves nothing.

A return whose shape cannot be classified is reported as ``UNKNOWN`` and treated
as a violation, not waved through. A guard that exempts what it cannot read is
defeated by ``return _ok()`` — and the whole point of this module is that the
guard must fail on the shape it has never seen.

Comments are not in the AST. That is not a nice property of the implementation,
it is the requirement: ``test_a_comment_can_never_satisfy_the_guard`` in
``test_repair_pm_never_graded_durability_p092.py`` re-runs the cert's exact
mutation and asserts this analyser still reports the fifth site.

Limits, stated rather than implied
----------------------------------
* It reads ONE module's source. A publisher reached through a helper in another
  module is out of scope; :data:`PUBLISHER_NAMES` is the seam.
* Dominance is computed over ``If``/``Try``/``With`` nesting. Loops never
  dominate (they may run zero times) and ``match`` is not modelled — both fail
  CLOSED, i.e. they report a violation rather than assuming a read happened.
* It proves the read is CALLED, not that its result is checked. The four
  shipping sites do check it; a site that reads and ignores would pass here and
  is the next attack, not this one.
"""

from __future__ import annotations

import ast
from typing import Iterable, NamedTuple

#: The durable-store write seam.
PUBLISHER_NAMES: frozenset[str] = frozenset(
    {"publish_snapshot_standalone", "publish_snapshot"}
)

#: The durable-store read seam — what "consumer-facing" means concretely: the
#: reader a later consumer (the apply, a retry, the halt check) would itself use.
READER_NAMES: frozenset[str] = frozenset(
    {"read_snapshot_standalone", "read_snapshot"}
)

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class Violation(NamedTuple):
    function: str
    publisher_line: int
    return_line: int
    kind: str  # "no_dominating_read" | "unclassifiable_return"
    detail: str


class Site(NamedTuple):
    function: str
    line: int


def _callee_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _calls_in(node: ast.AST, *, descend_into_functions: bool = False) -> list[ast.Call]:
    """Every ``Call`` under ``node``, stopping at nested function boundaries.

    Not descending is the point: a nested ``def`` that calls the reader has not
    read anything until somebody calls IT.
    """
    out: list[ast.Call] = []
    for child in ast.iter_child_nodes(node):
        if not descend_into_functions and isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            continue
        if isinstance(child, ast.Call):
            out.append(child)
        out.extend(_calls_in(child, descend_into_functions=descend_into_functions))
    return out


def _module_functions(tree: ast.Module) -> dict[str, FunctionNode]:
    """Every function defined anywhere in the module, by name.

    Nested helpers are included so the callgraph can follow a call into one; a
    duplicate name is kept as the first definition, which is the conservative
    read (a redefinition that ADDS a read must not retroactively bless callers of
    the earlier one).
    """
    out: dict[str, FunctionNode] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, node)
    return out


def reader_reaching_functions(tree: ast.Module) -> frozenset[str]:
    """Module functions that reach a :data:`READER_NAMES` call, transitively.

    Fixed-point over the callgraph rather than one hop, because the rail's real
    shape is ``_save_plan -> _load_plan -> read_snapshot_standalone`` and a
    one-hop rule would either miss it or force the reader inline.
    """
    functions = _module_functions(tree)
    direct = {
        name
        for name, fn in functions.items()
        if any(_callee_name(c) in READER_NAMES for c in _calls_in(fn))
    }
    reaching = set(direct)
    changed = True
    while changed:
        changed = False
        for name, fn in functions.items():
            if name in reaching:
                continue
            if any(_callee_name(c) in reaching for c in _calls_in(fn)):
                reaching.add(name)
                changed = True
    return frozenset(reaching)


def _is_read(node: ast.AST, reaching: Iterable[str]) -> bool:
    reaching = set(reaching)
    return any(
        (_callee_name(c) in READER_NAMES) or (_callee_name(c) in reaching)
        for c in _calls_in(node)
    )


def _exits(stmt: ast.stmt) -> bool:
    """Does this statement definitely leave the function (return/raise)?

    Used to decide whether an exception handler can fall THROUGH to the code
    after a ``try``. A handler that returns or raises cannot, so a read in the
    ``try`` body still dominates what follows.
    """
    if isinstance(stmt, (ast.Return, ast.Raise)):
        return True
    if isinstance(stmt, ast.If):
        return bool(stmt.orelse) and _block_exits(stmt.body) and _block_exits(stmt.orelse)
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return _block_exits(stmt.body)
    if isinstance(stmt, ast.Try):
        return _block_exits(stmt.body + stmt.orelse) and all(
            _block_exits(h.body) for h in stmt.handlers
        )
    return False


def _block_exits(body: list[ast.stmt]) -> bool:
    return any(_exits(s) for s in body)


def _dominates(stmt: ast.stmt, reaching: Iterable[str]) -> bool:
    """Does executing ``stmt`` guarantee a consumer-facing read happened?

    Straight-line statements count if the read is in them. ``If`` counts only if
    BOTH arms read. ``Try`` counts if the body reads and no handler can fall
    through into the code after it (a handler that swallows leaves a path with no
    read, which is exactly the hole worth catching). Loops never count.
    """
    reaching = set(reaching)
    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
        return False
    if isinstance(stmt, ast.If):
        return bool(stmt.orelse) and (
            _block_dominates(stmt.body, reaching)
            and _block_dominates(stmt.orelse, reaching)
        )
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return _block_dominates(stmt.body, reaching)
    if isinstance(stmt, ast.Try):
        body_reads = _block_dominates(stmt.body, reaching) or _block_dominates(
            stmt.orelse, reaching
        )
        handlers_cannot_fall_through = all(_block_exits(h.body) for h in stmt.handlers)
        return body_reads and handlers_cannot_fall_through
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    return _is_read(stmt, reaching)


def _block_dominates(body: list[ast.stmt], reaching: Iterable[str]) -> bool:
    return any(_dominates(s, reaching) for s in body)


def _classify_return(node: ast.Return) -> str:
    """``"success"`` | ``"failure"`` | ``"unknown"`` for this family's ``(ok, note)``."""
    value = node.value
    if value is None:
        return "failure"
    if isinstance(value, ast.Constant) and isinstance(value.value, bool):
        return "success" if value.value else "failure"
    if isinstance(value, ast.Tuple) and value.elts:
        first = value.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, bool):
            return "success" if first.value else "failure"
    return "unknown"


def _innermost_enclosing(tree: ast.Module) -> dict[int, FunctionNode]:
    """Map ``id(node) -> innermost enclosing function`` for every node."""
    owner: dict[int, FunctionNode] = {}

    def walk(node: ast.AST, current: FunctionNode | None) -> None:
        for child in ast.iter_child_nodes(node):
            nxt = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else current
            if current is not None:
                owner[id(child)] = current
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner[id(child)] = current if current is not None else child
            walk(child, nxt)

    walk(tree, None)
    return owner


def _returns_of(fn: FunctionNode) -> list[ast.Return]:
    """This function's OWN returns — nested ``def``s are their own scope."""
    out: list[ast.Return] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Return):
                out.append(child)
            walk(child)

    walk(fn)
    return out


def _ancestor_chain(fn: FunctionNode, target: ast.stmt) -> list[list[ast.stmt]]:
    """Each enclosing statement LIST between ``fn``'s body and ``target``, outermost first."""
    chain: list[list[ast.stmt]] = []

    def search(body: list[ast.stmt], stack: list[list[ast.stmt]]) -> bool:
        for stmt in body:
            if stmt is target:
                chain.extend(stack + [body])
                return True
            for field in ("body", "orelse", "finalbody"):
                inner = getattr(stmt, field, None)
                if isinstance(inner, list) and search(inner, stack + [body]):
                    return True
            for handler in getattr(stmt, "handlers", []) or []:
                if search(handler.body, stack + [body]):
                    return True
        return False

    search(fn.body, [])
    return chain


def audit_module(source: str, *, filename: str = "<module>") -> dict[str, object]:
    """The whole rule, over one module's source. Pure: no imports, no execution.

    Returns ``sites`` (every publisher call and its enclosing function) and
    ``violations``. An empty ``violations`` with a non-empty ``sites`` is the
    only shape that means "this rail is proved".
    """
    tree = ast.parse(source, filename=filename)
    reaching = reader_reaching_functions(tree)
    owner = _innermost_enclosing(tree)

    sites: list[Site] = []
    publisher_functions: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee_name(node) in PUBLISHER_NAMES:
            fn = owner.get(id(node))
            name = fn.name if fn is not None else "<module>"
            sites.append(Site(name, node.lineno))
            publisher_functions.setdefault(name, []).append(node.lineno)

    functions = _module_functions(tree)
    violations: list[Violation] = []
    for name, lines in sorted(publisher_functions.items()):
        fn = functions.get(name)
        if fn is None:
            violations.append(
                Violation(name, lines[0], -1, "no_dominating_read",
                          "publisher call is not inside a function")
            )
            continue
        first_publish = min(lines)
        for ret in _returns_of(fn):
            kind = _classify_return(ret)
            if kind == "failure":
                continue
            if kind == "unknown":
                violations.append(
                    Violation(
                        name,
                        first_publish,
                        ret.lineno,
                        "unclassifiable_return",
                        "the guard cannot tell whether this return is a success "
                        "path; state it as `return True, ...` / `return False, ...` "
                        "rather than leaving the rule to guess",
                    )
                )
                continue
            proved = False
            for body in reversed(_ancestor_chain(fn, ret)):
                index = next(
                    (i for i, s in enumerate(body) if s is ret or _contains(s, ret)), None
                )
                if index is None:
                    continue
                before = [
                    s for s in body[:index] if getattr(s, "lineno", 0) > first_publish
                ]
                if _block_dominates(before, reaching):
                    proved = True
                    break
            if not proved:
                violations.append(
                    Violation(
                        name,
                        first_publish,
                        ret.lineno,
                        "no_dominating_read",
                        "this success path returns without a consumer-facing read "
                        "after the publisher call — an acknowledgement is not "
                        "durability (C-APPLY-PRE-1912-R3-R2/R3-R3)",
                    )
                )

    return {
        "sites": sites,
        "violations": violations,
        "reader_reaching_functions": sorted(reaching),
        "publisher_functions": {k: sorted(v) for k, v in publisher_functions.items()},
    }


def _contains(stmt: ast.stmt, target: ast.stmt) -> bool:
    return any(node is target for node in ast.walk(stmt))


def describe(violations: Iterable[Violation]) -> str:
    return "\n".join(
        f"  {v.function} (publisher line {v.publisher_line}) -> return line "
        f"{v.return_line} [{v.kind}]: {v.detail}"
        for v in violations
    )
