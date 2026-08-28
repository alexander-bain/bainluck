# RULING 139 — A near-duplicate rule may never collapse across subjects

date: 2026-08-27
author: Alex (directive authored in Alex's Fable session and delivered through the lane runner Alex
launched under his standing authorization)

**Amends:** ruling 8 of UX-P138 ("never a repeating template"), whose *reading* is replaced, not
whose clause is.
**Binds:** every de-duplication, cap, family, story-key or "we already have one of these" rule that
groups user-facing items by a derived key.
**Applied by:** UX-P147 (`frontend/lib/tournamentProps.ts`, and the register's `props` /
`props_declined`).

---

## The clause

> alcaraz-second-major and sinner-second-major are DIFFERENT PLAYERS and must both render. Key the
> near-duplicate rule so it never collapses across players.
> — Alex, 2026-08-27

## What it amends, and why the earlier reading was wrong

UX-P138 ruling 8 said the props section is "curated by interestingness, **never a repeating
template**." The implementation read *template* as **the same question with a different name in
it**: `propTemplateFamily` dropped the leading token of a register key, so `alcaraz-second-major`
and `sinner-second-major` both reduced to `second-major`, one card was kept and the other counted
as `dropped.template`. A later hand-edit then did the same thing at the source, moving
`alcaraz-second-major` into the register's `props_declined` with the reason "one question with two
names in it."

Both were defensible from the words and both were wrong about the product. Two rivals' odds of the
same feat is not one question asked twice — **it is the comparison**, and on a two-horse men's draw
it is the most interesting thing the section has. Measured on Kalshi the night of the ruling:
Alcaraz's `2+ Grand Slam wins` is 27c on 42,723 open interest; Sinner's is 1c, because his "to play"
market is also 1c. Side by side, those two numbers are the entire state of the men's draw. Either
one alone is trivia.

The cap was not too strong. It was **keyed wrong** — on the topic instead of on the topic *and* the
subject — so it could not tell "we are repeating ourselves" from "we are drawing a contrast".

## The general clause

**A rule that suppresses an item for resembling another must key on everything that makes the two
items answer different questions. Dropping a field from the key to make the rule fire more often is
not a stronger rule; it is a rule that has stopped being able to see the distinction it exists to
protect.** Where a key is `<subject>-<topic>`, a family is the whole key. Two items about different
subjects are not duplicates however identical their shape, and the comparison between them is
usually worth more than either alone.

The failure this generalises is silent by construction: a suppression rule reports a COUNT, so the
section looks curated rather than lossy, and the item that was deleted leaves no trace on the page.
That is why the rule is stated as a constraint on the key rather than as a threshold.

## Where else it reaches

- **Discover story caps and semantic dismiss** (`feed_market_quality.py`, gotcha #25). Story keys
  suppress for 14 days and semantic dismiss already ignores generic tokens; this clause is the
  reason that exclusion exists and the standard against which the next one is judged.
- **Cross-source near-match** (`utils/cross_source_matching.py`), whose numeric and direction guards
  are the same idea: two questions that differ in a load-bearing field are not the same question,
  however high their Jaccard.
- **Any future "one card per family" rule.** The test to apply is not "how similar are these" but
  "if a reader saw both, would they learn something from the second one."

## What it does NOT change

- **The cap still exists.** One card per family, where a family is the whole register key. Two
  entries for the same subject and the same topic still collapse, and the drop is still counted.
- **Nothing is inferred from the title.** The family is the curated key, so the rule cannot be
  defeated by rewording and cannot be triggered by coincidental phrasing.
- **The advance-to-round rule (ruling 3) is untouched.** A per-player "does X reach the semifinals"
  question is still a grid cell and still not a prop. ⚠️ A consequence worth writing down: because
  `advanceRound` claims any key ending in a round suffix, a curated question that is *about* a round
  without being a per-player advance market — "how many Americans reach the quarter-finals" — must
  not be keyed `*-quarterfinals`, or it is routed to a grid that has one row per player and no row
  for a count.

## Guard

`frontend/__tests__/components/tournamentPickerRotation.test.tsx` — "ruling 8 as amended". Asserts
the family key at the pure layer, that the two second-major cards do not merge, that both RENDER
through the shipped component, and that the same question about the same subject still collapses.
The render assertion is the load-bearing one: a library test stays green the day the component
stops printing the card.
