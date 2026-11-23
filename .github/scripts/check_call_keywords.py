"""Find calls passing a keyword or positional count the target function does not accept (#13281)."""

from __future__ import annotations

import ast
import collections
import os
import sys


def _extract_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[list[str], list[str], bool, bool, int, list[str], int]:
    a = node.args
    pos = [x.arg for x in a.posonlyargs + a.args]
    nreq = len(pos) - len(a.defaults)
    req_kw = [x.arg for x, dflt in zip(a.kwonlyargs, a.kw_defaults) if dflt is None]
    return (
        pos,
        [x.arg for x in a.kwonlyargs],
        a.vararg is not None,
        a.kwarg is not None,
        nreq,
        req_kw,
        len(a.posonlyargs),
    )


def scan_tree(root: str) -> tuple[int, int, list[tuple[str, int, str, str]]]:
    """Scan ``root`` (typically ``backend/app``) and return ``(files, indexed_fns, findings)``."""
    norm_root = os.path.normpath(root)
    parent = os.path.dirname(norm_root)

    def modname(path: str) -> str:
        rel = os.path.relpath(path, parent)
        return rel[:-3].replace(os.sep, ".").removesuffix(".__init__")

    defs: dict[str, dict[str, tuple[list[str], list[str], bool, bool, int, list[str], int]]] = {}
    trees: dict[str, ast.Module] = {}

    for dp, _dn, fn in os.walk(norm_root):
        for f in fn:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            with open(p, encoding="utf-8") as fh:
                t = ast.parse(fh.read(), filename=p)
            trees[p] = t
            d: dict[str, tuple[list[str], list[str], bool, bool, int, list[str], int]] = {}
            counts = collections.Counter(
                n.name for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            for n in t.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and counts[n.name] == 1:
                    d[n.name] = _extract_signature(n)
            defs[modname(p)] = d

    bad: list[tuple[str, int, str, str]] = []
    for p, t in trees.items():
        local = dict(defs[modname(p)])
        imported: dict[str, list[tuple[list[str], list[str], bool, bool, int, list[str], int]]] = {}
        rebound: set[str] = set()
        for n in ast.walk(t):
            if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                src = defs.get(n.module)
                for al in n.names:
                    nm = al.asname or al.name
                    if src and al.name in src:
                        imported.setdefault(nm, []).append(src[al.name])
                    elif nm in local:
                        rebound.add(nm)
            elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for tg in targets:
                    rebound.update(x.id for x in ast.walk(tg) if isinstance(x, ast.Name))
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                a = n.args
                args_list = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
                if a.vararg:
                    args_list.append(a.vararg)
                if a.kwarg:
                    args_list.append(a.kwarg)
                rebound.update(x.arg for x in args_list)
                if not isinstance(n, ast.Lambda) and n not in t.body:
                    rebound.add(n.name)
            elif isinstance(n, (ast.For, ast.comprehension)):
                rebound.update(x.id for x in ast.walk(n.target) if isinstance(x, ast.Name))
            elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                rebound.update(x.id for x in ast.walk(n.optional_vars) if isinstance(x, ast.Name))

        for n in ast.walk(t):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            nm = n.func.id
            if nm in rebound:
                continue
            sigs = [local[nm]] if nm in local else imported.get(nm, [])
            if len(sigs) != 1:
                continue
            pos, kwonly, vararg, kwarg, nreq, req_kw, npo = sigs[0]
            if any(isinstance(a, ast.Starred) for a in n.args) or any(
                k.arg is None for k in n.keywords
            ):
                continue
            probs = [
                f"unknown keyword '{k.arg}'"
                for k in n.keywords
                if k.arg not in pos[npo:] and k.arg not in kwonly and not kwarg
            ]
            if len(n.args) > len(pos) and not vararg:
                probs.append(f"{len(n.args)} positional, takes {len(pos)}")
            given = set(pos[: len(n.args)]) | {k.arg for k in n.keywords if k.arg is not None}
            miss = [x for x in pos[:nreq] if x not in given] + [
                x for x in req_kw if x not in given
            ]
            if miss:
                probs.append("missing " + ",".join(miss))
            if probs:
                bad.append((os.path.relpath(p, norm_root), n.lineno, nm, "; ".join(probs)))

    return len(trees), sum(len(d) for d in defs.values()), sorted(bad)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: check_call_keywords.py <backend/app>", file=sys.stderr)
        return 2
    n_files, n_fns, bad = scan_tree(args[0])
    print("files:", n_files, "| functions indexed:", n_fns, "| findings:", len(bad))
    for b in bad:
        print("  ", *b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
