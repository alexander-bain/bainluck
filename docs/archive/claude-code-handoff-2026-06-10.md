# Claude Code handoff prompt — June 10, 2026

Copy everything between the lines into Claude Code running in `~/bainluck`.

---

You are picking up the output of a two-document strategy cycle plus a production calibration audit. Your job this session is **tracker and docs execution only** — file issues, post comments, fix stale docs, and run two time-sensitive read-only queries. Do NOT start the engineering work itself this session (no changes to `backfill_winners.py`, `feed.py`, etc.); the point is to convert finished analysis into an execution queue other sessions can work.

## Context — read these first, in this order

1. `docs/unified-strategy-2026-06.md` — the strategy document. Pay particular attention to §1.3 (doc-drift ledger), §5.4 (Correctness Console), §6 (labeling/kid-labeler), §8 (correctness state with verified issue figures).
2. `docs/issue-roadmap-2026-q3.md` — the execution plan derived from it. §3 contains **paste-ready issue bodies (NEW-1 … NEW-8, with 2a/2b, 5a/5b, 6a/6b splits) and extend-comments (E-596, E-678, E-804, E-805, E-826, E-841, E-454, E-490)**. Treat those texts as verbatim sources — do not rewrite them, only paste.
3. `docs/github-issues-export.json` — a June 9 snapshot of the tracker used to write the docs. You have live `gh`; the snapshot is for reference only. If live state contradicts anything below (an issue closed since June 9, labels changed), adapt and note it in your commit message.
4. New context NOT yet in any repo doc: on June 10 Alex ran `heroku run -a bainluck python3 scripts/audit_golf_hockey_calibration.py`. Findings: golf MCE 16.77pp, hockey 21.05pp on 82,050 included outcomes. Hockey is dominated by one measured mechanism (M5, fake untraded opening asks on KXNHLPTS/AST/GOAL/FIRSTGOAL ladders — counterfactual MCE without it: 7.16pp). Golf is NOT explained by the script's detectors (<1.5pp attributed): its high buckets show a complement signature (pred+actual≈100 on KXPGAR1TOP5 96.8→2.2, KXDPWORLDTOURR1LEAD 95.0→2.9, KXPGAR2LEAD 89.2→0.8, KXDPWORLDTOUR 92.7→2.1) suggesting wrong-side price capture and/or systematically-false winners under an `api_settlement` tag (that cohort: n=952, pred 79.3, actual 36.3). The script's "M1: 0 affected" and "M3: 0 affected" lines are detector blind spots, not clean bills: M1 only fires on `resolution_source IS NULL` (`backend/scripts/audit_golf_hockey_calibration.py:339–341`) and M3 only on yes/no-named outcomes with a stored `kalshi_result` (`:347–353`) — player-named outcomes are structurally invisible to both. The 80–90 and 90–100 golf buckets are only n=336 and n=380, so a few hundred corrected rows fix the visible curve. Kalshi settlement data ages out after ~2–3 months (gotchas #35/#101), so the golf re-fetch is time-sensitive.

## Ground rules for this session

- Follow `docs/github-workflow.md` exactly: canonical labels only (`area:*`, `type:*`, `priority:*`, routing); every created issue gets a `Backlog source` section; backlog edits land in the same commit as the tracker changes they describe.
- Use `python3 scripts/claim_issue.py <N> "In Progress" --owner "Claude Code handoff session"` before editing anything tied to an existing issue; release to "Review / Verify" when the step is done.
- This session touches docs and the tracker only, so the mandatory pre-push checks are light — but if you edit ANY `.py` file (you shouldn't, except docstrings in NEW-8), run `cd backend && python3 -m pytest tests/test_startup.py -v` before pushing. Use `git -c push.default=simple push origin master` (gotcha #83 — a bare `git push` may be policy-blocked).
- For production queries use the established pattern: `source ~/.claude/.env && curl -s "$BAINLUCK_API/api/admin/query?secret=$ADMIN_TOKEN&sql=..." | python3 -m json.tool` (CLAUDE.md "Production API access").

## Step-by-step checklist

### Step 1 — Post the audit findings to #738 (5 min)

`gh issue comment 738` with exactly this body:

> Production audit June 9 (`scripts/audit_golf_hockey_calibration.py`, 82,050 included outcomes): golf 16.77pp / hockey 21.05pp. **Hockey:** M5 (opening-only fake asks on PTS/AST/GOAL/FIRSTGOAL ladders) explains 13.9pp — counterfactual MCE 7.16. Fix = #827 + #683/#651; expected delta is measured, not estimated. **Golf:** current detectors explain <1.5pp. High buckets show a complement signature (pred+actual≈100 on KXPGAR1TOP5/R1LEAD/R2LEAD/DPWORLDTOUR) and `api_settlement`-tagged rows gap −42.9 on n=952 → suspect wrong-side price capture and/or systematically-false winners under a settlement tag. Action 1 (time-sensitive, gotcha #35): 20-row manual spot-check of golf api_settlement rows vs Kalshi UI + settlement re-fetch for these series before the data ages out. Action 2: M2 samples still show lb=50 truncation — re-check #697's close (gotcha #90: closed without measured proof?). Detector gaps: M1 misses mistagged (non-NULL) losers; M3 can't see player-named outcomes — add an M6 complement-signature detector and an M3b that joins settled-events results by outcome ticker (gotcha #105 formats) instead of name.

### Step 2 — Elevate #827 to the headline hockey fix (5 min)

`gh issue comment 827`:

> June 9 audit generalizes this beyond the MLB example: hockey MCE is 21.05pp and the M5 counterfactual (excluding opening-only fake-ask outcomes) is 7.16pp — a measured ~14pp delta from this one fix. Failing prefixes: KXNHLPTS (−59.8), KXNHLAST (−63.5), KXNHLGOAL (−72.0), KXNHLFIRSTGOAL (−83.8); KXNHLTOTAL and KXNHLGAME are healthy. Scope note: apply the `volume_fp=0` exclusion across all sports' threshold ladders, not only MLB TB. Verification: re-run `scripts/audit_golf_hockey_calibration.py` post-fix; hockey high buckets (60–100) should collapse toward the 7pp counterfactual; also `GET /api/calibration` per-category MCE.

If #827 lacks `priority:p1`, leave as-is (it has it per the June 9 export); do not invent labels.

### Step 3 — Check #697's closure (10 min)

`gh issue view 697`. The June 9 audit's M2 samples still show `lb=50` truncated leaderboards (Hero Indian Open, Volvo China Open, the Memorial). If #697 was closed claiming leaderboard re-fetch was fixed, reopen it with a comment citing those sample rows, or — if reopening is wrong because the fix shipped after those tournaments resolved — comment on #738 instead noting the residual truncated population (3,525 outcomes, M2 cohort) needs a one-time historical re-fetch. Use your judgment after reading #697's close reason; cite gotcha #90 either way.

### Step 4 — Run the two time-sensitive read-only queries (15 min)

These inform the spot-check Alex must do; you only gather rows.

4a. Pull 20 golf api_settlement spot-check candidates:
```sql
SELECT fo.id, fm.external_id, fm.name, fo.name AS outcome, fo.calibration_probability,
       fo.opening_probability, fo.is_winner, fo.resolution_source
FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id
WHERE fm.llm_sport_category='golf' AND fo.resolution_source='api_settlement'
  AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.65
ORDER BY fo.calibration_probability DESC NULLS LAST LIMIT 20
```
via the `$BAINLUCK_API/api/admin/query` endpoint. Post the resulting table as a comment on #738 titled "Spot-check candidates (needs-user: verify each against Kalshi UI)". Flag any row where `calibration_probability + (actual win expectation) ≈ 1` pattern is visible.

4b. Run the #806 inflow check: `heroku run -a bainluck python3 scripts/audit_pass2_inflow.py` and post the JSON output as a comment on #806. If inflow > 0 on any recent day, say so prominently — it changes NEW-1's readiness.

### Step 5 — File the new issues (45 min)

Create each issue below using the EXACT body from `docs/issue-roadmap-2026-q3.md` §3 (they include Problem/Scope/Acceptance/Verification/Files/Relationships/Backlog-source). Use `gh issue create --title "..." --label "..." --body-file <(...)` or a temp file per issue. Labels are specified in each §3 entry — canonical only.

Order and dependency wiring (use "Depends on #N" / "Blocks #N" lines in bodies, and add the `blocked` label where stated):

1. NEW-2a (status endpoint timeout) — no deps
2. NEW-2b (Correctness Console) — blocked by NEW-2a's new number
3. NEW-1 (resolution authority ladder) — blocked by #806; **add one precondition line to its body before filing**: "Precondition (June 10 audit): before enshrining `api_settlement` as the top rung, the golf api_settlement spot-check on #738 must confirm the tag is trustworthy — see #738 comments."
4. NEW-3 (blend baseline) — `needs-user`
5. NEW-4 (kid labeler) — blocked by #671
6. NEW-5a (cold-start fast-lane + probe) — no deps
7. NEW-5b (chip-row card) — blocked by NEW-5a's number
8. NEW-6a (persist story_key) — no deps; note it is the quarter's only migration
9. NEW-6b (discover_llm v2) — blocked by NEW-6a's number
10. NEW-7 (election regex dead code) — `good-first-agent-task`
11. NEW-8 (doc-drift PR) — `good-first-agent-task`

After creating all 11, record the real numbers: edit `docs/issue-roadmap-2026-q3.md` replacing every "NEW-x" placeholder with the real "#NNN" (§2 plan, §3 headers, §4 critical path, §6 backlog deltas).

### Step 6 — Post the eight extend-comments (20 min)

Paste the E-* texts from roadmap §3 verbatim as comments on: #596, #678, #804, #805, #826, #841, #454, #490. For #804 and #490 the comments contain decisions for Alex — after posting, ensure those issues carry `needs-user` (both already do per the export; verify live).

### Step 7 — Tracker hygiene (10 min)

- #824 (CI alert): check whether master's current head has a green CI run (`gh run list --branch master --limit 5`). If green, close #824 with the standard alert-intake closing comment ("superseded — head is green as of <sha>"); no backlog edit needed (workflow rule, `docs/github-workflow.md:105`).
- #803 (KXNBAMENTION): do NOT close unilaterally. Comment: "Roadmap recommendation (docs/issue-roadmap-2026-q3.md §1): accept-as-unresolvable under the authority ladder and close as absorbed by #754, OR relabel priority:p3. 298 outcomes = 0.4% of the #754 population. Decision: Alex." and add `needs-user` if absent.

### Step 8 — Backlog + doc edits, one commit (30 min)

Apply `docs/issue-roadmap-2026-q3.md` §6 exactly — (a) through (g) — substituting the real issue numbers from Step 5. This includes fixing the two stale lines (#482 → `[shipped]`, #445 line replaced by the #678 line) and adding the new Active Execution Queue lines.

Then execute NEW-8's scope in the same working session IF time permits (it is docs-only and you just filed it): the 9 doc-drift ledger rows from `docs/unified-strategy-2026-06.md` §1.3 — CLAUDE.md category base scores (reference `CATEGORY_BASE_SCORES` instead of literals), the "exact-string only" cross-source paragraph, the interestingness "scaffold" paragraph, the demotion-exception thresholds, the "7 phases" line, `event_registry.py:11,185` "±4h" docstrings (docstring-only change — run the smoke test after), the backlog App Store + #482 lines (already done above), and gotcha #80's allowlist text if NEW-7's investigation will change semantics (if unsure, leave gotcha #80 and note it in NEW-7). Claim NEW-8's issue number first, close it on completion with the verification noted in its body: `python3 scripts/audit_backlog_github_sync.py --dry-run` clean for touched lines + grep shows the stale literals gone.

Commit message suggestion: `Tracker + docs sync: file Q3 roadmap issues, post audit findings, fix doc drift (roadmap docs/issue-roadmap-2026-q3.md)`. Push with the gotcha #83 form. Vercel/Heroku are unaffected by docs-only commits but CI will run — that's fine.

### Step 9 — Report back

End by printing for Alex:
1. The issue-number mapping (NEW-x → #NNN).
2. The #806 inflow result (tap open or closed?).
3. The 20 golf spot-check rows and a one-line instruction: "open each market on kalshi.com and record whether our is_winner matches — this is the #738 acceptance item and it's aging out."
4. The three decisions waiting on you: NEW-3 go-ahead (brief prod blend on/off), #804 path choice (create small-conference events vs accept-unresolvable), #803 close-or-p3. Plus the standing #678 device-verification checklist.

## Explicitly NOT this session

- No code changes beyond NEW-8's docstrings. No `backfill_winners.py`, `feed.py`, `polymarket.py` edits — those are owned by the issues you're filing, claimed one at a time per the Parallel Work Protocol (`tasks/backfill_winners.py` is Red-zone serialized across NEW-1/#754/#762/#818/#827).
- No closing of #754/#804/#805 buckets — they close on measured production evidence only (gotcha #90).
- Do not run the NEW-3 blend flip — it needs Alex's explicit go-ahead.

---

End of prompt.
