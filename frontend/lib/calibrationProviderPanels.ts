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
 * Counts are summed here for the same reason `buildSourcePanels` sums them:
 * `n` and `share` are sums of published per-bucket rows — formatting the
 * evidence, not adjudicating a metric.
 */

import type { CalibrationErrorBucket } from "./calibrationMath";

/** Where a panel's ECE came from. Published beside the number, never inferred. */
export type EceBasis = "published" | "pooled" | "none";

export interface ProviderPanelInput {
  provider: string;
  label: string;
  /** Source keys pooled into this provider, in the order the grouper returned. */
  sources: string[];
  /** The provider's POOLED buckets, as the curve draws them. */
  buckets: CalibrationErrorBucket[];
  /**
   * The server's published ECE. Meaningful ONLY for a single-shape provider,
   * where provider == source key and the published number IS the panel's
   * number. Ignored for a multi-shape provider, because the server publishes
   * nothing at that level and silently reusing one shape's figure would be a
   * lie about which outcomes it measures.
   */
  publishedEce?: number | null;
  /**
   * The pooled ECE the page already derived for Source Comparison. Used ONLY
   * for a multi-shape provider. Never computed in this module — passing it in
   * is what keeps the page's derivation count at one.
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
  /** The ECE to render, pp, or `null` when there is honestly none. */
  ece: number | null;
  /** Which of the two kinds of number `ece` is. `"none"` when it is null. */
  eceBasis: EceBasis;
  /** True when this panel owes a shape breakdown (more than one source key). */
  hasShapeBreakdown: boolean;
}

/** Round to the page's display precision. Formatting, not deriving. */
function toDisplay(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? Math.round(v * 10) / 10 : null;
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
      // The two inputs are read in mutually exclusive branches, so a caller
      // that supplies both cannot produce a number whose basis is ambiguous.
      const ece = multi ? toDisplay(i.pooledEce) : toDisplay(i.publishedEce);
      const eceBasis: EceBasis =
        ece === null ? "none" : multi ? "pooled" : "published";
      return {
        provider: i.provider,
        label: i.label,
        sources: [...i.sources],
        n: i.buckets.reduce((s, b) => s + b.n, 0),
        ece,
        eceBasis,
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
export function shapeBreakdownNote(panels: readonly ProviderPanel[]): string | null {
  const withShapes = panels.filter(p => p.hasShapeBreakdown);
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
 */
export function providerKpiDetail(
  groups: readonly { label: string; sources: readonly string[] }[],
  shapeLabel: (source: string) => string,
): string {
  return groups
    .map(g =>
      g.sources.length > 1
        ? `${g.label} (${g.sources.map(shapeLabel).join(", ")})`
        : g.label,
    )
    .join(" · ");
}
