#!/usr/bin/env python3
"""Scan a working tree for mutants an eval harness left behind.

`bcdcd95f` carried mutation **M3** of `typeahead_warmer_mutations.py` as an
edit nobody made: the harness died at exit 143 between writing the mutant and
restoring it. `_mutation_guard.py` is the prevention. This is the DETECTION,
and both are needed, because the guard cannot help against SIGKILL and cannot
retroactively clean a branch that already has residue on it.

The scan LAT-P081 ran to close that sweep was ad hoc — harvested by hand,
59 literals, 588 pairwise checks, reported in prose and then gone. A check
that exists only in a report cannot be re-run by the next window, so it gets
re-derived from scratch or, more likely, not run at all. This is that scan,
committed.

WHAT IT CHECKS

Every mutation harness declares (needle -> replacement) pairs. A replacement
that appears in a changed file, where the corresponding needle does NOT, is a
candidate residue: the source looks like the mutant rather than the original.

WHAT IT REFUSES TO DO

**Skip a harness it does not understand.** Every `*_mutations.py` must be in
`SHAPES` or the scan exits non-zero and names the file. A scanner that
silently covers 7 of 9 harnesses reports the same clean line as one that
covers all 9, and the two are worth opposite amounts (gotcha #53's discipline:
never let a narrowed denominator print as a full one). The same reason
`--changed-only` prints the file count it actually examined.

USAGE

    python3 scripts/evals/scan_mutation_residue.py                # vs origin/master
    python3 scripts/evals/scan_mutation_residue.py --base HEAD~3
    python3 scripts/evals/scan_mutation_residue.py --all-tracked  # whole tree

Exit codes (gotcha #54): `0` clean, `1` residue found — a real result, `2` the
scan could not be performed (unknown harness shape, git unavailable).
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
BACKEND = EVALS.parents[1]
REPO = BACKEND.parent

# module stem -> list of (table attr, needle key, replacement key, target)
#
# `target` is where the needle is supposed to live: an int index into the
# entry when the table carries its own Path, otherwise the name of a
# module-level constant.
#
# Explicit rather than inferred. Harness tables are heterogeneous by design —
# each was written for its own defect — and guessing indices is how a scan
# starts reading a `why` string as a code fragment and reporting nothing.
SHAPES: dict[str, list[tuple[str, object, object, object]]] = {
    "admin_auth_gate_mutations": [("MUTANTS", "needle", "replacement", "ADMIN_UTILS")],
    "cache_refresh_behind_mutations": [("MUTANTS", 2, 3, "TARGET")],
    "cold_path_rejected_sample_mutations": [("MUTANTS", 2, 3, 1)],
    "league_rails_fence_mutations": [("MUTANTS", 2, 3, 1)],
    "duration_sample_window_mutations": [
        ("ADHERENCE_MUTANTS", "needle", "replacement", "ADHERENCE"),
        ("REDIS_MUTANTS", "needle", "replacement", "REDIS_STATE"),
    ],
    # LAT-P119 (#2085) — the FIRST harness whose targets are not Python:
    # TypeScript, TSX and Swift. Pass A was already file-type agnostic (it reads
    # each declared target directly); Pass B was not, and see `_files` for the
    # narrowing that fixed. Placed at its alphabetical position, per LAT-P115's
    # note two entries below.
    "event_hero_duel_percent_mutations": [
        ("RESOLVER_MUTATIONS", "needle", "replacement", "RESOLVER"),
        ("COMPONENT_MUTATIONS", "needle", "replacement", "COMPONENT"),
        ("VIEW_MUTATIONS", "needle", "replacement", "VIEW"),
    ],
    "feed_personalization_roundtrip_mutations": [("MUTATIONS", 2, 3, "TARGET")],
    "feed_prewarm_absent_shape_net_mutations": [("MUTATIONS", 3, 4, 1)],
    # LAT-P122. Alphabetical, for the reason spelled out one entry below. Two
    # modules under one guard file — the tier's own policy and the serve-stale
    # primitive this ship moved into the shared policy home — so two tables with
    # two target constants, the `duration_sample_window_mutations` shape.
    "futures_categories_census_mutations": [
        ("CENSUS_MUTATIONS", "needle", "replacement", "CENSUS"),
        ("SERVE_STALE_MUTATIONS", "needle", "replacement", "CONCEPT_CACHE"),
    ],
    # LAT-P137. Alphabetical, for the reason spelled out two entries below.
    # Three targets in one table (the warmer, the beat that schedules it and the
    # verdict registry that makes its failures authoritative), so the target is
    # carried per-entry at index 2 — the `game_markets_shared_cache_mutations`
    # shape rather than a module constant.
    "futures_categories_warm_mutations": [("MUTANTS", 3, 4, 2)],
    # LAT-P127. Alphabetical, for the reason spelled out in the next entry.
    "futures_detail_sources_cache_mutations": [("MUTANTS", 2, 3, "ROUTE")],
    # LAT-P115. Placed at its alphabetical position rather than at the head of
    # the dict: six consecutive latency branches have now collided on the two
    # lines directly under `admin_auth_gate_mutations`, because that is where an
    # append lands when nobody looks. Sorted insertion is not tidiness here, it
    # is the thing that stops the next cycle resolving this same hunk.
    "futures_movers_warm_mutations": [("MUTATIONS", "needle", "replacement", "WARM")],
    # LAT-P148. Alphabetical, for the reason spelled out above.
    "futures_source_breakdown_loose_scan_mutations": [("MUTANTS", 2, 3, "ROUTE")],
    # LAT-P121. Alphabetical, for the reason spelled out above. Two targets in
    # one table, so the target is carried per-entry at index 2 rather than by a
    # module constant.
    "game_markets_shared_cache_mutations": [("MUTANTS", 3, 4, 2)],
    # LAT-P126. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above. Two targets in one table (the route
    # and its warmer), carried per-entry at index 1.
    "golf_schedule_cache_mutations": [("MUTANTS", 3, 4, 1)],
    # LAT-P120. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above. Its targets are `.swift`, so Pass B's
    # hardcoded `*.py` glob cannot reach them — the harness carries its own
    # sha256 residue check at exit until that glob is derived from the declared
    # targets (written, waiting on `program/latency-104`).
    "ios_duel_percent_served_pair_mutations": [("MUTANTS", 3, 4, 2)],
    # LAT-P147. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above. Two targets in one table (the
    # shared loader and the route that delegates to it), carried per-entry at
    # index 2 — the `futures_categories_warm_mutations` shape.
    "latest_observation_mutations": [("MUTANTS", 3, 4, 2)],
    # LAT-P128. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above.
    "league_context_grid_cache_mutations": [("MUTANTS", 2, 3, "SERVICE")],
    "offline_rerank_fidelity_mutations": [("MUTATIONS", 3, 4, 1)],
    "outcome_evidence_class_mutations": [("MUTATIONS", 3, 4, 1)],
    # LAT-P138. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above. Four targets in one table — the
    # route, its producer, the beat wiring and the enrolment ledger — so the
    # target is carried per-entry at index 1, the `golf_schedule_cache_mutations`
    # shape.
    "prop_families_cache_mutations": [("MUTANTS", 3, 4, 1)],
    # LAT-P136. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above. Two targets in one table (the route
    # ladder and the policy module) carried per-entry at index 1 — the same
    # shape as its sibling `game_markets_shared_cache_mutations`, because the
    # defect it pins is that the two halves have to AGREE.
    "related_futures_shared_cache_mutations": [("MUTANTS", 3, 4, 1)],
    # LAT-P118. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above — an append at the head of this dict
    # is what six consecutive latency branches have collided on.
    "search_origin_channel_mutations": [
        ("MUTANTS", "needle", "replacement", "TARGET")
    ],
    "search_scorer_wiring_mutations": [("MUTATIONS", 2, 3, "TARGET")],
    "search_tier_split_mutations": [("MUTANTS", "needle", "replacement", "TARGET")],
    "search_stemmer_alias_mutations": [("MUTANTS", 2, 3, 1)],
    # LAT-P124. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above — an append at the head of this dict
    # is what several consecutive latency branches have collided on. Placed here
    # rather than in `DISK_FREE` on purpose: its oracle is the 21-test guard
    # suite run against the mutated file, which is stronger than any in-process
    # fake for a change whose whole measurement is a QUERY COUNT taken through
    # the real route. That trade is argued in the harness docstring.
    "search_suggestions_cold_mutations": [("MUTANTS", 2, 3, "TARGET")],
    # LAT-P151. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above. Two targets in ONE table — the
    # route and the shared `movement_pool` bound — so the target is carried per
    # entry at index 1, the `golf_schedule_cache_mutations` shape, and both
    # files are swept whichever mutant left residue.
    "search_suggestions_movers_pool_mutations": [("MUTANTS", 3, 4, 1)],
    "search_word_test_mutations": [("MUTANTS", 2, 3, 1)],
    # LAT-P144. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above — and note `season_` sorts AFTER
    # every `search_` entry, which is easy to get wrong by eye. Two targets in
    # one table (the route's ask and the module's policy) carried per-entry at
    # index 1, the same shape as its sibling `related_futures_shared_cache_
    # mutations`, because the defect it pins is that the two halves have to
    # AGREE: a cache that is never consulted and a cache that answers wrongly
    # are different bugs and both have to be visible.
    "season_market_discovery_mutations": [("MUTANTS", 3, 4, 1)],
    # LAT-P146. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above. Two targets in one table — the
    # shared population module and the adapter that consumes it — so the target
    # is carried per-entry at index 4, the `futures_categories_warm_mutations`
    # shape.
    "tennis_population_mutations": [("MUTANTS", 2, 3, 4)],
    "typeahead_concept_provenance_mutations": [("MUTATIONS", 2, 3, "TARGET")],
    # LAT-P143. Alphabetical, for the reason spelled out under
    # `futures_movers_warm_mutations` above — it sorts between the two
    # `typeahead_*` entries already here, and honouring that is what keeps
    # consecutive latency branches off one hunk. Single target carried as a
    # module constant, the `cache_refresh_behind_mutations` shape.
    "typeahead_outcome_arm_mutations": [("MUTANTS", 2, 3, "TARGET")],
    "typeahead_warmer_mutations": [("MUTATIONS", 3, 4, 1)],
}

# Harnesses that write NOTHING, anywhere — every mutant is a source string
# held in memory, `exec`'d or passed straight to the oracle. Not "restores
# carefully": no write at all, so there is no backup to restore and nothing a
# SIGKILL can leave behind. `_mutation_guard.py` calls this strictly the better
# design and asks new harnesses to prefer it.
#
# They need an entry here rather than an empty list in `SHAPES`. An empty list
# harvests zero pairs and prints nothing, which is indistinguishable from the
# harness having been forgotten — the silent-narrowing failure this scanner
# exists to refuse. Listed here they are counted and NAMED in Pass A.
#
# And the claim is VERIFIED, not taken on trust: each module must itself
# declare `MUTATES_WORKING_TREE = False`. A name in a list here can drift away
# from a harness that later grew a `write_text` on a real file; a constant in
# the harness is edited by the person doing the growing.
DISK_FREE: frozenset[str] = frozenset({
    # LAT-P123. Alphabetical, and deliberately here rather than in `SHAPES`:
    # every mutant is a source STRING `exec`'d into a throwaway module, so
    # there is no backup to restore and a SIGKILL can leave nothing behind.
    # Placing it here rather than at the head of `SHAPES` also keeps this
    # branch off the hunk seven consecutive latency branches have collided on.
    "browse_single_scan_mutations",
    # LAT-P139. Same construction again: the mutated tier is exec'd into a
    # throwaway module and swapped into `sys.modules`, never written down.
    #
    # 🔴 IT SITS BETWEEN THE TWO LAT-P123 NAMES BECAUSE THE RULE IS ALPHABETICAL
    # AND THE RULE WINS. `search_...` sorts between `browse_...` and
    # `tag_counts_...`, so honouring the ordering splits the pair that one
    # comment above introduced — the pair is still those two names, and this
    # note is here so the next reader does not "tidy" the ordering back into a
    # collision. Sorted insertion is not tidiness in this file; it is what has
    # kept seven consecutive latency branches off the same hunk.
    "search_suggestions_mirror_mutations",
    "tag_counts_group_by_mutations",
    # LAT-P135. Same construction: each mutant is a source STRING fed to the
    # guard's own imported checks, never written anywhere. Its oracle is
    # `tests/test_typeahead_fuzzy_index_lat_p135.py::CHECKS` imported directly,
    # so there is no second copy of the contract to drift, either.
    "typeahead_fuzzy_index_mutations",
})

# A replacement short enough to occur by coincidence is not evidence. `"}"`
# (search_stemmer_alias's president-synonym-removed) would match every Python
# file in the repo. Below this length the pair is counted and REPORTED as
# unscannable rather than dropped in silence.
MIN_LITERAL = 24


def _load(stem: str):
    spec = importlib.util.spec_from_file_location(stem, EVALS / f"{stem}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(EVALS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class Pair:
    __slots__ = ("harness", "mid", "needle", "repl", "target")

    def __init__(self, harness, mid, needle, repl, target):
        self.harness, self.mid, self.needle, self.repl, self.target = (
            harness,
            mid,
            needle,
            repl,
            target,
        )

    def __str__(self) -> str:
        return f"{self.harness}:{self.mid}"


def harvest() -> tuple[list[Pair], list[str]]:
    """Return (pairs, unknown_harnesses)."""
    on_disk = sorted(p.stem for p in EVALS.glob("*_mutations.py"))
    unknown = [s for s in on_disk if s not in SHAPES and s not in DISK_FREE]

    pairs: list[Pair] = []

    for stem in sorted(DISK_FREE):
        if stem not in on_disk:
            unknown.append(f"{stem} (listed in DISK_FREE, absent from disk)")
            continue
        if getattr(_load(stem), "MUTATES_WORKING_TREE", None) is not False:
            unknown.append(
                f"{stem} (listed in DISK_FREE but does not declare "
                "MUTATES_WORKING_TREE = False)"
            )

    for stem in on_disk:
        if stem in unknown or stem in DISK_FREE:
            continue
        module = _load(stem)
        for attr, n_key, r_key, target_spec in SHAPES[stem]:
            table = getattr(module, attr, None)
            if table is None:
                unknown.append(f"{stem}.{attr} (declared in SHAPES, absent from the module)")
                continue
            for index, entry in enumerate(table):
                mid = str(entry.get("id", index) if isinstance(entry, dict) else entry[0])
                needle, repl = entry[n_key], entry[r_key]
                if not isinstance(needle, str) or not isinstance(repl, str):
                    unknown.append(f"{stem}.{attr}[{index}] is not a (str, str) pair")
                    continue
                if isinstance(target_spec, int):
                    target = entry[target_spec]
                else:
                    target = getattr(module, target_spec, None)
                if not isinstance(target, Path):
                    unknown.append(f"{stem}.{attr}[{index}] has no resolvable target path")
                    continue
                pairs.append(Pair(stem, mid, needle, repl, target))

    return pairs, unknown


def _suffixes(pairs: list[Pair]) -> list[str]:
    """The file extensions Pass B must sweep, DERIVED from the declared targets.

    🔴 LAT-P119. This was hardcoded to `*.py`, and for eleven harnesses that was
    the whole truth. The twelfth mutates `.ts`, `.tsx` and `.swift`, and the
    scan went on printing a clean Pass B line over a scope that structurally
    could not contain its mutants — the silent-narrowing failure this scanner's
    own docstring refuses. Deriving the globs from `SHAPES` means the next
    harness in a new language widens the sweep by existing, rather than by
    somebody remembering.

    `.py` is always included: Pass B's job is to catch a mutant COPIED outside
    its declared target, and the likeliest place for that is a Python file even
    when the target is not one.
    """
    found = {p.target.suffix for p in pairs if p.target.suffix}
    return sorted(found | {".py"})


def _files(base: str, all_tracked: bool, suffixes: list[str]) -> list[Path]:
    globs = [f"*{s}" for s in suffixes]
    if all_tracked:
        cmd = ["git", "-C", str(REPO), "ls-files", "--", *globs]
    else:
        cmd = ["git", "-C", str(REPO), "diff", "--name-only", f"{base}...HEAD", "--", *globs]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        # EXIT 2, NOT 1 — this is the harness failing, not a finding.
        #
        # `raise SystemExit("message")` prints the message and exits **1**, the
        # same code this scanner reserves for RESIDUE FOUND. So an unresolvable
        # base — the ordinary state of a shallow PR checkout, where
        # `origin/master` was never fetched — reported as though a mutant had
        # been found sitting in the tree. The docstring above already promised
        # `2` for "the scan could not be performed"; only the code disagreed.
        #
        # This is gotcha #54's amendment applied to our own tooling: `1` is a
        # result and every other code is a story about the harness. A scanner
        # that spends the result code on its own inability to run destroys the
        # distinction it exists to enforce.
        print(
            f"🔴 scan: CANNOT MEASURE — git failed ({out.returncode}) resolving "
            f"the diff base: {out.stderr.strip()}",
            file=sys.stderr,
        )
        print(
            "   Pass B needs a merge base. In CI that means the checkout must "
            "fetch it (fetch-depth: 0); locally, `git fetch origin master`.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    paths = [REPO / line for line in out.stdout.split("\n") if line.strip()]
    return [p for p in paths if p.is_file()]


def _base_already_has(base: str, rel: str, literal: str) -> bool:
    """Did `rel` contain `literal` at `base`? Then it is not this branch's residue.

    Fails CLOSED: an unreadable base blob (a file this branch ADDED, a base that
    cannot be resolved) returns False, so the candidate stays a finding. A
    baseline lookup that cannot answer must not be the thing that clears a hit.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{base}:{rel}"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return False
    return literal in out.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="origin/master")
    ap.add_argument("--all-tracked", action="store_true")
    args = ap.parse_args()

    pairs, unknown = harvest()

    if unknown:
        print("🔴 scan: CANNOT MEASURE — harnesses this scanner does not understand:")
        for u in unknown:
            print(f"     {u}")
        print("   Add them to SHAPES. A partial scan must not print a clean line.")
        return 2

    # ---- PASS A: target integrity. Length-independent, and the one that
    # matters: residue can only exist in a file a harness actually mutates,
    # and in a clean tree every needle is present in its own target. This is
    # what makes the scan able to clear a one-character replacement like
    # `search_stemmer_alias:president-synonym-removed`, which no substring
    # search over the replacement could ever distinguish from ordinary code.
    residue: list[str] = []
    drift: list[str] = []
    cache: dict[Path, str] = {}
    for pair in pairs:
        if pair.target not in cache:
            try:
                cache[pair.target] = pair.target.read_text()
            except OSError:
                cache[pair.target] = ""
        text = cache[pair.target]
        if pair.needle in text:
            continue
        rel = pair.target.relative_to(REPO) if pair.target.is_relative_to(REPO) else pair.target
        if pair.repl and pair.repl in text:
            residue.append(f"{rel}  <-  {pair}  (mutant present, original absent)")
        else:
            drift.append(f"{rel}  <-  {pair}  (needle drifted; harness needs re-targeting)")

    print(f"PASS A — target integrity: {len(pairs)} needles across {len(cache)} target file(s)")
    if DISK_FREE:
        print(
            f"  + {len(DISK_FREE)} harness(es) declared disk-free and verified "
            f"(MUTATES_WORKING_TREE = False): {', '.join(sorted(DISK_FREE))}"
        )
        print("    They write no target file, so they cannot leave residue.")
    if drift:
        print(f"  {len(drift)} needle(s) no longer present AND no mutant either — harness DRIFT,")
        print("  not residue. These mutants would score NOT-APPLIED, never a false kill.")
        for d in drift:
            print(f"     {d}")
    if residue:
        print(f"🔴 RESIDUE: {len(residue)} target(s) hold the MUTANT and not the original")
        for r in residue:
            print(f"     {r}")
        return 1
    print("  ✅ every needle present in its own target — no mutant is sitting in a target file")

    # ---- PASS B: the broad sweep. Catches a mutant COPIED somewhere that is
    # not a declared target — the only case Pass A structurally cannot see.
    # Short replacements are excluded here because they match by coincidence,
    # and the count of what was excluded is printed rather than swallowed.
    scannable = [p for p in pairs if len(p.repl.strip()) >= MIN_LITERAL]
    skipped = len(pairs) - len(scannable)
    suffixes = _suffixes(pairs)
    files = _files(args.base, args.all_tracked, suffixes)
    kinds = " ".join(suffixes)
    scope = (
        f"all tracked {kinds}" if args.all_tracked else f"changed {kinds} vs {args.base}"
    )

    print()
    print(f"PASS B — broad sweep: {len(scannable)} literals x {len(files)} files ({scope})")
    print(f"  = {len(scannable) * len(files)} pairwise checks")
    if skipped:
        print(
            f"  {skipped} replacement(s) under {MIN_LITERAL} chars excluded here as "
            "coincidence-prone — all of them are cleared by Pass A."
        )

    hits: list[str] = []
    preexisting: list[str] = []
    for path in files:
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(REPO))
        for pair in scannable:
            if pair.repl in text and pair.needle not in text:
                if _base_already_has(args.base, rel, pair.repl):
                    preexisting.append(f"{rel}  <-  {pair}")
                    continue
                hits.append(f"{rel}  <-  {pair}")

    print()
    if preexisting:
        # 🔴 LAT-P122. Pass B's question is "was a mutant COPIED out of its
        # target by this branch", and it was answering "does this literal appear
        # here" — which is a different question whenever a replacement is,
        # verbatim, a real line of some other module.
        #
        # The instance: `game_markets_shared_cache:M13` replaces game-markets'
        # `CACHE_PREFIX` with `"bainluck:event_concept:"`, and that string is the
        # genuine, shipped constant at the top of `event_concept_cache.py`. It
        # went unseen only because Pass B sweeps CHANGED files and nothing had
        # changed that file since the harness landed. The first branch to touch
        # it — this one — turned the gate red on a line master already had.
        #
        # So the comparison is against the BASE. A literal already present in the
        # same file at `base` cannot be residue this branch left; it predates
        # every mutant run. Named and COUNTED rather than filtered in silence,
        # because a scan that quietly narrows its own scope is the failure this
        # file's docstring refuses.
        print(
            f"  {len(preexisting)} literal(s) matched a replacement but are "
            f"ALREADY in that file at {args.base} — pre-existing source, not residue:"
        )
        for p in preexisting:
            print(f"     {p}")
    if hits:
        print(f"🔴 RESIDUE: {len(hits)} candidate mutant(s) outside a declared target")
        for h in hits:
            print(f"     {h}")
        return 1

    print(
        f"✅ CLEAN — 0 residual mutants: {len(pairs)} needles verified in place, "
        f"{len(scannable) * len(files)} broad checks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
