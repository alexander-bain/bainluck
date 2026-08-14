# RULING 050 — A control that cannot fail is not a control

date: 2026-08-13
author: Alex
issues: #993 #1545

## The ruling

A change predicted to move **nothing** on a measured surface is still **read**, and the read is
taken **expecting no movement**.

If the number moves, the attribution model is wrong. Further merges of ranking changes **HALT**
until the movement is explained.

That halt is what makes it a control. A null-result read with no consequence attached is a
formality — it can only ever confirm, so it carries no information. Arm it, or do not take it.

## Why — the occasion

`program/latency-45` changes `/search` only. The 46 gold probes grade `/typeahead`. So the
prediction for its deploy is **no movement in `entity_top_1`**, and the temptation is to skip the
read entirely: there is nothing to see.

Skipping it throws away the only free test of the attribution model this program has. The two
surfaces share helpers — `_typeahead_evidence`, the scorer, the concept upsert. If a `/search`-only
change moves the `/typeahead` number, then something believed to be surface-local is not, and every
per-deploy attribution taken under ruling 046 is resting on an assumption that has just been shown
false. Better to learn that from a cheap control than from a projection that misses by 7 and cannot
be explained.

## The second specimen, from the same window

LAT-P050 found the same principle already earning its keep one level down, in the instrument.

The offline reranker had no control at all. Nobody had ever asked the obvious question: *if you
re-rank a capture of the scorer's own output, with the same scorer, do you get the same order back?*
It is a property that must hold, it costs one run to check, and it had never been checked.

When it was finally asked, on production v3804: production scored **35/44**, the harness re-ranking
production's own output scored **30/44**. The harness had been destroying five passes on every run
for four cycles, in silence, while its docstring described its output as a conservative floor.

The instrument had a control available the whole time. It simply was not armed.

## What this does not say

It does not say every change needs a control read — most changes predict movement, and the movement
*is* the read. It says that when the prediction is *null*, the read is still owed, because a null
prediction is the only kind that can falsify the model rather than merely score the change.

**Sibling ruling, deliberately kept separate: 050 does not supersede RULING 049** (calibration lane,
claimed 2026-08-14, not yet merged when this was written — cited by number rather than by link so
the reference cannot dangle if its slug changes). 049
forbids writing an acceptance criterion that cannot fail once the fix is in. 050 is the other half:
it requires taking the read whose expected result is "nothing happened", and attaching a halt to it.
049 is about not fooling yourself when you check; 050 is about checking at all when you are sure.
