"""Resolve the X-Feed-Cache value domain from `routes/feed.py` BY AST.

#2143, second pass. Two guards — `test_cache_status_domain_matches_its_producer`
(`test_client_timing_contract.py`) and
`test_bucket_allowlist_covers_everything_its_writer_emits`
(`test_latency_stats.py`) — derived the producer's domain with a regex that
matched STRING LITERALS only::

    produced = set(re.findall(r'cache_status\\s*=\\s*"([a-z_]+)"', text))

`feed.py` also writes four values through a variable, so the regex never saw
them, the allowlists were built from the regex, and `produced - allowlist` was
empty BY CONSTRUCTION. Both guards compared a set against itself and passed
while 43.2% of bucketed `/api/feed` samples sat in `other` (measured on a
release-pure window 2026-09-22 00:12Z).

THE FIX IS NOT A BIGGER REGEX, IT IS REFUSING TO GUESS. This resolver returns
what it could resolve AND what it could not, and the callers fail on a
non-empty `unresolved`. A derivation that cannot go quietly incomplete cannot
go quietly vacuous — which is the property the literal parse never had, and the
reason its `assert produced` floor pin did not rescue it: a floor detects values
DISAPPEARING from a parse, never values the parse never reached.

Authority note: `X-Feed-Cache` has exactly one writer, `_set_feed_cache_status`,
called once — from `_finalize_feed_response`, the "single truthful finalizer for
EVERY successful /api/feed return path". So the domain is exactly the
`cache_status=` arguments at that finalizer's CALL SITES. The pass-through
inside the finalizer's own body is plumbing, not a value, and is excluded by
keying on the callee.
"""

from __future__ import annotations

import ast
import pathlib

#: `cache_status=None` is a documented non-write: "passing None leaves the
#: header exactly as the caller left it". It contributes no value to the domain
#: and is not an unresolved argument.
_NO_WRITE = object()

FINALIZER = "_finalize_feed_response"
HEADER_SETTER = "_set_feed_cache_status"


def feed_source_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"


def _callee_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _returns_of(func: ast.AST, index: int | None) -> tuple[set[str], list[str]]:
    """String constants a function returns, optionally at a tuple position."""
    values: set[str] = set()
    unresolved: list[str] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        target = node.value
        if index is not None:
            if not isinstance(target, ast.Tuple) or index >= len(target.elts):
                unresolved.append(
                    f"return at line {node.lineno} is not a {index + 1}-tuple"
                )
                continue
            target = target.elts[index]
        if isinstance(target, ast.Constant):
            if isinstance(target.value, str):
                values.add(target.value)
            elif target.value is None:
                continue  # `(None, None)` — the not-found arm, writes nothing
            else:
                unresolved.append(f"non-str return constant at line {node.lineno}")
        else:
            unresolved.append(f"unresolvable return at line {node.lineno}")
    return values, unresolved


class _Resolver:
    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.functions: dict[str, ast.AST] = {
            n.name: n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        # Every assignment to a bare Name, and every tuple-unpack position.
        self.assigns: dict[str, list[tuple[ast.AST, int | None]]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.assigns.setdefault(target.id, []).append((node.value, None))
                elif isinstance(target, ast.Tuple):
                    for i, elt in enumerate(target.elts):
                        if isinstance(elt, ast.Name):
                            self.assigns.setdefault(elt.id, []).append((node.value, i))

    def resolve(
        self,
        node: ast.AST,
        *,
        index: int | None = None,
        seen: frozenset[str] = frozenset(),
    ) -> tuple[set[str], list[str]]:
        # `await f(...)` is transparent for our purposes.
        if isinstance(node, ast.Await):
            return self.resolve(node.value, index=index, seen=seen)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return {node.value}, []
            if node.value is None:
                return set(), []
            return set(), [f"non-str constant at line {node.lineno}"]

        if isinstance(node, ast.IfExp):
            a, ua = self.resolve(node.body, index=index, seen=seen)
            b, ub = self.resolve(node.orelse, index=index, seen=seen)
            return a | b, ua + ub

        if isinstance(node, ast.BoolOp):
            values: set[str] = set()
            unresolved: list[str] = []
            for value in node.values:
                v, u = self.resolve(value, index=index, seen=seen)
                values |= v
                unresolved += u
            return values, unresolved

        if isinstance(node, ast.Tuple) and index is not None:
            if index < len(node.elts):
                return self.resolve(node.elts[index], seen=seen)
            return set(), [f"tuple too short at line {node.lineno}"]

        if isinstance(node, ast.Name):
            if node.id in seen:  # cycle guard
                return set(), []
            sources = self.assigns.get(node.id)
            if not sources:
                return set(), [f"`{node.id}` has no resolvable assignment"]
            values, unresolved = set(), []
            for src, src_index in sources:
                v, u = self.resolve(
                    src,
                    index=src_index if index is None else index,
                    seen=seen | {node.id},
                )
                values |= v
                unresolved += [f"via `{node.id}`: {m}" for m in u]
            return values, unresolved

        if isinstance(node, ast.Call):
            name = _callee_name(node)
            func = self.functions.get(name) if name else None
            if func is not None:
                return _returns_of(func, index)
            return set(), [f"call to `{name}` at line {node.lineno} is not local"]

        return set(), [f"{type(node).__name__} at line {getattr(node, 'lineno', '?')}"]


def resolve_cache_status_domain() -> tuple[set[str], list[str], int]:
    """(values, unresolved, call_site_count) written to X-Feed-Cache.

    `unresolved` non-empty means the derivation could not see everything the
    producer writes — the caller MUST fail rather than compare what it managed
    to parse, which is the #2143 defect.
    """
    tree = ast.parse(feed_source_path().read_text())
    resolver = _Resolver(tree)

    values: set[str] = set()
    unresolved: list[str] = []
    sites = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node)

        if name == FINALIZER:
            for kw in node.keywords:
                if kw.arg != "cache_status":
                    continue
                sites += 1
                v, u = resolver.resolve(kw.value)
                values |= v
                unresolved += [f"line {node.lineno}: {m}" for m in u]

        elif name == HEADER_SETTER and len(node.args) >= 2:
            # Direct writes. The one inside the finalizer passes the finalizer's
            # own parameter through, which is plumbing rather than a value — a
            # bare parameter Name resolves to nothing and is skipped here, but
            # any direct write of a real value is counted.
            arg = node.args[1]
            if isinstance(arg, ast.Name) and arg.id not in resolver.assigns:
                continue
            sites += 1
            v, u = resolver.resolve(arg)
            values |= v
            unresolved += [f"line {node.lineno}: {m}" for m in u]

    return values, unresolved, sites
