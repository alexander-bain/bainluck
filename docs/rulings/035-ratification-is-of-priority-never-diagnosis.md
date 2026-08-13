# RULING 035 — Ratification is of PRIORITY, never of DIAGNOSIS

date: 2026-08-12
author: Alex
issues: #1793, #1546

Applies to every lane, every queue, every issue — process batch. Related:
[030](030-census-runs-before-the-staged-work.md) (the census runs first),
[031](031-assigned-identity-beats-inferred.md) (the disease this one kept finding).

## The ruling

**When Alex or Fable ratifies an issue, what is ratified is that the problem MATTERS and WHEN it
gets worked. The "root cause" written in the issue is never ratified. It is a hypothesis.**

An issue body has a diagnosis field because whoever filed it had a theory, and a theory recorded
at filing time is worth keeping. It is not worth *believing*. A signature on the issue — anyone's,
including Alex's — transfers no truth to that field. It says "work this, and work it next"; it
does not say "and the cause is as written".

So the obligation on the executing lane is unchanged by ratification:

1. **Re-derive the mechanism from the running system before writing the fix.** Ruling 030 already
   requires the census to run first; this ruling says what the census is *for* when the issue
   already claims to know the answer. It is for checking the claim.
2. **When the census falsifies the stated cause, say so out loud** — in the queue's Item 0, in the
   commit message, and in the in-tree comment on the fix. A silently-corrected premise teaches
   nobody, and the next lane inherits the same wrong story from the same issue body.
3. **A falsified premise may re-decide the queue.** Ruling 030's authority applies: if the real
   mechanism is a different size, a different layer, or a different file than the issue assumed,
   restage against the mechanism, not against the ticket.
4. **Priority still holds.** Falsifying the diagnosis does not reopen the question of whether to do
   the work. That part WAS ratified. Do not use a wrong root cause as grounds to drop or defer a
   problem someone with the authority to rank it has already ranked.

## Why — the named failure

**#1793 was the sixth consecutive falsified premise, and this one carried Alex's signature.**

The issue stated: the tennis adapter "falls back to the nearest/current tennis winner-field market
rather than returning `None`", and "what is missing is a floor."

Measured against production on 2026-08-12, every clause of that was false:

- **There was already a floor, and it worked.** `build_event` ends `if winner is None: return None`,
  and `event:tennis:zzqqxx-does-not-exist-9999` 404s correctly.
- **Nothing fell back.** The resolver was not reaching for a neighbour in the absence of data.
- **The data was never absent.** The US Open's own winner fields were already in production — four
  of them, at 41 / 33 / 23 / 23 outcomes.

The actual mechanism was that **the identity was not representable**. Resolution matched on
`tournament_tokens`, which drops tokens shorter than four characters. `us` is two. So
`tournament_tokens("US Open Men's Singles Winner")` is `{"open"}` — the same single token as
Cincinnati Open, French Open and Australian Open. Matching is a *subset* test, so a slug with fewer
tokens matches *more* tournaments: degrading the slug widened the blast radius instead of narrowing
it. Cincinnati then won the tie-break on a 78-player draw. Resolution by popularity instead of by
identity — [ruling 031](031-assigned-identity-beats-inferred.md)'s disease, one cycle after it was
banked, sitting in the resolver.

**The cost of believing the field would have been a shipped non-fix.** A lane that built the stated
floor would have added a guard that was already there, passed its own tests, and left
`event:tennis:us-open-2026` serving "Cincinnati Open" — with the US Open twelve days out.

## What this is not

- **Not a licence to relitigate priority.** Diagnosis is the lane's; ranking is not.
- **Not a reason to stop writing root causes in issues.** Keep filing them. Label them as what they
  are and check them before spending on them.
- **Not scepticism reserved for other people's tickets.** The sixth instance is the one that
  matters here precisely because it was signed by the person with the most context.

## How to apply

- Queues quote the issue's stated cause in Item 0 and record **confirmed** or **falsified**, with
  the measurement.
- A falsified premise is a headline finding, not a footnote — it goes in the commit body and in the
  in-tree comment beside the fix, so the next reader of the *code* learns it too.
- Report acceptance against the mechanism you measured, never against the sentence you were handed.
