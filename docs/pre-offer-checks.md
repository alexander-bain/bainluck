# Early feedback before publishing a product fix

Parent #11075; implementation #11076. This supports the already queued TRUTH
and FORMATTING fixes (#994, #683, #9483) by finding known inexpensive failures
before they consume a full hosted CI cycle.

After committing an isolated candidate, run from that worktree:

```sh
bash tools/pre-offer-gate.sh origin/master HEAD
```

Use a locally available ancestor as the first argument if appropriate; the
command does not fetch. The requested head must be the checkout's actual HEAD.
Dirty or untracked source, missing inputs, failed children and timeouts refuse
the check. It runs existing startup, PostgreSQL assignment, warning-count,
cross-tier manifest, required-context and backend-sharding guards, followed by
the same dependency-free Node contract command used by CI.

When the workflow, pytest configuration/conftest, or #10090 release-wake test changes, it also collects that
test and compares the selection with the workflow's own literal summary pin.
This deliberately supports only that demonstrated invocation. Changed selectors
or unfamiliar shell forms require qualification; they never count as a pass.
Collection retains configured selection options and does not run PostgreSQL
test bodies or prove their runtime behavior. Each child has a ten-minute limit;
the complete command is not promised to finish in seconds.

The final JSON receipt identifies the base, checked head, elapsed time and scope.
Include it with the normal offer's builder, exact source, focused tests,
dependencies and responsible non-author reviewer. A failure names the missing
proof to repair; an unavailable local dependency is not permission to skip it.

This is early feedback, not full acceptance. It does not prove browser/Apple
behavior, fresh-host clock safety, a real database run or general dependency
coverage. Keep affected build/type checks, hosted CI and the Integrator's full
exact-composed-tree CI before the master push. CI success, merge, delivery and
product acceptance remain distinct. Tools-only changes ride an eligible product
delivery through the existing Integrator rather than causing a standalone server
release.
