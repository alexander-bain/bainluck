# REPORT — lane1/113, Friday 2026-09-04

**PILLAR: TRUTH.** **SHIP: one game can never again be stored under another game's ESPN
id — the mechanism behind a card printing the wrong score.** Kickoff Thu 9/10, six days.

Consumed: `runner-inbox/lane1/113-night-two-is-due-read-the-clock-first.md` **and**
`runner-inbox/lane1/094-friday-the-index-lands-today-d42.md` (Fable-5, 06:36am PT today —
the newer of the two and the one that set the session's work).

**One line:** the index pre-check reached **0 for the first time** — the last 5 refused
groups (11 rows) were re-asked of ESPN from production, refused again, and unstamped under
D42's Friday clause with a backup written first; PR 2776 is rebased, retitled and waiting
on one word from Alex.

---

## 1. What this session did

| | |
|---|---|
| **Contested `espn_id`s** | **196 → 0.** Measured 13:41Z (5 groups / 11 rows), 13:52Z (0), re-verified 14:00Z |
| **Write** | 11 rows unstamped on production, `rowcount=1` × 11, dyno `run.8124` |
| **Backup** | `artifacts/LANE1-113-UNSTAMP-BACKUP-2769.md`, **pushed before the write** |
| **PR 2776** | rebased onto `b53a8224`, docstring corrected, retitled, measurement commented, **full CI green at `fdd5e354`** |
| **#2769** | closed with proof |
| **Alex** | `alex-inbox/lane1-113-…` — one decision, "go 2776" |
| **Week 1** | still **18**. 23rd consecutive hold |
| **Night two** | correctly NOT read — not due until Sat 06:47Z |

## 2. The count, and why it was not 8 groups / 17 rows

Directive 094 expected #2769's eight groups. Production said **five groups, 11 rows**.
Three had cleared on their own between 09-03 and 09-04 — `401882924`, `401884813`,
`761621`. Three of the four groups #2769 predicted #1204 would clear as a by-product did
exactly that, unattended. **Re-measure a filed population before acting on its filed
number**; a week-old census of a moving population is a prediction, not a count.

The remaining five were re-asked of ESPN **through the repair rail's own dry run**, so the
question went out from a Heroku dyno and not from this sandbox (notice 7 — the "ESPN 403"
of 9/1 was sandbox egress only). All five refused again: `rows_planned: 0`,
`TEAMS_DISAGREE` 11/11, `401504210` still 502, `401873756` still no usable record.

**Asking again was worth the five minutes even though the answer did not change.** Had the
502 cleared, the rail would have resolved that group properly and two rows would have kept
a correct anchor instead of being unstamped by fiat.

## 3. The write, and why plan B was cheap rather than merely permitted

**All 11 rows are finished fixtures** — newest kickoff 2026-05-29, oldest November 2022.
`espn_sync` writes status, clock and score, and none of those has moved on any of these
rows in months, so unstamping cost no live channel. That fact is what turned D42's Friday
clause from a licence into an easy call, and it is the first thing I checked.

The alternative — keep the best-ranked row's id, unstamp the rest — is guessing which row
is the game in precisely the five cases where the authority said it could not tell. A wrong
guess there is not a smaller version of the bug; it *is* the bug.

Statement, per-row session, per-row commit, default lock wait (`events` is write-hot; a
short `lock_timeout` rolls back on every row):

```sql
UPDATE events SET espn_id = NULL WHERE id = :i AND espn_id = :v
```

The compare is **in** the write — the repair rail's own `_CLEAR_SQL`, byte for byte. A row
whose id moved between the measurement and the write matches nothing and is left alone.

Rail: one plain `heroku run:detached` (not base64 — that trips the obfuscation guardrail),
no `cd` and no path prefix. **Verified through db-query, never through the dyno's stdout**
— though the stdout *was* readable via the log-session API and agreed.

## 4. Evidence found while verifying, and it is the ship's own argument

Reading the 11 rows back after the write, two of the refused pairs carry **identical scores
on both rows while naming different opponents**:

* `14706321` (Cal State Fullerton @ UC Irvine) and `14707563` (Cal State Fullerton @ UC
  Riverside) — **both 10-7**
* `14797493` (Eastern Illinois @ TBD) and `14797677` (Arkansas-Little Rock @ Eastern
  Illinois) — **both 3-4**

That is the defect caught in the act: one game's score written onto a second fixture
through a shared `espn_id`. It is on #2769 as the closing evidence. **The ship is not
hypothetical.**

## 5. PR 2776 — what changed and what did not

Rebased onto current master; `alembic heads` → single head `uq_event_espn_id`; mutation-residue
scan clean. **Full CI green at `fdd5e354`** — 4/4 backend shards, `frontend-build`,
`search-recall`, `shard-completeness`, browser-audit fixtures, CodeQL, gitleaks, Vercel;
`deploy` SKIPPED, correct on a PR rollup.

**The first CI run failed, and it was this branch working.** Shard 3 raised
`IntegrityError: UNIQUE constraint failed: events.espn_id` in three tests of
`tests/test_anchor_schedule_sentinel.py` — a file that landed *after* this PR was parked. Its
fixture helper defaulted **every** row to `espn_id="401"` and three tests insert two and three
rows each. With `Event` declaring `uq_events_espn_id`, the SQLite test database now enforces
the same invariant production is about to get.

Fixed by giving each row its own id (`f"401{event_id}"`); the kwarg stays for any test that
needs a particular value, and no call site passed one. 32/32 pass. **None of those three tests
is about collisions** — they are about which sports the loader returns, so the shared id was
incidental. That is the branch's argument in miniature: while the schema merely *allowed* a
shared authority id, both fixtures and production drifted into one. No other test in the suite
shares an `espn_id`; all four shards are green.

**The only diff change is the docstring**, in two places that had gone false:

* "The precondition is not met today" → the precondition **is** met, with the order it
  happened in, and a pointer to the backup artifact.
* "Measured 2026-09-03T06:5xZ it prints 196" → prints **0** at 13:52Z — **and re-run it at
  release time anyway.** Zero on Friday morning is not zero at release time: nothing in the
  database enforces the invariant until this file installs it, and #2741's `|| echo` means
  a regrowth would fail the migration *silently*. `upgrade()` re-asks under
  `ACCESS EXCLUSIVE` so nothing can slip between check and build — but the operator's own
  pre-check is the only **loud** signal.

**It does not self-merge. D45: migration-class shas are attended.**

## 6. Everything else checked

* **Night two:** `date -u` = 13:37Z Friday. Not due until Sat ~06:47Z. Nothing read, nothing
  filed. §1 of directive 113 carries forward **verbatim** — it is the next session's work
  if that session runs after 06:47Z Saturday.
* **§3 sweep, with `--limit`:** six lane1 BLOCK rows (843, 846, 851, 853, 856, 870), all
  previously chased and resolved. **33 open lane1 PRs** — matches #3021 exactly, integrator's
  under D52. Nothing new. PR 2228 and PR 2776 remain the two that must not be swept, and
  2776 is no longer "deliberately parked" — it is waiting on Alex.
* **Week 1 = 18**, counted at 13:58Z. Both phantoms present: `14780595` (SF @ LA Chargers,
  Sep 10) and `14781140` (ARI @ LA Rams, Sep 13). Alex has not run lane1-067's command.
* **LOOK** (D48), `https://bainluck.com/sports/americanfootball_nfl`, phone width, after the
  write: "Upcoming 19" / "Showing 19 events" = 18 in-window + Bills@Lions Sep 17, as
  expected. Both duplicate pairs render live. **112's corrected baseline confirmed a sixth
  time**: the Sep 10 phantom **has** a Proj (25-23), the Sep 13 phantom (Rams 86% /
  Cardinals 14%) has **none**. No regression from today's write — nothing filed.
  *Honest gap: there is no matching before-shot. The write landed before the shop, because
  the surfaces it touches are 2022–May-2026 fixtures that no live page renders. Next time
  the shot comes first regardless.*

## 7. Traps this session paid

* **A filed population number goes stale.** #2769 said 8 groups / 17 rows; production said
  5 / 11. Acting on the filed number would have meant unstamping six rows that no longer
  needed it.
* **`printf '%q'` is the way to get a python program through `heroku run:detached`.** zsh
  emits `$'\n'` ANSI-C quoting, bash on the dyno accepts it, and it is plain text — unlike
  base64, which trips the obfuscation guardrail on a DB write.
* **A newer test file can be the thing your parked branch breaks.** A branch parked for two days
  is not just stale against master's *code* — it is stale against fixtures written in the
  meantime that assume the invariant it installs does not exist. Rebase then run CI; local
  focused tests would never have found this.
* **Prove the rail read-only first.** A throwaway `SELECT` one-off (`run.8599`) proved the
  quoting, the import path and the log-session read *before* a single row was written.
* **I numbered this session 114 for its first half.** The session that consumes directive
  NNN is lane1/NNN, and 113 was the directive. The artifact was renamed and the marker
  string the apply actually printed (`LANE1-114-UNSTAMP`) is recorded in the backup rather
  than tidied away — an artifact records the run, not a corrected version of it.

## 8. What the next session inherits

1. **If it is Saturday after 06:47Z, night two is the session** — §1 of directive 113,
   verbatim, unchanged.
2. **PR 2776 waits on Alex.** If he has said "go", the four-line sequence is
   `alex-inbox/lane1-066-…` and the migration's docstring; **re-run the pre-check
   immediately before the release** and hold `LANE-integrator.lock` for the push.
3. **The pre-check is a number to watch, not a box that is ticked.** Until the index
   installs, nothing stops the population growing back. One db-query, every session.
