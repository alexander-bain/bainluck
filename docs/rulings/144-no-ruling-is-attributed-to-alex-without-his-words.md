# RULING 144 — No lane attributes a ruling to Alex without quoting his words

date: 2026-08-28
author: Alex
issues: #2199
supersedes:

## Alex's words

Delivered with the UX-P151 directive (Fable session, MC, 2026-08-28):

> STANDING DOCTRINE ADDITION (record where directive-authoring guidance lives,
> and obey it yourself): no lane may attribute a ruling to Alex without quoting
> his actual words with date and source (chat/MC). "Exactly as ruled" without a
> quote is a violation — this queue exists because a paraphrase inverted a
> ruling. Fable audits every "as ruled" claim that reaches YOUR-TURN.

## The case

The queue this was issued with (ruling 143) exists because of a paraphrase.
Alex's UX-P138 note observed that two curated cards were *"one templated question
with the name swapped"*. The lane that executed it recorded that as a ruling to
remove the repetition, and removed a PLAYER — Alcaraz, from the file and from the
render. He then had to spend UX-P147 saying *"DIFFERENT PLAYERS and must both
render"* to get him back, and UX-P151 saying what he had wanted in the first
place. Three queues, and at no point was the original sentence written down where
the next lane could read it.

The mechanism is worth naming exactly, because it is not carelessness. A
paraphrase is a lane's INTERPRETATION wearing Alex's authority. Once it is in a
comment or a test name — `// Alex's item 11` — it is indistinguishable from the
ruling itself, it cannot be checked against anything, and every lane downstream
inherits it as settled. A quote can be wrong about its own meaning and still be
re-read; a paraphrase cannot be re-read at all, because the words it replaced are
gone.

## The ruling

**A lane may not attribute a decision to Alex without his actual words, a date,
and a source.**

- **Quote.** His sentence, verbatim, in the artifact that acts on it — the
  ruling file, the code comment, the test name's docstring, the report.
- **Date.** The day he said it. Rulings are amended; an undated quote cannot be
  ordered against its own amendments.
- **Source.** Where he said it: chat, MC, a review comment, a directive. A lane
  reading a directive is reading a relay, and the relay must say so.
- **"Exactly as ruled" with no quote is a violation**, not a shorthand. So is
  "Alex's item N" standing alone: an item number is an index into a document the
  next reader does not have.

Where a lane must act on its own reading of an ambiguous note, it says so in
those terms — *this lane read X as Y* — and the reading is falsifiable rather
than authoritative. That is the whole difference: the reading survives being
wrong, and the paraphrase does not.

## Where the guidance lives

**Directive-authoring guidance is `docs/rulings/144` and this section is its
home.** It applies to whoever writes a queue's directive (today, Fable) and to
whoever executes it. Two obligations, not one:

- The AUTHOR of a directive carries Alex's words into it.
- The EXECUTOR carries them into the code, the guards and the report, and does
  not upgrade its own reading into a quote on the way.

**Fable audits every "as ruled" claim that reaches `YOUR-TURN.md`.** A claim of
Alex's authority with no quote behind it is sent back rather than actioned.

## General form

An attribution is a claim about evidence, so it is subject to the same rule as
every other claim this program makes: state the evidence, or state that you are
inferring. This is ruling 140's clause applied to authority instead of to data —
an inference reaching a surface needs something that can refute it, and for
"Alex ruled X" the refuting object is the sentence he wrote.
