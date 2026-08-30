#!/usr/bin/env python3
"""LAT-P146 mutation battery: a shared population must stay a strict superset.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way a later edit could put the defect
back, and most of them read as a tidy-up — which is exactly why they are here.
A SURVIVOR is a hole in the suite and the fix is to add the missing assertion,
never to delete the mutant.

The defect this pins, in one line: `TennisEventAdapter.build_event` answered
"what is the US Open" by loading every tennis market in a 30-day window with all
of their outcomes — 23,101 markets and 50,842 outcomes in ~47 queries, to render
1,307 children — which measured 21.0 s on production `944c466e` and 30.3 s (an
H12 error page) on one of that page's alias slugs.

The fix has two halves and the DANGEROUS half is the first:

  1. the resolved arm is fetched once and SHARED across every tennis key. It is
     only safe because it is a strict SUPERSET — the cached query reaches
     further back than any caller's window and the caller's exact cutoff is
     re-applied on every read — and because it carries IDENTITY ONLY, never a
     price and never a grade. Mutants M1-M13 attack exactly those two claims.
  2. outcomes are loaded for the winner candidates and the associated children
     instead of for the whole population. That is safe only because
     `winner_candidate_ids` is a provable superset of what the resolver asks
     about; M18-M21 attack that.

🔴 M19 SURVIVED THE FIRST RUN, AND THE SURVIVOR WAS THE FINDING. Dropping the
exact-slug arm from `winner_candidate_ids` changed nothing any assertion could
see, because every exact-slug market in the fixture corpus was ALSO reachable by
the subset arm. The case that separates them is a market whose name is entirely
stopwords — `canonical_tokens("Men's Singles Winner")` is the empty set, so no
slug can reach it by subset and only its own exact slug can. Search emits
`event:tennis:{clean_slug(name)}` for any winner market, so that key is
reachable in production, and the prefetch losing it would resolve the page on
zero competitors. Fixed by adding the market and the assertion, not by deleting
the mutant.

Two files are mutated, because the ship spans two:

  app/utils/tennis_population.py   the arms, the shared slot, the window and
                                   the two-phase loaders
  app/utils/event_tennis.py        the adapter's use of them

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: a source edit under a running suite produces
phantom failures that read as real reds.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose NEEDLE
is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/tennis_population_mutations.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
POP = ROOT / "app" / "utils" / "tennis_population.py"
ADAPTER = ROOT / "app" / "utils" / "event_tennis.py"
SUITE = ROOT / "tests" / "test_tennis_population_lat_p146.py"
CONTRACT = ROOT / "tests" / "test_event_tennis.py"
IDENTITY = ROOT / "tests" / "test_event_tennis_identity.py"

#: (id, description, old, new, target). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, str, str, str, pathlib.Path]] = [
    # --- the superset property -------------------------------------------
    (
        "M1",
        "serve the cached window whole — the superset stops being narrowed",
        """    return [
        r
        for r in rows
        if r.resolution_date is not None and r.resolution_date >= cutoff
    ]""",
        """    return list(rows)""",
        POP,
    ),
    (
        "M2",
        "exclude the row sitting exactly on the cutoff",
        "if r.resolution_date is not None and r.resolution_date >= cutoff",
        "if r.resolution_date is not None and r.resolution_date > cutoff",
        POP,
    ),
    (
        "M3",
        "a cache HIT skips the window re-application",
        """    stored = _read_cached(rc, PAYLOAD_KEY)
    if stored is not None and _is_fresh(rc):
        return _within(stored, cutoff)""",
        """    stored = _read_cached(rc, PAYLOAD_KEY)
    if stored is not None and _is_fresh(rc):
        return stored""",
        POP,
    ),
    (
        "M4",
        "cache the caller's OWN window — the payload stops being a superset",
        "    widened = cutoff - timedelta(seconds=CUTOFF_SLACK_SECONDS)",
        "    widened = cutoff",
        POP,
    ),
    (
        "M5",
        "the widening no longer outlives the mirror",
        "CUTOFF_SLACK_SECONDS = RESOLVED_MIRROR_TTL_SECONDS + 3600",
        "CUTOFF_SLACK_SECONDS = 3600",
        POP,
    ),
    (
        "M6",
        "the fresh fetch is served unfiltered while the cache is filtered",
        """    _write_cached(rc, fresh)
    return _within(fresh, cutoff)""",
        """    _write_cached(rc, fresh)
    return fresh""",
        POP,
    ),
    # --- serve-stale on the ordinary expiry ---------------------------------
    (
        "M6b",
        "a TTL expiry walks the reader into the scan instead of the mirror",
        """    if stored is not None and serve_stale_and_refresh(
        SLOT_KEYS, lambda: _refresh_shared_arm(widened), rc=rc
    ):
        return _within(stored, cutoff)""",
        """    if False:
        return _within(stored, cutoff)""",
        POP,
    ),
    (
        "M6c",
        "serve the mirror with NOTHING behind it — serve-stale-forever",
        """    if stored is not None and serve_stale_and_refresh(
        SLOT_KEYS, lambda: _refresh_shared_arm(widened), rc=rc
    ):
        return _within(stored, cutoff)""",
        """    if stored is not None:
        return _within(stored, cutoff)""",
        POP,
    ),
    (
        "M6d",
        "the rebuild behind the mirror narrows the window it re-caches",
        "        SLOT_KEYS, lambda: _refresh_shared_arm(widened), rc=rc",
        "        SLOT_KEYS, lambda: _refresh_shared_arm(cutoff), rc=rc",
        POP,
    ),
    (
        "M6e",
        "the rebuild scans and throws the rows away",
        """        rows = await fetch_resolved_arm(session, widened)
    _write_cached(_get_client(), rows)""",
        """        rows = await fetch_resolved_arm(session, widened)
    _ = rows""",
        POP,
    ),
    # --- the shared slot ---------------------------------------------------
    (
        "M7",
        "store an EMPTY population — a broken read freezes into a 24 h mirror",
        """    if rc is None or not rows:
        return""",
        """    if rc is None:
        return""",
        POP,
    ),
    (
        "M8",
        "never stamp the payload fresh — every read becomes a serve-stale",
        "        rc.setex(FRESH_KEY, RESOLVED_TTL_SECONDS, FRESH_MARKER)",
        "        pass",
        POP,
    ),
    (
        "M9",
        "the payload expires with the freshness marker — no serve-stale left",
        "        rc.setex(PAYLOAD_KEY, RESOLVED_MIRROR_TTL_SECONDS, _pack([_encode_row(r) for r in rows]))",
        "        rc.setex(PAYLOAD_KEY, RESOLVED_TTL_SECONDS, _pack([_encode_row(r) for r in rows]))",
        POP,
    ),
    (
        "M10",
        "no Redis reads as an EMPTY population instead of a miss",
        """    if rc is None:
        return None""",
        """    if rc is None:
        return []""",
        POP,
    ),
    (
        "M11",
        "an empty cached list reads as a miss — absent and empty collapse",
        "    if not isinstance(decoded, list):",
        "    if not decoded or not isinstance(decoded, list):",
        POP,
    ),
    (
        "M12",
        "one malformed cached row empties the whole population",
        "    rows = [r for r in (_decode_row(item) for item in decoded) if r is not None]",
        """    rows = [_decode_row(item) for item in decoded]
    rows = [] if None in rows else rows""",
        POP,
    ),
    (
        "M13",
        "decode an oversized payload instead of refusing it",
        "    if len(raw) > MAX_PAYLOAD_BYTES:",
        "    if False:",
        POP,
    ),
    (
        "M13b",
        "store a SECOND copy of the population — 6% of a 100 MB LRU Redis",
        "        rc.setex(FRESH_KEY, RESOLVED_TTL_SECONDS, FRESH_MARKER)",
        "        rc.setex(FRESH_KEY, RESOLVED_TTL_SECONDS, _pack([_encode_row(r) for r in rows]))",
        POP,
    ),
    (
        "M13c",
        "stop compressing the payload — 3.06 MB where 1.13 MB would do",
        "    return zlib.compress(_dumps(payload), COMPRESSION_LEVEL)",
        "    return _dumps(payload)",
        POP,
    ),
    (
        "M13d",
        "a compressed payload is no longer readable as plain JSON on the way back",
        """    if isinstance(raw, bytes) and raw[:1] == _ZLIB_MAGIC:
        return _loads(zlib.decompress(raw))
    return _loads(raw)""",
        "    return _loads(zlib.decompress(raw))",
        POP,
    ),
    (
        "M13e",
        "stamp fresh BEFORE the payload — a crash leaves the marker lying for a TTL",
        """        rc.setex(PAYLOAD_KEY, RESOLVED_MIRROR_TTL_SECONDS, _pack([_encode_row(r) for r in rows]))
        rc.setex(FRESH_KEY, RESOLVED_TTL_SECONDS, FRESH_MARKER)""",
        """        rc.setex(FRESH_KEY, RESOLVED_TTL_SECONDS, FRESH_MARKER)
        rc.setex(PAYLOAD_KEY, RESOLVED_MIRROR_TTL_SECONDS, _pack([_encode_row(r) for r in rows]))""",
        POP,
    ),
    (
        "M13f",
        "a Redis that cannot answer reads as FRESH — serve-stale never engages",
        """        logger.warning("tennis population: freshness read failed")
        return False""",
        """        logger.warning("tennis population: freshness read failed")
        return True""",
        POP,
    ),
    # --- identity only -----------------------------------------------------
    (
        "M14",
        "a naive cached timestamp is left naive — it cannot be compared",
        """        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)""",
        """        if False:
            when = when.replace(tzinfo=timezone.utc)""",
        POP,
    ),
    (
        "M15",
        "the reader destroys outcomes the row already carried",
        """    carried = getattr(row, "outcomes", None)
    if carried:
        market.outcomes = list(carried)""",
        """    carried = None
    if carried:
        market.outcomes = list(carried)""",
        POP,
    ),
    # --- the population ----------------------------------------------------
    (
        "M16",
        "the open arm is dropped — the live half comes from the cache",
        "    for row in open_rows + resolved_rows:",
        "    for row in resolved_rows:",
        POP,
    ),
    (
        "M17",
        "the arms are not deduplicated — a status change renders twice",
        """        if row.id in seen:
            continue""",
        """        if False:
            continue""",
        POP,
    ),
    (
        "M18",
        "the population order is left to the database again",
        "    combined.sort(key=lambda r: r.id)",
        "    pass",
        POP,
    ),
    # --- the winner-candidate superset -------------------------------------
    (
        "M19",
        "the prefetch drops the exact-slug arm — #1793's direct request goes cold",
        '''        exact = clean_slug(m.name or "") == slug
        subset = bool(slug_tokens) and slug_tokens <= canonical_tokens(m.name)
        if exact or subset:''',
        """        exact = False
        subset = bool(slug_tokens) and slug_tokens <= canonical_tokens(m.name)
        if exact or subset:""",
        POP,
    ),
    (
        "M20",
        "the prefetch uses the CHILD token space — #1793's own defect, exactly",
        """        canonical_slug_tokens,
        canonical_tokens,
        is_winner_market,
    )""",
        """        canonical_slug_tokens,
        is_winner_market,
        tournament_tokens as canonical_tokens,
    )""",
        POP,
    ),
    (
        "M21",
        "the prefetch adds the field floor the resolver applies AFTER counting",
        """        if exact or subset:
            ids.append(m.id)""",
        """        if (exact or subset) and len(m.outcomes or []) >= 2:
            ids.append(m.id)""",
        POP,
    ),
    # --- the two-phase loaders ---------------------------------------------
    (
        "M22",
        "an outcome-less market vanishes from the load instead of reading empty",
        "    out: dict[int, list[OutcomeRow]] = {i: [] for i in ids}",
        "    out: dict[int, list[OutcomeRow]] = {}",
        POP,
    ),
    (
        "M23",
        "an unattributable outcome row is dropped silently",
        """        logger.warning(
            "tennis population: %d outcome rows carried no requested market_id",
            unattributable,
        )""",
        """        pass""",
        POP,
    ),
    (
        "M24",
        "attach EMPTIES a market the other phase already loaded",
        """        rows = loaded.get(market.id)
        if rows:""",
        """        rows = loaded.get(market.id)
        if rows is not None:""",
        POP,
    ),
    # --- the adapter -------------------------------------------------------
    (
        "M25",
        "the adapter loads the WHOLE population's outcomes again",
        "            markets, await load_outcomes(db, winner_candidate_ids(markets, slug))",
        "            markets, await load_outcomes(db, [m.id for m in markets])",
        ADAPTER,
    ),
    (
        "M26",
        "the children's outcomes are never loaded — every child loses its price",
        """        attach_outcomes(
            (m for m, _ in associated),
            await load_outcomes(db, [m.id for m, _ in associated]),
        )""",
        """        attach_outcomes((m for m, _ in associated), {})""",
        ADAPTER,
    ),
    (
        "M27",
        "the children loop walks the population again, association discarded",
        "        for m, method in associated:",
        "        for m, method in [(x, \"token\") for x in markets if x.id != winner.id]:",
        ADAPTER,
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            str(CONTRACT),
            str(IDENTITY),
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets(
        [POP, ADAPTER],
        "/tmp/lat_p146_tennis_population_guard_backups",
        "tennis_population",
    ):
        return _main()


def _main() -> int:
    originals = {POP: POP.read_text(), ADAPTER: ADAPTER.read_text()}

    print(
        f"denominator: {len(MUTANTS)} mutants queued against "
        f"{POP.name} + {ADAPTER.name}"
    )
    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    print("baseline: suite GREEN on the unmutated tree\n")

    killed, survived, broken = [], [], []
    try:
        for mid, desc, old, new, target in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is a no-op — NOT APPLIED"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED")
                continue
            target.write_text(mutated)
            # Prove the mutation is actually on disk before believing its result:
            # a mutant that failed to apply reports a green suite as a survivor.
            if target.read_text() != mutated:
                target.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED on disk")
                continue
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:5} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:5} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      pytest exit {rc} — the gate never ran"
                )
    finally:
        for path, text in originals.items():
            path.write_text(text)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(broken)} harness failures"
    )
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    if broken:
        for mid, why in broken:
            print(f"  BROKEN {mid}: {why}")
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
