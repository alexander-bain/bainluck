# RULING 094 — A shared tree is not a measurement

date: 2026-08-19
author: Fable
issues: #1981 · #1979 · #1947

**Every code finding is read from a detached worktree at a freshly fetched `origin/master`,
never from the shared master tree. The shared tree's checkout is whatever the last session
left; a finding read there can be a fact about someone's stale checkout wearing the clothes of
a fact about production.**

## Why

`~/bainluck` sat at `6f0d724c` while `origin/master` was `43f33396`. Both are real commits and
`6f0d724c` is an *ancestor* of master — so nothing was broken, no command errored, and every
file read there was internally consistent. It simply predated PR #1971, so a session grepping
that tree for #1971's guard would find it absent and correctly report what it saw: that the fix
never landed. The reading is honest and the conclusion is false.

That is the whole hazard: a stale tree does not fail, it *agrees with itself*. There is no
symptom to notice, and the usual instinct — re-read the file more carefully — makes it worse,
because the file is exactly what the reader thinks it is.

This is the READ-direction twin of gotcha #51, which put `-C` on every write verb because a
command's target directory is invisible in the command itself. Same root, other direction: the
tree a read lands in is invisible in the read, and the shared tree is the one nobody owns.

Practice: `git fetch`, `git worktree add --detach <path> origin/master`, read there, and name
the SHA in the finding. Naming the SHA is the load-bearing half — a finding that cannot say
which tree it came from cannot be re-checked, and cannot be distinguished from this failure by
anyone reading it later.
