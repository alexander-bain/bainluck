"""Extends calibration_population_integrity: derive fingerprint coverage from code.

Unlike CAL-P031's hand-maintained map, both the source-hashed roots and explicit
by-value inputs are parsed from the real ``_main_input_fingerprint`` body.
"""
from __future__ import annotations
import ast, hashlib, json
from pathlib import Path
from typing import Any

BACKEND=Path(__file__).resolve().parents[2]
BUILD=BACKEND/"app/tasks/precompute_calibration.py"
DEFAULT_MAP=BACKEND/"tests/evals/fixtures/calibration_fingerprint_derived_map.json"

#: Carried forward from CAL-P031's hand map when the generated artifact replaced
#: it as sole authority. It is the one thing the artifact cannot express: WHEN
#: the fix may be applied. Ruling 024 answers it — the fix rides the single
#: combined invalidation window, not on its own.
FIX_SEQUENCING_NOTE = """\
Covering these means adding them to `_main_input_fingerprint`, in the idiom that
function already uses for `COVERAGE_CENSUS_ENABLED` — hashed by NAME and by
VALUE, so the input is greppable rather than an incidental substring.

TWO CONSTRAINTS, EACH INDEPENDENTLY SUFFICIENT TO BLOCK IT TODAY:

1. `precompute_calibration.py` is FROZEN (ruling 009), and ruling 024 places the
   fix inside the ONE combined invalidation window that opens at the first fresh
   publish — together with ruling 011's two-tier well-traded, the cricket and
   entertainment exclusions, and the population-version bump plus its published
   before/after census. Shipped separately, each invalidates the last and no
   before/after census means anything.

2. APPLYING THE FIX WIPES EVERY BANKED UNIT. Moving the digest is, by design, a
   wholesale cursor invalidation. Doing it mid-convergence destroys exactly the
   progress the fix exists to protect and restarts a multi-hour walk.

   => Apply IMMEDIATELY AFTER a successful publish, never during a convergence.

The instinct "we found a correctness bug, fix it now" is wrong here, and it is
wrong in a way that costs the SLO. That is why this note ships beside the census
instead of the patch.
"""

def _functions(tree): return {n.name:n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
def _fingerprint_node(tree): return _functions(tree)["_main_input_fingerprint"]
def derive_declared(source:str)->tuple[set[str],set[str]]:
 # CAL-P100: the coverable set is module-level defs AND imported names. It was
 # defs only, which made an IMPORTED constant permanently uncoverable: it could
 # be hashed by value in ``_main_input_fingerprint`` and still be reported as an
 # unguarded SQL-shaping hole, forever. That is a false positive in the one
 # number this file exists to make trustworthy, and the predictable response to
 # a tripwire that fires on correct code is to loosen the tripwire.
 # Found by ``PAIR_SUM_TOLERANCE``, imported from ``pair_opening_coherence`` so
 # the writer gate and the read-side gate cannot drift apart, hashed by value,
 # and counted as uncovered regardless. Widening this set REMOVES false
 # negatives in coverage; it cannot hide a real hole, because a name still has
 # to appear in the ``input_fingerprint(...)`` call to be counted covered.
 tree=ast.parse(source); node=_fingerprint_node(tree); roots=set(); values=set(); module_names=set(_module_defs(tree))|set(_imports(tree))
 for call in ast.walk(node):
  if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=="getsource" and call.args:
   if isinstance(call.args[0],ast.Name): roots.add(call.args[0].id)
  if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=="input_fingerprint":
   for arg in call.args:
    if isinstance(arg,ast.Name) and arg.id in module_names: values.add(arg.id)
    elif isinstance(arg,ast.JoinedStr):
     values.update(n.id for n in ast.walk(arg) if isinstance(n,ast.Name) and n.id in module_names)
 return roots,values
def _closure(tree,roots):
 funcs=_functions(tree); seen=set(); stack=list(roots)
 while stack:
  name=stack.pop()
  if name in seen: continue
  seen.add(name); node=funcs.get(name)
  if not node: continue
  for c in ast.walk(node):
   if isinstance(c,ast.Call):
    n=c.func.id if isinstance(c.func,ast.Name) else c.func.attr if isinstance(c.func,ast.Attribute) else None
    if n in funcs and n not in seen: stack.append(n)
 return seen
def _module_defs(tree):
 out={}
 for n in tree.body:
  if isinstance(n,(ast.Assign,ast.AnnAssign)):
   targets=n.targets if isinstance(n,ast.Assign) else [n.target]
   for t in targets:
    if isinstance(t,ast.Name) and t.id.upper()==t.id: out[t.id]=n
 return out
def _imports(tree):
 out={}
 for n in tree.body:
  if isinstance(n,ast.ImportFrom) and n.module and n.module.startswith("app."):
   for a in n.names: out[a.asname or a.name]=(n.module,a.name)
 return out
def _module_path(module): return BACKEND/Path(*module.split(".")).with_suffix(".py")
def _definition_closure_digest(text:str,origin:str)->str|None:
 tree=ast.parse(text); nodes={**_module_defs(tree),**_functions(tree)}
 if origin not in nodes: return None
 seen=set(); stack=[origin]; segments=[]
 while stack:
  name=stack.pop()
  if name in seen or name not in nodes: continue
  seen.add(name); node=nodes[name]; segments.append(f"{name}\n{ast.get_source_segment(text,node)}")
  for child in ast.walk(node):
   if isinstance(child,ast.Name) and isinstance(child.ctx,ast.Load) and child.id in nodes:
    stack.append(child.id)
 return hashlib.sha256("\n---\n".join(sorted(segments)).encode()).hexdigest()[:16]
def derive_map(source:str|None=None,module_sources:dict[str,str]|None=None)->dict[str,Any]:
 source=BUILD.read_text() if source is None else source; tree=ast.parse(source)
 roots,covered=derive_declared(source); closure=_closure(tree,roots); funcs=_functions(tree)
 defs=_module_defs(tree); imports=_imports(tree); used={}; interpolated=set()
 for fn in closure:
  node=funcs.get(fn)
  if not node: continue
  for f in (n for n in ast.walk(node) if isinstance(n,ast.FormattedValue)):
   interpolated.update(x.id for x in ast.walk(f.value) if isinstance(x,ast.Name))
  # CAL-P032: f-strings are not the only way a value reaches emitted SQL. This
  # module builds statements with ``+`` and ``%`` too, and an f-string-only
  # detector under-counts ``uncovered_sql_shaping`` — the one number that says
  # how many unguarded values shape the population predicate. Measured: it
  # missed VM_ROSTER_MARKET_INFO_EXTRA (20 -> 21).
  for b in (n for n in ast.walk(node) if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Mod))):
   sides=(b.left,b.right)
   if not any(isinstance(s,ast.Constant) and isinstance(s.value,str) for s in sides): continue
   for s in sides: interpolated.update(x.id for x in ast.walk(s) if isinstance(x,ast.Name))
  for n in ast.walk(node):
   if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and (n.id in defs or n.id in imports): used.setdefault(n.id,set()).add(fn)
 rows=[]
 for name in sorted(set(used)|covered):
  module="app.tasks.precompute_calibration"; origin=name; definition_sha=None
  if name in imports:
   module,origin=imports[name]; path=_module_path(module)
   text=(module_sources or {}).get(module,path.read_text() if path.exists() else "")
   if text: definition_sha=_definition_closure_digest(text,origin)
  rows.append({"name":name,"origin":f"{module}:{origin}","covered_by_value":name in covered,"used_in":sorted(used.get(name,[])),"sql_interpolated":name in interpolated,"impact":"sql_shaping" if name in interpolated else "behavior_or_evidence","definition_sha16":definition_sha})
 uncovered=[r for r in rows if not r["covered_by_value"]]
 return {"schema":"calibration-fingerprint-derived/v1","source":str(BUILD.relative_to(BACKEND.parent)),"source_sha256":hashlib.sha256(source.encode()).hexdigest(),"hashed_roots":sorted(roots),"covered_by_value":sorted(covered),"input_count":len(rows),"uncovered_count":len(uncovered),"uncovered_sql_shaping":sum(r["sql_interpolated"] for r in uncovered),"uncovered_behavior_or_evidence":sum(not r["sql_interpolated"] for r in uncovered),"inputs":rows}
def main():
 print(json.dumps(derive_map(),indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
