# RULING 113 — A merge offer is a branch with a green gate, not a file

date: 2026-08-20
author: Fable
issues: #1621, #2049, #2050, #2054, #2055

**Phase 0 sweeps READY tokens AND open PRs with passing CI, and reports either source being
unavailable as NOT RUN rather than clean.**

The Integrator's work queue is the set of things being offered for merge. A `READY-*.md` token is
one way to make that offer. **An open pull request with a green CI run is another, and it is just
as real** — it names a branch, it names a head, and it carries a gate result that is stronger
evidence than anything a token asserts about itself. A sweep that reads only one of the two
answers a narrower question than the one Phase 0 is asking, and answers it confidently.

## The charter case

INT-095 through INT-098 ran the ruling-109 sweep first, exactly as directed, and the sweep was
correct every time about the thing it measures. It still missed live work **two rounds running**,
and Fable had to name the branches by hand in two consecutive directives:

* `#2049` (`lane1/q382-espn-candidate`) and `#2050` (`lane1/q382-namesmatch-probes`) were CI-green
  and merge-eligible while `READY-lane1-382.md` read `branch: None` to the sweep — the token
  carries its two branches under `## Branch 1` / `## Branch 2` headings rather than a line-leading
  `branch:` field, and `sweep_ready_tokens.py` parses only line-leading fields.
* `#2054` and `#2055` had no READY token at all. `#2055` was the gate on Tranche A's 31 applies,
  so the cost of not seeing it was measured in blocked downstream work, not in tidiness.

That is three token-shape defects in three cycles — `READY-calibration-75.md` shipped with no
`status:` field and was invisible for a full cycle over gate-clean work; `READY-lane1-382.md`
with no parseable `branch:`; `READY-codex-adhoc-rebaseline.md` with a `base:` naming a commit that
is not in its own history. **The pattern is not that lanes are careless. It is that a token is a
hand-written assertion about a branch, and the branch is the thing that is true.**

## Why this is ruling 109 one level up, not a new idea

Ruling 109 retired a hand-maintained never-merge list because *"a list a human consults is a list a
human forgets"*, and moved containment into computed code. This is the same move applied to the
input side of the same sweep: **"also remember to check the PR list" is prose, so it will be
forgotten; a section in the sweep's own output is code, so it will be run.** A ruling that only
said "check PRs too" would be the list, not the fix. The enforcement half ships with the ruling.

## The NOT-RUN half is not decoration

Ruling 109's sweep already refuses to report health it did not measure — an empty never-merge set
prints `containment: NOT RUN` rather than marking every branch uncontained. The PR sweep inherits
that discipline, and it matters more here, because the PR source is a **network call**: `gh` can be
missing, unauthenticated, rate-limited, or simply slow. Every one of those failures produces an
empty list, and an empty list is indistinguishable from "no PRs are open" unless the sweep says so.

That is gotcha #53 exactly — *an empty 200 is not an absence, it is a response shape* — and the
same cycle that banked this ruling produced a second, sharper reminder of why absence must be
loud. INT-098's gotcha-#52 cleanup ran `rm -rf` on `artifacts/subcohort/`, a directory holding six
untracked files **and eight tracked siblings**, and deleted all fourteen. The tracked eight came
straight back with one `git checkout --`; the untracked six would not have, had they not been
banked to a rescue branch minutes earlier. Both halves of that are this ruling's point: **a thing
whose absence is visible and reversible is safe, and a thing whose absence looks like a clean
result is not.** A sweep that silently reports zero PRs is the second kind.

## What the sweep must do

1. Enumerate open PRs whose head is not already contained in `origin/master` by content.
2. Report each with its number, branch, head, mergeability and CI rollup, classified so a green,
   clean, uncontained PR is visibly a merge candidate.
3. Print `open PRs: NOT RUN — <reason>` when the PR source cannot be read, and never emit an empty
   PR section that reads like "there are none".
4. Keep the token sweep exactly as it is. This adds a source; it removes nothing. A token still
   promotes a branch into the candidate set, and ruling 034 still governs: **confirm by content
   before merging, whichever source surfaced it.**
