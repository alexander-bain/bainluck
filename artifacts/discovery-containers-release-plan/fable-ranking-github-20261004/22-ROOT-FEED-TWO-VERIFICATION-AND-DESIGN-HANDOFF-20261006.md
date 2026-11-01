# Feed Two: verification, evidence limits and future fidelity handoff

PILLARS: DISCOVER / FORMATTING / TRUTH. Preservation and evidence only, supporting the existing comparison-card work. No build, dispatch, owner, milestone, label, release-scope, issue-state or gate change. The design checklist below describes evidence for a future build; it is not a new release gate.

## Preservation and replay

Both supplied write-ups and both `.tar.gz` files are preserved unchanged. `ROOT-FEED-TWO-RECEIVED-HASHES-20261006.json` records their bytes and SHA-256. Safely inspected/extracted 65 members in the build archive and 30 in the result archive; no absolute/traversal paths, links or special files. Each archive contains its named directory, so extract into a scratch directory and run within that inner directory.

All **62 build-manifest entries** and **26 result-manifest entries** match bytes/SHA-256. Inspected the supplied scripts before executing. `feed_two_stats.py` reads local retained data; `result_stats.py` reads local exports and rewrites its joined CSV. Ran both with `python3 -I` in their extracted folders; both exited 0 and stdout matched their respective saved output files **byte-for-byte**. Afterward all manifest entries still matched, including the regenerated CSV. Original archives were never modified. No provider fetch, browser execution or production write was performed.

Verified output: 21 final cards; 64 distinct displayed claim IDs from 53 venue-family IDs, no family reused across cards. Already-happened checker: 106 distinct verdicts, 103 open / 2 happened / 1 unsure, with all three non-open IDs absent from final selection. Results: 16 liked / 5 not for me / 3 shared; every card reacted to, every share also liked. Two shares are round-ups (Division Series and NFL awards); Senate round-up is not for me. No detail opens or zero total-dwell records. First-visit medians: 10.3405s liked / 5.524s not for me. Average-rank Spearman first-visit time versus defined reaction score is +0.47; excluding the first and last positions gives +0.27, versus +0.28 with character count. The reaction score is Like + Share − Not for me, not an independent interest measurement.

The first trial had two shares, both round-ups: across trials this is four of five share actions, with the Division Series shared twice. These are repeated actions from one reader, not independent readers or proof of format superiority.

## Qualifications

- Dedup is verified by retained claim and venue-family IDs, not independent semantic equivalence of every proposition. Alex's lack of a repetition complaint is user testimony, not an inference from telemetry.
- Explicit negatives suggest topic preference in this run; wording, subject, format, position, prior exposure and the grading task are confounded. Do not train a “less state politics/less soccer” production rule from these five responses or treat Like as universally uninformative.
- The timer fixes removed zero total times, but the 0.3s first visit still exposes a visit-boundary problem. Correlation signs and nonzero counters do not validate reading-time accuracy. Zero opens cannot establish less doubt; weak destinations, sufficient summaries or the task itself also fit.
- The occurrence check demonstrates that flagged candidates were withheld. `open` is a checker judgment, not certification. The happened verdicts cite National Football Post and The Playlist, with notes attributing confirmation to the Steelers and Marvel; the unsure Gemini item cites a Google blog. This local replay did not independently validate the linked facts against full proposition/settlement rules or establish archived primary-source corroboration. No production occurrence gate was added.
- The small chart/no-chart comparison is confounded by topic. The AGI share is called “tipping point” in the narrative but has internal type `when`; the counts agree.
- The prototype's rendered-test claims remain attributed. There are no screenshot baselines in either archive, and this replay did not rerun the browser/store tests. Prototype desktop evidence is not production or installed-phone acceptance.

## Exact design reference for the implementing lane

The source is **`code/comparison-feed-two.html` inside `fable-evidence-20261006-feed-two.tar.gz`**, SHA-256:

`4548be100d86bbc9a2f591c73414c117c874b26b638fe91a58b1afc56235201e`

Do not reconstruct cards from prose, the result CSV or memory. At future implementation handoff provide:

1. This immutable HTML plus its `cards5.json`, `final5.json`, history fixtures and referenced generation code; all tied to archive/PR hashes.
2. A component/state matrix for the eight admitted prototype types: round-up, movers, new favorite, swing, same-deadline board, `when`/tipping-point, same-odds band and dead heat. Pin representative fixture IDs, exact text/data, row count and chart presence. The fixture is for visual replay, not permission to serve stale prototype prices.
3. A measured geometry/type specification extracted from the source and a mapping to existing production tokens/components. Preserve hierarchy, line breaks, whitespace, bar/tick placement, details and action positions. No silently simplified list, omitted row/context or generic replacement chart.
4. Reference renders captured from the preserved source at the start of the future build, with source hash, viewport, browser/OS/font versions, data and interaction state recorded. The archive currently supplies source and tests, not screenshots.
5. A short deviations ledger identifying each necessary production adaptation, its reason and its visible effect. Material design changes should be explicit in design review, not hidden inside a refactor. Existing product ownership and release acceptance remain unchanged.

### Concrete source details to retain

Line references below are to the preserved 459-line HTML.

- One centered column capped at **30rem**, **16px** outer padding, **34px** between feed items; card radius **16px**, padding **18px 18px 13px**, internal gap **14px** (33, 56–58). No desktop multicolumn breakpoint: at 950px the cards remain a narrow centered column.
- System sans and monospaced tabular number stacks; headlines **23px**, **19px** when longer than 44 characters, row probabilities **20px**, paired probabilities **30px** (10–11, 34, 62–81, 299). Font metrics/wrapping are part of the reference.
- Quiet uppercase kicker/tag, numeric column **3.1rem**, flexible row text, **6px** bars / **8px** paired bars; prior-value ticks, dated movement text, blue/amber quantity legends, “level with” dead-heat language and remaining-field mass (64–98, 275–305).
- Inline SVG charts: clock **320×138**, historical duel **320×132**, responsive width, fixed **0/50/100** grid, actual timestamp x positions, straight connectors, endpoint dots and collision-adjusted labels (213–273). Preserve truthful gaps and accessible names; no smoothing or rescaling the probability axis.
- Like/Share/Not for me **outside the card**, on the page background, wrapping pill controls with **40px** minimum height; Details aligned right, switching to Hide, opening fine print (145–158, 386–402). Fine print carries proposition, components, prior observations, IDs and qualifications (308–329). Validate closed/open, pressed/unpressed and keyboard-focus states.

### Deliberate production adaptations

- **Light-only production**: use the prototype's light rendering as the reference and map to repository design tokens. Its dark palettes remain experimental evidence, not a production theme requirement.
- **Real supported product quantity**: the page explicitly uses venue prices (169). Production must use its actual supported probability, contributors and dated history; never place a venue-only chart beneath a blended number. Truthful missing/refused/stale states are required where the attractive fixture cannot be supplied.
- The clock chart starts with a synthetic “now, 0” vertex (225). That vertex may be used only if the proposition/current-state evidence supports it and it is not passed off as an observed market quote. Any needed correction must be visible in the deviations ledger.
- Sharing must reflect actual share/clipboard success or cancellation, not blindly copy the prototype's stored-toggle behavior. Experiment intro/save banners and behavioral measurement are not automatically product features; “checked against news today” cannot become an unsupported product guarantee.
- The standalone file lacks a viewport meta declaration. Future mobile comparison must explicitly normalize viewport configuration; do not reproduce a broken mobile viewport to match an accidental browser default.

## Evidence that the built card matches

At the future build review, attach **reference and implementation screenshots side-by-side and as overlays** using the same frozen fixtures, font environment, scroll position and state at **390×800** and **950×1028**. Include per-card crops plus whole-feed context; cover every admitted archetype, chart/no-chart variants, short/long labels, varying row counts, near-colliding chart endpoints, probabilities near 0/100, Details open/closed and action/focus states. Pixel diffs locate drift but a human visual read decides whether typography, hierarchy and chart labels still match; do not use an arbitrary universal pixel threshold to hide layout changes.

Add short interaction recordings for Details, reaction behavior, real sharing, navigation/Back and scroll preservation. Semantic/DOM tests protect exact values, accessible names, state transitions, fixed axes and no horizontal overflow, but cannot establish visual fidelity alone. Separately show safe live-data/no-history/refused states; synthetic fixture screenshots are design evidence, not production truth or installed-phone acceptance. No additional approval request or new release gate is created by this proposed handoff.

## Issue routing

One short evidence comment each on #5105 (signal limits/topic hypothesis), #10346 (round-up sharing and subject choice), #10356 (dedup result and Alex's report), and #10353 (occurrence-check verdicts/removals/sources). No new issue or changes to existing delivery metadata.
