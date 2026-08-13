# RULING 044 — Rendered-green is not communicates-green

date: 2026-08-13
author: Fable
via: the CAL-P050 / queue-316 acceptance
issues: #1544

> **A surface whose JOB is communication carries an explicit human-eyeball done-bar. That bar is
> distinct from its rendering gates and is never discharged by them. A screenshot proves the page
> rendered; only a reader proves it was read.**

## What produced it

The calibration page was **photographed in production, green, while failing exactly what it was
supposed to do.**

Exit-exam items 2 and 4 were marked 🟢 **PASSED** off browser-audit run
[`31431286342`](https://github.com/alexander-bain/bainluck/actions/runs/31431286342) — manifest
`result: pass`, `observed_frontend_sha` matching the audited commit. That evidence was not weak and
it was not faked. The section existed. The five per-source panels existed, on a shared 0–100 axis,
each labelled with n, % of curve, and ECE. Every element the exam named was present, correct, and
in the picture.

Then a reader looked at it. The section asked **"Does Trading Activity Matter?"** over data that
does not know whether anything traded — we receive no volume; `price_moved` is a stand-in, and the
tri-state includes sportsbook lines that carry no flag at all. The panels were labelled with five
raw **source keys** (`odds_api`, `odds_api_totals`, `odds_api_spreads`, …) rather than the three
**providers** a reader has a concept of. The price basis was implied, never stated. The numbers
were right the whole time. CAL-P050 changed no math, no payload and no version, and the page went
from correct to legible.

Both items reverted to 🟡, each naming the reason: **they passed a rendering gate while the page
failed a human reading it.** Neither pass was retracted — the rendering claim was true. It was
answering a different question.

## Why the gate cannot be strengthened into the bar

The tempting fix is a better automated check, and it does not exist. A browser audit asserts that
pixels were produced: element present, request 200, SHA matched, no console error. Comprehension is
a property of the reader, not of the DOM. There is no assertion that fails when a heading asks a
question the data cannot answer, because at the pixel level that heading is a perfectly rendered
heading.

So the two claims are not the same claim at different strengths — they are **different claims**,
and one cannot be escalated into the other by adding assertions:

| claim | proved by | fails when |
|---|---|---|
| it rendered | browser audit, screenshot, SHA match | the page is blank, broken, stale, or wrong-commit |
| it communicates | a person reading it | the page is correct and still misleads |

A green rendering gate over an illegible page is not a false pass. It is a **true answer to an
unasked question** — which is more dangerous than a false one, because nothing about it looks
wrong, and the strength of the evidence is exactly what makes it persuasive.

## How to apply

- When a queue's payoff is **communication** — copy, labelling, framing, an explanation, a chart's
  legend, an empty state — declare the human-eyeball done-bar **in the queue, at staging**, next to
  the rendering gates and explicitly not satisfied by them. Name who reads it.
- A queue may be `ready_for_integration` with that bar still open. Say so plainly: *code-done, bar
  owed to Alex.* Do not let the presence of green gates quietly promote the queue to done — that is
  the whole failure mode, arriving as good news.
- **Never close a communication item on a browser-audit run.** Cite the run for what it proves (it
  rendered, at this SHA, in production) and keep the item 🟡 until a reader reports.
- The eyeball bar usually needs a **deploy**, so it lands after integration. Record it as owed in
  the handoff so the obligation survives the lane that incurred it.
- Generalise past this page: any gate proves a property of the artifact. Before quoting one as
  done, ask **which claim it actually settles** — and whether that is the claim the work was for.

## Related

- [003](003-clients-format-never-adjudicate.md) — the same boundary from the other side: the client
  presents, it does not decide. Presentation being *its own* job is why presentation needs its own
  bar.
- [030](030-census-runs-before-the-staged-work.md) — measure before you build. 044 is the closing
  bracket: measure the reader after you ship.
- Gotcha #53 — an empty 200 is a response shape, not a fact. Same shape of error: a signal read as
  answering a question it was never about.
