# NFL division round-up card: design reference

PILLARS: FORMATTING, DISCOVER. Prepared by Fable for Alex, Tue 2026-10-06, 9:15pm PT; revised 9:35pm, 10:00pm and 10:20pm PT after the coordinator's replies and Alex's rulings. For the first comparison slice Alex approved on 10/6: "NFL division front-runners" (#4463, #10354, #10357). A reference for the build, not a ruling and not an assignment. This is revision 3. It supersedes revision 2 (`FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006-R2.md` and its folder) and the two earlier versions. The 24 prototype card images and the four fixture cards are unchanged.

**What changed from revision 2:** the old-numbers state now uses the product's own rule, words and mark (revision 2 had the wrong trigger and wrong words); a mixed-age state is added; a footer for four to seven qualifying divisions is proposed; Alex's ruling on what the container holds is recorded; the color check against the release branch is recorded; 15 new reference images cover the product footers and old-number states.

The rendered reference is `fable-nfl-division-roundup-design-20261006-r3/roundup-card-reference-standalone.html`, and https://claude.ai/artifact/5YKssYU8GQWaRsZ7ttpDCS for Alex. The card rules in it are copied verbatim from the Comparison Feed Two page source (`roundup-card.css`). A check of every element's position and style found no difference between the reference and the prototype (`verify_geom_output.txt`).

## Rulings so far

Alex ruled these on Oct 6. They override the prototype where the two differ.

- **Bars are blue.** Green stays for the leader within one contest and for "Won".
- **New parts, built to this reference.** The header and rows are not the existing grouped-card parts. If the card then looks inconsistent with other feed cards, the other cards may be the ones to change.
- **Rows run highest probability first.** The rule selects the four closest races; the card lists them high to low.
- **Tapping the card opens a container.** The container shows a card for each item in it. Rows are not separate links.
- **The container holds only what the card showed.** The same divisions, in the same order. It is the container this card opened, not the canonical one for NFL divisions. Containers will be made in large numbers and are not precious. The other divisions could later appear in a "related" section; that is not part of this slice.
- **The footer wording is accepted for now.** It can change if it looks wrong in production.

Settled without a ruling, after the coordinator's review of the product's design system:

- **Light only.** The product has no dark mode. Dark values stay on file below and are not part of the check.
- **Product colors where they exist.** Seven of the nine colors already exist in the product under other names. See the Colors table.
- **The product's number format.** The product's own formatter applies, so 99.7% prints as >99%. No exception is needed.

## Measurements

All sizes in CSS pixels, from a rendered card 358 wide.

| Part | Specification |
|---|---|
| Card | Padding 18 top, 18 sides, 13 bottom. Border 1px. Corner radius 16. 14 between stacked blocks. |
| Header line | Kicker left, tag right, vertically centred, at least 10 apart. |
| Kicker | 11px, weight 600, uppercase, letter-spacing 0.09em, color ink3. |
| Tag | 11px, weight 600, color ink2 on the elev fill. Padding 2 by 9. Fully rounded. |
| Headline | 23px, line-height 1.2, weight 700, letter-spacing −0.015em, balanced wrapping. Sits 8 below the header line. Over 44 characters it drops to 19px at line-height 1.25. |
| Row | Two columns: a 49.6-wide number column, a 12 gap, then the label column. 14 between rows. |
| Number | Monospaced, 20px, line-height 1.15, weight 700, letter-spacing −0.03em, right-aligned. Whole percentages only. |
| Percent sign | 60% of the number size (12px), weight 500, color ink3, 1 to the right of the digits. |
| Label | 15px, line-height 1.3, weight 400, color ink. Wraps to as many lines as it needs. Never truncated. |
| Bar | In the label column, 7 below the label. 6 tall, radius 3, track color. Fill width equals the probability as a share of the track, never under 3. Left end square against the track, right end rounded 3. |
| Footer | 11.5px, color ink3. 1px rule above it, then 10 of space. |

At 358 wide the canonical four-row card is 330 tall and the three-row card is 280 tall. Content starts 19 from the top edge, each row is 36 tall with 14 between rows, and the footer rule sits 14 below the last bar.

Type: the system sans-serif stack for text and a monospaced stack for numbers (JetBrains Mono, then SF Mono, then the system monospace). Faces differ by platform, so compare layout and weight, not letter shapes. The reference images were rendered in Chromium on Linux.

## Colors

| Prototype name | Used for | Value | Product color | Dark, on file |
|---|---|---|---|---|
| `--bg` | Ground behind the card | `#F5F5F7` | `--surface-deep` (same) | `#0B0F17` |
| `--card` | Card surface | `#FFFFFF` | `--surface-card` (same) | `#151B26` |
| `--line` | Card border, footer rule | `#E5E7EB` | `--surface-border` (same) | `#283244` |
| `--ink` | Headline, number, label | `#111827` | `--text-primary` (same) | `#F3F4F6` |
| `--ink2` | Tag text | `#4B5563` | `none` (keep #4B5563; the nearest product grey is too faint on the tag fill) | `#C3CAD6` |
| `--ink3` | Kicker, % sign, footer | `#6B7280` | `--text-secondary` (same) | `#97A1B2` |
| `--elev` | Tag fill | `#F0F0F2` | `--surface-elevated` (same) | `#1C2431` |
| `--track` | Bar track | `#ECEEF2` | `--surface-elevated` (#F0F0F2; the difference is not visible) | `#232C3B` |
| `--a` | Bar fill | `#2563EB` | `--series-1` (same) | `#3B82F6` |

Text is always one of the three inks. No text takes the bar color. The coordinator reports confirming this mapping against release `master` at `6c77da6e` on Oct 6; Fable read the main checkout and did not confirm that revision itself. The tag ink has no product name. It is 6.64:1 on the tag fill, against 4.25:1 for `--text-secondary`. The coordinator recommends adding a name for it, `--text-secondary-strong`; that is not yet decided and nothing has been added.

## What the build may change, and what it may not

**Must change from the prototype**

- The number is the Bain Luck blend. The prototype showed venue prices.
- The footer line. "Venue prices: Kalshi" belongs to the prototype. The product's line goes here, in the same style.
- The buttons under the card. Like, Share, Not for me and Details were test instruments. The product's existing card actions apply, with their own icons.
- The whole card is one target. A tap opens the container made for this card. Rows are not separate targets.

**May adapt**

- Card width, to fit the product's column. The card is fluid; it was checked from 340 to 448.
- Font faces, to the platform's system faces, keeping sizes and weights.
- The tag text, to the product's own league or topic name.
- Color names, to the product's tokens, as mapped in the Colors table.

**May not change without Alex**

- Type sizes, weights, spacing, corner radius or bar height.
- The order of parts: header line, headline, rows, footer.
- Row order: highest probability first.
- The number on the left with the small percent sign, and a bar under every label.
- No icons, emoji, chevrons, logos, images, colored text or motion inside the card.
- No ellipsis. Labels wrap.

## The footer line in the product

The selection rule shows the four divisions with the lowest leader probability, out of the divisions that have a blended number, and the card must disclose coverage and ordering. The footer carries it, in the footer style above, on one line.

- All eight qualify: `Bain Luck blend · the 4 closest of 8 divisions`. Accepted by Alex for now.
- Only three qualify: `Bain Luck blend · 3 of 8 divisions`, with three rows. Accepted by Alex for now.
- Four to seven qualify: `Bain Luck blend · the 4 closest of 6 covered divisions` (the count is the number compared). **Proposed, not ruled.** "Of 8" would claim a comparison that was not made.
- Fewer than three: no card, and the feed is unchanged.

All three fit on one line at 340 wide and leave the card height unchanged (see `r3_measure.json`). The headline stays "NFL division front-runners" and does not say "tightest".

## When a number is old

This replaces the old-numbers example in revision 2. The card uses the product's existing age mark and rule (`PriceAgeMark`, `lib/sourceAge`), unchanged. Fable read both files in the main checkout on Oct 6; they agree with the coordinator's description.

- Old means more than six hours for these season-long questions (the "futures" setting). At exactly six hours, or with no usable time, there is no mark. A missing time is not shown as fresh; it is simply not marked.
- The words are the product's: `7h ago`, `yesterday`, `2d ago`. The tooltip and screen-reader text is "Last number:" and the exact time.
- The mark is the product's: a 5px dot and a 10px age, in the muted grey `#9CA3AF`, 4 apart.
- A blended row is as old as its oldest contributing price. This is the coordinator's requirement and Fable agrees with it.

Two states:

- **Every row is old:** one mark at the right end of the footer line, showing the oldest row's age. Rows carry no mark. Card height unchanged.
- **Some rows are old:** the mark sits on each old row, at the right end of its label line. The footer carries no mark. Row height unchanged.

The two placements are Fable's proposal; the rule and wording are the product's. The product's grey is 2.54:1 on white at 10px, which is faint. It is kept so the mark looks the same everywhere; changing it is a product-wide question.

**Loading and errors** come from the feed, not the card: the existing loading placeholders, the existing feed-unavailable notice, and the last good cards kept on screen with a retry note.

## Buttons and Details in the prototype

`context-images/` shows the card inside the prototype page at 390 by 800 and 950 by 1028, with and without Details open. The four buttons (Like, Share, Not for me, Details) sat 10 below the card and were test instruments; the product's existing card actions replace them, with their own icons. Details listed the exact claim behind each row. It is not part of the first slice: tapping the card opens the container instead.

## Fixture data

`roundup-card-fixture.json` holds four cases: canonical (four rows), three (the minimum), long (long headline and labels), extremes (97% and 8%, no tag). The numbers are venue prices from Oct 6, 2:41pm PT, kept as fixed test content. The long and extremes cases are layout tests, not proposed cards.

`roundup-card-fixture-r3.json` adds the three footer lines and three age cases for the canonical card, with "now" fixed at 2026-10-06T21:41:00Z: `old` (all four rows 7 to 8 hours old; footer mark `7h ago`), `mixed` (one row a day old; that row marked `yesterday`), and `edge` (one row at exactly six hours; no mark).

## How a build is checked

1. Render the built card with the fixture data, in light, at card widths 340, 358 and 448, and in windows of 390 by 800 and 950 by 1028.
2. Place each image beside the matching reference image in `reference-images/` (named `proto_<case>_<theme>_<width>.png`, 2x). The product footers and old-number states are in `reference-images-r3/` (named `r3_<state>_light_<width>.png`, 2x; states `all8`, `three3`, `partial`, `old`, `mixed`).
3. Fable lists every difference in position, size, weight, color and wrapping. Positions should agree to within 1 pixel. Letter shapes may differ by platform.
4. Each difference is either fixed or accepted by Alex by name. The card is called faithful only after that.

Passing component tests does not replace this comparison.

## Not covered

- The selection rule itself. The coordinator proposed it on Oct 6 (#10354): the four lowest leader probabilities among qualifying divisions, three if only three qualify, no card below three. This reference covers the three- and four-row states that rule produces.
- The container's layout, and the card it shows for each division. Alex said "an event card for each item". The coordinator reports that a division is a season-long question, so the product's familiar card for it is the futures card, not the game card. Which card is used is Alex's call and is not designed here. The coordinator also reports that container cards read one venue today, so they must be given the same blended number as the round-up.
- The iPhone app. This reference is for the web card.
- Wording when four to seven divisions qualify, until Alex rules on the proposal above.
- A name for the tag ink in the product's color set.

## Files

In `fable-nfl-division-roundup-design-20261006-r3/`: everything from revision 2 unchanged except `roundup-card-reference-standalone.html` (rebuilt), plus `build_r3.py`, `build_r3_output.txt`, `r3_shots.py`, `r3_measure.json`, `r3_render.html`, `r2_page.html` and `r2.md` (the inputs), `roundup-card-fixture-r3.json`, `reference-images-r3/` (15 images), and a new `MANIFEST.json`.
