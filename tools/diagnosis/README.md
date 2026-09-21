# TBH diagnosis lane (#7590)

One fresh `tbh exec --yolo --model muse-spark-1.3-internal` session per issue, using the verified existing Meta gateway profile. The controller serializes work with a kernel file lock inherited by its child; a second controller cannot start another model. Each run receives an independent git snapshot without a remote or shared lane metadata. Worker permissions are instructions, not an OS sandbox: `--yolo` is Alex's chosen invocation. No production credentials are injected; no production calls or external writes are authorized.

From this checkout:

```sh
./diagnosis-lane.sh dry-run
./diagnosis-lane.sh start
./diagnosis-lane.sh status
./diagnosis-lane.sh stop
./diagnosis-lane.sh window   # open/reuse the Terminal view and ensure worker is started
./diagnosis-lane.sh watch    # show status/output in this terminal
```

`start` installs the single-user launch agent `com.bainluck.diagnosis`. This runs while the Mac is awake and the user session is available; it is not a cloud worker. `stop` terminates the current worker group through the runner's signal handler, retains artifacts and leaves PAUSED so login does not resume work. `start` clears PAUSED. Other lanes are untouched. The launch agent points to the checkout from which it was installed: retain this checkout until reinstalling from the merged canonical source.

`start-lanes.sh` also opens the **TBH diagnosis** Terminal window. It shows current issue, progress and recent results from the same supervised worker. Re-running the starter reuses the window. Closing it or pressing Ctrl-C closes only the view; use `diagnosis-lane.sh stop` to pause actual work. Starting all lanes resumes a paused diagnosis worker, just as `start` does. The view has no authority to accept results or run model tools.

State and results: `~/bainluck-diagnosis/STATUS.json`, `state.json`, `service.log`, and `runs/<timestamp>-<issue>-<id>/`. Each run includes its source checkout, issue snapshot, prompt, raw model log, report and result. Exit 0 alone does not count as delivery: a completed model terminal event and a validated result/report/evidence contract are required. Controller status is execution status, never product acceptance.

Explicit assignments: add a uniquely named JSON under `~/bainluck-diagnosis/inbox/` with integer `issue`, string `prompt`, and optionally `explicit_scope: true` ONLY for a coordinator-assigned disjoint diagnosis on an already owned issue. This does not grant implementation ownership. Never reuse a consumed mission filename; a new correction gets a new name. Automatic intake reads up to 300 open `needs-agent` issues, preserves priority order, skips blocked/assigned/in-progress issues and PR references, then rechecks before the run. Selection has a bounded window; idle does not mean the entire backlog is empty. No automatic GitHub writes or comments.

Failures retry after 15 minutes, up to three attempts, then need attention; the daemon continues with other eligible work. Killed sessions keep their working directories. Delivered/blocked/not-needed issues do not get re-investigated without an explicit new assignment. Five unreviewed useful packages stop automatic intake to avoid overwhelming review; explicit correction assignments still run. After independent review, place a `REVIEWED` marker in that run directory and route the finding to the existing owner. The marker acknowledges review, not acceptance of a patch. Codex reviews/routs handoffs; this runner does not notify by itself.

Tests: `python3 tools/diagnosis/test_runner.py`. No main application tests are required for this isolated controller. Do not invoke the ordinary build-lane restock prompt for this lane. Startup health scans, source-hash changes, production repairs and self-certification remain outside its scope.
