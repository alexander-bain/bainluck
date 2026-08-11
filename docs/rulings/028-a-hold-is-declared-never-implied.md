# RULING 028 — Readiness is a literal token; a hold is DECLARED, never implied by silence

date: 2026-08-11
author: Alex
via: Integrator INT-050/051/052, ratified
issues: #1766, #1769, #1767
relates: ruling 001 (a new ruling is a new file — same disease: a signal that only works if everyone writes it the same way), ruling 008 (pid-alive is the lock test; a claim about state is not the state), ruling 013 (an explicit RELEASED frees a lock — explicitness over inference), ruling 025 (the availability envelope: substitute content must declare itself)

A branch is ready when, and only when, its handoff file contains the exact bytes
`status: ready_for_integration`, **alone on its line, first character of the line**. Prose goes on
a separate `status_note:` line. `status:` is machine-readable and takes one of a closed set:
`ready_for_integration | running | approved | merged | done | blocked`.

**And a hold is declared with `codex_premerge:`, NEVER by withholding the token.** A truth-touching
branch that is genuinely ready-but-held still writes the token and declares the hold beside it. The
standing truth-touching rule already requires a held branch to be *"visibly held, not quietly
skipped"* — and being unmatchable by the Integrator's poll is the purest possible form of quietly
skipped. Withholding the signal to express caution produces the same bytes as forgetting.

**WHY.** The Integrator's continuous-operation poll is a string match, not a comprehension task,
and on 2026-08-11 it went blind in **three separate dialects at once**, every one of them written
by a careful author trying to be clear:

```
status: READY — awaiting the master-write lock      no token at all
- **status:** ready_for_integration                 token present, but the line starts with `- **`
verdict: **READY FOR INTEGRATOR.**                  no `status:` key at all
```

The third is the most dangerous, because it reads as *more* emphatic than a compliant entry —
emphasis is not a signal. PR #1770 sat green and invisible for three Integrator cycles. LAT-P037
reached its cycle only because a successor *queue* file happened to carry a status line the report
entry lacked. LAT-P038 reached its cycle only because Alex named the branch out loud. **Two of
three merges in one session were found by a human, not by the machine whose entire job is finding
them** — while successive lane reports diagnosed the symptom as lock contention, which fits, which
is why it survived three cycles.

The deeper failure is not the regex. It is that **the ready signal was carrying two meanings on one
line** — "this is done" and "here is the caveat" — so every author who had a caveat edited the part
the machine reads. Split the meanings and the pressure disappears: the token is for the poll, the
note is for the human, the hold has its own key. The same shape as ruling 025's envelope, applied
to the handoff bus: substitute content must declare itself rather than quietly look like the real
thing.

**Corollary — do not write the token before it is true.** It means *"merge this now, subject only
to the lock."* A branch still owing a gate, a regrade, or a fix is not ready; say what it owes in
`status_note:` and flip the token when the debt is paid. Writing it early converts a missed merge
into a premature one, which is the worse failure.

**Corollary — nothing lives only in an untracked file.** This ruling exists because
`.claude/handoff/README.md`, where the protocol is operationally documented, is gitignored
(`.gitignore:120`) and therefore cannot ride a push, cannot be reviewed, and exists on exactly one
disk. A named-failure fix recorded only there is one `rm -rf` from being relearned. The operational
copy stays in the handoff README for the lanes who read it daily; **the rule itself is banked
here, where CI asserts it.**
