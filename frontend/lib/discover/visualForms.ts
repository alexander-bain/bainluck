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
 *    are different propositions and are NEVER blended. They are paired by subject
 *    in a hand-kept register.
 * 2. After step 1 settles (e.g. nominations announced), the first number becomes
 *    `✓` or `✗` ("settled means settled").
 * 3. A row with no recent probability explicitly says so (e.g. "No recent win %"),
 *    never `0%` and never silently omitted.
 * 4. Every picture passes the kid-safe gate (#7461): text check (`isKidSafeText`),
 *    verified HTTPS host, `adult === false`, horror genre (`27`) excluded, and on
 *    kid surfaces (`kidSurface: true` / `/play`) delegates to `kidSafeImageUrl`.
 */

import { isKidSafeText, kidSafeImageUrl } from "@/lib/play/kidSafe";

export type FormVocabularyPart = "bars" | "tiles" | "strips" | "pictures" | "ticks";

export type VisualFormId =
  | "paired_bars_with_art"
  | "poster_spotlight_tiles"
  | "step_conversion_path"
  | "leader_and_chasers_split"
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
  genre_ids?: number[];
  adult: boolean;
  kid_safe_vetted: boolean;
}

export interface PairedSubjectEntry {
  subject_key: string;
  subject: string;
  detail: string;
  stage_1_market_id: number;
  stage_1_outcome: string | null;
  stage_1_probability: number | null;
  stage_1_settled_state: "yes" | "no" | null;
  stage_2_market_id: number;
  stage_2_outcome: string | null;
  stage_2_probability: number | null;
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
  stage_1_label: string;
  stage_2_label: string;
  stage_1_settled_yes_label: string;
  stage_1_settled_no_label: string;
  stage_1_market: {
    id: number;
    source: string;
    name: string;
  };
  stage_2_market: {
    id: number;
    source: string;
    name: string;
  };
  never_blend: true;
  as_of: string;
  entries: PairedSubjectEntry[];
}

export const VISUAL_FORM_LIBRARY: Record<VisualFormId, VisualFormContract> = {
  paired_bars_with_art: {
    form_id: "paired_bars_with_art",
    form_name: "Stacked Dual Bars with Art",
    data_shape: "two related numbers per subject, plus a picture",
    parts_vocabulary: ["pictures", "bars", "ticks"],
    slots: ["picture", "subject", "stage_1_bar_or_tick", "stage_2_bar"],
    missing_number_rule:
      "When stage 1 or stage 2 has no recent probability, render an explicit 'No recent <metric> %' badge in that bar slot.",
    settled_step_rule:
      "Once stage 1 settles, replace the stage-1 bar with ✓ (qualified/nominated) or ✗ (eliminated/missed).",
    domain_agnostic: true,
  },
  poster_spotlight_tiles: {
    form_id: "poster_spotlight_tiles",
    form_name: "Art-Led 2-Up Spotlight Tiles",
    data_shape: "two related numbers per subject, plus a picture",
    parts_vocabulary: ["pictures", "tiles", "bars", "ticks"],
    slots: ["picture", "subject", "stage_2_headline", "stage_1_badge_or_tick"],
    missing_number_rule:
      "Tile footer prints 'No recent <metric> %' instead of a numeric headline when missing.",
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
      "When stage 2 has no recent probability, show the outer stage-1 reach bar with an explicit 'No recent <stage-2> %' callout pill.",
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
      "Chasers without a recent stage-2 probability remain visible with 'No recent <metric> %' rather than dropping out.",
    settled_step_rule:
      "Stage-1 slot in both the leader hero and chaser strips flips to ✓ or ✗ once step 1 settles.",
    domain_agnostic: true,
  },
  settled_gate_after_nominations: {
    form_id: "settled_gate_after_nominations",
    form_name: "Settled Gate (✓ / ✗) + Live Final Race",
    data_shape: "two related numbers per subject, step 1 settled to ✓/✗, plus a picture",
    parts_vocabulary: ["pictures", "ticks", "bars"],
    slots: ["picture", "subject", "settled_tick_or_cross", "live_stage_2_bar"],
    missing_number_rule:
      "Qualified rows without a recent stage-2 probability say 'No recent <metric> %'.",
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
 *
 * - Fails closed on missing/unparseable URLs, non-HTTPS URLs, unknown hosts,
 *   any adult-flagged TMDB asset, any Horror (`genre_id === 27`) TMDB poster
 *   (the exact class of the #7461 Resident Evil leak), or any subject whose
 *   visible label fails `isKidSafeText`.
 * - When `kidSurface` is true (e.g. `/play` or a kid grader on `/grade/groupings`
 *   for external movie posters), enforces `kidSafeImageUrl` unless the asset is a
 *   verified sports team crest (`a.espncdn.com`).
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
 * Format Stage 1 (e.g. Nominated % or Make Playoffs %), respecting the unbending
 * rule that after nominations/clinching the first number becomes `✓` or `✗`, and
 * a row with no recent probability says so.
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
    const priorPct =
      typeof entry.stage_1_probability === "number"
        ? Math.round(entry.stage_1_probability * 100)
        : null;
    return {
      kind: "cross",
      percent: 0,
      symbol: "✗",
      label: `✗ ${set.stage_1_settled_no_label}`,
      sublabel: priorPct !== null ? `was ${priorPct}%` : undefined,
    };
  }

  if (
    typeof entry.stage_1_probability !== "number" ||
    !Number.isFinite(entry.stage_1_probability)
  ) {
    return {
      kind: "missing",
      percent: null,
      label:
        entry.missing_stage_1_reason ||
        `No recent ${set.stage_1_label.toLowerCase()} %`,
    };
  }

  const pct = Math.max(
    1,
    Math.min(99, Math.floor(entry.stage_1_probability * 100 + 0.5 + 1e-9)),
  );
  return {
    kind: "percent",
    percent: pct,
    label: `${pct}%`,
  };
}

/**
 * Format Stage 2 (e.g. Wins % or Win Cup %), never blending with Stage 1 and
 * explicitly reporting when a row has no recent probability.
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

  if (
    typeof entry.stage_2_probability !== "number" ||
    !Number.isFinite(entry.stage_2_probability)
  ) {
    return {
      kind: "missing",
      percent: null,
      label:
        entry.missing_stage_2_reason ||
        `No recent ${set.stage_2_label.toLowerCase()} %`,
    };
  }

  const pct = Math.max(
    1,
    Math.min(99, Math.floor(entry.stage_2_probability * 100 + 0.5 + 1e-9)),
  );
  return {
    kind: "percent",
    percent: pct,
    label: `${pct}%`,
  };
}

// ============================================================================
// Hand-Kept Pairing Register (Live Production Data as of 2026-11-11)
// ============================================================================

export const PAIRED_METRIC_REGISTER: Record<string, PairedMetricSet> = {
  "oscars-2027-best-picture": {
    set_id: "oscars-2027-best-picture",
    category: "entertainment",
    kicker: "OSCARS 2027 · BEST PICTURE",
    title: "Best Picture: nominated % and wins %",
    subtitle: "Ten nominees announced Jan 2027 · Paired by film (#5165726 + #6173044), kept separate",
    stage_1_label: "Nominated",
    stage_2_label: "Wins",
    stage_1_settled_yes_label: "Nominated",
    stage_1_settled_no_label: "Not nominated",
    stage_1_market: {
      id: 5165726,
      source: "kalshi",
      name: "Oscar nominees: Best Picture",
    },
    stage_2_market: {
      id: 6173044,
      source: "kalshi",
      name: "Oscar Winner: Best Picture",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "film:the-odyssey-2026",
        subject: "The Odyssey",
        detail: "Christopher Nolan · Universal",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Odyssey",
        stage_1_probability: 0.98,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Odyssey",
        stage_2_probability: 0.565,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1368337,
          url: "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
          genre_ids: [12, 28, 14],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:you-can-see-everything-2026",
        subject: "You Can See Everything",
        detail: "Nathan Fielder · A24",
        stage_1_market_id: 5165726,
        stage_1_outcome: "You Can See Everything",
        stage_1_probability: 0.855,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "You Can See Everything",
        stage_2_probability: 0.165,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1765072,
          url: "https://image.tmdb.org/t/p/w342/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
          genre_ids: [99],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:the-black-ball-2026",
        subject: "The Black Ball",
        detail: "Javier Calvo & Javier Ambrossi · (La Bola Negra)",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Black Ball",
        stage_1_probability: 0.94,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Black Ball",
        stage_2_probability: 0.145,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1422041,
          url: "https://image.tmdb.org/t/p/w342/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg",
          genre_ids: [18, 10752],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:dune-part-three-2026",
        subject: "Dune: Part Three",
        detail: "Denis Villeneuve · Warner Bros.",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Dune: Part Three",
        stage_1_probability: 0.82,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Dune: Part Three",
        stage_2_probability: 0.075,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1170608,
          url: "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
          genre_ids: [878, 12],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:wild-horse-nine-2026",
        subject: "Wild Horse Nine",
        detail: "Martin McDonagh · Searchlight",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Wild Horse Nine",
        stage_1_probability: 0.93,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Wild Horse Nine",
        stage_2_probability: 0.015,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 891621,
          url: "https://image.tmdb.org/t/p/w342/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg",
          genre_ids: [35, 80, 53],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:artificial-2026",
        subject: "Artificial",
        detail: "Luca Guadagnino · Amazon MGM",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Artificial",
        stage_1_probability: 0.57,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Artificial",
        stage_2_probability: 0.015,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1492198,
          url: "https://image.tmdb.org/t/p/w342/2bz0HPE8OFOqnyvl8sCdVDIg1KX.jpg",
          genre_ids: [35, 18, 36],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:project-hail-mary-2026",
        subject: "Project Hail Mary",
        detail: "Phil Lord & Christopher Miller · Amazon MGM",
        stage_1_market_id: 5165726,
        stage_1_outcome: "Project Hail Mary",
        stage_1_probability: 0.775,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "Project Hail Mary",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 687163,
          url: "https://image.tmdb.org/t/p/w342/iOb2fjXLbpJgyQXe46n1WtGCnaa.jpg",
          genre_ids: [878, 12],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:the-debut-2026",
        subject: "The Debut",
        detail: "Musical Drama · 2026",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Debut",
        stage_1_probability: 0.725,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Debut",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1391239,
          url: "https://image.tmdb.org/t/p/w342/qk8qWJxM9hZSbSjSoEz0LAzcoPb.jpg",
          genre_ids: [10402, 35, 18],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:the-invite-2026",
        subject: "The Invite",
        detail: "Olivia Wilde · A24",
        stage_1_market_id: 5165726,
        stage_1_outcome: "The Invite",
        stage_1_probability: 0.715,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: "The Invite",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 950028,
          url: "https://image.tmdb.org/t/p/w342/b7Dr8Chzse8VagexAporUu2RtLx.jpg",
          genre_ids: [35, 18, 10749],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:i-play-rocky-2026",
        subject: "I Play Rocky",
        detail: "Peter Farrelly · Amazon MGM",
        stage_1_market_id: 5165726,
        stage_1_outcome: "I Play Rocky",
        stage_1_probability: 0.475,
        stage_1_settled_state: null,
        stage_2_market_id: 6173044,
        stage_2_outcome: null,
        stage_2_probability: null,
        missing_stage_2_reason: "Not listed to win",
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1286656,
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
    title: "Best Director: nominated % and wins %",
    subtitle: "Paired by director (#5601024 + #5869747) · TMDB headshots",
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
      name: "Oscar Winner: Best Director",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "person:christopher-nolan",
        subject: "Christopher Nolan",
        detail: "The Odyssey",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Christopher Nolan",
        stage_1_probability: 0.985,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Christopher Nolan",
        stage_2_probability: 0.557,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 525,
          url: "https://image.tmdb.org/t/p/w185/xuAIuYSmsUzKlUMBFGVZaWsY3DZ.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:denis-villeneuve",
        subject: "Denis Villeneuve",
        detail: "Dune: Part Three",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Denis Villeneuve",
        stage_1_probability: 0.63,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Denis Villeneuve",
        stage_2_probability: 0.214,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 137427,
          url: "https://image.tmdb.org/t/p/w185/xzQYqb4nR8xT7Zdw5itbEL9K3fd.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:nathan-fielder",
        subject: "Nathan Fielder",
        detail: "You Can See Everything",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Nathan Fielder",
        stage_1_probability: 0.65,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Nathan Fielder",
        stage_2_probability: 0.119,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1212667,
          url: "https://image.tmdb.org/t/p/w185/x0UOcjml8WnBfnb89QOh0iXM0w0.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:javier-calvo-ambrossi",
        subject: "Javier Calvo & Javier Ambrossi",
        detail: "The Black Ball (La Bola Negra)",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Javier Calvo",
        stage_1_probability: 0.90,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Javier Calvo and Javier Ambrossi",
        stage_2_probability: 0.071,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1443615,
          url: "https://image.tmdb.org/t/p/w185/4XfEHAholH6DI1flBpQDHYGSC1l.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:martin-mcdonagh",
        subject: "Martin McDonagh",
        detail: "Wild Horse Nine",
        stage_1_market_id: 5601024,
        stage_1_outcome: "Martin McDonagh",
        stage_1_probability: 0.61,
        stage_1_settled_state: null,
        stage_2_market_id: 5869747,
        stage_2_outcome: "Martin McDonagh",
        stage_2_probability: 0.024,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 54472,
          url: "https://image.tmdb.org/t/p/w185/s44uliUJ8ksUKNpP0822cM2NBkI.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:alejandro-inarritu",
        subject: "Alejandro G. Iñárritu",
        detail: "Digger",
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
    title: "Best Actor: nominated % and wins %",
    subtitle: "Paired by actor (#5388752 + #5869749) · Open three-way race at the top",
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
      name: "Oscar Winner: Best Actor",
    },
    never_blend: true,
    as_of: "2026-11-11",
    entries: [
      {
        subject_key: "person:john-malkovich",
        subject: "John Malkovich",
        detail: "The Black Ball",
        stage_1_market_id: 5388752,
        stage_1_outcome: "John Malkovich",
        stage_1_probability: 0.945,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "John Malkovich",
        stage_2_probability: 0.424,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 6949,
          url: "https://image.tmdb.org/t/p/w185/7GoOdGNc4ra1L0F5nJTkmIB37iu.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:andrew-scott",
        subject: "Andrew Scott",
        detail: "Elsinore",
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
          url: "https://image.tmdb.org/t/p/w185/4F8XpjyQCvtuu21WFm5d8RF5Rl.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:matt-damon",
        subject: "Matt Damon",
        detail: "The Odyssey",
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
          url: "https://image.tmdb.org/t/p/w185/aCvBXTAR9B1qRjIRzMBYhhbm1fR.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:anthony-ippolito",
        subject: "Anthony Ippolito",
        detail: "I Play Rocky",
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
          url: "https://image.tmdb.org/t/p/w185/a5wHhLA0HwOHnoajmFGpMRtY6OT.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:tom-cruise",
        subject: "Tom Cruise",
        detail: "Digger",
        stage_1_market_id: 5388752,
        stage_1_outcome: "Tom Cruise",
        stage_1_probability: 0.485,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "Tom Cruise",
        stage_2_probability: 0.052,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 500,
          url: "https://image.tmdb.org/t/p/w185/maf8PhSvDCdEwjEMbYfGpojR5RP.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:ryan-gosling",
        subject: "Ryan Gosling",
        detail: "Project Hail Mary",
        stage_1_market_id: 5388752,
        stage_1_outcome: "Ryan Gosling",
        stage_1_probability: 0.445,
        stage_1_settled_state: null,
        stage_2_market_id: 5869749,
        stage_2_outcome: "Ryan Gosling",
        stage_2_probability: 0.014,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 30614,
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
    title: "Best Actress: nominated % and wins %",
    subtitle: "Paired by actress (#5388751 + #5869748) · Julianne Moore commands the race",
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
        detail: "You Can See Everything",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Julianne Moore",
        stage_1_probability: 0.975,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Julianne Moore",
        stage_2_probability: 0.75,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 1231,
          url: "https://image.tmdb.org/t/p/w185/3YF19rWusxWfEI59ZM33dFhasRq.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:inde-navarrette",
        subject: "Inde Navarrette",
        detail: "The Debut",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Inde Navarrette",
        stage_1_probability: 0.78,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Inde Navarrette",
        stage_2_probability: 0.165,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 2638587,
          url: "https://image.tmdb.org/t/p/w185/qlNBUGON8FebgzcqVhhRSVFYSa5.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:sandra-huller",
        subject: "Sandra Hüller",
        detail: "1949 / Fatherland",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Sandra Hüller",
        stage_1_probability: 0.64,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Sandra Hüller",
        stage_2_probability: 0.025,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 7152,
          url: "https://image.tmdb.org/t/p/w185/jQfKXVCPTH9KEnzHHU4QemCnlMe.jpg",
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "person:olivia-wilde",
        subject: "Olivia Wilde",
        detail: "The Invite",
        stage_1_market_id: 5388751,
        stage_1_outcome: "Olivia Wilde",
        stage_1_probability: 0.715,
        stage_1_settled_state: null,
        stage_2_market_id: 5869748,
        stage_2_outcome: "Olivia Wilde",
        stage_2_probability: 0.01,
        art: {
          kind: "tmdb_headshot",
          tmdb_id: 59315,
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
    title: "Best Animated Feature: nominated % and wins %",
    subtitle: "Paired by film (#6330235 + #58492239) · Family-safe animated posters",
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
        detail: "LAIKA · Travis Knight",
        stage_1_market_id: 6330235,
        stage_1_outcome: "Wildwood",
        stage_1_probability: 0.965,
        stage_1_settled_state: null,
        stage_2_market_id: 58492239,
        stage_2_outcome: "Wildwood",
        stage_2_probability: 0.85,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 791523,
          url: "https://image.tmdb.org/t/p/w342/snFM00mpNAfUzUtkdEW0uDEvXA0.jpg",
          genre_ids: [16, 12, 14],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:toy-story-5-2026",
        subject: "Toy Story 5",
        detail: "Pixar · Andrew Stanton",
        stage_1_market_id: 6330235,
        stage_1_outcome: "Toy Story 5",
        stage_1_probability: 0.915,
        stage_1_settled_state: null,
        stage_2_market_id: 58492239,
        stage_2_outcome: "Toy Story 5",
        stage_2_probability: 0.06,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1084244,
          url: "https://image.tmdb.org/t/p/w342/sfQtVlIHljToOwYjhe21KPGzZWK.jpg",
          genre_ids: [16, 10751, 35, 12],
          adult: false,
          kid_safe_vetted: true,
        },
      },
      {
        subject_key: "film:tangles-2026",
        subject: "Tangles",
        detail: "Animated Memoir · 2026",
        stage_1_market_id: 6330235,
        stage_1_outcome: "Tangles",
        stage_1_probability: 0.555,
        stage_1_settled_state: null,
        stage_2_market_id: 58492239,
        stage_2_outcome: "Tangles",
        stage_2_probability: 0.04,
        art: {
          kind: "tmdb_poster",
          tmdb_id: 1316999,
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
    title: "NHL contenders: make playoffs % and win Stanley Cup %",
    subtitle: "Same two-number form on live NHL markets (#63068142 + #52755659) · Paired by club with ESPN team crests",
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
        stage_1_probability: 0.935,
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
        stage_1_probability: 0.68,
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
        stage_1_probability: 0.89,
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
  item_key: string;
  label: string;
  form: VisualFormContract;
  set_id: string;
  force_settled_stage_1?: boolean;
  why_it_exists: string;
}

export const VISUAL_FORM_LOOK_SHEET_CARDS: LookSheetCardSpec[] = [
  {
    position: 1,
    item_key: "form-1-paired-bars-with-art-best-picture",
    label: "Card 1 · Stacked Dual Bars with Poster (Best Picture 2027)",
    form: VISUAL_FORM_LIBRARY.paired_bars_with_art,
    set_id: "oscars-2027-best-picture",
    why_it_exists:
      "Alex's Nov 4 / Nov 10 baseline: one row per film with its poster and both bars stacked together in one column (Nominated % above Wins %).",
  },
  {
    position: 2,
    item_key: "form-2-poster-spotlight-tiles-best-picture",
    label: "Card 2 · Poster-Led 2-Up Spotlight Tiles (Best Picture 2027)",
    form: VISUAL_FORM_LIBRARY.poster_spotlight_tiles,
    set_id: "oscars-2027-best-picture",
    why_it_exists:
      "Cinema-first grid: the poster leads each tile while Wins % remains the headline number and Nominated % sits beside it.",
  },
  {
    position: 3,
    item_key: "form-3-step-conversion-path-best-picture",
    label: "Card 3 · Path from Nominated to Wins (Best Picture 2027)",
    form: VISUAL_FORM_LIBRARY.step_conversion_path,
    set_id: "oscars-2027-best-picture",
    why_it_exists:
      "Draws the two propositions as one funnel track (outer reach = Nominated %, inner fill = Wins %), immediately exposing nomination locks that are longshots to win (Wild Horse Nine: 93% → 2%).",
  },
  {
    position: 4,
    item_key: "form-4-leader-and-chasers-split-best-picture",
    form: VISUAL_FORM_LIBRARY.leader_and_chasers_split,
    label: "Card 4 · One Leader and Its Chasers (Best Picture 2027)",
    set_id: "oscars-2027-best-picture",
    why_it_exists:
      "Picked when #1 holds >= 40% to win: The Odyssey (57% win / 98% nom, +40 pts ahead of #2) gets a hero spotlight banner while the chasing pack sits in compact two-number strips.",
  },
  {
    position: 5,
    item_key: "form-5-sports-playoffs-to-title-nhl",
    label: "Card 5 · Non-Oscars Proof: NHL Make Playoffs % beside Win Stanley Cup % (with Team Logos)",
    form: VISUAL_FORM_LIBRARY.paired_bars_with_art,
    set_id: "nhl-2026-27-playoffs-and-cup",
    why_it_exists:
      "Proves the form travels outside the Oscars without hardcoding: same 'two related numbers per subject + picture' contract, swapping movie posters for verified ESPN NHL crests.",
  },
  {
    position: 6,
    item_key: "form-6-post-nominations-settled-gate",
    label: "Card 6 · Post-Nominations State: ✓ / ✗ Replaces the First Bar ('Settled Means Settled')",
    form: VISUAL_FORM_LIBRARY.settled_gate_after_nominations,
    set_id: "oscars-2027-best-picture",
    force_settled_stage_1: true,
    why_it_exists:
      "Shows the unbending post-nomination rule: once nominations settle, the first bar becomes ✓ Nominated or ✗ Not nominated while the live Winner % bar continues.",
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
    position: 7,
    item_key: "container-a-alternating-form-magazine",
    option_code: "A",
    title: "Container A · Magazine Rhythm (Adjacent Sections Never Repeat a Form)",
    subtitle:
      "Section 1: Best Picture (Leader + Chasers) → Section 2: Best Director (Circular Headshot Tiles) → Section 3: Best Actress (Step Conversion Path) → Section 4: Best Animated Feature (Poster Strip)",
    rule_summary:
      "Container rule: each section picks a form from the library subject to `form[i] !== form[i-1]`, using movie posters for film categories and circular headshots for person categories.",
  },
  {
    position: 8,
    item_key: "container-b-shape-driven-contrast",
    option_code: "B",
    title: "Container B · Shape-Driven Contrast (Runaway Locks vs Open Duels vs Deep 10-Film Field)",
    subtitle:
      "Top: Runaway Favorites (>=70% to win: Wildwood 85%, Julianne Moore 75%) → Middle: Open 3-Way Actor Duel (Malkovich 42% vs Scott 22% vs Damon 17%) → Bottom: Full 10-Film Best Picture Board",
    rule_summary:
      "Container rule: the probability distribution chooses the visual form — a >=70% leader gets a compact Lock Banner, a tight top-3 gets a Headshot Duel Strip, and a 10-nominee slate gets Stacked Dual Bars.",
  },
  {
    position: 9,
    item_key: "container-c-two-act-ballot",
    option_code: "C",
    title: "Container C · Two-Act Ballot (90%+ Nomination Locks Rail + Category Cards)",
    subtitle:
      "Act I: 2-up grid of 90%+ nomination locks across categories (Nolan 99%, Odyssey 98%, Moore 98%, Wildwood 97%, Malkovich 95%, The Black Ball 94%) → Act II: Best Picture Poster Tile Grid + Best Director Headshot Conversion Path",
    rule_summary:
      "Container rule: separates 'What's locked for January nominations?' at the top from 'Who wins the statue in March?' below, and flips the top rail to ✓ Confirmed Nominees on nomination morning.",
  },
];
