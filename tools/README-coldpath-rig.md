# The cold-path rig

Five tools that together answer "will this frontend change make the landing page's first card
arrive sooner, and by how much?" — with a real browser, on a real build, in milliseconds and bytes.

Landed by **LAT-P214**. Before that the rig lived on two unmerged program branches and in `/tmp`,
and four consecutive cycles (P208, P209, P211, P213) each spent part of a session re-deriving it —
seven re-derivations in total, filed as `alex-inbox/latency-043`. The rig cannot land behind a cut
that does not touch it, so it is landed on its own.

| tool | answers |
|---|---|
| `entry-bytes.mjs` | how many bytes is the landing page's **entry set**, chunk by chunk? |
| `entry-chunkmap.mjs` | **which source modules** are in each of those chunks? |
| `entry-graph.mjs` | how many **eager importers** does a module have — i.e. can it be split at all? |
| `arm-proxy.mjs` | serve **two builds** behind one origin so an A/B can switch between them |
| `cold-load.mjs` | measure a **cold load** in a real headless Chromium: `ttfc`, wire bytes, chunk list |

---

## The one metric rule

**Grade the landing page on `ttfc` (time to first card), never on FCP or LCP.** Six independent
measurements say the two chrome metrics lie on this page, because every card is client-rendered and
the server HTML is nav chrome plus a skeleton grid. The cleanest of the six (LAT-P211): a diff whose
real effect was **`ttfc` −76.7 ms at U = 100 % with zero overlap between the arms** registered as
**FCP −2.0 ms, U 54 %, p 0.75**. LCP is worse still — its *mean* moved **+308 ms** (a large false
regression) on the same diff whose median moved −90 ms, because one outlier poisons it.

Do not go shopping for a quieter proxy either. `stage.scriptEnd` looks purpose-built for an
entry-chunk cut and **inverts**: it closes on the *last* script, and a split *adds* a chunk. Any
"all scripts done" metric punishes a split however good it is.

**Grade on `ttfc`, or grade on bytes.**

## What a byte cut is worth, measured

| brotli cut | result |
|---|---|
| 7.41 kB | −76.7 ms, U=100 %, p=7.1e-05, zero overlap (n=11+11) |
| 7.0 kB | −78 ms, arms disjoint |
| 2.6 kB | −18.0 ms, U=81 % (n=12+12) |
| 2.40 kB | flat null, U=60 %, p≈0.45 (n=12+12) |
| 1.26 kB | unresolved, U=72 %, p≈0.073 (n=12+12) |
| 0.77 kB | not claimable (n=8+8) |

* **Above ~4 kB** — n=12+12 resolves, emphatically.
* **~1.5–4 kB** — budget n=12+12 up front; expect direction without magnitude.
* **Under ~1.5 kB** — do not grade in milliseconds at all. Ship or drop on bytes.

**Print your own sd per arm, and never pool it.** LAT-P213's two arms differed by two orders of
magnitude on the same 16 runs — control 502.6 ms vs treatment 5.4 ms, from a single outlier. A quiet
treatment arm is not evidence that the control arm was quiet.

---

## Recipe: grading a built diff

```bash
F="$PWD/frontend"

# 0. always build BOTH arms with the same dummy Firebase env, or UserMenu renders null and the
#    two arms emit identical HTML.
export NEXT_PUBLIC_FIREBASE_API_KEY=dummy-api-key \
       NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=dummy.firebaseapp.com \
       NEXT_PUBLIC_FIREBASE_PROJECT_ID=dummy-project \
       NEXT_PUBLIC_GOOGLE_CLIENT_ID=dummy-client-id

# 1. control
(cd frontend && npm run build)
node tools/entry-bytes.mjs frontend/.next/server/app/index.html frontend/.next
rm -rf /tmp/arm-control && mkdir -p /tmp/arm-control
cp -R frontend/.next/server/app /tmp/arm-control/app-html
cp -R frontend/.next/static     /tmp/arm-control/static

# 2. apply the diff, rebuild, same copy into /tmp/arm-treatment

# 3. serve both behind one origin. Port 3000 is not a preference — the API's CORS allowlist
#    names it and nothing else.
ARM_FILE=/tmp/cold-arm CONTROL=/tmp/arm-control TREATMENT=/tmp/arm-treatment \
  PUBLIC_DIR=frontend/public PORT=3000 node tools/arm-proxy.mjs &

# 4. the count is PER ARM: 12 => 24 runs
COLD_THROTTLE=3g COLD_CPU=4 COLD_ARM_FILE=/tmp/cold-arm \
  node tools/cold-load.mjs http://127.0.0.1:3000 12 out.json

# 5. re-derive every run's arm from the SERVED BYTES in out.json before believing it.
```

**Step 5 is not optional, and `app/page-*.js` is the wrong discriminator** — on a layout-only diff
that hash is identical in both arms. Use whichever entry chunk your diff changed, and assert the
*other* arm's hash is **absent**, not merely that yours is present. Smoke-test both arms with one
curl each through the proxy before spending the runs.

Reading `out.json`: the top-level key is `results` (not `runs`). URLs live in `results[].crit[].n`,
`results[].slowest[].name` and `results[].wireAboveFold.items[].url`.

**Filter `items[].kind === 'script'` before quoting any wire number.** `wireAboveFold` totals
include the Pexels hero image, which varies by ~21 kB run to run. Script-only wire is deterministic
(sd = 0 across every cycle that has measured it). And do not panic at the total-wire column
mid-run — LAT-P213's first five runs showed a systematic-looking +37 kB regression that was hero
noise; a *control* run showed the same value by run 9.

## Recipe: sizing a proposal before you build it

```bash
F="$PWD/frontend"
node tools/entry-graph.mjs --root "$F" --validate                 # trust nothing until this passes
node tools/entry-graph.mjs --root "$F" --list > /tmp/eager.txt    # the eager module set
node tools/entry-graph.mjs --root "$F" --target lib/yourModule.ts # THE EDGE COUNT — check it first
sed -n '2,$p' /tmp/eager.txt | sed 's/^  //' > /tmp/mods.txt
node tools/entry-chunkmap.mjs --root "$F" --modules /tmp/mods.txt # chunk -> modules
```

`COLD_ABLATE=` can also size a proposal, **but only for something that is its own network
resource.** A module buried in a shared chunk cannot be sized that way.

---

## Traps this rig exists to stop you falling into

**A chunk's size is not the size of the cut.** Four measurements: a 7,867-brotli chunk yielded a
1,192 B cut (15 %); a 4,982 chunk yielded 2,396 (48 %); a 7,398 chunk yielded 7,414 (~100 %, one
library removed whole). And LAT-P213's raw/brotli trap: the *same* cut was −6,889 raw (9.4 % of its
chunk) but **−771 brotli (0.5 %)** — a 19× disagreement, because three sibling card components share
their entire vocabulary (Tailwind class strings, JSX shape) with their chunk-mates, so brotli was
already paying almost nothing for them. **Never size a proposal in raw bytes.**

**A deferral is only a cut if the branch is unreachable on a cold load** — and "cold load" on
Discover means **three `/api/feed` builds and 34 rendered cards**, with no scrolling and no
interaction (`stage.feedCount === 3`; measured by P213 and re-measured independently by P214 on a
fresh build: 34 cards, 3/3 runs). "Absent from page one" is **not** "off the cold path". Five
observed classes:

1. deferred chunk fetched anyway — work wasted (`EndOfFeedCard`);
2. clean — the new chunks are fetched on **zero** runs, or no chunk is added at all;
3. knowingly fetched but shipped, because the entry-set cut still exceeded what came back;
4. **best** — the chunk is *removed*, not moved (27 scripts → 26, wire −7,603 B);
5. **worst** — fetched *and* the entry-set cut is smaller than what comes back (+2,282 B on the
   wire against a −771 B entry-set cut). This one would have shipped a regression.

**The only thing that separates class 2 from class 5 is running the A/B** — so run it even when the
byte cut is below the floor and you think the milliseconds are ungradeable. In P213 the milliseconds
*were* ungradeable and the chunk list was the entire answer.

**A barrel launders, and a dispatcher is a barrel wearing a runtime branch.** A static re-export is
not tree-shaken across a `'use client'` boundary. And `components/DiscoverCard.tsx` eagerly imports
every card variant and picks one on `item.type` — the branch is runtime, the dependency is
build-time. Look for that shape before assuming a big chunk is atomic.

**A verdict written app-wide is not a cold-path verdict.** `tailwind-merge` sat on the ruled-out list
for five cycles as "not removable" — correctly, for the *app*: 1,299 of 1,530 `cn()` calls have a
load-bearing conflict. But the landing page had exactly **one** eager importer of it. Removing it
there was worth −7,414 brotli and −76.7 ms. Always say which question your verdict answered.

**But a coarse ruling is not automatically wrong.** Chunk `487` was ruled out as a category; P213
re-walked it at module granularity and the category ruling held, for a reason nobody had written
down. Re-deriving a coarse ruling costs one session and is worth it once. It is not worth it twice.

## Guard note

`frontend/__tests__/lib/emittedEntryGraph.test.ts` is the entry-graph gate (6 controls, 40 routes).
If you add a deferral, add its marker there. Prefer a `data-*` attribute the app already owns over a
Tailwind class string — a restyle silently retires a class-string marker and the guard then goes
green for the wrong reason. Check for a same-named sibling before choosing
(`components/TournamentCard.tsx` and `components/discover/TournamentCard.tsx` are different
modules). Prove the guard red-first against a control build that is **your diff minus the
deferral** — not the branch point, because if your diff introduces the marker string itself then the
branch point fails a different control than the one you meant to prove.
