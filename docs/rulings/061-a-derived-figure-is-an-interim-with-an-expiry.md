# RULING 061 — A derived figure is an interim, and an interim carries an expiry

date: 2026-08-14
author: Alex
issues: #1544, #1865

Ruling 003 says **clients render, never derive**. A client-side derivation that
exists only because the payload publishes nothing is an **honest interim** —
but it is an interim only while it carries all three of these:

1. It is **labelled as derived** in the artifact itself, in a form a grader can
   read without trusting our prose (a `data-*` basis attribute, not a comment).
2. It is **guarded by a pairing assertion** against the figure it stands in for
   — never by a ban on the derivation. A ban is satisfied by hard-coding a
   number; a pairing is only satisfied by the thing you actually wanted.
3. It carries a **routed request for the publisher to publish the real thing**,
   and it is **DELETED in the same change that adopts it**.

Without the third, it is not an interim. It is a permanent fixture that has not
noticed yet.

## The occasion

UX-P078 collapsed `/calibration`'s By Source from five source keys into three
providers. The payload publishes ECE **per source key** and **none per
provider**. Recomputing one is what ruling 003 forbids; rendering nothing reads
as missing data directly under a table that just printed the number. The lane
took the third path — render the figure the page had already derived once,
publish `data-ece-basis={published|pooled|none}`, guard it with a pairing
assertion that the panel's pooled ECE is identical to the table's — and then
**offered the question up on #1544 rather than deciding it quietly**.

That is ruled the lane's way, and then one step further: **the payload SHOULD
carry the per-provider ECE.** "Clients render, never derive" is ruling 003's own
text, and a client-derived figure with a basis attribute is an honest interim,
not an end state. A small calibration-lane item is routed to publish it.

## What this ruling actually adds

The distinction being banked is not "derivations are bad". It is:

> **An interim is defined by its exit condition, not by its apology.**

A derivation with a basis attribute, a pairing test and a routed publisher
request is an interim. The same derivation with a comment saying `TODO` is
indistinguishable from permanent, because nothing in it can ever become false.

The pairing-over-ban half is this page's own `PROXY_FOOTNOTE` lesson from
UX-P075 applied a second time, and it generalises: **guard the property you
want, not the mechanism you fear.**

## Live instance this governs

`frontend/lib/calibrationProviderPanels.ts` — the pooled provider ECE and its
`data-ece-basis`. The pairing-assertion guard **stands until** the calibration
lane publishes a per-provider ECE in the payload. On the day it lands, the
derivation is deleted and the payload figure adopted in the same change. If that
deletion does not happen in that change, this ruling was not followed.

Related: [[003]] (clients render, never derive), ruling 044 (rendered-green is
not communicates-green — the same page's other standing bar).
