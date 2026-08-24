"""LAT-P035/LAT-P037 — mutation harness for the futures word test and its gates.

LAT-P037 EXTENDED THIS, and the reason is the harness's own argument turned on
itself. LAT-P035 shipped 13/13 killed and was reverted anyway (`e22576db`),
because every mutant it wrote attacked a property the queue KNEW it had — and the
property that broke was one nobody had named: the rule's behaviour at two
characters. A mutation harness inherits the blind spots of the person listing the
mutants. So `fragment-boundary-removed` reproduces the revert exactly, and if this
file cannot kill it, the queue has re-shipped reverted work with a new docstring.


A green suite proves the code works on the paths the suite walks. It does not prove
the suite would NOTICE the code being undone, and that second property is the only
reason a regression guard exists. So each mutant below deliberately breaks one
property this queue shipped, and the harness demands the oracle FAIL.

TWO DIRECTIONS, on purpose
--------------------------
Half the mutants REMOVE the fix (drop the word test, drop the lexeme-less guard,
un-allowlist ``numnode``). The other half OVER-APPLY it — AND the guard instead of
OR-ing it, put the word test on the outcome arm, count a bucket reorder as a flap.
A guard that only catches deletion lets the next cycle "improve" the rule into the
LAT-P002 revert, which is exactly how the futures bucket emptied the last time.

WHY IT MUTATES ON DISK, AND WHAT THAT OBLIGES
---------------------------------------------
The oracles are pytest modules that import ``app.routes.events`` and read it with
``inspect.getsource``; an in-memory exec'd copy would not be the module they see.
So the mutation is written to the real file and restored from a ``cp`` backup.

That makes one failure mode load-bearing: **a mutation that does not APPLY reports
green**, because the oracle passes against unmutated source and a naive harness
scores that as a kill. Every mutant therefore asserts its needle was present, that
the file actually changed, and — after restore — that the file is byte-identical to
the backup. A mutant that fails to apply is a HARNESS failure and exits non-zero; it
is never silently counted as a kill.

Usage::

    python scripts/evals/search_word_test_mutations.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _mutation_guard import guarded_targets  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
EVENTS = BACKEND / "app/routes/events.py"
GUARD = BACKEND / "app/utils/sql_read_guard.py"
PRODUCER = BACKEND / "scripts/evals/search_bucket_producer.py"
REGISTRY_GEN = BACKEND / "scripts/evals/build_search_gold_registry.py"

SHAPE_ORACLE = "tests/test_search_latency_contract.py"
STABILITY_ORACLE = "tests/evals/test_search_bucket_stability.py"
REGISTRY_ORACLE = "tests/evals/test_search_gold_registry.py"
DEDUP_ORACLE = "tests/test_search_futures_dedup_identity.py"  # LAT-P038/#1769

# (id, file, needle, replacement, oracle, why)
MUTANTS: list[tuple[str, Path, str, str, str, str]] = [
    # ---- direction 1: undo the fix -------------------------------------
    (
        "futures-drop-word-test",
        EVENTS,
        """    return and_(
        _build_expanded_ilike(FuturesMarket.name, term, exp),
        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),
    )""",
        """    return _build_expanded_ilike(FuturesMarket.name, term, exp)""",
        SHAPE_ORACLE,
        "Reverts the futures name arm to substring-only: `nba champion` returns "
        "nine ITF tennis set markets again (#1758).",
    ),
    (
        "futures-or-instead-of-and",
        EVENTS,
        """    return and_(
        _build_expanded_ilike(FuturesMarket.name, term, exp),
        or_(
            _term_has_no_lexemes(term),""",
        """    return or_(
        _build_expanded_ilike(FuturesMarket.name, term, exp),
        or_(
            _term_has_no_lexemes(term),""",
        SHAPE_ORACLE,
        "OR-s the unindexable FTS arm at the top level — 1c's seq scan, the 20s median.",
    ),
    (
        "futures-drop-guard",
        EVENTS,
        """        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),""",
        """        _build_expanded_fts(FuturesMarket.name, term, exp),""",
        SHAPE_ORACLE,
        "Removes the lexeme-less guard from futures: a stopword term zeroes the "
        "conjunction and gold probe `taylor swift pregnant by...?` is lost.",
    ),
    (
        "events-drop-guard",
        EVENTS,
        """        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(Event.home_team_name, term, expansion),""",
        """        or_(
            _build_expanded_fts(Event.home_team_name, term, expansion),""",
        SHAPE_ORACLE,
        "Removes the guard from events: `dodgers and cubs` returns zero events "
        "(measured live on v3775 before the fix).",
    ),
    (
        "single-term-path-unguarded",
        EVENTS,
        "        futures_name_ilike = _futures_name_match_term(term, exp)",
        "        futures_name_ilike = _build_expanded_ilike(FuturesMarket.name, term, exp)",
        SHAPE_ORACLE,
        "Word-tests only the multi-term path. `nba champion` looks fixed while every "
        "single-term query keeps its substring collisions.",
    ),
    (
        "multi-term-path-unguarded",
        EVENTS,
        """            _futures_name_match_term(term, exp)
            for term, exp in expanded""",
        """            _build_expanded_ilike(FuturesMarket.name, term, exp)
            for term, exp in expanded""",
        SHAPE_ORACLE,
        "The inverse: single-term guarded, multi-term not — the motivating query "
        "itself stays broken.",
    ),
    (
        "unallowlist-numnode",
        GUARD,
        '"numnode", "phraseto_tsquery"',
        '"phraseto_tsquery"',
        SHAPE_ORACLE,
        "Blinds the plan rail to the search path's own SQL: EXPLAIN ANALYZE of the "
        "shipped predicate is refused by name.",
    ),
    (
        "registry-drop-adjudication",
        REGISTRY_GEN,
        '     ["team:boston-red-sox"], "pass",',
        '     [], "pass",',
        REGISTRY_ORACLE,
        "Removes the Red Sox alternative: the headline recall number goes back to "
        "being decided by which duplicate row sorts first.",
    ),
    (
        "flap-reported-as-stable",
        PRODUCER,
        '"STABLE" if len(unique) == 1',
        '"STABLE" if len(unique) >= 1',
        STABILITY_ORACLE,
        "Calls a flapping probe stable — the exact failure this mode exists to catch.",
    ),
    (
        "unverified-reported-as-stable",
        PRODUCER,
        '"UNVERIFIED" if len(good) < 2',
        '"UNVERIFIED" if len(good) < 0',
        STABILITY_ORACLE,
        "Absence of evidence read as evidence of stability (gotcha #53): one good "
        "run and one failure score the same as two agreeing runs.",
    ),
    # ---- direction 2: over-apply it ------------------------------------
    (
        "guard-anded-not-ored",
        EVENTS,
        """        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),""",
        """        and_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),""",
        SHAPE_ORACLE,
        "Inverts the guard into a REQUIREMENT that the term be a stopword — every "
        "real query matches nothing.",
    ),
    (
        "outcome-arm-word-tested",
        EVENTS,
        """        return FuturesMarket.id.in_(
            select(FuturesOutcome.market_id).where(
                _build_expanded_ilike(FuturesOutcome.name, term, exp)
            )
        )""",
        """        return FuturesMarket.id.in_(
            select(FuturesOutcome.market_id).where(
                and_(
                    _build_expanded_ilike(FuturesOutcome.name, term, exp),
                    _build_expanded_fts(FuturesOutcome.name, term, exp),
                )
            )
        )""",
        SHAPE_ORACLE,
        "Extends the rule to the outcome arm — a ~95% candidate cut (measured on "
        "`fed`: 1,027 markets -> 47) smuggled in on this queue's evidence.",
    ),
    (
        "reorder-counted-as-flap",
        PRODUCER,
        """    by_bucket: dict[str, set[str]] = {}
    for row in candidates:
        by_bucket.setdefault(str(row.get("bucket")), set()).add(str(row.get("entity_id")))
    return [[bucket, *sorted(ids)] for bucket, ids in sorted(by_bucket.items())]""",
        """    return [[str(row.get("bucket")), str(row.get("entity_id"))] for row in candidates]""",
        STABILITY_ORACLE,
        "Makes within-bucket reordering count as instability: the mode cries wolf "
        "every run and gets switched off.",
    ),
    # ---- LAT-P037: the fragment boundary, in BOTH directions ------------
    #
    # The mutant this queue exists for is `fragment-boundary-removed`. It is the
    # literal defect that reverted LAT-P035, so if the harness cannot kill it, this
    # queue has re-shipped a reverted change with a new docstring.
    (
        "fragment-boundary-removed",
        EVENTS,
        """    if not _has_extractable_trigram(term):
        # Fragment: substring recall only. See the LAT-P037 section above — the
        # word test cannot be right about a word the user has not finished
        # typing, so it does not get a vote.
        return _build_expanded_ilike(FuturesMarket.name, term, exp)
    return and_(""",
        """    return and_(""",
        SHAPE_ORACLE,
        "THE REVERT ITSELF (e22576db). The word test votes at two characters, where "
        "it can only ever vote FALSE: measured in production, the name arm goes "
        "25,576 open markets -> 16, and 'US Recession in 2026?' matches NEITHER.",
    ),
    (
        "fragment-boundary-always-exempts",
        EVENTS,
        """    if not _has_extractable_trigram(term):""",
        """    if True:""",
        SHAPE_ORACLE,
        "Over-applies the exemption so nothing is ever word-tested — green on the "
        "2-char test while silently undoing the whole queue (`nba champion` returns "
        "the nine Zhiyenbayeva rows again).",
    ),
    (
        "fragment-boundary-back-to-length",
        EVENTS,
        """    if not _has_extractable_trigram(term):""",
        """    if len(term) < 3:""",
        SHAPE_ORACLE,
        "Re-hand-rolls the cliff as a length check — the third copy, and blind to "
        "`u.s.`/`a.i.`/`d'or` (length 4, measured 22-31x their length-matched "
        "controls in LAT-P013).",
    ),
    (
        "events-arm-silently-exempted",
        EVENTS,
        """    return and_(
        or_(
            _build_expanded_ilike(Event.home_team_name, term, expansion),
            _build_expanded_ilike(Event.away_team_name, term, expansion),
        ),""",
        """    if not _has_extractable_trigram(term):
        return or_(
            _build_expanded_ilike(Event.home_team_name, term, expansion),
            _build_expanded_ilike(Event.away_team_name, term, expansion),
        )
    return and_(
        or_(
            _build_expanded_ilike(Event.home_team_name, term, expansion),
            _build_expanded_ilike(Event.away_team_name, term, expansion),
        ),""",
        SHAPE_ORACLE,
        "Spreads the exemption to the EVENTS arm by symmetry. That is a live, "
        "deployed, measured surface (LAT-P034: `re` 6,597 events -> 0) and changing "
        "it needs its own before/after, not an argument from consistency.",
    ),
    (
        "empty-expected-bucket-not-checked",
        PRODUCER,
        """                empty = row["bucket_sizes"].get(want_bucket) == 0""",
        """                empty = False""",
        STABILITY_ORACLE,
        "Restores the original blindness: an HTTP 200 with the primary bucket empty "
        "— the f98d8104 signature — is recorded as an ordinary missing id.",
    ),
    (
        "empty-expected-bucket-over-fires",
        PRODUCER,
        """                empty = row["bucket_sizes"].get(want_bucket) == 0""",
        """                empty = any(size == 0 for size in row["bucket_sizes"].values())""",
        STABILITY_ORACLE,
        "Flags every probe with ANY empty bucket. It would fire on nearly all of "
        "them, and a check that always fires is one nobody reads.",
    ),
    (
        "declared-xfail-empty-bucket-counted",
        PRODUCER,
        """                if empty and failure_status == "xfail":""",
        """                if False:""",
        STABILITY_ORACLE,
        "Counts the declared wedding-query xfail, whose empty 200 IS its declared "
        "breakage — leaving the check permanently red from the day it ships.",
    ),
    # ---- LAT-P038/#1769: the dedup key is an identity, not a taxonomy ----
    (
        "canonical-shortcircuit-restored",
        EVENTS,
        """    name = (market.name or "").strip()
    name = _FUTURES_DEDUP_STRIP.sub("", name).strip()""",
        """    if getattr(market, "canonical_market_key", None):
        return f"canonical:{market.canonical_market_key}"
    name = (market.name or "").strip()
    name = _FUTURES_DEDUP_STRIP.sub("", name).strip()""",
        DEDUP_ORACLE,
        "Puts a CATEGORY key back in the identity slot: `president` returns one "
        "market again with 461 open ones behind it (#1769).",
    ),
    (
        "fold-deletes-punctuation",
        EVENTS,
        """    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())""",
        """    return " ".join(re.sub(r"[^a-z0-9]+", "", text).split())""",
        DEDUP_ORACLE,
        "OVER-APPLIES the fold — deleting punctuation instead of separating on it "
        "merges the prop lines `O/U 5.5` and `O/U 55` into one row, reintroducing "
        "the same silent deletion one layer down.",
    ),
    (
        "fold-removed",
        EVENTS,
        """    return f"name:{_fold_dedup_punctuation(name_lower)}:{market.market_tier or 0}\"""",
        """    return f"name:{name_lower}:{market.market_tier or 0}\"""",
        DEDUP_ORACLE,
        "Drops the fold: 'NBA: 2027 Champion' and 'NBA Championship Winner' stop "
        "merging, so the one merge the canonical arm really was performing is lost.",
    ),
    (
        "futures-window-back-to-a-literal",
        EVENTS,
        """        .limit(_SEARCH_FUTURES_WINDOW)
    )

    # Apply sport filter to futures if specified""",
        """        .limit(20)
    )

    # Apply sport filter to futures if specified""",
        DEDUP_ORACLE,
        "Re-hides the relationship between the window and the page — the fact "
        "that the window IS the page's only dedup headroom goes uncommented "
        "again, which is how 1b survived.",
    ),
    (
        "refill-fires-unconditionally",
        EVENTS,
        """        len(deduped_futures) < _SEARCH_FUTURES_PAGE
        and len(futures_markets_raw) >= _SEARCH_FUTURES_WINDOW""",
        """        len(deduped_futures) < _SEARCH_FUTURES_PAGE""",
        DEDUP_ORACLE,
        "OVER-APPLIES the refill: every short page — including the honestly short "
        "ones — pays a second futures query, on the stage that is already #1731's "
        "open cost subject.",
    ),
    (
        "refill-ignores-the-deadline",
        EVENTS,
        """        and time.monotonic() < _deadline
    ):
        logger.warning(
            "search futures bucket COLLAPSED""",
        """    ):
        logger.warning(
            "search futures bucket COLLAPSED""",
        DEDUP_ORACLE,
        "Lets the refill run after the budget is spent — trading the LAT-P002 "
        "failure (a fast wrong answer) for its twin (a late one).",
    ),
    (
        "collapse-never-reported",
        EVENTS,
        """    _futures_collapsed = (
        len(futures_markets_raw) >= _SEARCH_FUTURES_WINDOW
        and len(futures_markets) < _SEARCH_FUTURES_PAGE
    )""",
        """    _futures_collapsed = False""",
        DEDUP_ORACLE,
        "Silences the only signal a client cannot compute for itself, returning "
        "the gate to grading recall on a bucket it cannot see the size of.",
    ),
    (
        "producer-ignores-the-collapse-key",
        PRODUCER,
        """            row["bucket_collapse"] = bool(collapse)""",
        """            row["bucket_collapse"] = False""",
        STABILITY_ORACLE,
        "Reads the server's collapse report and throws it away — the exact "
        "'recorded bucket_sizes and never looked at them' failure, third time.",
    ),
    (
        "collapse-inferred-from-bucket-size",
        PRODUCER,
        """            collapse = payload.get("futures_collapse")""",
        """            collapse = (
                {"inferred": True}
                if len(payload.get("futures") or []) < 10
                else None
            )""",
        STABILITY_ORACLE,
        "OVER-APPLIES the verdict by guessing it from the outside: `tush push` "
        "honestly returns one market and would be flagged, so the check fires on "
        "correct answers and gets switched off.",
    ),
]


def _run_oracle(oracle: str) -> bool:
    """True when the oracle PASSES (i.e. the mutant survived)."""

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", oracle, "-x", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    return proc.returncode == 0


def _main() -> int:
    files = {EVENTS, GUARD, PRODUCER, REGISTRY_GEN}
    backups: dict[Path, Path] = {}
    tmp = Path(tempfile.mkdtemp(prefix="lat-p035-mutations-"))
    for path in files:
        backup = tmp / path.name
        shutil.copy2(path, backup)
        backups[path] = backup

    killed, survived, unapplied = [], [], []
    try:
        for mutant_id, path, needle, replacement, oracle, why in MUTANTS:
            original = path.read_text(encoding="utf-8")
            if needle not in original:
                # A drifted needle is a HARNESS failure. Reporting it as a kill is
                # the specific lie this harness is built to make impossible.
                unapplied.append((mutant_id, "needle not found — the source moved"))
                print(f"  UNAPPLIED {mutant_id}: needle not found")
                continue
            mutated = original.replace(needle, replacement, 1)
            if mutated == original:
                unapplied.append((mutant_id, "replacement was a no-op"))
                print(f"  UNAPPLIED {mutant_id}: replacement changed nothing")
                continue
            path.write_text(mutated, encoding="utf-8")
            if path.read_text(encoding="utf-8") != mutated:
                unapplied.append((mutant_id, "write did not land"))
                print(f"  UNAPPLIED {mutant_id}: write did not land")
                continue

            oracle_passed = _run_oracle(oracle)
            path.write_text(original, encoding="utf-8")

            if oracle_passed:
                survived.append((mutant_id, why))
                print(f"  SURVIVED  {mutant_id} — {why}")
            else:
                killed.append(mutant_id)
                print(f"  killed    {mutant_id}")
    finally:
        for path, backup in backups.items():
            shutil.copy2(backup, path)
            assert path.read_bytes() == backup.read_bytes(), f"restore failed for {path}"
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"MUTATION SUMMARY: {len(killed)} killed, {len(survived)} survived, "
          f"{len(unapplied)} unapplied, {len(MUTANTS)} total")
    for mutant_id, reason in unapplied:
        print(f"  UNAPPLIED {mutant_id}: {reason}")
    for mutant_id, why in survived:
        print(f"  SURVIVED  {mutant_id}: {why}")
    return 1 if (survived or unapplied) else 0



def main() -> int:
    """Guarded entry point — this harness's own `try/finally` is not enough.

    It restores on exceptions, which is most of the cases. It does NOT restore
    on **SIGTERM**, because Python's default disposition kills the interpreter
    without unwinding, and SIGTERM (exit 143, the 10-minute tool cap) is the
    signal that actually put a mutant into `bcdcd95f`. So these two harnesses
    were counted as "already guarded" against the wrong hazard.
    `tests/test_mutation_guard.py` pins that with a control.
    """
    with guarded_targets(sorted({EVENTS, GUARD, PRODUCER, REGISTRY_GEN}), "/tmp/lat_word_test_guard_backups", 'search_word_test'):
        return _main()

if __name__ == "__main__":
    raise SystemExit(main())
