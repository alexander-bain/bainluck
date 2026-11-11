Fable: needed (reader-visible)

This first slice adds server-owned source marks to the event headline and every
game-market row, including totals, team totals, spreads, period markets, props,
matchups, the script, and the game matrices. The source mark describes the inputs
the calculation selected. A settled result carries no trading sources. The two
headline axes are computed on the server. The Apple lane owns the glyph and sheet.

Decision 145-A keeps contracts with different participation rules out of a blend.
The NFL reader selects one book for a held pair, preserves protected contracts as
separate stat families, and shapes Polymarket-only props for installed readers.
Only Polymarket rows shaped this way use the legacy `bainluck` compatibility key;
their source marks keep the actual venue. This key makes the installed iOS venue
pill absent. The web dashboard counts mark venues, so the key cannot become an
extra source. No raw compatibility label is printed.

The captured Patriots–Lions cohort (event 14639206, Nov 11, 8:20 AM PT) was read in
one READ ONLY transaction with 2-second statements, 250 ms locks and a 90-second
outer bound. It returned 151 markets and 836 outcomes/observations, rolled back,
and finished in 3.36 seconds. SQL SHA256:
`700c2d180055e7ae76e2102db9a2be5c85a18652e4095c21b8b916204c1c33c6`.
Both route versions replay the same captured cohort offline; no branch code was
executed against production.

| Patriots–Lions prop replay | Baseline 63206ba6a2 | This slice |
| --- | ---: | ---: |
| Rows | 214 | 270 |
| Underlying outcome IDs represented | 336 | 336 |
| Kalshi rows | 130 | 252 |
| Polymarket rows | 84 | 18 canonical rows |
| Held cross-venue predicates | 24 overlaps | 24 selected once; zero blends |
| Capped rows | 15 | 0 |
| Lost or newly introduced outcome IDs | — | 0 |

The extra Kalshi rows separate protected contracts that were previously averaged
into ordinary contracts. Sam LaPorta 15+ receiving yards was 0.8525, the mean of
0.86 standard and 0.845 protected; it is now two distinct rows at those prices.
All 24 held pairs select Kalshi in this snapshot: 22 have the tighter book and
two have the only known book width. An unknown width is recorded as unknown;
a tie is recorded as a tie. Neither is called
"tighter." The full rules of each held pair are retained.

The 15 baseline caps arose before the shared predicates used one integer axis and
one selected contract. No capped number is blanked by this change. The existing
cap calculation remains: if it caps a row, the row and number remain, its mark is
`none` with `monotonic_conflict`, and its own pre-cap quote is retained separately.
The cap test explicitly preserves 0.30 on a rung whose own quote was 0.45.

Two examples from the captured baseline show why the full ledger matters:

| Prop | Own Kalshi standard / protected quotes | Baseline capped number | Selected standard number |
| --- | --- | --- | --- |
| Drake Maye 1+ passing TD | 0.855 / 0.830 | 0.785 | 0.855 |
| Drake Maye 2+ passing TD | 0.555 / 0.545 | 0.530 | 0.555 |

These are selection and contract-separation changes under 145-A, before the cap
pass. Every old row maps to its replacement rows in the complete ledger.

The named Kalshi-only control is Denver at Kansas City, event 14638896: the served
read on Nov 11 at 8:31 AM PT has 448 prop rows, all Kalshi. Passing those saved
rows through the local selection utility retains all 448 and the `kalshi` header
source. This is a finished-game control; the deployed check must also use a
scheduled Kalshi-only NFL game, because graded rows skip the shaping.

For the Patriots–Lions headline and all ten NBA games scheduled tonight, replay of
the selected source inputs reproduces all eleven served hero values. Each has
Kalshi, Polymarket and Sportsbooks: **33 source entries, zero bound observation
clocks, 33 null clocks** (eleven nulls per source). Publication/poll-touch stamps
are not used as quote ages. This is the product gap assigned to #2024; the sheet
must omit the age when its clock is null.

Review data:

- [Captured inputs](../../backend/tests/fixtures/source_mark_12581/patriots_lions.json)
- [All 214 before/after row mappings](../../backend/tests/fixtures/source_mark_12581/row_ledger.json)
- [The 24 held pairs and both full rule texts](../../backend/tests/fixtures/source_mark_12581/held_rules.json)
- [Eleven headline source/clock records](../../backend/tests/fixtures/source_mark_12581/headline_clock_ledger.json)
- [Kalshi-only control receipt](../../backend/tests/fixtures/source_mark_12581/kalshi_only_control.json)

Validation at preparation: 664 backend checks including startup, followed by 33
source checks after the book-width tie/unknown controls; 55 web grouping/SSR
checks; build and typecheck (65 baseline, no new errors). All 33 source checks,
including the two book-width controls, pass all twelve clock points.
The real-cohort test rebases timestamps and checks all 336 IDs, 270 rows, 24 holds
and 18 Polymarket-only props. Cache tests reject pre-contract primary and mirror
payloads. A failed quote read propagates an error.

Still owed: live NBA cap count (none was live at the morning read), fresh CI,
head-bound bot approval, Fable ACCEPT, protected merge, deployment and served
390 px proof including the mixed card and Kalshi-only control. No column, index,
stored-data repair or iOS edit is part of this slice.

The Nov 11, 9:01 AM PT review asks for title-case stat pills on installed readers.
`NFL_LABELS` now matches the venue's casing, including `(Protected)`. The same
captured cohort was replayed again: only names and labels in the row ledger
change; prices, clocks and contributor identities are unchanged. All 33 source
tests and the four startup checks pass after this correction.

Fable's deployment conditions: land outside live NBA hours, Speed records web
memory before and after with the restart capture, and Builder C or the Apple
lane captures a mixed NFL props card on build 5704. Follow-up records remain on
#12581: non-NFL blended-prop count and slice 2's selection, same-venue versus
cross-venue capped rungs, the settled row/script source mismatch, scheduled
opening-only headlines, and the repeated mark's payload cost. These are not
claimed fixed by this first slice.
