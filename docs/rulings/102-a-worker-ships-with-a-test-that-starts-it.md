# RULING 102 — A worker ships with a test that STARTS it

date: 2026-08-19
author: Fable
issues: #1978, #1544

## The ruling

**Every worker, consumer, task or script ships with at least one IMPURE test
that STARTS it** — one that drives the real entry point a human would call,
through the real wiring, over a stubbed transport or fixture, and asserts it
produced something.

Caller-not-helper applies to us, not just to codex. A test that exercises a
helper the caller happens to use is not a test of the caller; a test that
asserts on `inspect.getsource` or on a SQL string is not a test that the code
runs at all.

The pure tests stay. They are where the decisions live and they are the only
tests that can exist for logic behind a database this sandbox does not have.
The rule adds one test; it does not replace the suite.

## The case

`cohort_cell_census` (#1978) merged in CAL-P075 with **37 tests, all pure** — SQL
invariants and the pure fold — passed CI, passed a clean integration, and
deployed at v3863.

It had never run. Every invocation died in **73 milliseconds**:

```
task cohort_cell_census   starts_24h 1  failures_24h 1  last_duration_ms 73
last_error: '_AsyncGeneratorContextManager' object has no attribute '__anext__'
```

`get_task_session` is an `@asynccontextmanager`; the worker hand-drove it as a
bare async generator. One line, in the wiring, in the first thing the worker
does — and **17,093 tests were green over it**, because not one of them called
the worker.

Two more defects sat behind that one, each invisible for the same reason and
each found within minutes of the first real run: `resume=True` never resumed
(the job's completeness was passed to the envelope, so `decode_envelope` typed
every checkpoint as malformed), and `GET .../last` could not read a partial
census for the same cause. Three defects, one absent test.

## Why the obvious defence does not work

The tempting reading is "the tests were bad". They were not: the fold they
tested was correct, and it is still correct. The pure suite proved every
decision the worker makes and zero facts about whether the worker makes them.

Nor is the answer "add an integration test", as a category. There is no local
Postgres in this sandbox (`initdb` dies on `shmget`), so "start it against a
real database" is a CI-only move and lanes correctly do not write tests they
cannot run. The rule is deliberately weaker and therefore actually followed:
**start the entry point over a stub.** `main()` through `argparse`. The Celery
task body with a fake session. The route handler with a fake `db`. Everything
between the caller and the first decision has to execute once.

## The rule paid out in the window that banked it

CAL-P077 shipped `scripts/measure_price_provenance.py` under this rule and wrote
the impure test first. The test covered the fold read failing. It did not cover
the two optional side probes failing — and on the first real 49-cell sweep, one
`statement_timeout` on the heavier feasibility probe **killed a run that had
already measured thirty cells**, because only the fold's `ReadError` was caught.

The untested branch is where the defect was, again, in the same shape, in the
file written to obey the ruling about it. Which is the argument for the rule
rather than against it: the run happened, so the defect surfaced in nine
minutes instead of a queue later. Both branches are covered now.

## The general clause — routed, and deliberately NOT banked this cycle

The clause that survives deleting this case (ruling 081): **a green suite over
code that has never executed is evidence about the suite, not about the code.**
The measurement to trust is the one taken after something started.

It belongs in `docs/doctrine.md` and it is **OWED, not written**, for a
numbering reason worth stating rather than quietly working around.

The highest clause on this branch's base (`62846ab8`) is **14**. Clauses **15**
and **16** are claimed in `RULING-CLAIMS.md` by the latency lane, banked on
`program/latency-66` and `-67`, unmerged, and `16` explicitly depends on `15`
landing first. So:

* writing **15** here duplicates a live claim, and
* writing **17** here leaves this branch reading 14 -> 17, which
  `backend/tests/test_doctrine_clause_numbering.py` — a guard added *this
  cycle*, precisely because of repeated renumbering in this series — reds on as
  a gap. It would red on my own branch, before it ever met theirs.

There is no number this window can write that is correct on both trees, and the
ledger's own header says why: *"the ledger is a FLOOR, not an oracle, and master
is the only thing that says what exists."* One clause has already been
renumbered four times in two cycles. Minting a fifth to avoid an empty section
would be the failure the guard was built to stop, performed in the name of
tidiness.

**Obligation:** the next calibration window (or the Integrator, once `-66` and
`-67` land) banks this clause as the then-next free number, claiming it in
`RULING-CLAIMS.md` first. It is recorded here so that "the doctrine line is
missing" reads as a debt with an owner rather than as an omission.
