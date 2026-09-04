# lane1/094 — the clock, not the row count; and the sentinel finally read

**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.**
Kickoff Thu 9/10 — six days.

Session ran 04:08Z–~07:00Z Fri 2026-09-04 (9:08pm PT Thu onward).

---

## 0. TL;DR

| item | state |
|---|---|
| **Week 1 count** | **18.** Alex has not run the command. Plan re-verified sound. |
| **Owed check** `LANE1-093-BONDAR-CARD-LOOK` | **Discharged as far as it can be** — see §2. Bondár is out of the draw. |
| **#2919** | **Closed with proof.** It was open-but-shipped; the commit used `fix(#2919):`, which GitHub does not treat as a closing keyword. |
| **#2953** | **Fixed**, PR #2956, guard-tested and ablation-verified. |
| **#2957** | **New.** Discover serves 1 game card in 99 items during a Grand Slam. |
| **Item One (090 sentinel)** | see §5 |

---

## 1. ITEM TWO — Week 1 is still 18

Counted first, branching on `'rows' not in d` before reading anything, per the standing trap.

**18 rows.** Both phantoms present and unchanged:

| game | event_id | espn_id | we say | ESPN says |
|---|---|---|---|---|
| SF 49ers @ LA Chargers | 14780595 | 401873124 | Sep 11 00:35Z | **Dec 18** |
| Arizona Cardinals @ LA Rams | 14781140 | 401873004 | Sep 13 20:25Z | **Oct 18** |

`14632820` (SF 49ers @ LA Rams, Sep 11 00:35Z) is the real 49ers fixture, so the duplicate sits at
the identical kickoff — which is what a fan actually sees.

**The plan is re-verified sound.** Dry run at `limit=20`:
`authority_moves_us: 2, teams_disagree: 0, agrees: 18`, both movers on page one, deltas 98.03d and
34.99d. **Alex's existing command needs no reissue.**

I did not run the apply and did not build a way around the gate. The generic repair rail
(`POST /api/admin/repairs/{name}`, `_check_admin_secret` only) remains the available bypass and
remains refused — 091 refused the `heroku config` path, 092 direct-Celery, 093 and 094 this one.
The unreconciled authority question (D51 + `YOUR-TURN.md` §1 say the Week-1 fix is lane1's; the
mechanism says it is not) is still open in `NOTE-TO-FABLE-FROM-LANE1-092-...`. **One line, as
instructed — no fourth note.**

---

## 2. The owed post-deploy check, discharged

CERT-879 granted its token with a LOOK at Anna Bondár's card owed **when it next appears**.

**It cannot appear: she is out of the tournament.** She lost to Madison Keys today (event
`15300682`, completed 18:08Z, Keys 2–1). Waiting for her card is waiting for a card that will not
be drawn this fortnight. So I discharged the check's *intent* on three legs instead, and I am
explicit that leg 1 is not her:

**(a) The render works, photographed.** `/sports` Live Now, phone width, 04:24Z: a US Open card —
Quentin Halys 12% / Alexander Zverev 88% — draws **both players' photographs**, while the NCAAF
card directly above it draws `A`/`BB` initials and the MLB cards draw club logos. The tennis card
is no longer the one falling back.
`artifacts/lane1-094-shots/sports-live-now-usopen-faces.png`.

**(b) The four newly-resolved names all answer**, run against the shipped register at master's code:

| name | face | flag | URL check |
|---|---|---|---|
| Anna Bondár | ✅ | 🇭🇺 | 200 image/jpeg **42,529 B** |
| Iva Jović | ✅ | 🇺🇸 | 200 image/jpeg 38,894 B |
| Federico Cinà | — flag only, as registered | 🇮🇹 | 200 image/png 3,316 B |
| JJ Wolf | ✅ | 🇺🇸 | 200 image/jpeg 59,796 B |

Every URL fetched, not merely present in a payload — a URL in a field is not a face on a screen.

**(c) The accent renders.** The event page prints **"Bondár"** correctly.

**What is honestly NOT proven:** no accented, newly-resolved player was on screen tonight, because
Bondár is eliminated and Jović's match had finished. Leg (a) is Zverev and Halys, both of whom were
almost certainly inside the pre-fix 239. So: the *path* is proven live, the *four names* are proven
at the resolver and at the CDN, and the two are not joined by one screenshot. Worth 60 seconds for
095 if Jović draws again (she has a fixture `15304374`, Sat 00:00Z).

---

## 3. #2953 — the bound that could not hold

**Filed by 093 as a one-liner. It is not one, and the measurement is why.**

`DEFAULT_LIMIT = 100` rested on a docstring claiming `~0.2s` per ESPN call. Timed against
production:

| limit | elapsed | examined |
|---|---|---|
| 10 | 5.66s | 10 |
| 20 | 11.52s | 20 |
| 40 | 23.32s | 40 |

Marginal cost **0.589 s/row**, near-zero fixed cost — **3× the assumed figure**. 100 rows ≈ 59s
against a 30-second router. On `apply` that is the worst shape a destructive endpoint can have:
killed *after* the writes commit.

The docstring already asserted the bound "is a *wall-clock* bound before it is anything else." It
was not one — **nothing in the file read a clock.** A row count was standing in for a duration.

### Shipped

- `DEFAULT_LIMIT` 100 → **25** (~15s), docstring carrying the measured cost.
- **`EXAMINE_BUDGET_SECONDS = 18.0`** ends the fetch loop on the clock, so *any* `limit` is
  router-safe. Mirrors the `stopped_by`/deadline idiom already in `anchor_schedule_sentinel`.

Three ways a deadline goes wrong, all closed:

1. **Counting rows it never asked about.** The tail is dropped from the population, not summarised.
   The authority agrees with most rows, so a leaked tail lands in `agrees` — the bucket that reads
   as an all-clear.
2. **A cursor that skips the tail.** `rows` is trimmed to the answered prefix, so `next_cursor`
   names the last row **answered**, not the last row **loaded**. Otherwise the sweep steps over the
   gap permanently while every field looks healthy.
3. **A count outranking evidence.** `has_more` ORs in `budget_cut_tail`, because `remaining` is a
   separate COUNT that can go stale by a settle.

The operator line no longer prints "raise limit above N" for a page the clock ended — that advice
makes the next call time out.

### Guards — ablation-verified, not just green

11 tests, clock injected rather than slept on.

| ablation | result |
|---|---|
| remove the deadline | **5 red** |
| remove the row trim | cursor-identity test red |
| remove `or budget_cut_tail` | stale-count test red |

**One of my own guards was vacuous and I caught it by ablating.** The stale-count test first called
*uncursored*, where `remaining` is just `eligible` — it passed with the fix removed. `remaining` is
only its own count on a cursored call. Fixed, and the docstring now says why, because the next
person will make the same mistake.

**The old guard is the real lesson:** `assert DEFAULT_LIMIT * 0.2 < 25` carried its own unverified
constant, so it stayed green while the thing it described stopped being true. A test that supplies
its own facts cannot fail when the world moves.

### Gates

155 passed (`test_anchor_schedule*`, `test_reconcile_anchor_schedule*`,
`test_repair_index_note_scope_2839`, `test_startup`) · residue **CLEAN** (550 needles) · ruff clean ·
black applied **to my lines only** — the file carries 7 pre-existing non-conformant hunks and
reformatting wholesale would bury the diff (black is not a CI gate here).

No migration, no data write, no schedule change. Backend-only → bus-graded.

---

## 4. #2957 — the fix shipped onto an empty surface

D48 mystery-shop of my own domain turned up something bigger than the shop.

`/api/feed` paged to exhaustion (`total: 99`): **futures 69, concept 14, bundle 11, tournament 4,
event 1.** One game card in ninety-nine, and **zero tennis** — during the US Open, at 9:20pm PT.
Page one is cycling futures, one MLB game, and "Will the U.S. confirm that aliens exist?".

Available in the same window: 106 soccer live, 8 MLB live, 8 tennis_other live, **13 US Open
scheduled**. The one event card scored **35** — the event-demotion cap exactly, against futures at
79. Games are not losing on merit; they are capped, and the cap is the ranking.

This is CLAUDE.md priority #2's named failure ("game events are never capped into an empty tab —
#1091's lesson") and the second direction of gotcha #43.

**It is also why #2919's fix has nearly no surface**: faces are attached in `routes/feed.py` only,
so they ride feed-built cards — and there are no tennis feed cards to ride.

Filed unclaimed; Discover ranking is not lane1's.

---

## 5. ITEM ONE — the 06:40Z sentinel

Session started **04:08Z**, which is *before* the first firing (06:40Z). Ran `date -u` first, as
instructed. Rather than restock a fifth time, **this session stayed alive to read it** — the loop
091→092→093 repeated precisely because each session started in the dead window and handed the
question on.

093's detached watcher (`lane1-090-anchor-sentinel-watch.detached.sh`, PID 43854, PPID 1) was
verified alive at 04:23Z, sleeping to 06:43Z. It survived its session correctly.

**FINDINGS: this window ended before 06:40Z and §5.1 was never written.** The continuation window
read the firing and discharged Item One in full — see **`REPORT-LANE1-094B.md` §1**: fired 06:40:40Z,
`terminal: partial`, `stopped_by: deadline`, 6/12 pages, 600/685 examined, one deduped issue filed
(**#2978**), nothing closed on a partial sweep, and **both Week-1 phantoms re-derived independently**.

---

## 6. Traps this session added

- **`gh issue list --search` matched my own substring.** Filtering feed cards on `"ond"` returned
  three "hits" that were `Second Round` and friends — zero were Bondár. Substring collisions cost me
  a wrong conclusion for two minutes; the same class as the residue scan's Pass B.
- **`fix(#NNNN):` does not close a GitHub issue.** Conventional-commit scope, not a closing keyword.
  #2919 shipped 9/3 and sat open. **Check `gh issue view` after any merge that claims to close one.**
- **The event page is `/events/<id>`, not `/event/<id>`.** `/event/` renders a plausible
  "Event not found" card rather than a 404 — an empty render that looks like an answer.
- **`remaining` equals `eligible` on an uncursored call.** Any test asserting on `remaining` without
  a cursor is testing `eligible` and will pass with the code removed.
- **`participant_images_for_event` is called from `routes/feed.py` and nowhere else.** Any surface
  not built from the feed payload — league sub-pages, event pages — will not show faces no matter
  what the register holds. Check the consumer before judging a render a regression.
- Standing and re-confirmed: `look.sh` defaults to 1280 wide, use `SHOT_W=390 SHOT_H=844`; crop with
  PIL before `Read` (tonight: 16,642px and 17,996px tall); `cd backend &&` persists into later Bash
  calls; `area:matching` is not a label.
