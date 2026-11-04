# Futures page — November 2026 prototype

**Pillar: FORMATTING / TRUTH. Ship:** a futures detail that answers at a glance, with the event page’s hierarchy and a body suited to its market. [Open preview](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/109085). **Preview only**, on `design/futures-page-proto`, under `/kernels-preview/futures/[id]`. Production routes and APIs are untouched. Production payloads were captured Nov 3, 6:33 PM PT; these are dated snapshots, not a live price feed.

**Reused.** `EventHeroProbabilityPair` supplies the hero numeral and boundary marks; the shared duel rounding keeps the hero, split and `ProbabilityBar` coherent. `FuturesChart`, also used by the event composition’s `WinnerEvolutionChart` and `SettledPathChart`, supplies the recorded journey, fixed 0–100 scale, unsmoothed paths, gaps and settlement marks. The chart mounts in the browser to keep timezone labels consistent. `ChartRangeChips` and `ChartFullscreenDialog` retain range selection, Escape and focus return. `outcomeRowVerdict` and `SettledMark` own result language. Existing light surfaces, card radius, type, spacing, accents and site navigation remain.

**New.** A quiet category/status strip, one large answer and its subject, then the native body: duel split; full-field shares with top three and **21 more**; ascending snowfall rungs; independent qualification band; or one supplied outcome. Selecting a row highlights its history; selecting a rung changes its hero and chart. Related markets become a desktop side column and follow the journey on mobile. Attribution stays beside the numbers. Every probability location reserves a quiet ⓘ, including chart readouts; there is no sources sheet. The small preview drawer contains navigation and clearly labelled state studies.

| Example | Production evidence / design consequence |
|---|---|
| Duel · 109085 | Kansas hero uses the existing container’s registered-twin blend, joined by outcome ID. Its history endpoint supplies a single-venue recorded path; the caption declares that coverage. No invented blend history or appended current endpoint. |
| Field · 108629 | All 24 outcomes retained. Top-three rows keep their shares of the entire field; expanding never renormalizes them. |
| Quantity · 65536371 | Six thresholds; only five isolated history readings. The chart slot shows an explicit limited-history state. The served 4-inch / 6-inch chances are **60% / 64%**; the design does not repair their upstream ordering. |
| Participation · 227 | Stored shape is `field`, with `mutually_exclusive: false`. That field’s independent form is the qualification band; the stored classification is not rewritten. No sum-to-100 normalization or combined-probability line. A dedicated participation classification/semantic relation is missing from this detail payload. |
| One leg · 109918 | Production says resolved, with `ungradeable_result`: no winner or loss is asserted. The 58% last reading is labelled historical. Open and settled studies demonstrate the layouts without fabricating an opposing outcome. |
| Settled today · 108645 | Georgia Governor: `settled_at` Nov 3, **6:27 PM PT**, found by a bounded read of stored grades; both outcomes carry `api_settlement`. Winner name leads; rows say Won/Lost; chart retains the completed journey. Detail does not serve `settled_at`; the prototype’s dated capture records it separately. |

**Taste calls for Alex — recommendations, not rulings.**

- **A — answer hierarchy:** large leader + native body (**recommend**) or equal-size outcomes throughout. The leader preserves the event page’s immediate answer; the body keeps context.
- **B — participation:** independent bars in one band (**recommend**) or a plain ranked list. The band makes multiple qualifiers legible without implying a shared pie.
- **C — one-leg settlement:** a result word replacing the percentage (**recommend**) or a result word plus the last percentage in the hero. Historical numbers belong in the journey; an unavailable grade stays explicit.
- **D — related markets:** side column at 1280 px, below the chart at 390 px (**recommend**) or below the chart at every width. The side column uses desktop space without interrupting mobile reading.

**Review controls:** `?state=open` and `?state=settled` are labelled layout studies, never production results. Duel/field studies assume the selected winner; quantity studies assume the selected rung is the last cleared; participation studies assume the twelve leading teams qualify. Assumed results are never added to recorded chart data. Actual settled acceptance is the Georgia page.

Screenshots, the review link and validation are linked in the [evidence index](futures-page-2026-11/README.md) and the single NOW #11852 comment signed **Codex design thread**.
