# Futures pages in the event atlas · 2026-11-03 study, iteration 3

PILLARS: FORMATTING / TRUTH / DISCOVER.
SHIP: Alex can review six real futures markets in the atlas's headline, journey, marks and sheet grammar before production adoption.

This study replaces the shipped-page references of iterations 1–2. The date in the directory is the brief's date; implementation/captures continue Nov 4 PT. It is an isolated browser prototype on branch `design/futures-page-proto`, mounted under `frontend/app/kernels-preview/futures/[id]`. It accompanies the atlas's adoption, and does not change the live futures route, APIs or native app. No PR to master.

The current design authority is [atlas-v6's contract](../atlas-v6/COMPONENT-CONTRACT.md). Its hierarchy and semantics outrank later visual studies. The [v473 selection entry](../event-system-adoption-current-v473/README.md) supplies prepared source alternatives. We opened both the v6 local preview and its v473-selected browser source, v471. The temporary servers use copies under `/tmp` so none of the input atlas files or build caches change.

| Preview suffix | Stored shape / selected body | Actual atlas comparison on the left |
|---|---|---|
| `109085` | duel / two-sided dial | v471 `nba-live`, recorded Suns–Spurs |
| `108629` | field / three leaders + full field | v471 `ceremony-hub`, Best Picture before awards |
| `65536371` | quantity / independent threshold profile | v471 `weather-range`, New York before Oct 16 |
| `227` | field + nonexclusive / qualification band | v471 `lacrosse-field`, no-trades qualification |
| `109918` | unshaped / one supplied side, confirmed result | v471 `economics`, reported Unity Bancorp earnings |
| `108645` | duel / settled result + opening | v471 `nba`, final Clippers–Warriors |

`109918?state=open` retains the real archived quote in an explicitly labelled open-state study. `109918?state=open&price=missing` demonstrates No recent price and last-quote details. Neither asserts that the venue is still trading. The default is the later real API settlement. The original settled-on-capture-day specimen remains Georgia, Nov 3; dates are never moved forward to make it “today.”

Screenshots under `screenshots/` include full-page 390px and 1280px views, plus one atlas-left/futures-right composite per example. Composite top row shows the headline/journey; the second shows the scrolled story. The left is the atlas's own software-phone rendering at 393×852, resized to 390px for comparison with runtime status/home chrome cropped. The right is the actual 390×844 futures web viewport. Content, probability precision and eligibility differ between real specimens; these compare shared grammar, not identical data. No UI is reconstructed or image-generated. `compose.py` records the mechanical crops/labels.

Read [SOURCE-CHECKS](SOURCE-CHECKS.md), [ADOPTION-MAP](ADOPTION-MAP.json), [source hashes](source-manifest.json), and the [one-page note](../../../../docs/designs/futures-page-2026-11.md). The map names the actual atlas primitive and prepared native composition per block. It extends the selection process without editing frozen v473. Alternatives are never a union; priced futures adapters remain unimplemented natively.

Taste calls: **G** searchable full-field sheet, or inline expansion — **recommend sheet, shown**. **H** full journey, or recent week — **recommend full journey, shown**. Prior A–F are retired by the atlas grammar.

Verification: build and typecheck pass with the existing 65-error baseline unchanged; 33 targeted frontend checks and four backend startup checks pass. Render/interaction checks and final hosted receipts are retained alongside the screenshots. Native compile/render/VoiceOver/device/TestFlight were not run and are not claimed.

## Hosted screenshot index

| Example | Phone · 390px | Wide · 1280px | Atlas-left composite |
|---|---|---|---|
| Kansas duel | [phone](screenshots/duel-390.jpg) | [wide](screenshots/duel-1280.jpg) | [comparison](screenshots/duel-comparison.png) |
| Governor field | [phone](screenshots/field-390.jpg) | [wide](screenshots/field-1280.jpg) | [comparison](screenshots/field-comparison.png) |
| Denver thresholds | [phone](screenshots/ladder-390.jpg) | [wide](screenshots/ladder-1280.jpg) | [comparison](screenshots/ladder-comparison.png) |
| CFP qualification | [phone](screenshots/participation-390.jpg) | [wide](screenshots/participation-1280.jpg) | [comparison](screenshots/participation-comparison.png) |
| One-leg result | [phone](screenshots/one-leg-390.jpg) | [wide](screenshots/one-leg-1280.jpg) | [comparison](screenshots/one-leg-comparison.png) |
| Georgia settled | [phone](screenshots/settled-390.jpg) | [wide](screenshots/settled-1280.jpg) | [comparison](screenshots/settled-comparison.png) |

One-leg [archived open phone](screenshots/one-leg-open-390.jpg), [open wide](screenshots/one-leg-open-1280.jpg), [No recent price phone](screenshots/one-leg-missing-390.jpg), [missing wide](screenshots/one-leg-missing-1280.jpg), and [last-quote sheet](screenshots/one-leg-missing-details-390.jpg) preserve the extra states.

[Hosted receipt](HOSTED-RECEIPT.json) names the deployed code commit, passing gates and production-file identity. The hosted render, journey, field, qualification and dialog/console JSON files record the actual checks. [Screenshot manifest](screenshot-manifest.json) pins dimensions and hashes. Browser console warnings/errors: none observed. Exact observation, blank-gap refusal, all 24/54 outcomes, enlarged text, Escape and return-focus were exercised. The final protected preview is linked in the single NOW comment; its deployment-scoped capability is not stored in the repository.
