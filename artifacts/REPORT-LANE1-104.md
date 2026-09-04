# REPORT — lane1/104

**Stamped from `date`:** Fri 2026-09-04, 03:42–03:47am PT / 10:42–10:47Z.
**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.** Kickoff Thu 9/10 — six days.

**Verdict: held the line. Nothing filed, nothing merged, nothing built.** One thing changed versus 103:
production finished deploying `115dcc07`, so the D48 LOOK was stale and I re-shot it.

---

## 1. Night two — correctly NOT read (sixth consecutive session)

`date -u` → **2026-09-04T10:42:10Z**. Night two is due **2026-09-05T06:40Z**, ~**20 hours out**.
The sentinel was not polled and **no P1 was filed**. Night one (`2026-09-04T06:40:40Z`, examined
600/685, pages 6, `resumed_from: null`) remains the baseline, not a finding.

The clock-first rule has now prevented a false finding in 099, 100, 101, 102, 103 and 104.

**Grading rubric for night two carries forward unused** — it is reproduced intact in the 105 brief
(§1.1), including the correction that the deploy escape hatch is closed: the five window-pass fields
shipped in `3a1e6c9f`/`75dabbc2`, and production is now on `115dcc07`, which has both as ancestors.

## 2. CERT-906 — verified queued, not touched

```
ls runner-inbox/integrator/ | grep 047f57ba
→ 159-merge-047f57badad1306e99afecc9f78497be5df43e51.md      (bare — no suffix)
```

The integrator owns it. I did not self-merge, re-stage, or write a second directive.

**Integrator health, checked before drawing any conclusion** (brief §2, §8 trap 1):
`integrator-20260904-031445.log` was last written **03:41:12 PT — one minute before I read it.**
A lane writing continuously is working, not wedged. Its tail shows it mid-flight on the CERT-905
train: blocked on the lane lock held by ux/1064 → prepared `d6ed5167` in `/tmp/int156-cert905` while
waiting → found PR 2994's merge ref stale against a moved base → pushed the exact intended tree as
`integrator/156-cert905-merge` → **15/15 green on PR 3003** → claimed the lock → re-ran merge gates
13 and 18 → pushed **`115dcc07`** → now waiting on master CI + deploy.

906 sits behind 156/157/158 in a queue that is visibly draining. This is the fourth consecutive
session where reading the integrator's own log turned an apparent stall into a healthy lane.

## 3. Week 1 — still 18. Destructive line held for the 14th session.

Branched on `'rows' not in d` first, per the brief. Count: **18**.

Alex has not run the repair. **I did not run it, and did not use the generic
`POST /api/admin/repairs/{name}` rail to get around the `apply=true` gate** — refused by 091–104.
The ask stays where it is: `YOUR-TURN.md` DO 1. No second note written, that file not edited.

The dry run was **not** re-run: 100 ran it at 10:1xZ, and 102/103/104 have all confirmed the count is
unchanged since. Both phantoms re-confirmed byte-for-byte from the row dump:

| id | row as stored | clock it is holding | belongs |
|---|---|---|---|
| `14780595` | SF 49ers @ LA **Chargers**, 2026-09-11 00:35Z, espn `401873124` | identical to `14632820` SF@**LAR** | 2026-12-18 |
| `14781140` | Arizona @ LA **Rams**, 2026-09-13 20:25Z, espn `401873004` | identical to `14780147` ARI@**LAC** | 2026-10-18 |

Both collisions are between the two Los Angeles clubs. Unchanged from 099 onward.

## 4. D48 LOOK — re-shot, because production moved

`GET /api/health` → **`115dcc07`**. 101's photograph was taken on `75dabbc2`, so it was stale and I
re-shot rather than assume. CERT-905 is an esports tournament-name repair and the NFL page *should*
be visually identical — this proves it is.

**Artifact:** `artifacts/lane1-104-nfl-week1-both-la-duplicates-on-115dcc07-phone.png`
(`SHOT_W=390`, 780×9052, all 7 bands read).

Both duplicates are still on the page, with the same numbers 101 recorded:

| slot | real game | phantom directly beside it |
|---|---|---|
| Sep 10 5:35 PM | LA **Rams** v SF 49ers — 65/35 | LA **Chargers** v SF 49ers — 57/43 |
| Sep 13 1:25 PM | LA **Rams** v Arizona — 86/**14** | LA **Chargers** v Arizona — 83/17 |

Each phantom carries its own distinct win probabilities, its own Proj line and its own broadcast tag —
two independently scored, fully-populated events, not one row rendered twice.

**One honest limitation:** the fixed bottom nav overlay is baked into the full-page capture at
y≈4290–4400 and hides the top team row of the Sep 13 ARI@LAR card. Arizona's **14%** is visible and
matches 101's 86/14 exactly, and the DB row (`14781140`, ARI @ LA Rams) names the opponent. I did not
see the string "Los Angeles Rams" on that one card in this shot.

**No new regressions from `115dcc07`:** crests on every card, every pair sums to 100, Proj lines and
broadcast tags populated throughout, no flat or empty cards, footer intact. Page footer reads
"Showing 19 events" = 18 in-window + Bills@Lions Sep 17 (Week 2, outside the query window) — **not a
discrepancy.** Bills and Lions each appearing twice is Week 1 + Week 2.

## 5. #2869 — deliberately not commented on (fourth session running)

Nothing to add that the issue does not already say. Confirming the duplicates survived a deploy is not
new information — it would be a fifth "still there". 099, 100 and the authority lane have each already
said it; 101, 102, 103 and now 104 correctly stayed silent. Held under D35 while #2693 is open.

## 6. Nothing else done

No issues filed, no code written, no cert staged, no merge, no push to master. Per CLAUDE.md LANE
ROLES, an idle build lane is a signal, not a failure, and I did not fill it with measurement.

**105 restocked:** `runner-inbox/lane1/105-night-two-is-readable-tomorrow-morning-hold-the-line-today.md`
