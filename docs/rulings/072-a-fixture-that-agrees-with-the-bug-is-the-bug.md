# RULING 072 — A fixture written from the code's assumption cannot falsify it; production is the only author of a wire-shape fixture

date: 2026-08-17
author: Fable (UX cycle-81 directive), banked by program-ux UX-P085
context: #1886 — iOS dropped EVERY Discover bundle card for as long as the feature has existed, while five test files asserted bundle behaviour and passed. Extends the cycle-80 ruling that two copies of a rule are the defect (delete the copy, do not add an agreement test).

## The ruling

**A test fixture that encodes the same assumption as the code under test proves only that the assumption is self-consistent.** For any boundary the product does not control — a wire payload, a third-party response, a file on disk — the fixture must be **captured from the real producer**, verbatim, and frozen with the date and the query that produced it.

Three consequences, all mechanical:

1. **Capture, never author.** A hand-written JSON literal describing someone else's payload is a guess wearing evidence's clothes. Fetch it, compact it, commit it, say when.
2. **Never trim what you do not understand.** The field that breaks the decode is by definition the one you did not think mattered. `DiscoverFeedProdFixture` keeps `debug_bundles` and every unread analytics key for exactly this reason.
3. **Count against the SOURCE, not against the parse.** Assert the decoded count equals the count *the server reported at capture time*. A tolerant parser that dropped an element agrees with itself perfectly.

## What made this necessary

`FeedItem.init` read bundles from a top-level `bundle` key. **No server has ever sent one** — measured 0 of 83 items on 2026-08-14 and 0 of 60 on 2026-08-17, and all four emitters in `app/utils/discover_bundles.py` serialise under `data`. Every bundle therefore fell through to the futures branch, threw on its string `id`, and was eaten by `FeedResponse`'s deliberately tolerant skip loop. Six curated theme cards — "2028 Election", "Fed & Rates", "Middle East", "Russia–Ukraine", "Washington Power" — have never rendered on iOS.

The decode bug is ordinary. **What this ruling is about is why it survived.** Five test files exercised bundles — decode, sanitisation, lifecycle, pagination, categorisation — and *all five* built their fixtures with `"bundle": { … }`, the shape the decoder wanted. The suite was not weak here; it was thorough, and thoroughly wrong, because every fixture inherited its shape from the same misunderstanding as the code. Adding more such tests would have moved the number of green assertions and not the probability of catching this.

Note the aggravating detail, because it is the recurring one: `FeedItem.init` already carried a comment on the `concept` branch explaining that L2-179 had discarded every concept card by this exact mechanism. **The repaired copy is what hid the broken one** (gotcha #128) — the comment read as evidence the class was handled, one branch above the place it was not.

## The general form

This is the fixture-side member of the family the batch keeps meeting: an instrument that reports confidently about something it never measured.

- **#53** — an empty 200 is a response shape, not a fact.
- **#124** — `$?` belongs to the last thing that ran, so a gate that never ran reports success.
- **#135** — a truncated `xcodebuild` is byte-identical to a pass.
- **071** — a lock saying two things at once is uninformative while looking informative.
- **This one** — a fixture agreeing with the code proves the code agrees with itself.

In every case the reader is handed a real, well-formed value in exactly the place the answer belongs, and it is the wrong one. The defence is always the same shape: **grade the thing against an artifact produced by something other than itself.**

## Scope, stated so it is not over-applied

This binds fixtures standing in for an **external producer's wire format**. It does not bind synthetic fixtures for pure logic — `DiscoverCategoryTests`' interleave stubs are invented on purpose, because the interleave's input is our own data structure and the test's job is to explore its space, not to attest to a shape. The question to ask is: *if my belief about this shape were wrong, would this fixture still be green?* If yes, capture it instead.
