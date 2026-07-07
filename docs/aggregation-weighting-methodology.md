# Source-Weighting Methodology — earning the blend weights

Written 2026-07-06 (Fable, at Alex's request: *"I'm not positive how our current weighting of the sources was chosen, but I doubt there was much science to it."*) Correct doubt: the weights in `config/win_prob_sources.py` (betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8) are hand-set priors with no recorded empirical basis. This doc defines how to replace them with **weights earned from measured predictive skill** — and the guardrails that keep the exercise honest.

## Principle

A source's weight should equal its demonstrated ability to predict outcomes, measured on the same events, at the same moments, against the same ground truth. Nothing else — not intuition about "books are sharp," not vendor prestige. The machinery to measure this already exists: `win_prob_snapshots` (multi-source, timestamped) × resolved events is a large labeled corpus.

## Method (4 steps, each independently valuable)

**1. Build the eval corpus (read-only lane work).** Sample aligned observations: for each resolved event, at fixed checkpoints (e.g. T-24h, T-1h, and in-game at 75%/50%/25% of elapsed time), take each source's probability from `win_prob_snapshots` (nearest snapshot within a staleness window; none → source absent at that checkpoint). Label = final outcome. **Apples-to-apples rule: sources are only compared on checkpoints where BOTH are present.** Coverage differences are a separate (also useful) statistic, never conflated with skill.

**2. Score each source.** Brier score and log-loss per source, segmented by sport-tier × game-phase (pregame / early / late). Report with n and CIs. This alone answers "is ESPN actually worth 1.5?" and is publishable on the source-intelligence admin page.

**3. Fit the blend.** Log-odds pooling: `logit(p_blend) = Σ wᵢ · logit(pᵢ)` over present sources, weights ≥ 0, renormalized over the present set (matches the current aggregation shape — verify against `utils/aggregation.py` before assuming). Fit w by minimizing log-loss on a training window; validate **out-of-time** (train on months 1–4, test on month 5+ — never random split; market regimes drift). Segment weights by sport-tier × phase with shrinkage toward the global fit where a segment is thin (< ~500 resolved events). Baselines to beat: current hardcoded weights, best-single-source, equal weights.

**4. Ship as config + harness, not as a one-off.** Fitted weights land in `win_prob_sources.py` with the fit date and eval metrics in comments; the fitting script lives in `scripts/` (like `calibrate_interestingness.py`) and re-runs quarterly. **Promotion gate: new weights must beat current weights on held-out log-loss AND not degrade blend ECE — otherwise keep current and report why.**

## Honesty guardrails

- **Correlated sources / double-counting:** Kalshi and Polymarket prices partly incorporate the books already. Fitted log-odds weights handle correlation implicitly (a redundant source earns a small weight), but check the pairwise residual correlations and report them — if two sources are near-duplicates, cap the pair rather than letting the fit split arbitrarily.
- **Staleness:** a source's weight applies to a *fresh* reading. Decay or drop a source past its staleness window (per-source windows already exist in the stale-snapshot filtering) rather than blending old numbers at full weight.
- **Don't overfit segments:** more segments always fit better in-sample. The shrinkage + out-of-time gate is the defense; if a segment's fitted weights don't beat global weights out-of-time, the segment doesn't deserve its own weights.
- **Selection honesty:** evaluate on ALL resolved events with source coverage, not the ones where the blend looked good. Same freeze-then-measure discipline as the D2 liquidity rule and the Instant Answers benchmark.

## Routing

Eval corpus + scoring (steps 1–2) = read-only lane or ops analysis — stageable now. Fit + config change (steps 3–4) = Lane-1 code queue. **The weight flip itself is Alex-gated** (it moves every probability on the product); the decision packet = the step-2 table + the step-3 out-of-time comparison. Related: #843 (ESPN pre-game predictor as a new source) should enter at a *fitted* weight from this harness, not a hand-set one — that's the first natural use.
