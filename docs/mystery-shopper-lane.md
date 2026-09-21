# Mystery Shopper & Issues lane

PILLARS: TRUTH / FORMATTING / MATCHING / DISCOVER.
SHIP: users encounter fewer broken journeys, and the sprint board accurately shows what is being built, delivered and still blocked without Alex asking.

Lane name: `shopper`. Worktree: `~/bainluck-dev/shopper`. Shared inbox: `~/bainluck/.claude/handoff/runner-inbox/shopper/`. Setup/tracking issue: #7898.

This is the dedicated QA and issue-maintenance lane Alex requested on September 21. It is not a build lane. UX continues building; Native retains simulator/build ownership. Do not take another lane's implementation, edit application code, merge, deploy, run production writes, change billing settings, or perform Apple actions. Do not run the entire launcher to start this one lane.

## Every hourly pass

1. Read only new inbox messages and changes since the last pass. The current sprint is #7569 and `sprint:live-charts`; GitHub is the source of truth. Use existing lane reports and issue/PR/release receipts. No broad database census or repeated unchanged probes.
2. Maintain Project 1 views 5 and 6: Delivery stage, Release target, User outcome, Delivery owner, Next step, Evidence checked. Field IDs and maintenance instructions: `~/bainluck/artifacts/chart-sprint-board/github/fields.json` and `README.md`. Preserve execution Status and ownership locks. One issue spanning web and phone must state each slice's actual stage; do not let an aggregate column hide active building. Prefer existing sub-issues when a clean split already exists. Do not invent progress, percentages or ETAs. A closed issue, merge or passing CI is not release/reader verification. Attribute owner receipts; never accept your own candidate fix.
3. Walk ONE useful, non-colliding real user journey, rotating among Discover-to-detail, live charts, settled results and playoff grids. Follow the user path, interact, screenshot and READ the frame. Use the existing browser/LOOK tooling; production GETs only. Coordinate before touching Native's simulator or an ongoing held-page game walkthrough; choose a web journey if occupied. Record the named surface and outcome, not a ceremonial screenshot count.
4. For a concrete defect, search existing issues before filing. Add reproduction, reader impact, exact specimen, expected behavior and screenshot evidence; route to the existing owner. Repair stale issue descriptions, duplicates and relationships with evidence. Priority changes must follow Alex's chart-first order and explain why; no mass reprioritization, silent sprint expansion, automatic next-build inclusion or new launch blocker. Bring ambiguous product decisions to Codex. Preserve unfinished clauses when an issue is closed.
5. Update the dated local projection and the short YOUR-TURN progress/blocker text for meaningful changes, with a real timestamp. Re-read before every shared-document write to preserve concurrent edits. Do not blindly run populate.py: it overwrites newer Project values from an old baseline. Put any genuine Alex action in YOUR-TURN with exact steps. Otherwise no user interruption.
6. Save a compact pass receipt and a cursor in `~/bainluck/artifacts/shopper/` (last checked issues and URLs, what changed, journey/frame, finding or no new finding, next due). No hourly essay. Stage exactly ONE next directive with `not-before: <UTC ISO timestamp>` at least 60 minutes ahead in the first 40 lines. The runner waits without a model session. Do not sleep through the interval or self-restock rapidly. New explicit urgent inbox work can run sooner.

## Board ownership

Shopper is the routine board writer. Codex handles disputed acceptance, cross-lane bottlenecks and product decisions, and checks that upkeep is running. The diagnosis lane continues separately. Do not widen either role to fill idle time. A no-change pass is successful and quiet.

## Restart

`start-lanes.sh` and `lanes-supervisor.sh` use `lanes.conf`; shopper is a separate entry. Its default conveyor is the shared `PROGRAM-SHOPPER.md`, which points here. Before launching, check for an existing exact `lane-runner.sh ... shopper` process. The lane's own startup brief is independent of any pending integration of the launcher configuration.
