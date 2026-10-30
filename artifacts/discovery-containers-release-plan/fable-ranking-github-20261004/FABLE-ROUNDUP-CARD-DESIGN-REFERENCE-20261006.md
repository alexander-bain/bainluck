# Round-up card: design reference

PILLARS: FORMATTING, DISCOVER. Prepared by Fable for Alex, Tue 2026-10-06, 9:35pm PT. For the first comparison slice Alex approved on 10/6: "NFL division front-runners" (#4463, #10354, #10357). A reference for the build, not a ruling and not an assignment.

The rendered reference is `roundup-card-reference-standalone.html` in this folder, and https://claude.ai/artifact/5YKssYU8GQWaRsZ7ttpDCS for Alex. The card rules in it are copied verbatim from the Comparison Feed Two page source (`roundup-card.css`). A check of every element's position and style found no difference between the reference and the prototype (`verify_geom_output.txt`).

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

| Token | Used for | Light | Dark |
|---|---|---|---|
| `--bg` | Ground behind the card | `#F5F5F7` | `#0B0F17` |
| `--card` | Card surface | `#FFFFFF` | `#151B26` |
| `--line` | Card border, footer rule | `#E5E7EB` | `#283244` |
| `--ink` | Headline, number, label | `#111827` | `#F3F4F6` |
| `--ink2` | Tag text | `#4B5563` | `#C3CAD6` |
| `--ink3` | Kicker, % sign, footer | `#6B7280` | `#97A1B2` |
| `--elev` | Tag fill | `#F0F0F2` | `#1C2431` |
| `--track` | Bar track | `#ECEEF2` | `#232C3B` |
| `--a` | Bar fill | `#2563EB` | `#3B82F6` |

Text is always one of the three inks. No text takes the bar color.

## What the build may change, and what it may not

**Must change from the prototype**

- The number is the Bain Luck blend. The prototype showed venue prices.
- The footer line. "Venue prices: Kalshi" belongs to the prototype. The product's own source or freshness line goes here, in the same style.
- The buttons under the card. Like, Share, Not for me and Details were test instruments. The product's existing card actions apply.
- A row opens its question page. The whole row is the target, at least 44 tall including the space around it.

**May adapt**

- Card width, to fit the product's column. The card is fluid; it was checked from 340 to 448.
- Font faces, to the platform's system faces, keeping sizes and weights.
- The tag text, to the product's own league or topic name.

**May not change without Alex**

- Type sizes, weights, spacing, corner radius or bar height.
- The order of parts: header line, headline, rows, footer.
- Row order: highest probability first.
- Whole-number percentages with the small percent sign.
- No icons, logos, images, colored text or motion on the bars.
- No ellipsis. Labels wrap.

**Open choice for Alex: the bar color.** The prototype's bars are blue. On Oct 6 the live site drew the leader's bar green in Discover lists and used green for "Won". Here every row is a leader and none has won. Fable's recommendation is to keep blue, so that green keeps one meaning.

## Fixture data

`roundup-card-fixture.json` holds four cases: canonical (four rows), three (the minimum), long (long headline and labels), extremes (97% and 8%, no tag). The numbers are venue prices from Oct 6, 2:41pm PT, kept as fixed test content. The long and extremes cases are layout tests, not proposed cards.

## How a build is checked

1. Render the built card with the fixture data, in light and dark, at card widths 340, 358 and 448.
2. Place each image beside the matching reference image in `reference-images/` (named `proto_<case>_<theme>_<width>.png`, 2x).
3. Fable lists every difference in position, size, weight, color and wrapping. Positions should agree to within 1 pixel. Letter shapes may differ by platform.
4. Each difference is either fixed or accepted by Alex by name. The card is called faithful only after that.

Passing component tests does not replace this comparison.

## Not covered

- The selection rule for which divisions appear, ties, and what shows when fewer than three qualify. Those are with the coordinator.
- The iPhone app. This reference is for the web card.
- Loading, error and stale states. The prototype had none; the product's existing card states apply and should be shown to Alex before the build is called done.

## Files

`roundup-card-reference-standalone.html`, `roundup-card.css`, `roundup-card-fixture.json`, `reference-images/` (24 images), `measure.json`, `proto_render.html`, `build_ref.py`, `measure.py`, `verify_geom.py`, `verify_geom_output.txt`, `MANIFEST.json`.
