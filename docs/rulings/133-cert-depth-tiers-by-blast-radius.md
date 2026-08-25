# RULING 133 — Cert depth tiers by BLAST RADIUS: full adversarial cert is for code that writes production data or feeds the canonical key

date: 2026-08-24
author: Alex (banked by lane1, Q405 addendum 2)
issues: #2161
supersedes:

---

## The ruling

Certification depth is no longer uniform. It tiers by **blast radius** — by what a defect in the
code could do if it shipped, not by how large the diff is or how hard it was to write.

**Tier 1 — full adversarial cert.** Code that **writes production data** or **feeds the canonical
key**. Named examples, as ruled: categorizers, capture, calibration applies, grading. The existing
machinery applies in full: an independent window, author-never-certifies, red-first receipts,
specimen-level attack, BLOCK as the default posture.

**Tier 2 — one review pass.** Display fixes, docs, tests, read-only tooling. One competent read by
someone who did not write it. No adversarial round, no red-first ceremony, no cert-log row.

## Why — the cost was landing on the wrong work

Full adversarial cert is the most expensive thing this system does, and it was being spent flat.
A docs edit and a categorizer rewrite drew the same machinery. Two consequences, both bad:

**It slowed the tier that needed it.** Cert capacity is finite — one independent window, a mission
bus, a serial queue. Every tier-2 subject in that queue is a tier-1 subject waiting. The
categorization work in #2161 took two adversarial rounds to converge while the queue also carried
subjects whose worst case was a wrong label on a page.

**It cheapened the verdict.** A BLOCK that can arrive over a stale figure in a report reads the same
as a BLOCK over a categorizer that would mis-tag production rows. When the severity of the process
carries no information about the severity of the subject, the verdict stops being a signal and starts
being a toll. Reviewers under a uniform-depth regime drift toward pro-forma passes on the low-stakes
end, which is precisely where the discipline then fails to be available at the high-stakes end.

Tiering restores the signal in both directions: a tier-1 cert is expensive **because** the subject
can corrupt data, and a tier-2 subject moves in one pass **because** its worst case is visible and
reversible.

## The line, and why it is drawn there

The test is not "is this important" — everything is important. It is:

> **If this ships wrong, is the damage (a) written into data we will later read as truth, or
> (b) visible on a surface and fixable by the next deploy?**

(a) is tier 1. (b) is tier 2.

That is why **write** and **canonical key** are the two named triggers rather than a list of
directories. A wrong number on a page is a wrong number on a page; a wrong number written to
`is_winner`, or a wrong `canonical_market_key`, becomes the input to every later computation and to
every audit that would have caught it. Ruling 130's shape: the damage that survives the deploy that
caused it is a different class from the damage that does not.

It is also why **tests** sit in tier 2 despite guarding tier-1 code. A bad test is loud — it fails,
or it passes vacuously and the next reviewer of the subject notices. A bad categorizer is silent,
and its output is indistinguishable from a correct one without the corpus.

## Binds

- **The proposing lane declares the tier, in writing, when it stages the work** — and declares it
  *before* the review, not after a verdict it dislikes. A tier declaration is a claim like any other
  and is attackable.
- **The reviewer may escalate; the author may not de-escalate.** A tier-2 subject a reviewer judges
  to be tier-1 becomes tier-1, and that re-tiering is itself the finding. The asymmetry is
  deliberate: the author is the party with an incentive to want the cheaper path.
- **Mixed diffs take the highest tier present.** A commit touching a display file and a grading path
  is tier 1 in full. Splitting the commit to get the cheaper tier on the display half is legitimate
  and encouraged — splitting it *in the description only* is not.
- **Read-only tooling is tier 2 only while it stays read-only.** The moment a script gains a write
  path it is tier 1, and the tier does not carry over from its previous life.
- **Tier 2 is one pass by someone who did not write it.** It is a reduction in depth, not in
  independence. Author-never-certifies survives tiering intact.
- **Tier 2 still records its pass.** One line, not a cert-log row. "Less ceremony" is not "no
  record" — an unrecorded review and no review look identical (gotcha #53).

## What this does NOT say

It does not lower the bar on tier 1. Nothing about the adversarial process changes for code that
writes production data; if anything, tiering exists so that process can be run properly where it
matters.

It does not license shipping display bugs. One review pass is a real gate with a real reviewer, and
a tier-2 subject can still be sent back.

And it does not make "read-only" a self-certifying claim. Whether a change is read-only is a
question about the code, answerable by reading it, and a lane that declares tier 2 on a path that
turns out to write is not merely wrong about the tier — it has mis-declared the thing the tier was
computed from, which is the more serious finding.

## General form

**Match the cost of verification to the reversibility of the failure. Damage written into data we
will later read as truth earns the full adversarial round; damage the next deploy erases earns one
competent independent read.**
