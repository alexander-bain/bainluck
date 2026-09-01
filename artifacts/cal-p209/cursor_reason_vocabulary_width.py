#!/usr/bin/env python3
"""CAL-P209 / Q17 target C — how many DISTINCT ``cursor_reason`` tokens can the
deployed code emit, and how many did P208-1's own count name?

P208-1 asked Q17 of the PC-1 rubric and answered "the producer emits 15, the
rubric names 3". This harness asks Q17 of *that answer*: one of P208's fifteen
is a dynamic f-string, ``f"envelope_{read.status}"``, and a token template is
not a token. Counting it as one collapses a whole enum into a single name — the
same collapse P208-1 is a finding ABOUT.

POPULATION (stated in the noun the marker will use): **distinct string VALUES
that can reach ``record_stage(f"staged:cursor_reason:{reason}")`` on the
deployed sha.** Not sites, not constants — values, because a value is what an
operator reads off the ledger and looks up.

Everything is read from ``git show <SHA>:<path>`` — the DEPLOYED source, never
the worktree (which is on ``calibration-190`` and does not contain CERT-697).

CONTROL ARMS (the six-clause discipline):
  1. KNOWN HIT reproduced — the static table must contain
     ``legacy_fingerprint_accepted``, which P208 observed LIVE on production at
     22:36:02Z. If the extractor cannot recover a token that was demonstrably
     emitted, the extractor is broken and every count it produces is void.
  2. SHAPE of the hit stated — a dynamic f-string reason whose interpolated
     value is an enum owned by a DIFFERENT module.
  3. COVERAGE fraction reported — what share of the reason-emitting return
     sites this harness could classify. An unclassified site makes the total a
     floor, not a total.
  4. POPULATION named in the marker's noun — see above.
  5. FAILS WHEN THE STATUS QUO WOULD HAVE BEEN RIGHT — if the interpolated
     enum has <= 1 reachable member on this path, the collapse was harmless,
     expansion is 0, and the finding VOIDS itself (``verdict: VOID``).
  6. SHAPE GUARD — every AST fact this depends on is asserted. If the source
     shape moves, exit non-zero and void rather than silently reporting a
     number computed from a structure that no longer exists.

Exit codes: 0 = ran and reported. 2 = shape guard tripped, finding void.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys

SHA = "c139713996b7e957ac4eb239c82faf3b3f84ce10"  # Heroku v3981

STAGED = "backend/app/utils/calibration_staged_futures.py"
MAIN_BUILD = "backend/app/tasks/calibration_main_build.py"
PRECOMPUTE = "backend/app/tasks/precompute_calibration.py"
DURABLE_STATE = "backend/app/utils/durable_state.py"
DURABLE_SNAP = "backend/app/services/durable_snapshots.py"

#: ARM 1. Observed LIVE in the production ledger at 22:36:02Z on 2026-09-01
#: (CAL-P208 arm 1). Any extractor that misses it is broken.
KNOWN_HIT = "legacy_fingerprint_accepted"

#: The reader side. The three tokens the CAL-P208 conveyor rubric (directive
#: 978/979, ITEM 3 step 1 + the PC-1 arms) names by string.
RUBRIC_TOKENS = {"legacy_fingerprint_accepted", "resumable", "input_fingerprint_changed"}

failures: list[str] = []


def guard(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def src(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{SHA}:{path}"], capture_output=True, text=True, check=True
    ).stdout


def tree(path: str) -> ast.Module:
    return ast.parse(src(path))


def module_str_constants(mod: ast.Module, prefix: str) -> dict[str, str]:
    """Module-level ``PREFIX_X = "literal"`` assignments."""
    out: dict[str, str] = {}
    for node in mod.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name) or not tgt.id.startswith(prefix):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out[tgt.id] = node.value.value
    return out


def func(mod: ast.Module, name: str) -> ast.AST | None:
    for node in ast.walk(mod):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
# STEP 1 — the static reason table
# ---------------------------------------------------------------------------
staged_mod = tree(STAGED)
reason_consts = module_str_constants(staged_mod, "REASON_")
static_values = set(reason_consts.values())

guard(bool(reason_consts), "no REASON_* constants found in calibration_staged_futures.py")
# ARM 1 — the known hit.
arm1_reproduced = KNOWN_HIT in static_values
guard(arm1_reproduced, f"ARM 1 FAILED: known live token {KNOWN_HIT!r} not recovered")
guard(
    len(static_values) == len(reason_consts),
    "two REASON_ constants share a string value — the value population is smaller than the names",
)


# ---------------------------------------------------------------------------
# STEP 2 — every site that produces a reason, and how it produces it
# ---------------------------------------------------------------------------
def reason_sites(path: str, fn_names: list[str]) -> list[dict]:
    """Third element of every 3-tuple ``return`` inside the named functions.

    The classifier contract is ``(cursor, action, reason)``; anything returning
    a 3-tuple from these functions is emitting a reason.
    """
    mod = tree(path)
    sites: list[dict] = []
    for fname in fn_names:
        fn = func(mod, fname)
        guard(fn is not None, f"SHAPE: {fname} not found in {path}")
        if fn is None:
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Tuple):
                continue
            if len(node.value.elts) != 3:
                continue
            sites.append(
                {"file": path, "fn": fname, "line": node.lineno, "node": node.value.elts[2]}
            )
    return sites


sites = reason_sites(
    STAGED, ["decode_staged_cursor_detailed"]
) + reason_sites(MAIN_BUILD, ["load_staged_cursor"])

guard(bool(sites), "SHAPE: no 3-tuple reason returns found at all")


def classify(node: ast.AST) -> tuple[str, object]:
    """(kind, payload). ``unclassified`` is the honest fallthrough."""
    if isinstance(node, ast.Name) and node.id in reason_consts:
        return "const", {reason_consts[node.id]}
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "literal", {node.value}
    if isinstance(node, ast.IfExp):
        kb, vb = classify(node.body)
        ko, vo = classify(node.orelse)
        if kb == "unclassified" or ko == "unclassified":
            return "unclassified", set()
        return "ternary", set(vb) | set(vo)  # type: ignore[arg-type]
    if isinstance(node, ast.JoinedStr):
        return "fstring", node
    return "unclassified", set()


static_emitted: set[str] = set()
fstrings: list[dict] = []
unclassified: list[dict] = []

for s in sites:
    kind, payload = classify(s["node"])
    s["kind"] = kind
    if kind == "fstring":
        fstrings.append(s)
    elif kind == "unclassified":
        unclassified.append(s)
    else:
        static_emitted |= payload  # type: ignore[operator]

# The lease branch returns a reason via a multi-line tuple too; make sure we did
# not silently drop a whole class of site.
guard(
    len(sites) >= len(reason_consts) - 3,
    f"SHAPE: only {len(sites)} reason sites for {len(reason_consts)} constants — extractor too narrow",
)


# ---------------------------------------------------------------------------
# STEP 3 — expand the f-string. What enum is being interpolated, and how wide?
# ---------------------------------------------------------------------------
def fstring_shape(node: ast.JoinedStr) -> tuple[str, str]:
    """('envelope_', 'read.status') for f"envelope_{read.status}"."""
    prefix = ""
    expr = ""
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            prefix += part.value
        elif isinstance(part, ast.FormattedValue):
            expr = ast.unparse(part.value)
    return prefix, expr


guard(len(fstrings) == 1, f"SHAPE: expected exactly 1 dynamic reason site, found {len(fstrings)}")
prefix, expr = ("", "")
if fstrings:
    prefix, expr = fstring_shape(fstrings[0]["node"])
    guard(expr == "read.status", f"SHAPE: interpolated expr is {expr!r}, expected 'read.status'")


def envelope_status_domain() -> tuple[set[str], list[str]]:
    """Every ``status=`` an EnvelopeRead can carry on the read_snapshot_standalone path.

    Walks the two modules that construct EnvelopeRead on this path and resolves
    each ``status=`` keyword against the module-level status constants.
    """
    ds = tree(DURABLE_STATE)
    consts = {}
    for node in ds.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if (
                isinstance(t, ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                consts[t.id] = node.value.value

    found: set[str] = set()
    prov: list[str] = []
    # decode_envelope + failed_read live in durable_state; read_snapshot in
    # durable_snapshots. Only these three are on the standalone read path.
    for path, fns in ((DURABLE_STATE, ["decode_envelope", "failed_read"]),
                      (DURABLE_SNAP, ["read_snapshot", "read_snapshot_standalone"])):
        mod = tree(path)
        for fname in fns:
            fn = func(mod, fname)
            guard(fn is not None, f"SHAPE: {fname} missing from {path}")
            if fn is None:
                continue
            # Names bound as PARAMETERS of this function are not literals; their
            # domain is the signature default plus every call-site override, both
            # of which are resolved separately below. Recording them here would
            # double-count; failing on them (the scan-must-RAISE default) would
            # be a false alarm. So they are named and excused, explicitly.
            params = {
                a.arg
                for a in list(getattr(fn.args, "args", []))
                + list(getattr(fn.args, "kwonlyargs", []))
            }
            for node in ast.walk(fn):
                # EnvelopeRead(status=...) constructions
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
                        node.func.id == "EnvelopeRead":
                    for kw in node.keywords:
                        if kw.arg != "status":
                            continue
                        if isinstance(kw.value, ast.Constant):
                            found.add(kw.value.value)
                            prov.append(f"{path}:{node.lineno} literal {kw.value.value!r}")
                        elif isinstance(kw.value, ast.Name) and kw.value.id in consts:
                            found.add(consts[kw.value.id])
                            prov.append(f"{path}:{node.lineno} {kw.value.id}={consts[kw.value.id]!r}")
                        elif isinstance(kw.value, ast.Name) and kw.value.id in params:
                            prov.append(
                                f"{path}:{node.lineno} status=<param {kw.value.id}> "
                                f"— domain from signature default + call-site overrides"
                            )
                        else:
                            guard(False, f"SHAPE: unresolvable status= at {path}:{node.lineno}")
                # failed_read(...) calls: default status=UNAVAILABLE unless overridden
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
                        node.func.id == "failed_read":
                    override = next((k for k in node.keywords if k.arg == "status"), None)
                    if override is None:
                        found.add(consts["UNAVAILABLE"])
                        prov.append(f"{path}:{node.lineno} failed_read default=UNAVAILABLE")
    # failed_read's own signature default
    dsf = func(ds, "failed_read")
    if isinstance(dsf, ast.FunctionDef):
        for kw, default in zip(dsf.args.kwonlyargs, dsf.args.kw_defaults):
            if kw.arg == "status" and isinstance(default, ast.Name):
                found.add(consts[default.id])
                prov.append(f"{DURABLE_STATE} failed_read signature default={consts[default.id]!r}")
    return found, prov


status_domain, status_prov = envelope_status_domain()

# The two statuses load_staged_cursor handles BEFORE reaching the f-string.
HANDLED_BEFORE_FSTRING = {"ok", "missing"}
reaching = sorted(status_domain - HANDLED_BEFORE_FSTRING)
expanded = {f"{prefix}{s}" for s in reaching}

# ---------------------------------------------------------------------------
# ARM 5 — the counterfactual. If the collapse was harmless, say so and void.
# ---------------------------------------------------------------------------
expansion = len(expanded) - 1  # P208 counted the template as ONE token
collapse_harmful = expansion > 0

# ---------------------------------------------------------------------------
# The wipe classification (P208-1's axis), recomputed on the widened vocabulary
# ---------------------------------------------------------------------------
KEEPS_BANK = {"legacy_fingerprint_accepted", "resumable", "nothing_banked"}
NOTHING_TO_KEEP = {"absent"}
STANDS_DOWN = {"lease_held_by_other"}
static_wipes = static_emitted - KEEPS_BANK - NOTHING_TO_KEEP - STANDS_DOWN
all_wipes = static_wipes | expanded          # every envelope_* returns INVALIDATE

total_vocab = static_emitted | expanded

#: Honest reachability, per expanded token. All five are STRUCTURALLY reachable
#: — that is what makes them tokens an operator can meet. They are not equally
#: LIKELY, and a finding that implied they were would be overclaiming.
REACHABILITY = {
    "envelope_unavailable": "LIVE — any DB error or session failure on the cursor read",
    "envelope_malformed": "LIVE — checksum/shape failure on a torn or truncated write",
    "envelope_wrong_type": "LIVE — payload not a dict",
    "envelope_wrong_version": "ON A SCHEMA BUMP — and it SHADOWS the static "
                              "'schema_mismatch' token, which can only fire when the "
                              "envelope version is RIGHT and the inner payload field is wrong",
    "envelope_stale": "ONLY AFTER A 14-DAY GAP — STATE_MAX_AGE_S = 14*86400 and the "
                      "cursor is rewritten per banked unit",
}

report = {
    "sha": SHA,
    "reachability": REACHABILITY,
    "population": "distinct cursor_reason string VALUES emittable on the deployed sha",
    "arms": {
        "arm1_known_hit_reproduced": arm1_reproduced,
        "arm1_known_hit": KNOWN_HIT,
        "arm2_hit_shape": f'dynamic f-string reason f"{prefix}{{{expr}}}" over an enum owned by durable_state.py',
        "arm3_coverage": {
            "reason_return_sites": len(sites),
            "classified": len(sites) - len(unclassified),
            "unclassified": [f'{u["file"]}:{u["line"]}' for u in unclassified],
            "fraction": round((len(sites) - len(unclassified)) / len(sites), 4) if sites else None,
        },
        "arm5_counterfactual": {
            "reachable_statuses_at_fstring": reaching,
            "expansion_beyond_one_token": expansion,
            "collapse_harmful": collapse_harmful,
            "note": "expansion == 0 would mean P208's single token was correct and this finding voids",
        },
    },
    "producer": {
        "static_constants_defined": len(reason_consts),
        "static_values_emitted": sorted(static_emitted),
        "static_emitted_count": len(static_emitted),
        "dynamic_template": f"{prefix}{{{expr}}}",
        "dynamic_expansion": sorted(expanded),
        "status_domain_provenance": status_prov,
        "TOTAL_DISTINCT_VALUES": len(total_vocab),
    },
    "p208_comparison": {
        "p208_claimed_total": 15,
        "p208_claimed_wipes": 11,
        "measured_total": len(total_vocab),
        "measured_wipes": len(all_wipes),
    },
    "reader": {
        "rubric_tokens_named": sorted(RUBRIC_TOKENS),
        "rubric_names_of_wipes": sorted(RUBRIC_TOKENS & all_wipes),
        "wipe_coverage_p208": "1/11 = 9.1%",
        "wipe_coverage_measured": f"{len(RUBRIC_TOKENS & all_wipes)}/{len(all_wipes)} = "
                                  f"{100 * len(RUBRIC_TOKENS & all_wipes) / len(all_wipes):.1f}%",
    },
    "wipe_tokens": sorted(all_wipes),
    "verdict": (
        "VOID (shape guard tripped)" if failures
        else ("CONFIRMED" if collapse_harmful else "VOID (collapse was harmless)")
    ),
    "shape_guard_failures": failures,
}

print(json.dumps(report, indent=2))
if failures:
    print("\nSHAPE GUARD TRIPPED — finding is void.", file=sys.stderr)
    sys.exit(2)
