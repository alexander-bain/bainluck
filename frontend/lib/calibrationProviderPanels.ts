/**
 * Provider panels for the calibration **By Source** section.
 *
 * WHY THIS EXISTS (UX-P078, Alex ruling 2026-08-14(b) item 3).
 *
 * `lib/calibrationProviders.ts` collapsed the *Source Comparison table* to one
 * row per provider (queue 316 item 2 / CAL-P050). It deliberately did NOT
 * collapse **By Source**, and wrote that decision down: the per-source panels
 * were named as the "annex" where the sportsbook shapes break apart, kept
 * separate because the prediction markets have no equivalent split and a
 * per-shape column present for one provider and blank for the others "reads as
 * missing data rather than as a difference in what the providers publish".
 *
 * That reasoning is sound and it is **OVERTURNED for the presentation**, by the
 * owner, later and specific:
 *
 *   > "Alex explicitly asked on 08-13 for the sportsbook shapes combined in By
 *   > Source. CAL-P050's written keep-separate decision is OVERTURNED for the
 *   > presentation: three provider rows, with the shape-by-shape breakdown
 *   > preserved as an expandable detail under Sportsbooks so the annex's stated
 *   > purpose survives inside the provider frame."   — Alex, 2026-08-14
 *
 * Handled per **ruling 055** (a conflict resolution that changes a decision is
 * a decision): the overturned reasoning is quoted above rather than deleted,
 * the later-and-specific authority is cited, and the reversal is posted to the
 * CAL-P050 record and to #1865. The annex is not cut — it MOVES, from a
 * separate section into a disclosure under the provider it describes. Its
 * stated purpose (the shapes are visible, separately, with their own numbers
 * and their own drill-in) survives intact.
 *
 * ── THE RULING 003 TENSION, RESOLVED IN THE OPEN ─────────────────────────────
 *
 * Ruling 003: *a panel's ECE is the SERVER's `by_source` number, rendered; a
 * client that recomputed it here would be the ruling's own named failure — the
 * same calibration number derived twice, guaranteed to drift.*
 *
 * The payload publishes ECE **per source key**. It publishes none for a
 * PROVIDER, so a Sportsbooks panel has no server number to render. Three ways
 * out, and only one of them is honest:
 *
 *  1. Recompute the provider ECE here → exactly what ruling 003 forbids.
 *  2. Render no ECE on the Sportsbooks panel → the reader has just read
 *     "Sportsbooks … 4.2pp" in the table directly above; a blank beneath it
 *     reads as missing data, which is gotcha #53's shape in a panel frame.
 *  3. Render the number the page has ALREADY derived once — `providerMetrics`,
 *     the same memo Source Comparison renders — and label its basis.
 *
 * **This module takes (3), and it does not launder it.** `publishedEce` and
 * `pooledEce` are separate inputs that can never be confused, the output states
 * its own `eceBasis`, and the page publishes that basis as a `data-` attribute
 * so the browser rail can tell a server number from a pooled one without
 * reading our prose.
 *
 * Ruling 003's actual failure mode is DRIFT between two independent
 * derivations. There is one derivation here: `providerMetrics` is computed
 * once and rendered twice. The guard that makes that true rather than merely
 * intended is a pairing assertion — *the Sportsbooks panel's ECE is identical
 * to the Sportsbooks row's ECE* — which makes disagreement unrepresentable
 * instead of merely discouraged. (UX-P075 proved twice in one cycle that a
 * pairing assertion beats a ban: a ban is satisfied by deleting the word.)
 *
 * ── #7422: THE SAME RESOLUTION, FOR THE COHORT THE SERVER NEVER MEASURED ────
 *
 * The reasoning above was written about the Sportsbooks panel and was scoped
 * to it, on the premise that a single-shape provider always HAS a server
 * number to render. That premise is false under the cohort toggle.
 * `by_source[].ece` carries no cohort dimension, so the moment a reader is in
 * the traded cohort the payload has published no figure for the population on
 * screen — the Sportsbooks case exactly, arriving by a different door.
 *
 * It printed: the traded Polymarket panel read **1.6pp ECE** (the whole
 * population, n=264,956) directly above "79,278 outcomes", while the Source
 * Comparison row for the same provider and the same cohort read **2.7pp**.
 * Everything else in the frame — n, share, and the plotted curve — was
 * cohort-filtered; only the headline number was not, so the ECE did not move
 * when the reader flipped the toggle and its own population did.
 *
 * So option (3) is not a Sportsbooks carve-out; it is what this module does
 * whenever the server has no figure for the panel's population. `publishedEce`
 * now means "the server measured THIS population", `pooledEce` means "it did
 * not, here is the one the page already derived", and the CALLER decides,
 * because the caller is what knows whether a filter is on. Ruling 003 is
 * untouched in the unfiltered cohort: the server's number is still rendered.
 *
 * And the pairing assertion is extended to EVERY provider panel in BOTH
 * cohorts, which is the part that was actually missing. Scoping that guard to
 * the `pooled` branch is why a `published` branch could disagree with the row
 * beside it for as long as the toggle has existed. Kalshi had the identical
 * defect the whole time and hid inside its own rounding (0.92 traded against
 * 0.89 published, both printing "0.9pp") — a guard that only watches the arm
 * that already behaves is how a defect gets to be invisible rather than
 * absent.
 *
 * Counts are summed here for the same reason `buildSourcePanels` sums them:
 * `n` and `share` are sums of published per-bucket rows — formatting the
 * evidence, not adjudicating a metric.
 */

import type { PanelBucket } from "./calibrationMath";
import { censoringVerdict } from "./calibrationSourceRows";

/**
 * Where a panel's ECE came from, or why there is none.
 *
 * `"censored"` is not a third provenance — it is the one case where a number
 * EXISTS and we decline to publish it, which is a different fact about the
 * panel than `"none"` ("the server published nothing"). The page renders it as
 * `data-ece-basis`, so keeping them apart is what lets a rail tell a refusal
 * from an absence without reading our prose (#7411).
 */
export type EceBasis = "published" | "pooled" | "none" | "censored";

export interface ProviderPanelInput {
  provider: string;
  label: string;
  /** Source keys pooled into this provider, in the order the grouper returned. */
  sources: string[];
  /**
   * The provider's POOLED buckets, as the curve draws them.
   *
   * `winners` is REQUIRED, not optional, and #7411's own fail-closed direction
   * is why: `censoringVerdict` floors a missing `winners` to 0, which reads as
   * an all-losers population and withholds the ECE. On the table that is the
   * right way to be wrong. Silently applied to every panel on the page it
   * would read as a site-wide regression, so the compiler is made to prove the
   * field is supplied instead. The page already supplies it — `aggregateBuckets`
   * returns `AggBucket`, which has carried `n` and `winners` since
   * `calibrationParity.ts`; only this type narrowed it away.
   */
  buckets: PanelBucket[];
  /**
   * The server's published ECE. Meaningful ONLY when this panel's population
   * IS the population the server measured — a single-shape provider (provider
   * == source key) with no cohort filter narrowing it. Ignored for a
   * multi-shape provider, because the server publishes nothing at that level
   * and silently reusing one shape's figure would be a lie about which
   * outcomes it measures.
   *
   * #7422: "single-shape" alone was the wrong test. `by_source[].ece` has no
   * cohort dimension, so under a cohort filter the server's figure describes a
   * population this panel is not drawing. The caller is what knows whether a
   * filter is on, so the caller decides — it supplies `pooledEce` instead, and
   * a supplied pooled figure wins. See the module header.
   */
  publishedEce?: number | null;
  /**
   * The pooled ECE the page already derived for Source Comparison. Required
   * for a multi-shape provider, and used for ANY provider whose population the
   * server published no figure for — which since #7422 includes a single-shape
   * provider under a cohort filter. Never computed in this module — passing it
   * in is what keeps the page's derivation count at one.
   */
  pooledEce?: number | null;
}

export interface ProviderPanel {
  provider: string;
  label: string;
  /** Source keys behind this panel. Length > 1 means it has a shape breakdown. */
  sources: string[];
  /** Outcomes behind this provider. */
  n: number;
  /** This provider's share of the panelled population, 0-1. */
  share: number;
  /**
   * The ECE to render, pp, or `null` when there is honestly none — either
   * because the payload published none, or because the population is censored
   * and the figure would measure that censoring rather than the provider.
   */
  ece: number | null;
  /** Which of the two kinds of number `ece` is, or why there is none. */
  eceBasis: EceBasis;
  /**
   * Winners pooled across this panel's buckets, on a CENSORED panel only;
   * `null` otherwise. Mirrors `SourceRow.winners` so the two surfaces state
   * one population from one field.
   */
  winners: number | null;
  /** True when this panel owes a shape breakdown (more than one source key). */
  hasShapeBreakdown: boolean;
}

/** Round to the page's display precision. Formatting, not deriving. */
function toDisplay(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? Math.round(v * 10) / 10 : null;
}

/**
 * Which of the two ECE figures a provider panel is ALLOWED to use (#7422).
 *
 * This lived inline at the page's `buildProviderPanels` call as two ternaries
 * keyed on `sources.length`, and that is where the defect was: shape count
 * answers "does the server publish at this level", but the question the panel
 * actually needs answered is "did the server measure THIS population". Under
 * the cohort toggle those come apart, and the traded Polymarket panel printed
 * the whole-population 1.6pp beside its own "79,278 outcomes" while the Source
 * Comparison row said 2.7pp.
 *
 * Extracted and named so the rule is testable in BOTH cohorts. The page can
 * only render the default one in a static test, so an inline rule here was
 * a rule with an untestable half — and the untestable half is the one that
 * shipped wrong.
 *
 * The returned pair is always exclusive: exactly one side can be non-null, so
 * a call site cannot hand `buildProviderPanels` an ambiguous basis.
 *
 * @param sourceCount   how many source keys this provider pools
 * @param cohortFiltered whether a cohort filter is narrowing the panel away
 *                      from the population `by_source` measured
 * @param serverEce     `by_source[].ece` for the provider's single source key
 * @param pooledEce     the cohort-aware figure Source Comparison already
 *                      derived for this provider
 */
export function eceInputsForPanel(
  sourceCount: number,
  cohortFiltered: boolean,
  serverEce: number | null | undefined,
  pooledEce: number | null | undefined,
): Pick<ProviderPanelInput, "publishedEce" | "pooledEce"> {
  // The server publishes per SOURCE KEY, over the WHOLE population. So its
  // figure is this panel's figure only when the provider is one source key
  // (there is a row for it) and nothing has narrowed the population (that row
  // counts the same outcomes).
  const serverMeasuredThisPopulation = sourceCount === 1 && !cohortFiltered;
  return {
    publishedEce: serverMeasuredThisPopulation ? serverEce ?? null : null,
    pooledEce: serverMeasuredThisPopulation ? null : pooledEce ?? null,
  };
}

/**
 * Order the provider panels and give each the numbers a shared-area layout
 * would otherwise erase.
 *
 * Largest first, matching `buildSourcePanels` — the reader meets the provider
 * carrying most of the headline number first. Providers with no outcomes are
 * DROPPED rather than rendered as an empty frame: an empty panel asserts "we
 * measured this provider and found nothing", which is not what it means.
 *
 * The drop rule is `n`, not `buckets.length`, for the same reason it is there:
 * a provider present with all-empty buckets is as absent as one with no
 * buckets at all, and both must fall out in the same place.
 */
export function buildProviderPanels(
  inputs: ProviderPanelInput[] | null | undefined
): ProviderPanel[] {
  if (!inputs || !inputs.length) return [];

  const withN = inputs
    .filter(i => i && Array.isArray(i.buckets) && Array.isArray(i.sources))
    .map(i => {
      const multi = i.sources.length > 1;
      // #7422. WHICH input is meaningful is not a property of the provider's
      // shape count — it is a property of whether the server measured THIS
      // panel's population. Selecting on `multi` assumed those were the same
      // question, and under a cohort filter they are not: `by_source[].ece` is
      // whole-population, so the traded Polymarket panel printed 1.6pp
      // (n=264,956) beside its own "79,278 outcomes" while the Source
      // Comparison row one section above said 2.7pp.
      //
      // So a supplied `pooledEce` WINS. The caller passes one exactly when the
      // payload published nothing for the population on screen — always for a
      // multi-shape provider, and for a single-shape provider once a cohort
      // filter has narrowed it. `multi ||` keeps the other invariant the
      // header names: a multi-shape panel can never fall back to one shape's
      // published figure, it renders no ECE instead.
      const pooled = toDisplay(i.pooledEce);
      const usePooled = multi || pooled !== null;
      const published = usePooled ? pooled : toDisplay(i.publishedEce);
      // #7411. The same verdict the Source Comparison row is judged by, called
      // on the same pooled buckets the panel's own curve is drawn from — so
      // the two surfaces cannot reach opposite conclusions about one
      // population. Read BEFORE the `n > 0` drop below, because a censored
      // provider has outcomes (DataGolf had 36) and survives that filter.
      const verdict = censoringVerdict(i.buckets);
      const ece = verdict.censored ? null : published;
      const eceBasis: EceBasis = verdict.censored
        ? "censored"
        : ece === null
          ? "none"
          : usePooled
            ? "pooled"
            : "published";
      return {
        provider: i.provider,
        label: i.label,
        sources: [...i.sources],
        n: i.buckets.reduce((s, b) => s + b.n, 0),
        ece,
        eceBasis,
        // Which side the population fell on, so the panel can state it without
        // pooling the buckets a second time. `null` on a measured panel: there
        // is no censoring to describe, and a number here would invite a caller
        // to render one.
        winners: verdict.censored ? verdict.winners : null,
        hasShapeBreakdown: multi,
      };
    })
    .filter(p => p.n > 0);

  const total = withN.reduce((s, p) => s + p.n, 0);
  return withN
    .map(p => ({ ...p, share: total > 0 ? p.n / total : 0 }))
    .sort((a, b) => b.n - a.n || a.provider.localeCompare(b.provider));
}

/**
 * The sentence that names where the shape breakdown lives, derived from the
 * panels themselves rather than from a condition that implies them.
 *
 * UX-P075's `PROXY_FOOTNOTE` lesson, applied: the first draft of that footnote
 * guessed at a condition and was wrong twice, because a second expression that
 * must stay in agreement with a rendered string is #1620's disease. So this
 * reads the built panels — if no panel has a breakdown, there is no sentence to
 * write, and the page renders nothing rather than describing a disclosure that
 * is not on it.
 */
/**
 * The panels the sentence is about, as data.
 *
 * #4340 folded the sentence away from the reader (notice 34), and the remedy
 * that clause names is that the FACT keeps travelling even when the prose
 * stops rendering. By Source carries this list on `data-shape-breakdown-
 * providers`, and the sentence below is built from the same call — so an
 * attribute and a paragraph can never disagree about which providers publish
 * more than one shape. Splitting them into two filters would be exactly the
 * second-expression drift the header above was written about.
 */
export function shapeBreakdownProviders(
  panels: readonly ProviderPanel[]
): ProviderPanel[] {
  return panels.filter(p => p.hasShapeBreakdown);
}

export function shapeBreakdownNote(panels: readonly ProviderPanel[]): string | null {
  const withShapes = shapeBreakdownProviders(panels);
  if (!withShapes.length) return null;
  const names = withShapes.map(p => p.label).join(" and ");
  return (
    `${names} publishes more than one question shape. Each panel is the ` +
    `provider's outcomes pooled and measured together; open “Break out the ` +
    `shapes” inside it to see the shapes separately, each with its own curve, ` +
    `its own published error and its own per-bucket examples.`
  );
}

/**
 * How far apart the drawn panels are in size, as the panels-key fold states it.
 *
 * #7581. This was a hardcoded `28x` in the JSX, and both halves of the number
 * had moved out from under it: it was measured when the section overlaid FIVE
 * source curves on one axis (~420K against ~15K), and the default cohort now
 * draws three panels spanning 2.7x. The fold's own header says its notes are
 * derived from the built panels "never from a condition that implies them" —
 * this was the one sentence in it that wasn't, and it was the one that was
 * wrong. Wrong in both directions, too: 2.7x in the traded cohort, and 9,081x
 * in the all-markets cohort, where a 36-outcome DataGolf panel is drawn the
 * same size as a 326,909-outcome Kalshi one. That second case is the whole
 * reason the sentence exists, and the frozen figure understated it 325x.
 *
 * The size half is unconditional — every panel does state its own n — so this
 * always returns a sentence. Only the comparison is conditional, and it drops
 * out when there is nothing to compare: fewer than two panels, or panels close
 * enough that the ratio rounds to 1.0.
 *
 * No bound verb over the ratio (#7573, same page): the figure is stated, not
 * capped. "More than Nx" has to be re-argued against the data every time the
 * data moves, which is how `28x` survived as long as it did.
 */
export function panelSpreadNote(panels: readonly ProviderPanel[]): string {
  const base = "Each panel states its own sample size";
  const ns = panels.map(p => p.n).filter(n => Number.isFinite(n) && n > 0);
  if (ns.length < 2) return `${base}.`;
  const spread = formatSpread(Math.max(...ns) / Math.min(...ns));
  if (!spread) return `${base}.`;
  return `${base}, and the largest here carries ${spread}x the outcomes of the smallest.`;
}

/**
 * The ratio at the precision the sentence quotes it, or null when it rounds to
 * parity and the comparison is not worth making. Formatting, not deriving —
 * the sibling of `toDisplay` above.
 */
function formatSpread(ratio: number): string | null {
  if (!Number.isFinite(ratio) || ratio < 1) return null;
  if (ratio < 10) {
    const oneDp = Math.round(ratio * 10) / 10;
    return oneDp <= 1 ? null : oneDp.toFixed(1);
  }
  return Math.round(ratio).toLocaleString("en-US");
}

/** Where the shape breakout lives, and what its own control counts. */
export interface ShapeBreakoutPointer {
  /** The provider panel(s) to name, joined for prose. */
  label: string;
  /** How many panels that label covers — the sentence's grammatical number. */
  providerCount: number;
  /**
   * The count the named control renders, or `null` when more than one control
   * does and no single number is true of any of them.
   */
  keyCount: number | null;
}

/**
 * The pointer a sentence elsewhere on the page uses to send a reader into the
 * shape breakout — the panel to name, and the number they will see on it.
 *
 * #7308. Source Comparison's note pointed at ONE provider's disclosure and
 * quoted the page-wide `sources.length`: the sentence promised "all 7 keys"
 * while the control it named renders "Break out the shapes (4)". Both numbers
 * were true — seven raw keys really are on the page, four of them really are in
 * that panel — and that is what made it survive #6265, whose census asked the
 * VOCABULARY question ("keys" is the right word for a raw count, so the line
 * passed) and never the locality one: the number of keys in *what*.
 *
 * So `keyCount` is the very expression the `<summary>` renders, read off the
 * same built panels, for the reason the header above already gives — a second
 * expression that must stay in agreement with a rendered string is #1620's
 * disease. Two breakout providers means two controls with two counts and no
 * single number the reader can be promised, so the count is `null` and the
 * caller writes the sentence without one, rather than summing two disclosures
 * into a figure neither of them shows.
 */
export function shapeBreakoutPointer(
  panels: readonly ProviderPanel[]
): ShapeBreakoutPointer | null {
  const withShapes = shapeBreakdownProviders(panels);
  if (!withShapes.length) return null;
  return {
    label: withShapes.map(p => p.label).join(" and "),
    providerCount: withShapes.length,
    keyCount: withShapes.length === 1 ? withShapes[0].sources.length : null,
  };
}

/**
 * The Sources KPI's subtext — UX-P080 / Alex round 2, item 2.
 *
 * The ruling: *"The SOURCES KPI counts providers, not shapes: 3, with shapes
 * named in the subtext."* The provider merge that By Source and Source
 * Comparison already agree on **reaches the KPI card**, which was the last
 * surface on this page still counting source KEYS and therefore still saying
 * "5" directly above two tables that say "3".
 *
 * The shapes are NOT dropped in the process — a KPI that says 3 with no way to
 * see what the third one is made of trades one confusion for another. They move
 * into the subtext, which is the same move the shape annex made inside its
 * provider panel (ruling: the annex moves inside the provider it describes).
 *
 * Derived from the SAME `ProviderGroup[]` the panels and the table are built
 * from, so the card cannot count something the tables do not. That is the
 * pairing discipline this page keeps re-learning: agreement is guaranteed by
 * shared derivation, never by two expressions that must be kept in step.
 *
 * #4214 — THE QUALIFIER IS SAID ONCE, NOT ONCE PER MEMBER.
 *
 * In production this read *"Sportsbooks (Odds API) (Per-sportsbook (Odds API),
 * Odds API, Totals (Odds API), Spreads (Odds API))"* — "Odds API" five times,
 * three parentheses deep, in a KPI card's subtext. Neither half was wrong: the
 * group is named for its provider and each source label carries its own
 * provider too, because a source label has to stand alone everywhere else on
 * the page. Composing them nested repeated the qualifier the group had already
 * established.
 *
 * So the group's trailing parenthetical is lifted out and stated once, and each
 * member drops the copy it carried: `Sportsbooks (Odds API: Per-sportsbook,
 * Odds API, Totals, Spreads)`.
 *
 * Two things this deliberately does NOT do. It does not rename any label — the
 * page's labels come from the server's `source_labels` vocabulary since
 * CAL-P1025 (#3357), and a client-side rename is the shadowing bug #4067 was
 * filed for. And it drops nothing: every source key is still named, which is
 * the promise UX-P080 item 2 made. The residual "Odds API" in the example above
 * is the moneyline key having no shape name of its own; that is a server-side
 * vocabulary question, recorded on #4214, not something to guess at here.
 */
export function providerKpiDetail(
  groups: readonly { label: string; sources: readonly string[] }[],
  shapeLabel: (source: string) => string,
): string {
  return groups
    .map(g => {
      if (g.sources.length <= 1) return g.label;
      const qualifier = groupQualifier(g.label);
      const members = g.sources.map(s => withoutGroupQualifier(shapeLabel(s), g.label));
      return qualifier
        ? `${g.label.slice(0, qualifier.at)} (${qualifier.text}: ${members.join(", ")})`
        : `${g.label} (${members.join(", ")})`;
    })
    .join(" · ");
}

/**
 * A group label's trailing parenthetical, if it has one.
 *
 * `"Sportsbooks (Odds API)"` → `{ text: "Odds API", at: 12 }`; `"Kalshi"` → null.
 */
function groupQualifier(groupLabel: string): { text: string; at: number } | null {
  const m = /\s*\(([^()]+)\)\s*$/.exec(groupLabel);
  return m ? { text: m[1], at: m.index } : null;
}

/**
 * Drop a trailing `(qualifier)` from a member label when the group already said it.
 *
 * #4214, AND ITS SURVIVOR. `providerKpiDetail` was the render this was filed
 * against, and fixing that one alone left the defect on screen: the Source
 * Comparison TABLE composes the same two vocabularies independently
 * (`SourceComparisonRow`, `row.sources.map(sourceLabel)`), under a first column
 * narrow enough that "Per-sportsbook (Odds API) · Odds API · Totals (Odds API)
 * · Spreads (Odds API)" wrapped to seven lines at 390px. It was the more
 * visible of the two, and it was found by photographing the deployed page
 * rather than by reading the diff. So the rule lives here, exported, and both
 * call sites use it — the guard for this class is that a second render path
 * cannot quietly keep the old composition.
 *
 * Returns the label untouched when the group has no qualifier, when it does not
 * match, or when stripping would leave nothing — a member that IS the qualifier
 * still has to be named, and an empty list entry is worse than a repeated word.
 */
export function withoutGroupQualifier(memberLabel: string, groupLabel: string): string {
  const qualifier = groupQualifier(groupLabel);
  if (!qualifier) return memberLabel;
  const suffix = ` (${qualifier.text})`;
  if (!memberLabel.endsWith(suffix)) return memberLabel;
  const stripped = memberLabel.slice(0, -suffix.length).trim();
  return stripped.length > 0 ? stripped : memberLabel;
}
