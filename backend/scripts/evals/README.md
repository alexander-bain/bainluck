# Bain Luck evals

An eval here is a **contract plus cases**: a named oracle decides what an input
means, and a committed case file states the expected answer. Most contract
oracles grade dictionaries that model a product decision. Passing them does
not prove the production route, rendered card or device did the same thing.

Five instruments complement each other:

- **Contracts and cases:** small repeatable decisions and adversarial examples.
- **Mutation batteries:** deliberate edits test whether a named guard notices.
  They may write source temporarily; the restore guard and residue scanner are
  safety tools, not proof that a mutant was killed.
- **Matching golden set:** captured market/event pairs replay the real matcher;
  its recorded passing set is also a floor against silent regression.
- **Human-rating harnesses:** `calibrate_interestingness.py` and
  `rater_reliability.py` evaluate taste and rater agreement. Sparse labels can
  legitimately leave no measurable baseline.
- **Forward record:** published probabilities graded against later outcomes,
  with a methodology ledger. The public calibration record grades sources;
  it does not establish the accuracy of an unrecorded blend.

Run from the repository's `backend/` directory:

```sh
python3 -m scripts.evals.scoreboard
python3 -m scripts.evals.scoreboard --json
```

This offline command needs Python's standard library, takes under 30 seconds,
and reads committed evidence. Each registry canonical and its extensions form
one family on the screen. JSON lists every member, case source, unit and last
recorded test result. Counts include fixture rows, literal mutants and named
generated tests; shared corpora are identified in their units and are not
independent samples; family totals count a shared case source once. `+?` means
a missing count; `unrecorded` means no test/run
receipt. The timestamp and source SHA belong to the receipt, not this command.
The bite sample is replayed offline; the golden baseline and residue verdict
are recorded results. Red numbers print unchanged and exit 0; unreadable
evidence exits 2. This is a report, not a new CI quality threshold.

To add or materially change an eval:

1. Find its domain in `eval_registry.json`. Extend the canonical contract (or
   explicitly supersede it), add the registry entry, and name that parent in
   the module's header. Prefer a new case in an existing oracle to a duplicate.
2. Commit a versioned case file under `backend/tests/evals/fixtures/` (or the
   existing family file here), including clean controls and the known defect.
   State whether it is a stand-in or crosses a real product boundary.
3. Add the corresponding test under `backend/tests/evals/`; run it and
   `tests/test_startup.py`. Add case selectors to `scoreboard_record.json`.
   Record a run only with its command, source SHA, date, test files and actual
   pass/fail/skip split; do not copy an older green onto new work.
4. An exclusion needs a named widening mutation and its specific expected red.
   Run source-writing batteries only in an isolated checkout, serially, with
   the shared mutation guard. Report kills here separately from work owed to
   CI, naming what future run discharges the debt. Never treat an unapplied
   mutant or failed control as a kill.

The binding rulings are [002: canonical contracts](../../../docs/rulings/002-eval-registry-canonical-contracts.md),
[065: report the mutation split](../../../docs/rulings/065-report-the-mutation-split.md),
and [087: exclusions need a reddening mutation](../../../docs/rulings/087-an-exclusion-is-only-safe-where-a-mutation-can-red-it.md).
The [Nov 2026 registry audit](../../../docs/evals/REGISTRY-AUDIT-2026-11.md)
reviews all 47 unregistered artifacts from the story: all are keepers, zero
were justified as legacy. Pre-ratification unregistered files remain a distinct
visible count; they have not silently been declared legacy.
