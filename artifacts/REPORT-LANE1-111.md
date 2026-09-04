# lane1/111 — Fri 2026-09-04, 05:06–05:12am PT (12:06–12:12Z)

**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.**
Kickoff Thu 9/10 — **six days.**

Branch `lane1/099-artifacts`. Production `6c6a9277` throughout (moved from `e84e3f4e`
before the session started; native/007 merged 11:46Z).

---

## Verdict in one line

Night two not due; Week 1 still 18 (**21st** session holding the destructive line); CERT-911's
token is granted and the integrator owns the merge; §3 triage surfaced one candidate and it
was already resolved. One real contribution: the CERT-911 follow-up now has a durable home.

---

## 1. Night two — NOT due. Twelfth-plus consecutive correct hold.

`date -u` = **2026-09-04T12:06Z**. Readable from ~06:47Z **Sat 9/5**. Not polled, nothing filed.

Night four (Mon 9/7) remains the first night that can close #2978.

**Hazard still unowned and still worth watching:** the sentinel is live 06:40Z–~06:46Z and under
D45 every master merge cycles `worker-heavy`. The integrator merged native/007 at 11:46Z and is
actively draining a queue right now — nowhere near the window, but the queue is *busy*, which
raises the odds that a Saturday-morning merge lands inside it. Not pre-emptively asking anyone to
pause. If night two comes back missing, check the merge timestamp against the window first.

## 2. CERT-911 — GREEN, token granted, correctly NOT merged by this lane

Ledger `CODEX-CERT-LOG.md:673`. Both merge gates re-run at 12:07Z:

- **gate 13** — `grep d12caafa… | grep -q 'TOKEN GRANTED'` → **PASS**
- **gate 18** — `grep -nE 'supersedes:?[[:space:]]*\`?CERT-911\b'` → **empty, PASS**

**Still did not merge, and 112 should not either.** The token carries
**"EXACT CURRENT-MASTER FULL CI REQUIRED BEFORE MERGE"**, and it is unsatisfied — measured, not
assumed:

```
PR2900 state=OPEN mergeable=MERGEABLE mergeState=CLEAN
head=d12caafa22ad66d094db96b09c40bdfbb18343e2
base=e84e3f4ea2aacbe8b6f6187b5ac31708ce20afad     <-- master is 6c6a9277
```

The base is pinned to the *old* master. A base move does not re-trigger PR CI. Satisfying the
condition means rebasing, which moves the sha away from the granted one — and a granted token
freezes the branch.

**Confirmed the brief's disjointness claim rather than inheriting it:** native/007 (PR 2990) is
exactly four files, all `ios/**` Swift. Zero overlap with PR 2900's backend files. So the merge is
low-risk — but low-risk is not the named condition, and arguing a condition away is not satisfying it.

**The integrator owns it and is demonstrably alive.** Directive
`162-merge-d12caafa….md` is bare (queued). Log mtimes: 161 consumed 05:05 (merged native/007,
deployed), 164 rewritten 05:08. Three minutes before the check — working, not wedged.

## 3. The §3 triage step — ran it, and it earned its place

110 added this because nine sessions missed live work. It surfaced **two** things the brief
did not list:

**(a) CERT-870 / lane1/088 (#2919) — a lane1 BLOCK at 01:15Z, newer than CERT-853.** Looked like
exactly the failure mode 110 described. It is **not** live work: #2919 is **CLOSED** (04:48Z) and
`lane1/088-merge-train` **PR 2945 is MERGED**. The repair landed via the merge train. Resolved,
not missed.

**(b) Three open lane1 PRs the brief never mentioned** — all `CONFLICTING`, all last touched 9/2:

| PR | branch | state |
|---|---|---|
| 2669 | lane1/049-polymarket-resolved-status-newest-first | CONFLICTING, 9/2 |
| 2640 | lane1/046-identity-keys | CONFLICTING, 9/2 |
| 2613 | lane1/q506-a-final-nobody-reported-is-not-a-final | CONFLICTING, 9/2 |

Two days stale, not the seven that triggers the integrator's D52 rescue sweep. **Left alone —
but 112 should re-check the clock on them: they cross the 7-day line around 9/9.** Do not rebase
them speculatively; D52 gives that sweep to the integrator.

The brief's two known PRs are unchanged: **2900** live (§2), **2776** correctly parked until the
unique-index pre-check reaches 0 — **do not loosen the index (D42)**.

## 4. Week 1 = 18. Twenty-first session.

Driven from a python file, not inline `curl -d` (shell quoting mangles this payload), and
branched on `'rows' not in d` first.

Both phantoms re-confirmed byte-for-byte at 12:07Z:

| id | matchup | espn_id | stored clock | belongs | clock stolen from |
|---|---|---|---|---|---|
| `14780595` | SF @ LA **Chargers** | `401873124` | `2026-09-11 00:35:00+00` | 2026-12-18 | SF@LAR (`14632820`) |
| `14781140` | ARI @ LA **Rams** | `401873004` | `2026-09-13 20:25:00+00` | 2026-10-18 | ARI@LAC (`14780147`) |

18 means Alex has not run the attended repair. **Did not run it. Did not route around the gate.**
The generic rail `POST /api/admin/repairs/{name}` is gated on `_check_admin_secret` only and is a
real bypass — refused by 091–111. The ask is `YOUR-TURN.md` DO 1; no second note written, that
file not edited. Dry-run not re-run (100 ran it; 102–111 confirm the count is unchanged).

## 5. D48 LOOK — re-shot on `6c6a9277`, no regressions

Production had moved off 110's `e84e3f4e` baseline, so the shot was owed. `SHOT_W=390`,
`/sports/americanfootball_nfl`, PNG Read.

| slot | real game | phantom directly beside it |
|---|---|---|
| Sep 10 5:35 PM | LA **Rams** v SF — 65/35, Proj 26-22, Netflix | LA **Chargers** v SF — 57/43, Netflix, **no Proj** |
| Sep 13 1:25 PM | LA **Chargers** v Arizona — 82/**18**, Proj 29-18, CBS | Arizona — **14%**, CBS, **no Proj** |

"Upcoming 19" / "Showing 19 events" = 18 in-window + Bills@Lions Sep 17 — **not a discrepancy.**
Probability drift is ordinary market movement. Both phantoms still sit directly beside their real
twins; the ship is still unshipped and still visible to a 49ers fan.

**Sep 13 assignment confirmed a FOURTH time** (108, 109, 110, 111): `14780147` ARI @ LA **Chargers**
is the real game. 104's table had it swapped. **Do not "correct" it back.**

**Capture note, third data point:** the baked-in bottom nav's y offset moved *again*. 108 → hid the
real Sep 13 card; 110 → hid the phantom; 111 → hid the phantom's "Los Angeles Rams" line
specifically. **Find the nav, never assume its offset, never reuse a prior crop.**

## 6. What this session actually contributed — #2879 comment

The one gap worth closing. CERT-911 raised a non-blocking follow-up,
`LANE1-086-MIXED-SPORT-COLLISION-RECEIPT`, which existed **only** as prose inside a ledger row —
and the §3 lesson is precisely that ledger rows go unread.

Checked first that it had no home: no issue matches the follow-up name or its substance
(searched three ways). Then checked the home would survive: PR 2900 says "Closes the lane1 half of
#2879" in **prose only** — `closingIssuesReferences` is **empty**, so **#2879 stays OPEN** after the
merge. Correct place.

**The substance, read out of the actual diff rather than paraphrased:**
`_find_statpal_row_in_sport` deliberately does not write `WHERE sport_id = :x`; it fetches and
compares in Python so the refusal can be *seen*, because D55 forbids a collision that silently
no-ops. That decision is right and pinned by the cross-sport regression. But the refusal's only
output is a `logger.warning` — **a log line is not a receipt.** Nothing durable counts how often a
cross-sport StatPal collision is refused, or on which fixtures.

Filed as a comment, **not built** (D35), unowned and unclaimed:
`#2879#issuecomment-5540241334`.

**If the bus attacks the Python-comparison choice** (it is invited to in the block), the answer is
in that comment: converting it to a SQL predicate deletes the very signal the follow-up wants to
record, so ask where the D55 receipt then lives.

## 7. #2869 — eleventh consecutive correct silence

Nothing new to say. "It survived another deploy" is **not** new, and 104–111 have each considered
exactly that and stayed silent — including across two real mid-session deploys now. Held under D35;
which rail wrote the false `commence_time_source = 'espn'` stamp is diagnosis, and LANE ROLES gives
diagnosis to the measurement lane. Parked.

Discarded theory unchanged: the rows are **not** frozen by the parity rule at
`event_registry.py:82` — `event_registry.py:376` does pass `claim_is_same_record(...)`.
**Do not re-chase it.**

## 8. Traps confirmed or added this session

- **§3 is worth its 30 seconds and it is not a formality.** It surfaced CERT-870 and three
  unlisted PRs in one query. Both turned out benign — *that is the check working*, not the check
  being useless. Run it in 112.
- **A cert FOLLOW-UP is as losable as a BLOCK.** 110's finding generalizes: anything whose only
  record is prose inside a ledger row is invisible to every normal triage query. Give it an issue.
- **"Closes X" in a PR body is prose, not a closing keyword.** Check
  `gh pr view N --json closingIssuesReferences` before assuming an issue will or won't survive a
  merge — the two disagree here.
- **`gh issue list --search` full-text is weak on ALL-CAPS hyphenated tokens.** Searching
  `MIXED-SPORT-COLLISION-RECEIPT` returned three unrelated issues. Search the *substance*
  (`statpal_fixture_id sport`) as well before concluding nothing is filed.
- **A directive file that is bare but whose siblings' mtimes are minutes old is a working queue,
  not a stall.** 164 was rewritten at 05:08, three minutes before the check.
- All of 110's traps re-confirmed: python-file db-query, nav offset instability, `--author '@me'`
  is not a lane filter, `git -C` for every git call.
