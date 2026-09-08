# BainLuck Discover: a product plan for a morning habit

Prepared for Alex Bain · September 8, 2026

## Product decision

Make Discover a living briefing about what changed, what is coming, and what is unexpectedly connected. Each card should deliver an insight before asking for a tap. The unit of editorial selection should be a story with evidence; one story can contain several markets.

The promise: **“Open this for three minutes and understand something you did not understand yesterday.”** A successful session can be short. Optimize for worthwhile returns and useful understanding, not the longest possible scroll.

This is a proposal, not an implementation or a measured 10× lift. Code observations refer to the checkout audited at `9894d15d7533908c4c8562735a0bf4e03cc9437f`. I additionally read relevant GitHub issue discussions, sampled current Discover API output, and inspected four recent marketing emails. I did not census the complete current Kalshi and Polymarket catalogs, inspect the deployed Gmail Apps Script configuration, query private production settings, or measure email-driven ranking lift.

## 1. What is already built, and why it does not yet add up

| Existing foundation | What I verified | Product implication |
|---|---|---|
| Card archetypes | The classifier emits binary probability, threshold heatmap, outcome distribution, probability timeline, and resolution recap. It also handles date buckets and comparison themes. | Consolidate and strengthen the semantic contract; avoid starting another disconnected taxonomy. |
| Grouping | Comparison, story/theme, awards, and biggest-swing assemblers run in the Discover composition pipeline. The current theme renderer previews up to five market rows and expands to full member cards. | A grouped container is a useful foundation, but still needs a shared question and a takeaway to become an editorial story. |
| Generalization | Rulings 143 and 145 explicitly demand combining same-question/different-subject markets and automatically detecting the family. | Your intuition is already documented. Completion means a new compatible subject joins without a new bespoke card. |
| Reasons | The feed has deterministic reasons and context text. | Text presence is insufficient. Judge whether the reader understands why this is relevant now. |
| Curation | The email loader, daily LLM review, external-curator recall, and direct curator adjustments are distinct paths. | Trace each path through to the served page; do not equate rows ingested or proposals written with a better feed. |
| Feed conventions | Likes, soft “less like this” gestures, sharing, expansions, first-run orientation, pagination, and an end state already exist. | Improve semantics and reliability before adding duplicate controls. |
| Measurement | Served-slate comparisons exist. Issue #1815's August 18 evidence shows composition can absorb or amplify earlier ranking changes. | Judge complete served editions, after grouping and composition, and then verify both clients actually render them. |

Sources: [card archetypes](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/utils/discover_card_archetypes.py), [bundle assembly](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/utils/discover_bundles.py), [theme renderer](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/frontend/components/discover/ThemeBundleCard.tsx), [ruling 145](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/docs/rulings/145-a-template-family-is-one-card-and-the-system-finds-it.md), [served-slate evidence](https://github.com/alexander-bain/bainluck/issues/1815#issuecomment-5332194660).

A September 8 request to the [public Discover feed](https://api.bainluck.com/api/feed?limit=20&offset=0) returned 20 items: 12 futures, seven bundles, and one concept. Examples included “Tracked by 2 sources,” “AI” with “2 related markets,” and an iPhone release card describing movement “from opening.” This is one API snapshot, not a rendered-UI census or a return-frequency study. It illustrates the editorial gap: provenance, a category, or lifetime movement can be accurate without answering why the story deserves attention this morning. The cached request reported 9.71 ms of feed processing; that is not end-to-end loading time or a percentile.

## 2. The experience to build

### A finite briefing with room to explore

Start with roughly 8–12 strong stories, fewer when evidence does not support more. Treat that range as a design hypothesis to test, not a quota to fill.

1. **Since your last visit:** significant developments in stories the reader follows or has actually seen. Preserve the comparison baseline for the visit.
2. **What matters today:** consequential fresh developments and upcoming catalysts, including stories outside the reader's usual interests.
3. **Something you might have missed:** an insightful comparison or unexpected connection. Reserve room for discovery without filling it with random novelty.
4. **What happened next:** close the loop on a previous forecast or followed story when a confirmed result becomes available.
5. **A real stopping point:** “You’re caught up on this edition,” followed by optional exploration and the next known scheduled catalyst. Do not promise an update unless one is scheduled or already available.

These are editorial jobs within one coherent feed, not five new navigation tabs. Start with light section labels and a chronological reading order on mobile. Prefer one main reading column on desktop with an optional compact watchlist; a grid of equally loud cards makes editorial priority harder to perceive.

Returning users should not have to distinguish meaningful changes from cosmetic reshuffling. Keep the reading position stable. Accumulate new stories behind a “3 new updates” control; insert them when the user asks. Reopening a story should show the delta from its last substantive version, not reset its age because its copy was regenerated.

### Every card must answer four questions

| Reader question | Visible treatment |
|---|---|
| What is the story? | A specific headline containing the interesting development or comparison. |
| What should I learn? | One dominant answer: a movement, a field, a distribution, or a compact comparison. |
| Why is this here now? | A concrete reason: changed since last visit, new favorite, release this week, confirmed result, or newly relevant connection. |
| How current and well-supported is it? | Observation time and a quiet evidence affordance; limitations when material to interpretation. |

Two different “whys” must remain separate. **Why shown** is a selection fact (“up 12 percentage points since yesterday”). **Why it changed** is a causal explanation that requires evidence. A price move alone proves the former, not the latter. When the cause is unknown, say so plainly and still show a worthwhile move.

Use percentage points for changes in probability. Do not lead with a large relative percentage increase caused by a tiny baseline. A movement “since market opening” belongs in longer-term context with a dated baseline; it should not masquerade as today's news.

### Standard interaction vocabulary

- Tap the headline or chart to open the story; return to the same feed position.
- Expand a group inline to reveal its members while retaining the shared question.
- Follow a story or entity to receive meaningful updates. Saving a card preserves a reference; these are different intentions.
- Keep “less like this” as a soft preference, with an undo. Separate it from explicit topic muting and “I’ve already seen this.” Do not turn dislike of one story into a silent ban on an entire category.
- Share a story with the observation time and context intact. A shared historical snapshot and the current live view should be distinguishable.
- Offer visible buttons for essential actions; swiping is an optional shortcut. Charts must work without hover and must not fight horizontal swipe gestures.
- Use readable type, stable image dimensions, large touch targets, accessible chart summaries, and labels in addition to color. Show uncertainty without burying the main answer under diagnostic badges.

Following, saving, and story-level context are familiar conventions; Google News provides a relevant example of separating personalized discovery from expanded story coverage. This is a useful precedent, not proof of fit for BainLuck. [Google News documentation](https://support.google.com/googlenews/answer/9005601?co=GENIE.Platform%3DDesktop&hl=en-SG).

## 3. A finite visual grammar, with explicit semantic boundaries

Separate three dimensions that currently risk being conflated:

**Market semantics × story angle × composition.** A sports playoff question and a product-launch question can share a probability primitive. The same primitive can tell a movement story today and a resolution story later. A movie comparison can compose several primitives into one card.

### Market primitives

| Primitive | Question shape | Rendering | Required safeguard |
|---|---|---|---|
| Binary | Will X occur under specified rules? | Clearly labelled probability and optional history | Preserve the affirmative/negative meaning, deadline, and resolution condition. |
| Exclusive field | Which one of these outcomes wins? | Ranked bars; compact leaders plus accessible full field | Only present a whole summing to 100 when outcomes are exclusive, exhaustive, and coherently measured. |
| Independent set | Which of these things will occur? | Separate labelled bars or rows | Multiple outcomes may happen; never normalize the set into a single race. |
| Ordered quantity | How much, how many, what score? | Disjoint buckets or a threshold curve, explicitly distinguished | Units and boundaries must agree. Overlapping “above X” probabilities are not disjoint buckets. Do not invent an expected value from insufficient thresholds. |
| Time to event | By when, or in which period? | Ordered dates with probabilities | Distinguish cumulative “by” from disjoint “during”; use explicit calendar anchors. |
| Conditional or compound | If A, then B? A and B? Which happens first? | Labelled branches, paired scenarios, or a compact sequence | Show conditional/joint probabilities only when supplied by valid evidence or a validated model. Marginal probabilities alone cannot produce them. |

Head-to-head games specialize the binary/field primitive with score, clock, and participant identity. Playoff paths specialize ordered milestones with conditional meaning. Resolved cards are a lifecycle treatment applied to these primitives, not another incompatible market model. A faithful generic question-and-answer fallback remains available for unclassified cases.

These six primitives are a proposed grammar for the shapes inspected, not a claim that every live contract on both platforms has been classified. Validate coverage with a catalog audit stratified by provider, category, series family, lifecycle, and volume bands. Record ambiguous cases explicitly; do not auto-promote a guessed shape. Use provider metadata and rules before title regex. Kalshi exposes structured strike types, boundaries, timing, rules, and compound-market legs in its market schema. [Kalshi market API](https://docs.kalshi.com/api-reference/market/get-markets).

### Compositions

| Composition | What makes it interesting | Example |
|---|---|---|
| Change | A material shift, crossover, or unusual reversal | A team's playoff outlook has changed since the reader last checked. |
| Peer comparison | Same question and measurement across subjects | Four upcoming films compared on their chance of clearing the same critic-score threshold. |
| Story package | Several distinct questions illuminate one subject | A game's launch timing, reception, sales, and awards prospects. |
| Milestone/path | Progress toward a meaningful destination | Qualifying, advancing, and winning, with the correct relationships. |
| Catalyst preview | Something scheduled may change the outlook | A release, final, launch, or announcement due today. |
| Connected consequences | A development is relevant to another measurable question | A film's opening weekend and its awards outlook. |
| Resolution/rewind | A followed uncertainty now has an outcome | What happened, and what the forecast said at a fixed prior time. |

Ship three templates first: **change, peer comparison, and story package**. Add catalyst and resolution treatments next; develop connected consequences once their evidence path works. This is deliberately fewer visible templates than the full grammar permits.

### Grouping must increase understanding

A group needs a sentence explaining why the members belong together. “Awards Season · 5 related” is navigation. “Which of this month's releases is best positioned for awards attention?” is an editorial question.

A comparison key should include question family, units, timeframe, rules, and subject cohort. A shared keyword or provider event identifier is insufficient. Four films must use a common score definition, release cohort, and comparable observation times. If only thresholds are known, compare a common threshold; do not manufacture four precise projected scores.

Generate group candidates **before final top-N selection**. Four individually unremarkable films can form a fascinating comparison; a ranker that only groups already-selected hits will never discover it. Score the group for what it teaches, not the sum of its members' scores, which would reward large bundles simply for being large. Once a group earns a slot, avoid repeating its unchanged member cards elsewhere in the same edition. Keep all legitimate outcomes accessible inside the group.

## 4. The email experiment: turn borrowed taste into a measurable learning loop

### Findings from the current implementation

The checked-in Apps Script uses the `Polymarket` label, reads at most 20 threads, skips threads labelled processed, extracts from plain text, and emits `source: polymarket`. Processing only the newest 20 threads can starve older unprocessed ones. Marking a whole thread processed can skip later messages added to it. The loader explicitly rejects non-Polymarket source rows, applies a minimum interestingness score, and deduplicates by normalized market name. Repeated coverage of a continuing story can therefore lose temporal meaning unless occurrences are retained separately. These are code observations; I have not inspected the deployed script or the label configuration. [Script](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/scripts/polymarket_email_parser.gs), [loader](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/utils/polymarket_email_ground_truth.py).

Four email bodies inspected included Kalshi's September 4 GTA package, August 28 Bond package, September 8 week-ahead edition, and Polymarket's August 28 daily briefing. The relevant lesson is format: deep dives, several questions about one entity, upcoming-event rundowns, and multi-story briefings. Some Kalshi material uses linked images for market information, making plain-text percentage extraction insufficient. These emails were inspected as editorial examples, not verified reporting or current probability sources. [GTA email](https://mail.google.com/mail/#all/1a06dd9c001fe197), [Bond email](https://mail.google.com/mail/#all/1a04a20429e5b662), [week-ahead email](https://mail.google.com/mail/#all/1a0819a3359e7837), [daily briefing](https://mail.google.com/mail/#all/1a048b2e55d94243).

The daily review code writes proposed decisions from email misses, while external-curator recall and direct curator score adjustments have other consumers. Finding the review path alone does not prove email influence is zero. Alex already approved bounded automatic curation on August 3; the plan should complete that route and measure its contribution instead of reinstating a daily approval queue. [Review code](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/tasks/enrich_markets.py), [approval](https://github.com/alexander-bain/bainluck/issues/1533#issuecomment-5172884102), [shared intake #1534](https://github.com/alexander-bain/bainluck/issues/1534).

### Proposed intake

1. Inventory actual sender/publication/template combinations. Include Kalshi and Polymarket newsletters, deep dives, alerts, and roundups; classify account notices and promotions separately from editorial candidates.
2. Process and checkpoint individual message IDs with complete pagination. Preserve each editorial occurrence, source, publication time, section, and canonical links.
3. Parse MIME/HTML structure and links, with text fallback. Resolve tracking links safely. Treat image-only content as an explicit extraction gap, using image extraction only when necessary. Fetch current probabilities from the underlying market source, never reuse emailed prices as live values.
4. Extract stories with zero, one, or several linked markets: editorial angle, asserted facts, evidence links, catalyst, expiry, and suggested composition. Separate the source's assertions from verified facts.
5. Route a normalized record through the existing shared intake. Include match confidence and explicit no-match/unsupported outcomes. Low-confidence cases enter an exception queue; routine valid cases need no daily human gate.
6. Trace the funnel: received → recognized → parsed → linked → eligible → group formed → ranked → served → rendered → useful. Count both losses and their causes per format.

### Three separate uses of the corpus

| Use | How it helps | What it cannot prove |
|---|---|---|
| Editorial input | Seeds timely candidates and narrative structures | Independent discovery of the same stories. |
| Coverage benchmark | Reveals stories and formats BainLuck failed to capture | That every marketed story deserves a feed slot, or that unmentioned stories are bad. |
| Held-out evaluation | Tests future discovery and presentation without access to the held-out picks | Long-term user value without human or behavioral validation. |

For independent-discovery evaluation, freeze a candidate edition at the intended morning cutoff before the held-out email arrives. Compare later editorial selections to the information actually available at cutoff; label later-breaking stories ineligible for that recall calculation. For assisted-feed evaluation, allow current email input but compare the resulting edition blindly with the current feed and a simple email-assisted baseline. Use rolling time holdouts and remove duplicate/syndicated story families across partitions. Preserve a separate set of interesting stories absent from both newsletters so novelty has a chance to win.

Evaluate the **story and angle**, not just whether a market title matched. Ask whether the reader receives the same insight, correct grouping, evidence, and current numbers. Display an ablation showing which served stories changed with curation enabled versus disabled, holding data and time fixed. If candidates change but the page does not, investigate the composition boundary rather than declaring success.

Treat marketing language as examples to critique. Borrow specificity, pacing, and story construction; independently verify claims and write original copy. Do not inherit sensationalism, sales incentives, or unsupported causal explanations.

## 5. Finding interesting material automatically

Candidate generation should consider several kinds of new information: material movement, a new leader, an upcoming catalyst, a confirmed resolution, a newly available market, a coherent peer comparison, or a relevant follow-up. A fresh observation of an unchanged probability is healthy data, but usually not a new story. Conversely, a story can become relevant today without a probability moving: the premiere or final is tomorrow.

Require eligibility before ranking: correct identity and lifecycle, usable and current observations, coherent question semantics, and evidence adequate for the claims. Detect noise and discontinuities such as a new provider entering the blend, an illiquid print, or a contract rollover. A large numerical change caused by those mechanisms is not automatically a meaningful real-world development.

Then rank stories using significance, information gained since last exposure, personal relevance, timeliness, evidence strength, and contribution to the edition's diversity. Penalize redundancy and unsupported thin stories. Preserve some broad-interest discovery rather than letting past clicks permanently narrow the feed. Start with interpretable signals and qualitative comparisons; avoid another unvalidated weighted score being mistaken for a solved editorial problem.

Use models for proposing connections, drafting concise language, and recognizing structures. Use deterministic checks for identity, numbers, timestamps, comparison compatibility, and lifecycle. All enrichment runs asynchronously. A useful factual template remains publishable when a model is unavailable.

### Connected consequences can be the distinctive feature

Start with a bounded set of relationships: film → cast/awards, team → standings/playoff path, and product → company/launch/reception. For a candidate connection, require canonical entities, a timestamped development, a plausible relationship, and independently verified state of the related market.

Offer three honest treatments:

- **Established mechanism:** explain it when supported by rules or a validated calculation.
- **Related movement:** show that two things changed around the same time, with sourced context and explicitly limited causal confidence.
- **What to watch:** explain the potential connection when no measured reaction exists; omit an invented effect size.

For the opening-weekend example, verify the gross and what expectation it missed, identify the relevant film/person/award/season, and use comparable before-and-after observations. Do not state that revenue caused an awards move merely because the narrative sounds plausible. If the relevant awards market is unavailable or stale, present a sourced watch item or withhold the quantitative consequence.

## 6. Speed and freshness are one product contract

Build on the existing feed cache, boot fetch, warmers, and bounded fallbacks. Precompute story candidates, evidence summaries, and shared editions; apply lightweight user-specific selection at read time. No model calls, remote article extraction, or fresh provider fan-out should block the initial feed response.

Track separate clocks: source observation, evidence publication, material story update, edition build, and viewer's last exposure. A cache rebuild must not rejuvenate old evidence. Invalidate or expire copy when its numerical basis or explanation no longer holds. Refresh in place without changing what “since your last visit” refers to mid-session.

Set freshness budgets by story type and lifecycle. A live game requires much tighter timing than an awards outlook. A useful opening policy is a measured, agreed budget per class with the oldest required supporting observation exposed internally. Missing or expired required evidence blocks a “current” claim. Cache failure must lead to a bounded last-good view or an honest partial/unavailable state.

Proposed initial performance targets, to validate on representative devices and networks: useful first content p75 ≤1 second on warm return and p75 ≤2 seconds on cold mobile open; interactive actions acknowledged within 200 ms locally. Record p95 and failure rates too. These are proposed targets, not current results. Measure from user action to visible useful content, separated by web/native, signed-in/anonymous, cold/warm, and network class.

## 7. A small evaluation system that actually changes decisions

The primary early question: **“Was this edition worth opening?”** Ask Alex and a small set of intended readers to judge complete current-versus-proposed editions blindly. Use the same cutoff, observation snapshots, and user interests. A small panel provides directional evidence, not population-level significance.

| Measure | Decision it supports |
|---|---|
| Worthwhile stories per first 10 | Whether the page delivers information or fascination. Reviewers can choose neither; no forced positive labels. |
| Five-second comprehension | Can a reader state the question, takeaway, and why-now reason? |
| Material novelty on the next visit | Did the reader get new information, rather than new order or rewritten text? |
| Supported explanation and number accuracy | Can every material claim be traced to the correct, time-appropriate evidence? |
| Stale, duplicate, and incompatible-group incidence | Trust gates; review by story type and client. |
| Curator funnel and held-out story/angle recall | Whether expanded email coverage creates useful discoveries, and where it fails. |
| Source-independent finds | Whether BainLuck discovers worthwhile stories beyond the newsletters. |
| Useful-content timing and interaction reliability | Whether the product is fast in the situations readers actually experience. |
| Voluntary next-morning return and user-rated value | Whether the habit is forming; distinguish ordinary returns from notification-driven opens. |

Do not use CTR alone. An informative card may answer the question so well that no click is needed. Dwell can measure confusion. Forecast calibration belongs in separate outcome-based evaluation over many resolved questions; one surprising result does not establish a bad forecast.

A practical starting gate: seven consecutive reviewed editions, no known critical factual/grouping defects in the reviewed cards, and at least eight of the first ten judged worthwhile on most review days. Predeclare the exact interpretation and compare against today's baseline. This is a candidate product bar, not evidence that it has already been met. Test follow-up editions as well as first visits.

## 8. Ship sequence

Organize one Discover initiative around the complete reader journey. Each slice includes data, composition, rendering, and live evidence. Link the existing issues rather than creating separate epics for each layer. Assign one accountable owner through production verification; other owners can contribute without splitting the definition of done.

| Slice | Deliverable | Acceptance evidence |
|---|---|---|
| 1. The first five cards | A working thin slice with change, peer comparison, and story-package templates; trustworthy identity/freshness; why-now text; fast initial rendering | Five real stories make sense without tapping, with checked evidence and no cross-screen disagreement. Implement group selection early enough for individually weak members to form a strong card. |
| 2. The editorial intake | Message-level, multi-format Kalshi/Polymarket ingestion using shared curation intake; bounded use in the feed; extraction exceptions | Every sampled supported message is accounted for; dedup/replies/image-heavy formats tested; a specific input can be traced through to a rendered card or a reason it did not appear. |
| 3. The second open | Stable story IDs/versions, exposure memory, meaningful update reasons, session-stable order, follow/less-like controls | Return later to genuinely new information when it exists; no relabelled repeats; updates do not move the current reading position. |
| 4. The edition | Broaden to a finite briefing; add catalyst and resolution treatments; compare final rendered editions | Blind review improves against the same-data baseline; first-ten quality and speed meet the agreed bars on both clients. |
| 5. The distinctive connection | First supported connected-consequence family, beginning with film/awards or sports/playoff relationships | Readers understand the connection; every factual claim is supported; no invented causal effect or conditional probability. |

Start with an evidence inventory and reference specimens measured in days, then make each slice a bounded ship. Calendar estimates require agreeing engineering capacity and confirming which existing paths are production-ready. Do not wait to classify every market in existence before shipping the first three templates.

Existing work to reuse: [curation #1533](https://github.com/alexander-bain/bainluck/issues/1533), [intake #1534](https://github.com/alexander-bain/bainluck/issues/1534), [source backlog #1537](https://github.com/alexander-bain/bainluck/issues/1537), [served evaluation #1815](https://github.com/alexander-bain/bainluck/issues/1815), [composition measurement #1923](https://github.com/alexander-bain/bainluck/issues/1923), [labeling queue #666](https://github.com/alexander-bain/bainluck/issues/666), and [native bundle rendering #1886](https://github.com/alexander-bain/bainluck/issues/1886). References identify relevant work and lineage, not assertions that every issue remains unfixed. Verify deployed behavior before implementing its proposed fix again.

## 9. Underappreciated opportunities

**Memory is part of the product.** “Here is what changed in the story you cared about yesterday” is more personal and useful than a category preference. Reuse one story history for Discover, following, notifications, and any digest so those surfaces cannot disagree.

**Resolution closes an open loop.** Save the forecast at a meaningful pre-event cutoff and revisit what happened. This creates continuity and teaches how probabilities behave, without turning every forecast into a binary right/wrong verdict.

**Editorial restraint is a feature.** A quiet day should produce a shorter edition or a timely explainer. Filling empty slots with weak cards trains users to ignore the next card.

**A source gap can itself be informative.** “There is no reliable current estimate” is occasionally worth saying about an important followed story. It is not permission to fill the feed with missing-data notices.

**Personalization needs an off switch and an exploration budget.** Let readers edit their interests and escape mistaken inferences. Preserve access to important general stories and a small amount of pleasant surprise.

**Distribution should reuse the same edition.** An optional morning digest, widget, or meaningful-change notification can help establish the habit after the feed earns it. Respect opt-in, local time, quiet hours, and notification limits. Do not build a separate editorial engine for each delivery channel.

**An approachable voice is useful; manufactured drama is expensive.** Prefer specific, curious language with modest wit. The payoff is understanding something surprising, not needing to click to discover what the headline meant.

**The finite asset is your attention.** Review complete editions and a few recurring failure families. Measure engineering progress as accepted, reliable reader experiences—not parser throughput, labels collected, issues closed, or the number of newly named primitives.
