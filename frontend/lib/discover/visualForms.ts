/**
 * #12577 / #12523 — Visual Forms Library & Hand-Kept Paired-Metric Register.
 *
 * The sixth grouping primitive after atoms, relations, sets, presentations,
 * and triggers: **visual forms**.
 *
 * - A form is a named way to draw a set, with an explicit contract:
 *   (1) the data shape it needs (e.g. "two related numbers per subject, plus a picture"),
 *   (2) the vocabulary of parts it uses (`bars`, `tiles`, `strips`, `pictures`, `ticks`),
 *   (3) the slots it fills, and
 *   (4) what it does when a number is missing or settled.
 * - None of the forms is hard-wired to the Oscars: an award category (Nominated %
 *   beside Wins %, with movie posters or headshots) and a playoff race (Make Playoffs %
 *   beside Win Title %, with team logos) share the same data shape and render through
 *   the same form library.
 *
 * Unbending rules (#12577):
 * 1. Stage-1 (e.g. Nominated / Make Playoffs) and Stage-2 (e.g. Wins / Win Title)
 *    are different propositions and are NEVER blended with each other. Equivalent
 *    venue legs for the SAME proposition (e.g. Kalshi #5165726 + Polymarket #27988771
 *    for Best Picture Nominee) ARE blended on the server via `futures_source_merge.blend_with_verdict`
 *    (`backend/app/services/paired_metric_register.py`) — never in the browser.
 * 2. After step 1 settles (e.g. nominations announced), the first number becomes
 *    `✓` or `✗` ("settled means settled").
 * 3. A row with no recent probability or not listed in one market explicitly says so
 *    (e.g. "Not listed to win"), never `0%` and never silently omitted.
 * 4. Every picture passes the kid-safe gate (#7461): text check (`isKidSafeText`),
 *    verified HTTPS host, `adult === false`, horror genre (`27`) excluded, and on
 *    kid surfaces (`kidSurface: true` / `/play`) delegates to `kidSafeImageUrl`.
 * 5. Rounding uses the product's single `renderedPercent` helper (#1933 / #3867)
 *    so half-percent values (`0.955`, `0.935`) always round the same way.
 * 6. Every TMDB-backed surface displays the official TMDB attribution sentence
 *    (`TMDB_ATTRIBUTION_LINE`) together with the official TMDB logo mark linked to
 *    `https://www.themoviedb.org/`.
 */

import { isKidSafeText, kidSafeImageUrl } from "@/lib/play/kidSafe";
import { renderedPercent } from "@/lib/renderedPercent";

export type FormVocabularyPart = "bars" | "tiles" | "strips" | "pictures" | "ticks";

export type VisualFormId =
  | "paired_bars_with_art"
  | "paired_bars_top5_expandable"
  | "paired_bars_single_line"
  | "paired_bars_top3_plus_strip"
  | "poster_spotlight_tiles"
  | "step_conversion_path"
  | "leader_and_chasers_split"
  | "podium_and_tiers"
  | "barbell_race_track"
  | "ballot_quadrant_map"
  | "settled_gate_after_nominations";

export interface VisualFormContract {
  form_id: VisualFormId;
  form_name: string;
  data_shape: string;
  parts_vocabulary: FormVocabularyPart[];
  slots: string[];
  missing_number_rule: string;
  settled_step_rule: string;
  domain_agnostic: true;
}

export interface PairedArtAsset {
  kind: "tmdb_poster" | "tmdb_headshot" | "espn_team_logo";
  url: string;
  tmdb_id?: number;
  poster_path?: string;
  profile_path?: string;
  genre_ids?: number[];
  adult: boolean;
  kid_safe_vetted: boolean;
}

export type ServerBlendAuthority =
  | "server:futures_source_merge.blend_with_verdict"
  | "single_venue"
  | null;

export interface PairedSubjectEntry {
  subject_key: string;
  subject: string;
  detail: string;
  credit_source?: string;
  stage_1_market_id: number;
  stage_1_outcome: string | null;
  stage_1_kalshi_probability?: number | null;
  stage_1_polymarket_market_id?: number | null;
  stage_1_polymarket_outcome?: string | null;
  stage_1_polymarket_probability?: number | null;
  stage_1_probability: number | null;
  stage_1_blend_rule?: string | null;
  stage_1_divergence?: Record<string, unknown> | null;
  stage_1_blend_authority?: ServerBlendAuthority;
  stage_1_settled_state: "yes" | "no" | null;
  stage_2_market_id: number;
  stage_2_outcome: string | null;
  stage_2_probability: number | null;
  stage_2_blend_rule?: string | null;
  stage_2_divergence?: Record<string, unknown> | null;
  stage_2_blend_authority?: ServerBlendAuthority;
  missing_stage_1_reason?: string;
  missing_stage_2_reason?: string;
  art: PairedArtAsset | null;
}

export interface PairedMetricSet {
  set_id: string;
  category: "entertainment" | "hockey" | "basketball" | "football";
  kicker: string;
  title: string;
  subtitle: string;
  selection_rule?: string;
  stage_1_label: string;
  stage_2_label: string;
  stage_1_settled_yes_label: string;
  stage_1_settled_no_label: string;
  stage_1_market: {
    id: number;
    source: string;
    name: string;
    companion_polymarket_id?: number;
  };
  stage_2_market: {
    id: number;
    source: string;
    name: string;
  };
  never_blend: true;
  blend_authority?: "server:futures_source_merge.blend_with_verdict";
  as_of: string;
  entries: PairedSubjectEntry[];
}

export const TMDB_ATTRIBUTION_LINE =
  "This product uses the TMDB API but is not endorsed or certified by TMDB.";

export const TMDB_ATTRIBUTION_URL = "https://www.themoviedb.org/";

export const TMDB_OFFICIAL_LOGO_PATH = "/tmdb-blue-short.svg";

export const SERVER_BLEND_AUTHORITY =
  "server:futures_source_merge.blend_with_verdict" as const;

/**
 * Deterministic tie-breaking rule for paired entries:
 * 1. Higher `stage_2_probability` (listed contenders before unlisted),
 * 2. Higher `stage_1_probability`,
 * 3. Alphabetical by `subject`.
 */
export function sortPairedEntries(
  entries: readonly PairedSubjectEntry[],
): PairedSubjectEntry[] {
  return [...entries].sort((a, b) => {
    const aHasS2 =
      typeof a.stage_2_probability === "number" &&
      Number.isFinite(a.stage_2_probability);
    const bHasS2 =
      typeof b.stage_2_probability === "number" &&
      Number.isFinite(b.stage_2_probability);
    if (aHasS2 !== bHasS2) return aHasS2 ? -1 : 1;
    const s2Diff = (b.stage_2_probability ?? -1) - (a.stage_2_probability ?? -1);
    if (Math.abs(s2Diff) > 1e-6) return s2Diff;
    const s1Diff = (b.stage_1_probability ?? -1) - (a.stage_1_probability ?? -1);
    if (Math.abs(s1Diff) > 1e-6) return s1Diff;
    return a.subject.localeCompare(b.subject);
  });
}

export const VISUAL_FORM_LIBRARY: Record<VisualFormId, VisualFormContract> = {
  paired_bars_with_art: {
    form_id: "paired_bars_with_art",
    form_name: "Stacked Dual Bars with Art (Full 10-Row Baseline)",
    data_shape: "two related numbers per subject, plus a picture",
    parts_vocabulary: ["pictures", "bars", "ticks"],
    slots: ["picture", "subject", "stage_1_bar_or_tick", "stage_2_bar"],
    missing_number_rule:
      "When stage 1 or stage 2 has no recent probability, render an explicit 'Not listed' / 'No recent <metric> %' badge in that bar slot.",
    settled_step_rule:
      "Once stage 1 settles, replace the stage-1 bar with ✓ (qualified/nominated) or ✗ (eliminated/missed).",
    domain_agnostic: true,
  },
  paired_bars_top5_expandable: {
    form_id: "paired_bars_top5_expandable",
    form_name: "Shorter Card 1A · Top 5 Dual Bars + 'Show All 10' Expander",
    data_shape: "two related numbers per subject, plus a picture (top-N + expander)",
    parts_vocabulary: ["pictures", "bars", "strips", "ticks"],
    slots: ["picture", "subject", "stage_1_bar_or_tick", "stage_2_bar", "expand_all_button"],
    missing_number_rule:
      "Collapsed summary pill and expanded rows explicitly state 'Not listed to win' or 'No recent <metric> %'.",
    settled_step_rule:
      "Once stage 1 settles, replace the stage-1 bar with ✓ or ✗ in both top-5 and expanded rows.",
    domain_agnostic: true,
  },
  paired_bars_single_line: {
    form_id: "paired_bars_single_line",
    form_name: "Shorter Card 1B · Compact One-Line-Per-Film Dual Table",
    data_shape: "two related numbers per subject, plus a mini picture (1 line per row)",
    parts_vocabulary: ["pictures", "bars", "strips", "ticks"],
    slots: ["mini_picture", "subject", "inline_dual_micro_bars", "stage_1_col", "stage_2_col"],
    missing_number_rule:
      "Stage-2 column prints 'Not listed to win' in place of a percentage and omits the lower micro-bar.",
    settled_step_rule:
      "Stage-1 column flips from '<N>%' to '✓' or '✗' on settled step 1.",
    domain_agnostic: true,
  },
  paired_bars_top3_plus_strip: {
    form_id: "paired_bars_top3_plus_strip",
    form_name: "Shorter Card 1C · Top 3 Full Dual-Bar Rows + 2-Up Chaser Grid",
    data_shape: "two related numbers per subject, plus a picture (top-3 rows + 2-up strip)",
    parts_vocabulary: ["pictures", "bars", "tiles", "ticks"],
    slots: ["top3_dual_bar_rows", "chaser_2up_pill_grid"],
    missing_number_rule:
      "Chaser pill prints 'Not listed to win' when absent from the stage-2 market.",
    settled_step_rule:
      "Top-3 rows and chaser pills replace stage-1 % with ✓ or ✗ after step 1 settles.",
    domain_agnostic: true,
  },
  poster_spotlight_tiles: {
    form_id: "poster_spotlight_tiles",
    form_name: "Art-Led 2-Up Spotlight Tiles",
    data_shape: "two related numbers per subject, plus a picture",
    parts_vocabulary: ["pictures", "tiles", "bars", "ticks"],
    slots: ["picture", "subject", "stage_2_headline", "stage_1_badge_or_tick"],
    missing_number_rule:
      "Tile footer prints 'Not listed to win' / 'No recent <metric> %' instead of a numeric headline when missing.",
    settled_step_rule:
      "Stage-1 corner pill flips from '<N>% nom' to '✓ Nominated' or '✗ Missed'.",
    domain_agnostic: true,
  },
  step_conversion_path: {
    form_id: "step_conversion_path",
    form_name: "Two-Step Conversion Funnel Track",
    data_shape: "a path with steps, plus a picture",
    parts_vocabulary: ["pictures", "strips", "bars", "ticks"],
    slots: ["picture", "subject", "outer_stage_1_reach", "inner_stage_2_conversion"],
    missing_number_rule:
      "When stage 2 has no recent probability, show the outer stage-1 reach bar with an explicit 'Not listed to win' callout pill.",
    settled_step_rule:
      "After stage 1 settles, ✓ locks the outer gate at 100% and shows live stage-2 bars; ✗ collapses eliminated rows.",
    domain_agnostic: true,
  },
  leader_and_chasers_split: {
    form_id: "leader_and_chasers_split",
    form_name: "One Leader Hero + Chasers Strip",
    data_shape: "one leader and its chasers, two numbers per subject + picture",
    parts_vocabulary: ["pictures", "tiles", "strips", "bars", "ticks"],
    slots: ["leader_hero_tile", "lead_margin_badge", "chaser_dual_strips"],
    missing_number_rule:
      "Chasers without a recent stage-2 probability remain visible with 'Not listed to win' rather than dropping out.",
    settled_step_rule:
      "Stage-1 slot in both the leader hero and chaser strips flips to ✓ or ✗ once step 1 settles.",
    domain_agnostic: true,
  },
  podium_and_tiers: {
    form_id: "podium_and_tiers",
    form_name: "Wild Form A · 3-Spot Trophy Podium + Ballot Tier Chips",
    data_shape: "top-3 podium + tiered field chips, two numbers per subject + picture",
    parts_vocabulary: ["pictures", "tiles", "strips", "ticks"],
    slots: ["podium_gold_silver_bronze", "nomination_locks_tier", "bubble_watch_tier"],
    missing_number_rule:
      "Tier chip prints 'Not listed to win' beside the stage-1 nomination % when absent from the winner market.",
    settled_step_rule:
      "Podium badges and tier chips flip stage-1 % to ✓ or ✗ once step 1 settles.",
    domain_agnostic: true,
  },
  barbell_race_track: {
    form_id: "barbell_race_track",
    form_name: "Wild Form B · 0–100% Barbell Gap Track (Wins ●━━━○ Nominated)",
    data_shape: "two related numbers on one shared 0–100% axis, plus a picture",
    parts_vocabulary: ["pictures", "strips", "bars", "ticks"],
    slots: ["picture", "subject", "stage_2_dot", "gap_connector_span", "stage_1_dot"],
    missing_number_rule:
      "When stage 2 is missing, only the stage-1 marker is plotted on the 0–100% axis with an inline 'Not listed to win' tag.",
    settled_step_rule:
      "After step 1 settles, the right endpoint locks to ✓ at 100% (or ✗ eliminated) while the stage-2 marker moves along the track.",
    domain_agnostic: true,
  },
  ballot_quadrant_map: {
    form_id: "ballot_quadrant_map",
    form_name: "Wild Form C · 2×2 Ballot Quadrant Board (Locks, Favorites, Spoilers & Bubble)",
    data_shape: "two-axis spatial grouping (stage 1 vs stage 2), plus a picture",
    parts_vocabulary: ["pictures", "tiles", "strips", "ticks"],
    slots: [
      "quadrant_trophy_favorites",
      "quadrant_safe_nominees_longshot_win",
      "quadrant_likely_nominees",
      "quadrant_bubble_watch",
    ],
    missing_number_rule:
      "Unlisted stage-2 contenders appear in their stage-1 tier with 'Not listed to win' printed on the tile.",
    settled_step_rule:
      "Quadrants collapse into Confirmed Nominees (✓) vs Missed Ballot (✗) after step 1 settles.",
    domain_agnostic: true,
  },
  settled_gate_after_nominations: {
    form_id: "settled_gate_after_nominations",
    form_name: "Settled Gate (✓ / ✗) + Live Final Race",
    data_shape: "two related numbers per subject, step 1 settled to ✓/✗, plus a picture",
    parts_vocabulary: ["pictures", "ticks", "bars"],
    slots: ["picture", "subject", "settled_tick_or_cross", "live_stage_2_bar"],
    missing_number_rule:
      "Qualified rows without a recent stage-2 probability say 'Not listed to win' / 'No recent <metric> %'.",
    settled_step_rule:
      "Step 1 is settled: ✓ rows compete in the live winner race; ✗ rows show their settled elimination state.",
    domain_agnostic: true,
  },
};

const TMDB_HORROR_GENRE_ID = 27;
const ALLOWED_VISUAL_ART_HOSTS = new Set([
  "image.tmdb.org",
  "a.espncdn.com",
  "images.pexels.com",
]);

/**
 * #7461 Kid-Safe Gate for per-outcome posters, headshots, and team logos.
 */
export function resolveKidSafeVisualArt(
  entry: Pick<PairedSubjectEntry, "subject" | "detail" | "art">,
  options?: { kidSurface?: boolean },
): string | null {
  const art = entry.art;
  if (!art || !art.url) return null;
  if (art.adult || !art.kid_safe_vetted) return null;
  if (Array.isArray(art.genre_ids) && art.genre_ids.includes(TMDB_HORROR_GENRE_ID)) {
    return null;
  }
  if (!isKidSafeText(entry.subject) || !isKidSafeText(entry.detail)) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(art.url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") return null;
  if (!ALLOWED_VISUAL_ART_HOSTS.has(parsed.hostname)) return null;

  if (options?.kidSurface) {
    if (art.kind === "espn_team_logo" && parsed.hostname === "a.espncdn.com") {
      return art.url;
    }
    return kidSafeImageUrl(art.url);
  }

  return art.url;
}

export interface FormattedStageDisplay {
  kind: "percent" | "tick" | "cross" | "missing";
  percent: number | null;
  symbol?: "✓" | "✗";
  label: string;
  sublabel?: string;
}

/**
 * Format Stage 1 (e.g. Nominated % or Make Playoffs %), using the product's
 * single `renderedPercent` rounding helper (#1933 / #3867).
 */
export function formatStage1Display(
  entry: PairedSubjectEntry,
  set: Pick<
    PairedMetricSet,
    "stage_1_label" | "stage_1_settled_yes_label" | "stage_1_settled_no_label"
  >,
  options?: { simulateSettledStage1?: boolean },
): FormattedStageDisplay {
  const settledState: "yes" | "no" | null =
    entry.stage_1_settled_state ??
    (options?.simulateSettledStage1
      ? (entry.stage_1_probability ?? 0) >= 0.65
        ? "yes"
        : "no"
      : null);

  if (settledState === "yes") {
    return {
      kind: "tick",
      percent: 100,
      symbol: "✓",
      label: `✓ ${set.stage_1_settled_yes_label}`,
    };
  }
  if (settledState === "no") {
    const priorRounded = renderedPercent(entry.stage_1_probability);
    const priorPct =
      priorRounded !== null ? Math.max(1, Math.min(99, priorRounded)) : null;
    return {
      kind: "cross",
      percent: 0,
      symbol: "✗",
      label: `✗ ${set.stage_1_settled_no_label}`,
      sublabel: priorPct !== null ? `was ${priorPct}%` : undefined,
    };
  }

  const rawPct = renderedPercent(entry.stage_1_probability);
  if (rawPct === null) {
    return {
      kind: "missing",
      percent: null,
      label:
        entry.missing_stage_1_reason ||
        `No recent ${set.stage_1_label.toLowerCase()} %`,
    };
  }

  const pct = Math.max(1, Math.min(99, rawPct));
  return {
    kind: "percent",
    percent: pct,
    label: `${pct}%`,
  };
}

/**
 * Format Stage 2 (e.g. Wins % or Win Cup %), never blending with Stage 1,
 * using `renderedPercent` (#1933 / #3867), and explicitly reporting when a row
 * is not listed or has no recent probability.
 */
export function formatStage2Display(
  entry: PairedSubjectEntry,
  set: Pick<PairedMetricSet, "stage_2_label">,
  options?: { simulateSettledStage1?: boolean },
): FormattedStageDisplay {
  const settledState: "yes" | "no" | null =
    entry.stage_1_settled_state ??
    (options?.simulateSettledStage1
      ? (entry.stage_1_probability ?? 0) >= 0.65
        ? "yes"
        : "no"
      : null);

  if (settledState === "no") {
    return {
      kind: "cross",
      percent: 0,
      symbol: "✗",
      label: "Eliminated",
    };
  }

  const rawPct = renderedPercent(entry.stage_2_probability);
  if (rawPct === null) {
    return {
      kind: "missing",
      percent: null,
      label:
        entry.missing_stage_2_reason ||
        `No recent ${set.stage_2_label.toLowerCase()} %`,
    };
  }

  const pct = Math.max(1, Math.min(99, rawPct));
  return {
    kind: "percent",
    percent: pct,
    label: `${pct}%`,
  };
}

// ============================================================================
// Hand-Kept Pairing Register (Mirrors backend/data/groupings/paired_metric_register.json)
// ============================================================================

export const PAIRED_METRIC_REGISTER: Record<string, PairedMetricSet> = {
  "oscars-2027-best-picture": {
    set_id: "oscars-2027-best-picture",
    category: "entertainment",
    kicker: "OSCARS 2027 · BEST PICTURE",
    title: "The Odyssey leads Best Picture, with 6 films at 75%+ to be nominated",
    subtitle:
      "99th Academy Awards · Top 10 most likely to be nominated (ordered by win %, ties broken by nominated %) · Nominee % (averaged across venues on server via futures_source_merge.blend_with_verdict: #5165726 + #27988771) paired beside Winner % (#6173044)",
    selection_rule: "top_10_by_stage_1_probability",
    stage_1_label: "Nominated",
    stage_2_label: "Wins",
    stage_1_settled_yes_label: "Nominated",
    stage_1_settled_no_label: "Not nominated",
    stage_1_market: {
      id: 5165726,
      source: "kalshi+polymarket",
      name: "Oscar nominees: Best Picture (averaged across venues on server via futures_source_merge.blend_with_verdict: #5165726 + #27988771)",
      companion_polymarket_id: 27988771,
    },
    stage_2_market: {
      id: 6173044,
      source: "kalshi",
      name: "Oscar Winner: Best Picture",
    },
    never_blend: true,
    blend_authority: "server:futures_source_merge.blend_with_verdict",
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "film:the-odyssey-2026",
        subject: "The Odyssey",
        detail: "Christopher Nolan · Universal Pictures",
        credit_source: "tmdb:movie:1368337",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Odyssey",
        stage_1_kalshi_probability: 0.98,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "The Odyssey",
        stage_1_polymarket_probability: 0.976,
        stage_1_probability: 0.978,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Odyssey",
        stage_2_probability: 0.565,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1368337,
          poster_path: "/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
          url: "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
          genre_ids: [12, 28, 14],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:you-can-see-everything-2026",
        subject: "You Can See Everything",
        detail: "Nathan Fielder & Lance Oppenheim · Blow Out Productions",
        credit_source: "tmdb:movie:1765072",
        stage_1_market_id: 5165726,
        stage_1_outcome: "You Can See Everything",
        stage_1_kalshi_probability: 0.85,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "You Can See Everything",
        stage_1_polymarket_probability: 0.855,
        stage_1_probability: 0.8525,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "You Can See Everything",
        stage_2_probability: 0.165,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1765072,
          poster_path: "/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
          url: "https://image.tmdb.org/t/p/w342/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
          genre_ids: [99],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:the-black-ball-2026",
        subject: "The Black Ball",
        detail: "Javier Ambrossi & Javier Calvo · Movistar Plus",
        credit_source: "tmdb:movie:1422041",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Black Ball",
        stage_1_kalshi_probability: 0.94,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "La Bola Negra",
        stage_1_polymarket_probability: 0.95,
        stage_1_probability: 0.945,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Black Ball",
        stage_2_probability: 0.145,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1422041,
          poster_path: "/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg",
          url: "https://image.tmdb.org/t/p/w342/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg",
          genre_ids: [18, 10752],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:dune-part-three-2026",
        subject: "Dune: Part Three",
        detail: "Denis Villeneuve · Legendary Pictures",
        credit_source: "tmdb:movie:1170608",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Dune: Part Three",
        stage_1_kalshi_probability: 0.815,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "Dune: Part Three",
        stage_1_polymarket_probability: 0.835,
        stage_1_probability: 0.825,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Dune: Part Three",
        stage_2_probability: 0.075,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1170608,
          poster_path: "/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
          url: "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
          genre_ids: [878, 12],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:wild-horse-nine-2026",
        subject: "Wild Horse Nine",
        detail: "Martin McDonagh · Searchlight Pictures",
        credit_source: "tmdb:movie:891621",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Wild Horse Nine",
        stage_1_kalshi_probability: 0.93,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "Wild Horse Nine",
        stage_1_polymarket_probability: 0.925,
        stage_1_probability: 0.9275,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Wild Horse Nine",
        stage_2_probability: 0.015,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 891621,
          poster_path: "/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg",
          url: "https://image.tmdb.org/t/p/w342/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg",
          genre_ids: [35, 80, 53],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:artificial-2026",
        subject: "Artificial",
        detail: "Luca Guadagnino · Heyday Films",
        credit_source: "tmdb:movie:1492198",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Artificial",
        stage_1_kalshi_probability: 0.575,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: null,
        stage_1_polymarket_probability: null,
        stage_1_probability: 0.575,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Artificial",
        stage_2_probability: 0.015,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1492198,
          poster_path: "/2bz0HPE8OFOqnyvl8sCdVDIg1KX.jpg",
          url: "https://image.tmdb.org/t/p/w342/2bz0HPE8OFOqnyvl8sCdVDIg1KX.jpg",
          genre_ids: [35, 18, 36],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:project-hail-mary-2026",
        subject: "Project Hail Mary",
        detail: "Phil Lord & Christopher Miller · Amazon MGM Studios",
        credit_source: "tmdb:movie:687163",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Project Hail Mary",
        stage_1_kalshi_probability: 0.775,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "Project Hail Mary",
        stage_1_polymarket_probability: 0.745,
        stage_1_probability: 0.76,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Project Hail Mary",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 687163,
          poster_path: "/iOb2fjXLbpJgyQXe46n1WtGCnaa.jpg",
          url: "https://image.tmdb.org/t/p/w342/iOb2fjXLbpJgyQXe46n1WtGCnaa.jpg",
          genre_ids: [878, 12],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:the-debut-2026",
        subject: "The Debut",
        detail: "Jesse Eisenberg · Topic Studios",
        credit_source: "tmdb:movie:1391239",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Debut",
        stage_1_kalshi_probability: 0.725,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "The Debut",
        stage_1_polymarket_probability: 0.72,
        stage_1_probability: 0.7225,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Debut",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1391239,
          poster_path: "/qk8qWJxM9hZSbSjSoEz0LAzcoPb.jpg",
          url: "https://image.tmdb.org/t/p/w342/qk8qWJxM9hZSbSjSoEz0LAzcoPb.jpg",
          genre_ids: [10402, 35, 18],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:the-invite-2026",
        subject: "The Invite",
        detail: "Olivia Wilde · Annapurna Pictures",
        credit_source: "tmdb:movie:950028",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Invite",
        stage_1_kalshi_probability: 0.71,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "The Invite",
        stage_1_polymarket_probability: 0.71,
        stage_1_probability: 0.71,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Invite",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 950028,
          poster_path: "/b7Dr8Chzse8VagexAporUu2RtLx.jpg",
          url: "https://image.tmdb.org/t/p/w342/b7Dr8Chzse8VagexAporUu2RtLx.jpg",
          genre_ids: [35, 18, 10749],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:i-play-rocky-2026",
        subject: "I Play Rocky",
        detail: "Peter Farrelly · Eden Rock Media",
        credit_source: "tmdb:movie:1286656",
        stage_1_market_id: 5165726,
        stage_1_outcome: "I Play Rocky",
        stage_1_kalshi_probability: 0.475,
        stage_1_polymarket_market_id: 27988771,
        stage_1_polymarket_outcome: "I Play Rocky",
        stage_1_polymarket_probability: 0.5,
        stage_1_probability: 0.4875,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: null,
        stage_2_probability: null,
        missing_stage_2_reason: "Not listed to win",
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1286656,
          poster_path: "/xE5tY3lppZUyG7WKKThsuYHuAHr.jpg",
          url: "https://image.tmdb.org/t/p/w342/xE5tY3lppZUyG7WKKThsuYHuAHr.jpg",
          genre_ids: [18, 36],
          adult: false,
          kid_safe_vetted: true,
        },
      },
    ],
  },
  "oscars-2027-best-director": {
    set_id: "oscars-2027-best-director",
    category: "entertainment",
    kicker: "OSCARS 2027 · BEST DIRECTOR",
    title: "Christopher Nolan leads Best Director, with 6 contenders above 20% to be nominated",
    subtitle: "Top 6 directors by win % (#5601024 + #5869747) · Verified TMDB headshots",
    selection_rule: "top_6_by_stage_2_then_stage_1",
    stage_1_label: "Nominated",
    stage_2_label: "Wins",
    stage_1_settled_yes_label: "Nominated",
    stage_1_settled_no_label: "Not nominated",
    stage_1_market: {
      id: 5601024,
      source: "kalshi",
      name: "Oscar nominees: Best Director",
    },
    stage_2_market: {
      id: 5869747,
      source: "kalshi",
      name: "Oscar winner: Best Director",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "person:christopher-nolan",
        subject: "Christopher Nolan",
        detail: "The Odyssey",
        credit_source: "tmdb:person:525",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Christopher Nolan",
        stage_1_probability: 0.985,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Christopher Nolan",
        stage_2_probability: 0.563,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 525,
          profile_path: "/xuAIuYSmsUzKlUMBFGVZaWsY3DZ.jpg",
          url: "https://image.tmdb.org/t/p/w185/xuAIuYSmsUzKlUMBFGVZaWsY3DZ.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:denis-villeneuve",
        subject: "Denis Villeneuve",
        detail: "Dune: Part Three",
        credit_source: "tmdb:person:137427",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Denis Villeneuve",
        stage_1_probability: 0.625,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Denis Villeneuve",
        stage_2_probability: 0.207,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 137427,
          profile_path: "/xzQYqb4nR8xT7Zdw5itbEL9K3fd.jpg",
          url: "https://image.tmdb.org/t/p/w185/xzQYqb4nR8xT7Zdw5itbEL9K3fd.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:nathan-fielder",
        subject: "Nathan Fielder",
        detail: "You Can See Everything",
        credit_source: "tmdb:person:1212667",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Nathan Fielder",
        stage_1_probability: 0.65,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Nathan Fielder",
        stage_2_probability: 0.12,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1212667,
          profile_path: "/x0UOcjml8WnBfnb89QOh0iXM0w0.jpg",
          url: "https://image.tmdb.org/t/p/w185/x0UOcjml8WnBfnb89QOh0iXM0w0.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:javier-calvo-ambrossi",
        subject: "Javier Calvo & Javier Ambrossi",
        detail: "The Black Ball",
        credit_source: "tmdb:person:1443615",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Javier Calvo",
        stage_1_probability: 0.9,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Javier Calvo and Javier Ambrossi",
        stage_2_probability: 0.072,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1443615,
          profile_path: "/4XfEHAholH6DI1flBpQDHYGSC1l.jpg",
          url: "https://image.tmdb.org/t/p/w185/4XfEHAholH6DI1flBpQDHYGSC1l.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:martin-mcdonagh",
        subject: "Martin McDonagh",
        detail: "Wild Horse Nine",
        credit_source: "tmdb:person:54472",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Martin McDonagh",
        stage_1_probability: 0.605,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Martin McDonagh",
        stage_2_probability: 0.024,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 54472,
          profile_path: "/s44uliUJ8ksUKNpP0822cM2NBkI.jpg",
          url: "https://image.tmdb.org/t/p/w185/s44uliUJ8ksUKNpP0822cM2NBkI.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:alejandro-inarritu",
        subject: "Alejandro G. Iñárritu",
        detail: "Digger",
        credit_source: "tmdb:person:223",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Alejandro González Iñárritu",
        stage_1_probability: 0.205,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Alejandro G. Iñárritu",
        stage_2_probability: 0.014,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 223,
          profile_path: "/opRQx3XlOoXH5EFlm0v8Q3O1ccn.jpg",
          url: "https://image.tmdb.org/t/p/w185/opRQx3XlOoXH5EFlm0v8Q3O1ccn.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
    ],
  },
  "oscars-2027-best-actor": {
    set_id: "oscars-2027-best-actor",
    category: "entertainment",
    kicker: "OSCARS 2027 · BEST ACTOR",
    title: "John Malkovich leads Best Actor, with 3 contenders above 90% to be nominated",
    subtitle: "Top 6 actors by win % (#5388752 + #5869749) · Verified TMDB headshots",
    selection_rule: "top_6_by_stage_2_then_stage_1",
    stage_1_label: "Nominated",
    stage_2_label: "Wins",
    stage_1_settled_yes_label: "Nominated",
    stage_1_settled_no_label: "Not nominated",
    stage_1_market: {
      id: 5388752,
      source: "kalshi",
      name: "Oscar nominees: Best Actor",
    },
    stage_2_market: {
      id: 5869749,
      source: "kalshi",
      name: "Oscar winner: Best Actor",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "person:john-malkovich",
        subject: "John Malkovich",
        detail: "The Black Ball",
        credit_source: "tmdb:person:6949",
        stage_1_market_id: 5388752,
        stage_1_outcome: "John Malkovich",
        stage_1_probability: 0.955,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "John Malkovich",
        stage_2_probability: 0.424,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 6949,
          profile_path: "/7GoOdGNc4ra1L0F5nJTkmIB37iu.jpg",
          url: "https://image.tmdb.org/t/p/w185/7GoOdGNc4ra1L0F5nJTkmIB37iu.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:andrew-scott",
        subject: "Andrew Scott",
        detail: "Elsinore",
        credit_source: "tmdb:person:125660",
        stage_1_market_id: 5388752,
        stage_1_outcome: "Andrew Scott",
        stage_1_probability: 0.91,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "Andrew Scott",
        stage_2_probability: 0.224,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 125660,
          profile_path: "/4F8XpjyQCvtuu21WFm5d8RF5Rl.jpg",
          url: "https://image.tmdb.org/t/p/w185/4F8XpjyQCvtuu21WFm5d8RF5Rl.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:matt-damon",
        subject: "Matt Damon",
        detail: "The Odyssey",
        credit_source: "tmdb:person:1892",
        stage_1_market_id: 5388752,
        stage_1_outcome: "Matt Damon",
        stage_1_probability: 0.935,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "Matt Damon",
        stage_2_probability: 0.167,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1892,
          profile_path: "/aCvBXTAR9B1qRjIRzMBYhhbm1fR.jpg",
          url: "https://image.tmdb.org/t/p/w185/aCvBXTAR9B1qRjIRzMBYhhbm1fR.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:anthony-ippolito",
        subject: "Anthony Ippolito",
        detail: "I Play Rocky",
        credit_source: "tmdb:person:1496755",
        stage_1_market_id: 5388752,
        stage_1_outcome: "Anthony Ippolito",
        stage_1_probability: 0.495,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "Anthony Ippolito",
        stage_2_probability: 0.062,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1496755,
          profile_path: "/a5wHhLA0HwOHnoajmFGpMRtY6OT.jpg",
          url: "https://image.tmdb.org/t/p/w185/a5wHhLA0HwOHnoajmFGpMRtY6OT.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:tom-cruise",
        subject: "Tom Cruise",
        detail: "Digger",
        credit_source: "tmdb:person:500",
        stage_1_market_id: 5388752,
        stage_1_outcome: "Tom Cruise",
        stage_1_probability: 0.495,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "Tom Cruise",
        stage_2_probability: 0.052,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 500,
          profile_path: "/maf8PhSvDCdEwjEMbYfGpojR5RP.jpg",
          url: "https://image.tmdb.org/t/p/w185/maf8PhSvDCdEwjEMbYfGpojR5RP.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:ryan-gosling",
        subject: "Ryan Gosling",
        detail: "Project Hail Mary",
        credit_source: "tmdb:person:30614",
        stage_1_market_id: 5388752,
        stage_1_outcome: "Ryan Gosling",
        stage_1_probability: 0.385,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "Ryan Gosling",
        stage_2_probability: 0.014,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 30614,
          profile_path: "/lyUyVARQKhGxaxy0FbPJCQRpiaW.jpg",
          url: "https://image.tmdb.org/t/p/w185/lyUyVARQKhGxaxy0FbPJCQRpiaW.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
    ],
  },
  "oscars-2027-best-actress": {
    set_id: "oscars-2027-best-actress",
    category: "entertainment",
    kicker: "OSCARS 2027 · BEST ACTRESS",
    title: "Julianne Moore leads Best Actress at 75% to win",
    subtitle: "Top 4 actresses by nominated % (#5388751 + #5869748) · Verified TMDB headshots",
    selection_rule: "top_4_by_stage_1_then_stage_2",
    stage_1_label: "Nominated",
    stage_2_label: "Wins",
    stage_1_settled_yes_label: "Nominated",
    stage_1_settled_no_label: "Not nominated",
    stage_1_market: {
      id: 5388751,
      source: "kalshi",
      name: "Oscar nominees: Best Actress",
    },
    stage_2_market: {
      id: 5869748,
      source: "kalshi",
      name: "Oscar winner: Best Actress",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "person:julianne-moore",
        subject: "Julianne Moore",
        detail: "The Debut",
        credit_source: "tmdb:person:1231",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Julianne Moore",
        stage_1_probability: 0.975,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Julianne Moore",
        stage_2_probability: 0.745,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1231,
          profile_path: "/3YF19rWusxWfEI59ZM33dFhasRq.jpg",
          url: "https://image.tmdb.org/t/p/w185/3YF19rWusxWfEI59ZM33dFhasRq.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:inde-navarrette",
        subject: "Inde Navarrette",
        detail: "Obsession",
        credit_source: "tmdb:person:2638587",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Inde Navarrette",
        stage_1_probability: 0.78,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Inde Navarrette",
        stage_2_probability: 0.17,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 2638587,
          profile_path: "/qlNBUGON8FebgzcqVhhRSVFYSa5.jpg",
          url: "https://image.tmdb.org/t/p/w185/qlNBUGON8FebgzcqVhhRSVFYSa5.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:sandra-huller",
        subject: "Sandra Hüller",
        detail: "1949 / Fatherland",
        credit_source: "tmdb:person:7152",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Sandra Hüller",
        stage_1_probability: 0.655,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Sandra Hüller",
        stage_2_probability: 0.025,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 7152,
          profile_path: "/jQfKXVCPTH9KEnzHHU4QemCnlMe.jpg",
          url: "https://image.tmdb.org/t/p/w185/jQfKXVCPTH9KEnzHHU4QemCnlMe.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:olivia-wilde",
        subject: "Olivia Wilde",
        detail: "The Invite",
        credit_source: "tmdb:person:59315",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Olivia Wilde",
        stage_1_probability: 0.725,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Olivia Wilde",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 59315,
          profile_path: "/eODi1QKamyVa41eSK2SjU20VAZS.jpg",
          url: "https://image.tmdb.org/t/p/w185/eODi1QKamyVa41eSK2SjU20VAZS.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
    ],
  },
  "oscars-2027-best-animated": {
    set_id: "oscars-2027-best-animated",
    category: "entertainment",
    kicker: "OSCARS 2027 · BEST ANIMATED FEATURE",
    title: "Wildwood leads Best Animated Feature at 86% to win",
    subtitle: "Top 4 animated films by win % (#6330235 + #58492239) · Sourced TMDB credits & posters",
    selection_rule: "top_4_by_stage_2_then_stage_1",
    stage_1_label: "Nominated",
    stage_2_label: "Wins",
    stage_1_settled_yes_label: "Nominated",
    stage_1_settled_no_label: "Not nominated",
    stage_1_market: {
      id: 6330235,
      source: "kalshi",
      name: "Oscar nominees: Best Animated Feature Film",
    },
    stage_2_market: {
      id: 58492239,
      source: "polymarket",
      name: "Oscars 2027: Best Animated Feature Film Winner",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "film:wildwood-2026",
        subject: "Wildwood",
        detail: "Travis Knight · LAIKA",
        credit_source: "tmdb:movie:791523",
        stage_1_market_id: 6330235,
        stage_1_outcome: "Wildwood",
        stage_1_probability: 0.97,
        stage_1_settled_state: null,
        stage_2_market_id: 58492239,
        stage_2_outcome: "Wildwood",
        stage_2_probability: 0.859,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 791523,
          poster_path: "/snFM00mpNAfUzUtkdEW0uDEvXA0.jpg",
          url: "https://image.tmdb.org/t/p/w342/snFM00mpNAfUzUtkdEW0uDEvXA0.jpg",
          genre_ids: [16, 12, 14],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:toy-story-5-2026",
        subject: "Toy Story 5",
        detail: "Andrew Stanton · Pixar",
        credit_source: "tmdb:movie:1084244",
        stage_1_market_id: 6330235,
        stage_1_outcome: "Toy Story 5",
        stage_1_probability: 0.85,
        stage_1_settled_state: null,
        stage_2_market_id: 58492239,
        stage_2_outcome: "Toy Story 5",
        stage_2_probability: 0.05,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1084244,
          poster_path: "/sfQtVlIHljToOwYjhe21KPGzZWK.jpg",
          url: "https://image.tmdb.org/t/p/w342/sfQtVlIHljToOwYjhe21KPGzZWK.jpg",
          genre_ids: [16, 10751, 35, 12],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:tangles-2026",
        subject: "Tangles",
        detail: "Leah Nelson · Monarch Media",
        credit_source: "tmdb:movie:1316999",
        stage_1_market_id: 6330235,
        stage_1_outcome: "Tangles",
        stage_1_probability: 0.56,
        stage_1_settled_state: null,
        stage_2_market_id: 58492239,
        stage_2_outcome: "Tangles",
        stage_2_probability: 0.039,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1316999,
          poster_path: "/agQGw5Cux2CYaxI8UHlLbta2bgw.jpg",
          url: "https://image.tmdb.org/t/p/w342/agQGw5Cux2CYaxI8UHlLbta2bgw.jpg",
          genre_ids: [16, 18, 35, 36],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:ray-gunn-2026",
        subject: "Ray Gunn",
        detail: "Brad Bird · Skydance Animation",
        credit_source: "tmdb:movie:940009",
        stage_1_market_id: 6330235,
        stage_1_outcome: "Ray Gunn",
        stage_1_probability: 0.71,
        stage_1_settled_state: null,
        stage_2_market_id: 58492239,
        stage_2_outcome: "Ray Gunn",
        stage_2_probability: 0.019,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 940009,
          poster_path: "/rpP29aOKpHy1FhX8OZQdUICEs2j.jpg",
          url: "https://image.tmdb.org/t/p/w342/rpP29aOKpHy1FhX8OZQdUICEs2j.jpg",
          genre_ids: [16, 878, 80, 9648],
          adult: false,
          kid_safe_vetted: true,
        },
      },
    ],
  },
  "nhl-2026-27-playoffs-and-cup": {
    set_id: "nhl-2026-27-playoffs-and-cup",
    category: "hockey",
    kicker: "NHL 2026–27 · PLAYOFF BERTH TO STANLEY CUP",
    title: "Carolina leads the Stanley Cup race, with all 9 clubs at 5%+ to win",
    subtitle:
      "All 9 NHL clubs at 5%+ to win the Cup (ties broken by playoff %) · Paired by club (#63068142 + #52755659) with ESPN team crests",
    selection_rule: "all_stage_2_at_least_5pct_ties_broken_by_stage_1",
    stage_1_label: "Make Playoffs",
    stage_2_label: "Win Cup",
    stage_1_settled_yes_label: "Clinched",
    stage_1_settled_no_label: "Eliminated",
    stage_1_market: {
      id: 63068142,
      source: "polymarket",
      name: "Which teams will make the NHL Playoffs?",
    },
    stage_2_market: {
      id: 52755659,
      source: "kalshi",
      name: "2026-27 Stanley Cup® Final Winner",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "team:nhl:carolina-hurricanes",
        subject: "Carolina Hurricanes",
        detail: "Metropolitan · Eastern Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Carolina Hurricanes",
        stage_1_probability: 0.94,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Carolina Hurricanes",
        stage_2_probability: 0.128,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/car.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:colorado-avalanche",
        subject: "Colorado Avalanche",
        detail: "Central · Western Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Colorado Avalanche",
        stage_1_probability: 0.934,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Colorado Avalanche",
        stage_2_probability: 0.10,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/col.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:minnesota-wild",
        subject: "Minnesota Wild",
        detail: "Central · Western Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Minnesota Wild",
        stage_1_probability: 0.955,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Minnesota Wild",
        stage_2_probability: 0.09,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/min.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:edmonton-oilers",
        subject: "Edmonton Oilers",
        detail: "Pacific · Western Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Edmonton Oilers",
        stage_1_probability: 0.91,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Edmonton Oilers",
        stage_2_probability: 0.09,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/edm.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:new-jersey-devils",
        subject: "New Jersey Devils",
        detail: "Metropolitan · Eastern Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "New Jersey Devils",
        stage_1_probability: 0.825,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "New Jersey Devils",
        stage_2_probability: 0.071,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/nj.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:florida-panthers",
        subject: "Florida Panthers",
        detail: "Atlantic · Eastern Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Florida Panthers",
        stage_1_probability: 0.7,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Florida Panthers",
        stage_2_probability: 0.071,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/fla.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:vegas-golden-knights",
        subject: "Vegas Golden Knights",
        detail: "Pacific · Western Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Vegas Golden Knights",
        stage_1_probability: 0.895,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Vegas Golden Knights",
        stage_2_probability: 0.062,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/vgk.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:dallas-stars",
        subject: "Dallas Stars",
        detail: "Central · Western Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Dallas Stars",
        stage_1_probability: 0.835,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Dallas Stars",
        stage_2_probability: 0.052,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/dal.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "team:nhl:tampa-bay-lightning",
        subject: "Tampa Bay Lightning",
        detail: "Atlantic · Eastern Conference",
        stage_1_market_id: 63068142,
        stage_1_outcome: "Tampa Bay Lightning",
        stage_1_probability: 0.82,
        stage_1_settled_state: null,
        stage_2_market_id: 52755659,
        stage_2_outcome: "Tampa Bay Lightning",
        stage_2_probability: 0.052,
        art: {
          kind: "espn_team_logo",
          url: "https://a.espncdn.com/i/teamlogos/nhl/500/tb.png",
          adult: false,
          kid_safe_vetted: true,
        },
      },
    ],
  },
};

export interface LookSheetCardSpec {
  position: number;
  block_id: number;
  item_key: string;
  label: string;
  form: VisualFormContract;
  set_id: string;
  force_settled_stage_1?: boolean;
  sheet?: 1 | 2;
  why_it_exists: string;
}

export const VISUAL_FORM_LOOK_SHEET_CARDS: LookSheetCardSpec[] = [
  {
    position: 7,
    block_id: 1,
    item_key: "form-1-v2-paired-bars-with-art-best-picture",
    label: "Card 1 (v2) · Stacked Dual Bars with Poster (Full 10-Row Baseline)",
    form: VISUAL_FORM_LIBRARY.paired_bars_with_art,
    set_id: "oscars-2027-best-picture",
    sheet: 1,
    why_it_exists:
      "Alex's baseline form: one row per film (for the 10 films most likely to be nominated, ordered by Wins %) with its poster and both bars stacked together in one column (Nominated % above Wins %).",
  },
  {
    position: 8,
    block_id: 2,
    item_key: "form-2-v2-poster-spotlight-tiles-best-picture",
    label: "Card 2 (v2) · Poster-Led 2-Up Spotlight Tiles (Best Picture 2027)",
    form: VISUAL_FORM_LIBRARY.poster_spotlight_tiles,
    set_id: "oscars-2027-best-picture",
    sheet: 1,
    why_it_exists:
      "Cinema-first grid: the poster leads each tile while Wins % remains the headline number and Nominated % sits beside it.",
  },
  {
    position: 9,
    block_id: 3,
    item_key: "form-3-v2-step-conversion-path-best-picture",
    label: "Card 3 (v2) · Path from Nominated to Wins (Best Picture 2027)",
    form: VISUAL_FORM_LIBRARY.step_conversion_path,
    set_id: "oscars-2027-best-picture",
    sheet: 1,
    why_it_exists:
      "Draws the two propositions as one funnel track (outer reach = Nominated %, inner fill = Wins %), immediately exposing nomination locks that are longshots to win (Wild Horse Nine: 93% → 2%).",
  },
  {
    position: 10,
    block_id: 4,
    item_key: "form-4-v2-leader-and-chasers-split-best-picture",
    form: VISUAL_FORM_LIBRARY.leader_and_chasers_split,
    label: "Card 4 (v2) · One Leader and Its Chasers (Best Picture 2027)",
    set_id: "oscars-2027-best-picture",
    sheet: 1,
    why_it_exists:
      "Picked when #1 holds >= 40% to win: The Odyssey (57% win / 98% nom, +40 pts ahead of #2) gets a hero spotlight banner while the chasing pack sits in compact two-number strips.",
  },
  {
    position: 11,
    block_id: 5,
    item_key: "form-5-v2-sports-playoffs-to-title-nhl",
    label: "Card 5 (v2) · Non-Oscars Proof: NHL Make Playoffs % beside Win Stanley Cup % (All 9 Clubs >= 5%)",
    form: VISUAL_FORM_LIBRARY.paired_bars_with_art,
    set_id: "nhl-2026-27-playoffs-and-cup",
    sheet: 1,
    why_it_exists:
      "Proves the form travels outside the Oscars without hardcoding: same 'two related numbers per subject + picture' contract with ESPN NHL crests and deterministic tie-breaking (Dallas Stars 84%/5% alongside Tampa Bay Lightning 82%/5%).",
  },
  {
    position: 12,
    block_id: 6,
    item_key: "form-6-v2-post-nominations-settled-gate",
    label: "Card 6 (v2) · Post-Nominations State: ✓ / ✗ Replaces the First Bar ('Settled Means Settled')",
    form: VISUAL_FORM_LIBRARY.settled_gate_after_nominations,
    set_id: "oscars-2027-best-picture",
    force_settled_stage_1: true,
    sheet: 1,
    why_it_exists:
      "Shows the unbending post-nomination rule: once nominations settle, the first bar becomes ✓ Nominated or ✗ Not nominated while the live Winner % bar continues.",
  },
];

export const VISUAL_FORM_SHEET_2_CARDS: LookSheetCardSpec[] = [
  {
    position: 1,
    block_id: 10,
    item_key: "form-1a-paired-bars-top5-expandable-best-picture",
    label: "Shorter Card 1A · Top 5 Dual Bars + 'Show All 10' Expander (Cuts Default Height by 48%)",
    form: VISUAL_FORM_LIBRARY.paired_bars_top5_expandable,
    set_id: "oscars-2027-best-picture",
    sheet: 2,
    why_it_exists:
      "Alex's 8:33 PM reaction: from the 10 films most likely to be nominated, keeps the exact poster + two-bar comparison row from Card 1 for the top 5 by Win % by default with a one-tap 'Show all 10 most likely nominees' expander.",
  },
  {
    position: 2,
    block_id: 11,
    item_key: "form-1b-paired-bars-single-line-best-picture",
    label: "Shorter Card 1B · One Line Per Film with Mini Poster, Micro-Bars & Both Numbers (All 10 Visible)",
    form: VISUAL_FORM_LIBRARY.paired_bars_single_line,
    set_id: "oscars-2027-best-picture",
    sheet: 2,
    why_it_exists:
      "Shows all 10 films most likely to be nominated (ordered by Win %) at once with zero truncation in 46% less vertical height by placing the mini poster, title, dual micro-bars, Nominated % and Wins % on one compact row.",
  },
  {
    position: 3,
    block_id: 12,
    item_key: "form-1c-paired-bars-top3-plus-strip-best-picture",
    label: "Shorter Card 1C · Top 3 Full Dual-Bar Rows + 2-Up Grid for the Other 7 Most Likely Nominees",
    form: VISUAL_FORM_LIBRARY.paired_bars_top3_plus_strip,
    set_id: "oscars-2027-best-picture",
    sheet: 2,
    why_it_exists:
      "From the 10 films most likely to be nominated, gives the top 3 by Win % (The Odyssey 57%, You Can See Everything 17%, The Black Ball 15%) full poster + dual-bar rows while packing the remaining 7 into a 2-column grid below.",
  },
  {
    position: 4,
    block_id: 13,
    item_key: "form-7-podium-and-tiers-best-picture",
    label: "Wild Form A · Three-Spot Trophy Podium + 70%+ vs <70% Nomination Tiers",
    form: VISUAL_FORM_LIBRARY.podium_and_tiers,
    set_id: "oscars-2027-best-picture",
    sheet: 2,
    why_it_exists:
      "Breaks out of row lists: puts #1 The Odyssey (center), #2 You Can See Everything (left), and #3 The Black Ball (right) on a visual podium, with the other 7 of the top 10 most likely nominees grouped into 'Likely Nominees (70%+ to be nominated)' vs 'On the Nomination Bubble (<70% to be nominated)'.",
  },
  {
    position: 5,
    block_id: 14,
    item_key: "form-8-barbell-race-track-best-picture",
    label: "Wild Form B · 0–100% Barbell Gap Track (Wins ●━━━━○ Nominated on One Shared Scale)",
    form: VISUAL_FORM_LIBRARY.barbell_race_track,
    set_id: "oscars-2027-best-picture",
    sheet: 2,
    why_it_exists:
      "For the 10 films most likely to be nominated, plots both numbers as a connected barbell on a single 0–100% horizontal track (green dot = Wins %, dark dot = Nominated %), turning the gap between getting nominated and winning into a physical span.",
  },
  {
    position: 6,
    block_id: 15,
    item_key: "form-9-ballot-quadrant-map-best-picture",
    label: "Wild Form C · 2×2 Ballot Quadrant Board (Favorites vs Safe Nominees vs Likely vs Bubble)",
    form: VISUAL_FORM_LIBRARY.ballot_quadrant_map,
    set_id: "oscars-2027-best-picture",
    sheet: 2,
    why_it_exists:
      "Maps the 10 films most likely to be nominated into a 2×2 spatial board by their printed (Nominated %, Wins %) numbers so a reader immediately sees who is a Trophy Favorite, who is a Safe Nominee / Longshot Winner, and who is on the Bubble.",
  },
];

export interface ContainerLookSheetSpec {
  position: number;
  item_key: string;
  option_code: "A" | "B" | "C";
  title: string;
  subtitle: string;
  rule_summary: string;
}

export const OSCARS_CONTAINER_LOOK_SHEET_OPTIONS: ContainerLookSheetSpec[] = [
  {
    position: 13,
    item_key: "container-a-v2-alternating-form-magazine",
    option_code: "A",
    title: "Container A (v2) · Magazine Rhythm (Adjacent Sections Never Repeat a Form)",
    subtitle:
      "Section 1: Best Picture (Leader + Chasers) → Section 2: Best Director (Circular Headshot Tiles) → Section 3: Best Actress (Step Conversion Path) → Section 4: Best Animated Feature (Poster Strip)",
    rule_summary:
      "Container rule: each section picks a form from the library subject to `form[i] !== form[i-1]`, using movie posters for film categories and circular headshots for person categories.",
  },
  {
    position: 14,
    item_key: "container-b-v2-shape-driven-contrast",
    option_code: "B",
    title: "Container B (v2) · Shape-Driven Contrast (Runaway Locks vs Open Duels vs Deep 10-Film Field)",
    subtitle:
      "Top: Runaway Favorites (>=70% to win: Wildwood 86%, Julianne Moore 75%) → Middle: Open 3-Way Actor Duel (Malkovich 42% vs Scott 22% vs Damon 17%) → Bottom: Compact Best Picture Board",
    rule_summary:
      "Container rule: the probability distribution chooses the visual form — a >=70% leader gets a compact Lock Banner, a tight top-3 gets a Headshot Duel Strip, and a 10-nominee slate gets Stacked Dual Bars.",
  },
  {
    position: 15,
    item_key: "container-c-v2-two-act-ballot",
    option_code: "C",
    title: "Container C (v2) · Two-Act Ballot (90%+ Nomination Locks Rail + Category Cards)",
    subtitle:
      "Act I: 2-up grid of 90%+ nomination locks across categories (Nolan 99%, Odyssey 98%, Moore 98%, Wildwood 97%, Malkovich 96%, The Black Ball 95%) → Act II: Best Picture Poster Tile Grid + Best Director Headshot Conversion Path",
    rule_summary:
      "Container rule: separates 'What's locked for January nominations?' at the top from 'Who wins the statue in March?' below, and flips the top rail to ✓ Confirmed Nominees on nomination morning.",
  },
];
