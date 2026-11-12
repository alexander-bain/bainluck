/**
 * #12609 — The NFL Playoffs and Super Bowl Container Look Sheet (Step 1).
 *
 * Pillar: DISCOVER.
 * What a reader gets: one place for the NFL playoffs and Super Bowl LXI
 * (Resolves Feb 14, 2027) that is fun to look at — who gets in, who gets
 * through, who wins it, with verified ESPN team crests and player headshots,
 * where adjacent sections never share a visual form and the shape of the
 * numbers picks the form (#12523).
 *
 * Includes Fable's 11:39 AM PT addition (#12609#issuecomment-6805505680):
 * Section 6 is a "too many props" section on a real NFL game with a full prop
 * board (Pittsburgh Steelers at Cincinnati Bengals, Event #14780578 — 681 live
 * game markets / 394 player prop lines), showing a first screen a reader can
 * take in (visually interesting, useful, fun, organized, not overwhelming) and
 * one way to reach the rest behind a toggle.
 *
 * Unbending rules:
 * 1. Stage 1 (Make Playoffs / Reach Conference Final / MVP Finalist) and Stage 2
 *    (Win Super Bowl / Win Conference / Win MVP) are distinct propositions and
 *    are NEVER blended with each other.
 * 2. Equivalent venue legs for the SAME proposition are blended.
 * 3. After Stage 1 settles, the first number becomes ✓ or ✗ ("settled means settled").
 * 4. Every logo and headshot is verified (`a.espncdn.com`) and passes the #7461
 *    kid-safe gate (`resolveNflKidSafeArt`).
 * 5. Rounding uses `renderedPercent` (#1933 / #3867).
 * 6. Never calls a market a "question" (#12591) and never prints internal
 *    database market IDs on the reader-facing card face (#12577 / #12600).
 */

import { isKidSafeText, kidSafeImageUrl } from "@/lib/play/kidSafe";
import { renderedPercent } from "@/lib/renderedPercent";
import type { FormVocabularyPart, VisualFormContract } from "@/lib/discover/visualForms";

export const NFL_PLAYOFFS_LOOK_SHEET_SLATE_ID = "nfl-playoffs-look-sheet-2026-11";

export type NflVisualFormId =
  | "paired_bars_top6_expandable"
  | "step_conversion_path_conference"
  | "shape_driven_division_contrast"
  | "podium_and_headshot_tiles"
  | "matchup_swing_cards"
  | "curated_prop_board_with_drawer"
  | "self_building_season_container";

export interface NflLookSheetContract extends Omit<VisualFormContract, "form_id"> {
  form_id: NflVisualFormId;
}

export interface NflArtAsset {
  kind: "espn_team_logo" | "espn_player_headshot";
  url: string;
  verified_id: string;
  adult: false;
  kid_safe_vetted: true;
}

const ALLOWED_NFL_ART_HOSTS = new Set(["a.espncdn.com"]);

/**
 * #7461 Kid-Safe Gate for NFL team crests and player headshots.
 */
export function resolveNflKidSafeArt(
  subject: string,
  detail: string,
  art: NflArtAsset | null | undefined,
  options?: { kidSurface?: boolean },
): string | null {
  if (!art || !art.url) return null;
  if (art.adult || !art.kid_safe_vetted) return null;
  if (!isKidSafeText(subject) || !isKidSafeText(detail)) return null;

  let parsed: URL;
  try {
    parsed = new URL(art.url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") return null;
  if (!ALLOWED_NFL_ART_HOSTS.has(parsed.hostname)) return null;

  if (options?.kidSurface) {
    if (parsed.hostname === "a.espncdn.com") {
      return art.url;
    }
    return kidSafeImageUrl(art.url);
  }
  return art.url;
}

export function formatPct(probability: number | null | undefined): string {
  const pct = renderedPercent(probability);
  if (pct === null) return "Not listed";
  return `${pct}%`;
}

// ============================================================================
// Section 1: Make Playoffs % beside Win Super Bowl % (12 Clubs in the Hunt)
// ============================================================================

export interface NflPlayoffSuperBowlClub {
  club_key: string;
  team: string;
  abbreviation: string;
  conference: "AFC" | "NFC";
  division: string;
  record: string;
  make_playoffs_market_id: number;
  make_playoffs_probability: number;
  win_super_bowl_market_id: number;
  win_super_bowl_probability: number;
  logo: NflArtAsset;
}

export const NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS: NflPlayoffSuperBowlClub[] = [
  {
    club_key: "nfl:sf",
    team: "San Francisco 49ers",
    abbreviation: "SF",
    conference: "NFC",
    division: "NFC West",
    record: "7-1",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.975,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.1283,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/sf.png",
      verified_id: "espn:nfl:sf",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:buf",
    team: "Buffalo Bills",
    abbreviation: "BUF",
    conference: "AFC",
    division: "AFC East",
    record: "7-2",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.975,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.1265,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/buf.png",
      verified_id: "espn:nfl:buf",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:jax",
    team: "Jacksonville Jaguars",
    abbreviation: "JAX",
    conference: "AFC",
    division: "AFC South",
    record: "7-2",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.955,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.1000,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/jax.png",
      verified_id: "espn:nfl:jax",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:chi",
    team: "Chicago Bears",
    abbreviation: "CHI",
    conference: "NFC",
    division: "NFC North",
    record: "6-2",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.875,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0918,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/chi.png",
      verified_id: "espn:nfl:chi",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:kc",
    team: "Kansas City Chiefs",
    abbreviation: "KC",
    conference: "AFC",
    division: "AFC West",
    record: "6-2",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.925,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0719,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/kc.png",
      verified_id: "espn:nfl:kc",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:cin",
    team: "Cincinnati Bengals",
    abbreviation: "CIN",
    conference: "AFC",
    division: "AFC North",
    record: "6-2",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.925,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0615,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/cin.png",
      verified_id: "espn:nfl:cin",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:lar",
    team: "Los Angeles Rams",
    abbreviation: "LAR",
    conference: "NFC",
    division: "NFC West",
    record: "4-4",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.455,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0553,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/lar.png",
      verified_id: "espn:nfl:lar",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:den",
    team: "Denver Broncos",
    abbreviation: "DEN",
    conference: "AFC",
    division: "AFC West",
    record: "6-3",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.920,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0505,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/den.png",
      verified_id: "espn:nfl:den",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:sea",
    team: "Seattle Seahawks",
    abbreviation: "SEA",
    conference: "NFC",
    division: "NFC West",
    record: "5-4",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.505,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0477,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/sea.png",
      verified_id: "espn:nfl:sea",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:det",
    team: "Detroit Lions",
    abbreviation: "DET",
    conference: "NFC",
    division: "NFC North",
    record: "6-2",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.765,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0449,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/det.png",
      verified_id: "espn:nfl:det",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:gb",
    team: "Green Bay Packers",
    abbreviation: "GB",
    conference: "NFC",
    division: "NFC North",
    record: "6-3",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.645,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0384,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/gb.png",
      verified_id: "espn:nfl:gb",
      adult: false,
      kid_safe_vetted: true,
    },
  },
  {
    club_key: "nfl:min",
    team: "Minnesota Vikings",
    abbreviation: "MIN",
    conference: "NFC",
    division: "NFC North",
    record: "6-2",
    make_playoffs_market_id: 62679,
    make_playoffs_probability: 0.695,
    win_super_bowl_market_id: 86832,
    win_super_bowl_probability: 0.0380,
    logo: {
      kind: "espn_team_logo",
      url: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/min.png",
      verified_id: "espn:nfl:min",
      adult: false,
      kid_safe_vetted: true,
    },
  },
];

// ============================================================================
// Section 2: AFC & NFC Conference Championship Conversion Paths
// ============================================================================

export interface NflConferencePathEntry {
  club_key: string;
  team: string;
  abbreviation: string;
  conference: "AFC" | "NFC";
  detail: string;
  reach_conf_final_market_id: number;
  reach_conf_final_probability: number;
  win_conference_market_id: number;
  win_conference_probability: number;
  logo: NflArtAsset;
}

export const NFL_CONFERENCE_PATH_ENTRIES: NflConferencePathEntry[] = [
  // AFC (#60087222 Reach AFC Title Game paired with #31616/#129172 Win AFC)
  {
    club_key: "afc:buf",
    team: "Buffalo Bills",
    abbreviation: "BUF",
    conference: "AFC",
    detail: "AFC East · 7-2",
    reach_conf_final_market_id: 60087222,
    reach_conf_final_probability: 0.485,
    win_conference_market_id: 31616,
    win_conference_probability: 0.245,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[1].logo,
  },
  {
    club_key: "afc:jax",
    team: "Jacksonville Jaguars",
    abbreviation: "JAX",
    conference: "AFC",
    detail: "AFC South · 7-2",
    reach_conf_final_market_id: 60087222,
    reach_conf_final_probability: 0.3635,
    win_conference_market_id: 31616,
    win_conference_probability: 0.210,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[2].logo,
  },
  {
    club_key: "afc:kc",
    team: "Kansas City Chiefs",
    abbreviation: "KC",
    conference: "AFC",
    detail: "AFC West · 6-2",
    reach_conf_final_market_id: 61380806,
    reach_conf_final_probability: 0.185,
    win_conference_market_id: 31616,
    win_conference_probability: 0.130,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[4].logo,
  },
  {
    club_key: "afc:cin",
    team: "Cincinnati Bengals",
    abbreviation: "CIN",
    conference: "AFC",
    detail: "AFC North · 6-2",
    reach_conf_final_market_id: 60087222,
    reach_conf_final_probability: 0.250,
    win_conference_market_id: 31616,
    win_conference_probability: 0.124,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[5].logo,
  },
  {
    club_key: "afc:den",
    team: "Denver Broncos",
    abbreviation: "DEN",
    conference: "AFC",
    detail: "AFC West · 6-3",
    reach_conf_final_market_id: 60087222,
    reach_conf_final_probability: 0.245,
    win_conference_market_id: 31616,
    win_conference_probability: 0.1125,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[7].logo,
  },
  // NFC (#60087221 Reach NFC Title Game paired with #31615/#129171 Win NFC)
  {
    club_key: "nfc:sf",
    team: "San Francisco 49ers",
    abbreviation: "SF",
    conference: "NFC",
    detail: "NFC West · 7-1",
    reach_conf_final_market_id: 60087221,
    reach_conf_final_probability: 0.445,
    win_conference_market_id: 31615,
    win_conference_probability: 0.275,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[0].logo,
  },
  {
    club_key: "nfc:chi",
    team: "Chicago Bears",
    abbreviation: "CHI",
    conference: "NFC",
    detail: "NFC North · 6-2",
    reach_conf_final_market_id: 60087221,
    reach_conf_final_probability: 0.340,
    win_conference_market_id: 31615,
    win_conference_probability: 0.180,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[3].logo,
  },
  {
    club_key: "nfc:det",
    team: "Detroit Lions",
    abbreviation: "DET",
    conference: "NFC",
    detail: "NFC North · 6-2",
    reach_conf_final_market_id: 60087221,
    reach_conf_final_probability: 0.240,
    win_conference_market_id: 31615,
    win_conference_probability: 0.1035,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[9].logo,
  },
  {
    club_key: "nfc:lar",
    team: "Los Angeles Rams",
    abbreviation: "LAR",
    conference: "NFC",
    detail: "NFC West · 4-4",
    reach_conf_final_market_id: 60087221,
    reach_conf_final_probability: 0.195,
    win_conference_market_id: 31615,
    win_conference_probability: 0.0875,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[6].logo,
  },
  {
    club_key: "nfc:min",
    team: "Minnesota Vikings",
    abbreviation: "MIN",
    conference: "NFC",
    detail: "NFC North · 6-2",
    reach_conf_final_market_id: 61380785,
    reach_conf_final_probability: 0.180,
    win_conference_market_id: 31615,
    win_conference_probability: 0.080,
    logo: NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[11].logo,
  },
];

// ============================================================================
// Section 3: Division Races by Distribution Shape (Open Battles vs Near-Locks)
// ============================================================================

export interface NflDivisionCandidate {
  team: string;
  abbreviation: string;
  probability: number;
  logo: NflArtAsset;
}

export interface NflDivisionRaceSpec {
  division: string;
  conference: "AFC" | "NFC";
  shape: "four_way_scramble" | "two_team_duel" | "near_lock";
  market_id: number;
  summary_note: string;
  candidates: NflDivisionCandidate[];
}

const TEAM_LOGO = (abbr: string): NflArtAsset => ({
  kind: "espn_team_logo",
  url: `https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/${abbr.toLowerCase()}.png`,
  verified_id: `espn:nfl:${abbr.toLowerCase()}`,
  adult: false,
  kid_safe_vetted: true,
});

export const NFL_DIVISION_RACES_BY_SHAPE: NflDivisionRaceSpec[] = [
  {
    division: "NFC North",
    conference: "NFC",
    shape: "four_way_scramble",
    market_id: 2279147,
    summary_note: "Sample note · Four-way division race with all four clubs in contention",
    candidates: [
      { team: "Chicago Bears", abbreviation: "CHI", probability: 0.380, logo: TEAM_LOGO("chi") },
      { team: "Detroit Lions", abbreviation: "DET", probability: 0.265, logo: TEAM_LOGO("det") },
      { team: "Minnesota Vikings", abbreviation: "MIN", probability: 0.245, logo: TEAM_LOGO("min") },
      { team: "Green Bay Packers", abbreviation: "GB", probability: 0.130, logo: TEAM_LOGO("gb") },
    ],
  },
  {
    division: "NFC South",
    conference: "NFC",
    shape: "four_way_scramble",
    market_id: 2279151,
    summary_note: "Sample note · Wide-open four-team division race",
    candidates: [
      { team: "Tampa Bay Buccaneers", abbreviation: "TB", probability: 0.388, logo: TEAM_LOGO("tb") },
      { team: "Carolina Panthers", abbreviation: "CAR", probability: 0.263, logo: TEAM_LOGO("car") },
      { team: "New Orleans Saints", abbreviation: "NO", probability: 0.195, logo: TEAM_LOGO("no") },
      { team: "Atlanta Falcons", abbreviation: "ATL", probability: 0.168, logo: TEAM_LOGO("atl") },
    ],
  },
  {
    division: "AFC West",
    conference: "AFC",
    shape: "two_team_duel",
    market_id: 2248392,
    summary_note: "Sample note · Two-team duel with both leaders holding strong playoff position",
    candidates: [
      { team: "Denver Broncos", abbreviation: "DEN", probability: 0.565, logo: TEAM_LOGO("den") },
      { team: "Kansas City Chiefs", abbreviation: "KC", probability: 0.415, logo: TEAM_LOGO("kc") },
      { team: "Las Vegas Raiders", abbreviation: "LV", probability: 0.026, logo: TEAM_LOGO("lv") },
    ],
  },
  {
    division: "NFC East",
    conference: "NFC",
    shape: "two_team_duel",
    market_id: 53674,
    summary_note: "Sample note · Two-team division race between New York and Dallas",
    candidates: [
      { team: "New York Giants", abbreviation: "NYG", probability: 0.617, logo: TEAM_LOGO("nyg") },
      { team: "Dallas Cowboys", abbreviation: "DAL", probability: 0.284, logo: TEAM_LOGO("dal") },
      { team: "Washington Commanders", abbreviation: "WSH", probability: 0.091, logo: TEAM_LOGO("wsh") },
    ],
  },
  {
    division: "AFC North",
    conference: "AFC",
    shape: "two_team_duel",
    market_id: 53677,
    summary_note: "Sample note · Bengals and Steelers meet Sunday night for first place",
    candidates: [
      { team: "Cincinnati Bengals", abbreviation: "CIN", probability: 0.635, logo: TEAM_LOGO("cin") },
      { team: "Pittsburgh Steelers", abbreviation: "PIT", probability: 0.305, logo: TEAM_LOGO("pit") },
      { team: "Cleveland Browns", abbreviation: "CLE", probability: 0.035, logo: TEAM_LOGO("cle") },
    ],
  },
  {
    division: "AFC South",
    conference: "AFC",
    shape: "near_lock",
    market_id: 53676,
    summary_note: "Sample note · Clear division leader with one trailing chaser",
    candidates: [
      { team: "Jacksonville Jaguars", abbreviation: "JAX", probability: 0.900, logo: TEAM_LOGO("jax") },
      { team: "Houston Texans", abbreviation: "HOU", probability: 0.100, logo: TEAM_LOGO("hou") },
    ],
  },
  {
    division: "AFC East",
    conference: "AFC",
    shape: "near_lock",
    market_id: 53678,
    summary_note: "Sample note · Clear division leader with one trailing chaser",
    candidates: [
      { team: "Buffalo Bills", abbreviation: "BUF", probability: 0.885, logo: TEAM_LOGO("buf") },
      { team: "New England Patriots", abbreviation: "NE", probability: 0.112, logo: TEAM_LOGO("ne") },
    ],
  },
];

// ============================================================================
// Section 4: NFL MVP & Offensive Player of the Year (Headshots + Paired Numbers)
// ============================================================================

export interface NflAwardCandidate {
  player_key: string;
  player: string;
  team_abbr: string;
  position: string;
  finalist_market_id: number;
  finalist_probability: number | null;
  winner_market_id: number;
  winner_probability: number;
  headshot: NflArtAsset;
}

const PLAYER_HEADSHOT = (espnId: string): NflArtAsset => ({
  kind: "espn_player_headshot",
  url: `https://a.espncdn.com/i/headshots/nfl/players/full/${espnId}.png`,
  verified_id: `espn:nfl:player:${espnId}`,
  adult: false,
  kid_safe_vetted: true,
});

export const NFL_MVP_CANDIDATES: NflAwardCandidate[] = [
  {
    player_key: "nfl:player:joe-burrow",
    player: "Joe Burrow",
    team_abbr: "CIN",
    position: "QB",
    finalist_market_id: 59164988,
    finalist_probability: 0.80,
    winner_market_id: 40532,
    winner_probability: 0.3155,
    headshot: PLAYER_HEADSHOT("3915511"),
  },
  {
    player_key: "nfl:player:josh-allen",
    player: "Josh Allen",
    team_abbr: "BUF",
    position: "QB",
    finalist_market_id: 59164988,
    finalist_probability: 0.71,
    winner_market_id: 40532,
    winner_probability: 0.2184,
    headshot: PLAYER_HEADSHOT("3918298"),
  },
  {
    player_key: "nfl:player:brock-purdy",
    player: "Brock Purdy",
    team_abbr: "SF",
    position: "QB",
    finalist_market_id: 59164988,
    finalist_probability: 0.56,
    winner_market_id: 40532,
    winner_probability: 0.1602,
    headshot: PLAYER_HEADSHOT("4361741"),
  },
  {
    player_key: "nfl:player:jordan-love",
    player: "Jordan Love",
    team_abbr: "GB",
    position: "QB",
    finalist_market_id: 59164988,
    finalist_probability: 0.70,
    winner_market_id: 40532,
    winner_probability: 0.1311,
    headshot: PLAYER_HEADSHOT("4036378"),
  },
  {
    player_key: "nfl:player:trevor-lawrence",
    player: "Trevor Lawrence",
    team_abbr: "JAX",
    position: "QB",
    finalist_market_id: 59164988,
    finalist_probability: 0.59,
    winner_market_id: 40532,
    winner_probability: 0.0825,
    headshot: PLAYER_HEADSHOT("4360310"),
  },
  {
    player_key: "nfl:player:caleb-williams",
    player: "Caleb Williams",
    team_abbr: "CHI",
    position: "QB",
    finalist_market_id: 59164988,
    finalist_probability: 0.685,
    winner_market_id: 40532,
    winner_probability: 0.0340,
    headshot: PLAYER_HEADSHOT("4431611"),
  },
  {
    player_key: "nfl:player:jared-goff",
    player: "Jared Goff",
    team_abbr: "DET",
    position: "QB",
    finalist_market_id: 59164988,
    finalist_probability: 0.79,
    winner_market_id: 40532,
    winner_probability: 0.0146,
    headshot: PLAYER_HEADSHOT("3046779"),
  },
];

export const NFL_OPOY_CANDIDATES: NflAwardCandidate[] = [
  {
    player_key: "nfl:player:jahmyr-gibbs",
    player: "Jahmyr Gibbs",
    team_abbr: "DET",
    position: "RB",
    finalist_market_id: 59164987,
    finalist_probability: null,
    winner_market_id: 53662,
    winner_probability: 0.3006,
    headshot: PLAYER_HEADSHOT("4429795"),
  },
  {
    player_key: "nfl:player:jaxon-smith-njigba",
    player: "Jaxon Smith-Njigba",
    team_abbr: "SEA",
    position: "WR",
    finalist_market_id: 59164987,
    finalist_probability: 0.80,
    winner_market_id: 53662,
    winner_probability: 0.2452,
    headshot: PLAYER_HEADSHOT("4430878"),
  },
  {
    player_key: "nfl:player:kenneth-walker-iii",
    player: "Kenneth Walker III",
    team_abbr: "SEA",
    position: "RB",
    finalist_market_id: 59164987,
    finalist_probability: null,
    winner_market_id: 53662,
    winner_probability: 0.1809,
    headshot: PLAYER_HEADSHOT("4567048"),
  },
  {
    player_key: "nfl:player:jamarr-chase",
    player: "Ja'Marr Chase",
    team_abbr: "CIN",
    position: "WR",
    finalist_market_id: 59164987,
    finalist_probability: 0.60,
    winner_market_id: 53662,
    winner_probability: 0.0332,
    headshot: PLAYER_HEADSHOT("4362628"),
  },
];

// ============================================================================
// Section 5: This Week's Games That Move the Playoff Picture Most
// ============================================================================

export interface NflSwingGameSpec {
  event_id: number;
  kickoff_label: string;
  stakes_tag: string;
  stakes_note: string;
  away_team: string;
  away_abbr: string;
  away_record: string;
  away_win_prob: number;
  away_playoff_prob: number;
  away_logo: NflArtAsset;
  home_team: string;
  home_abbr: string;
  home_record: string;
  home_win_prob: number;
  home_playoff_prob: number;
  home_logo: NflArtAsset;
}

export const NFL_SWING_GAMES_THIS_WEEK: NflSwingGameSpec[] = [
  {
    event_id: 14780578,
    kickoff_label: "Sun Nov 15 · 5:20 PM PT",
    stakes_tag: "AFC NORTH #1 PLACE",
    stakes_note: "Sample note · Sunday night division game between the top two clubs in the AFC North",
    away_team: "Pittsburgh Steelers",
    away_abbr: "PIT",
    away_record: "6-2",
    away_win_prob: 0.36,
    away_playoff_prob: 0.735,
    away_logo: TEAM_LOGO("pit"),
    home_team: "Cincinnati Bengals",
    home_abbr: "CIN",
    home_record: "6-2",
    home_win_prob: 0.64,
    home_playoff_prob: 0.925,
    home_logo: TEAM_LOGO("cin"),
  },
  {
    event_id: 14969886,
    kickoff_label: "Sun Nov 15 · 10:00 AM PT",
    stakes_tag: "NFC NORTH & WILD CARD SWING",
    stakes_note: "Sample note · Divisional matchup between two NFC North playoff contenders",
    away_team: "Minnesota Vikings",
    away_abbr: "MIN",
    away_record: "6-2",
    away_win_prob: 0.395,
    away_playoff_prob: 0.695,
    away_logo: TEAM_LOGO("min"),
    home_team: "Green Bay Packers",
    home_abbr: "GB",
    home_record: "6-3",
    home_win_prob: 0.605,
    home_playoff_prob: 0.645,
    home_logo: TEAM_LOGO("gb"),
  },
  {
    event_id: 14969889,
    kickoff_label: "Sun Nov 15 · 1:25 PM PT",
    stakes_tag: "NFC #1 SEED VS BUBBLE",
    stakes_note: "Sample note · Conference leader visits an NFC East club chasing a wild-card berth",
    away_team: "San Francisco 49ers",
    away_abbr: "SF",
    away_record: "7-1",
    away_win_prob: 0.655,
    away_playoff_prob: 0.975,
    away_logo: TEAM_LOGO("sf"),
    home_team: "Dallas Cowboys",
    home_abbr: "DAL",
    home_record: "4-5",
    home_win_prob: 0.345,
    home_playoff_prob: 0.295,
    home_logo: TEAM_LOGO("dal"),
  },
  {
    event_id: 14639206,
    kickoff_label: "Sun Nov 15 · 6:30 AM PT",
    stakes_tag: "AFC BUBBLE AT NFC CONTENDER",
    stakes_note: "Sample note · Interconference test between an AFC wild-card contender and an NFC North contender",
    away_team: "New England Patriots",
    away_abbr: "NE",
    away_record: "5-4",
    away_win_prob: 0.415,
    away_playoff_prob: 0.585,
    away_logo: TEAM_LOGO("ne"),
    home_team: "Detroit Lions",
    home_abbr: "DET",
    home_record: "6-2",
    home_win_prob: 0.585,
    home_playoff_prob: 0.765,
    home_logo: TEAM_LOGO("det"),
  },
];

// ============================================================================
// Section 6: The "Too Many Props" Section (Real NFL Game #14780578 — 671 Markets)
// ============================================================================

export interface NflStarScriptBenchmark {
  player: string;
  team_abbr: "CIN" | "PIT";
  role: string;
  headshot: NflArtAsset;
  primary_label: string;
  primary_probability: number;
  secondary_label: string;
  secondary_probability: number;
}

export interface NflCoinFlipProp {
  label: string;
  sublabel: string;
  left_side: string;
  left_probability: number;
  right_side: string;
  right_probability: number;
}

export interface NflFirstTdCandidate {
  player: string;
  team_abbr: "CIN" | "PIT";
  probability: number;
  headshot: NflArtAsset;
}

export type NflPropDrawerCategoryKey =
  | "passing"
  | "rushing"
  | "receiving"
  | "touchdowns"
  | "lines";

export interface NflPlayerMilestoneLadder {
  player: string;
  team_abbr: "CIN" | "PIT" | "GAME";
  stat_label: string;
  headshot?: NflArtAsset;
  milestones: Array<{
    threshold_label: string;
    probability: number;
  }>;
}

export const STEELERS_BENGALS_PROP_BOARD = {
  event_id: 14780578,
  matchup_title: "Pittsburgh Steelers at Cincinnati Bengals",
  kickoff_label: "Sun Nov 15 · 5:20 PM PT",
  win_prob_recorded_at_label: "Recorded Wed Nov 11, 2026 · 8:15 PM PT (blended game win probability)",
  away_team: "Pittsburgh Steelers",
  away_abbr: "PIT" as const,
  away_record: "6-2",
  away_win_prob: 0.36,
  away_logo: TEAM_LOGO("pit"),
  home_team: "Cincinnati Bengals",
  home_abbr: "CIN" as const,
  home_record: "6-2",
  home_win_prob: 0.64,
  home_logo: TEAM_LOGO("cin"),
  total_raw_markets: 681,
  total_player_prop_lines: 394,
  total_game_and_period_lines: 261,
  total_specials_and_first_td: 26,
  curated_first_screen_count: 11,
  // 1. The Script: 4 star players, 2 headline benchmarks each (>=50%)
  star_script: [
    {
      player: "Joe Burrow",
      team_abbr: "CIN",
      role: "Bengals QB",
      headshot: PLAYER_HEADSHOT("3915511"),
      primary_label: "2+ Passing TDs",
      primary_probability: 0.670,
      secondary_label: "275+ Passing Yds",
      secondary_probability: 0.565,
    },
    {
      player: "Ja'Marr Chase",
      team_abbr: "CIN",
      role: "Bengals WR",
      headshot: PLAYER_HEADSHOT("4362628"),
      primary_label: "1+ Touchdown",
      primary_probability: 0.525,
      secondary_label: "90+ Receiving Yds",
      secondary_probability: 0.500,
    },
    {
      player: "Aaron Rodgers",
      team_abbr: "PIT",
      role: "Steelers QB",
      headshot: PLAYER_HEADSHOT("8439"),
      primary_label: "1+ Passing TD",
      primary_probability: 0.815,
      secondary_label: "225+ Passing Yds",
      secondary_probability: 0.560,
    },
    {
      player: "Jaylen Warren",
      team_abbr: "PIT",
      role: "Steelers RB",
      headshot: PLAYER_HEADSHOT("4569987"),
      primary_label: "60+ Rushing Yds",
      primary_probability: 0.555,
      secondary_label: "3+ Receptions",
      secondary_probability: 0.530,
    },
  ] satisfies NflStarScriptBenchmark[],

  // 2. Closest 50/50 Toss-Ups (highest tension lines on the board)
  coin_flips: [
    {
      label: "Winning Margin (4+ Points)",
      sublabel: "Sample note · Key margin mark in Sunday night's AFC North matchup",
      left_side: "Steelers or 1–3 pt game",
      left_probability: 0.515,
      right_side: "Bengals by 4+ pts",
      right_probability: 0.485,
    },
    {
      label: "Ja'Marr Chase Receiving",
      sublabel: "Sample note · Yardage mark near an even split alongside Tee Higgins receptions",
      left_side: "90+ Rec Yds",
      left_probability: 0.500,
      right_side: "Under 90 Yds",
      right_probability: 0.500,
    },
    {
      label: "Aaron Rodgers Multi-TD",
      sublabel: "Sample note · Multi-touchdown passing mark alongside Chase Brown rushing",
      left_side: "2+ Pass TDs",
      left_probability: 0.480,
      right_side: "0–1 Pass TDs",
      right_probability: 0.520,
    },
  ] satisfies NflCoinFlipProp[],

  // 3. First Touchdown & Specials strip
  first_td_leaders: [
    {
      player: "Ja'Marr Chase",
      team_abbr: "CIN",
      probability: 0.125,
      headshot: PLAYER_HEADSHOT("4362628"),
    },
    {
      player: "Jaylen Warren",
      team_abbr: "PIT",
      probability: 0.115,
      headshot: PLAYER_HEADSHOT("4569987"),
    },
    {
      player: "Chase Brown",
      team_abbr: "CIN",
      probability: 0.115,
      headshot: PLAYER_HEADSHOT("4362238"),
    },
    {
      player: "Tee Higgins",
      team_abbr: "CIN",
      probability: 0.100,
      headshot: PLAYER_HEADSHOT("4239993"),
    },
  ] satisfies NflFirstTdCandidate[],
  weather_delay_probability: 0.02,

  // 4. Behind the Toggle: Category Drawer with Player Milestone Ladders
  drawer_categories: {
    passing: {
      label: "Passing (37)",
      ladders: [
        {
          player: "Joe Burrow",
          team_abbr: "CIN",
          stat_label: "Passing Yards (5 milestones)",
          headshot: PLAYER_HEADSHOT("3915511"),
          milestones: [
            { threshold_label: "250+", probability: 0.670 },
            { threshold_label: "275+", probability: 0.565 },
            { threshold_label: "300+", probability: 0.445 },
            { threshold_label: "375+", probability: 0.100 },
            { threshold_label: "400+", probability: 0.070 },
          ],
        },
        {
          player: "Joe Burrow",
          team_abbr: "CIN",
          stat_label: "Passing Touchdowns (4 milestones)",
          headshot: PLAYER_HEADSHOT("3915511"),
          milestones: [
            { threshold_label: "1+ TD", probability: 0.905 },
            { threshold_label: "2+ TDs", probability: 0.670 },
            { threshold_label: "3+ TDs", probability: 0.360 },
            { threshold_label: "4+ TDs", probability: 0.145 },
          ],
        },
        {
          player: "Aaron Rodgers",
          team_abbr: "PIT",
          stat_label: "Passing Yards (5 milestones)",
          headshot: PLAYER_HEADSHOT("8439"),
          milestones: [
            { threshold_label: "200+", probability: 0.685 },
            { threshold_label: "225+", probability: 0.560 },
            { threshold_label: "250+", probability: 0.445 },
            { threshold_label: "325+", probability: 0.095 },
            { threshold_label: "350+", probability: 0.065 },
          ],
        },
        {
          player: "Aaron Rodgers",
          team_abbr: "PIT",
          stat_label: "Passing Touchdowns (4 milestones)",
          headshot: PLAYER_HEADSHOT("8439"),
          milestones: [
            { threshold_label: "1+ TD", probability: 0.815 },
            { threshold_label: "2+ TDs", probability: 0.480 },
            { threshold_label: "3+ TDs", probability: 0.200 },
            { threshold_label: "4+ TDs", probability: 0.050 },
          ],
        },
      ] satisfies NflPlayerMilestoneLadder[],
    },
    receiving: {
      label: "Receiving (215)",
      ladders: [
        {
          player: "Ja'Marr Chase",
          team_abbr: "CIN",
          stat_label: "Receiving Yards (7 milestones) · 9+ Receptions 39%",
          headshot: PLAYER_HEADSHOT("4362628"),
          milestones: [
            { threshold_label: "50+", probability: 0.820 },
            { threshold_label: "70+", probability: 0.660 },
            { threshold_label: "90+", probability: 0.500 },
            { threshold_label: "100+", probability: 0.405 },
            { threshold_label: "120+", probability: 0.260 },
            { threshold_label: "140+", probability: 0.140 },
          ],
        },
        {
          player: "Tee Higgins",
          team_abbr: "CIN",
          stat_label: "Receiving Yards (7 milestones) · 6+ Receptions 49%",
          headshot: PLAYER_HEADSHOT("4239993"),
          milestones: [
            { threshold_label: "40+", probability: 0.790 },
            { threshold_label: "60+", probability: 0.655 },
            { threshold_label: "70+", probability: 0.535 },
            { threshold_label: "80+", probability: 0.465 },
            { threshold_label: "100+", probability: 0.280 },
            { threshold_label: "120+", probability: 0.165 },
          ],
        },
        {
          player: "DK Metcalf",
          team_abbr: "PIT",
          stat_label: "Receiving · 5+ Receptions 39% · Anytime TD 32%",
          headshot: PLAYER_HEADSHOT("4047650"),
          milestones: [
            { threshold_label: "5+ Rec", probability: 0.390 },
            { threshold_label: "1+ TD", probability: 0.320 },
            { threshold_label: "1st TD", probability: 0.065 },
          ],
        },
        {
          player: "Chase Brown",
          team_abbr: "CIN",
          stat_label: "Receiving Yards (6 milestones) · 5+ Receptions 42%",
          headshot: PLAYER_HEADSHOT("4362238"),
          milestones: [
            { threshold_label: "10+", probability: 0.770 },
            { threshold_label: "20+", probability: 0.575 },
            { threshold_label: "25+", probability: 0.455 },
            { threshold_label: "30+", probability: 0.370 },
            { threshold_label: "50+", probability: 0.150 },
          ],
        },
      ] satisfies NflPlayerMilestoneLadder[],
    },
    rushing: {
      label: "Rushing (95)",
      ladders: [
        {
          player: "Jaylen Warren",
          team_abbr: "PIT",
          stat_label: "Rushing Yards (8 milestones)",
          headshot: PLAYER_HEADSHOT("4569987"),
          milestones: [
            { threshold_label: "30+", probability: 0.845 },
            { threshold_label: "50+", probability: 0.630 },
            { threshold_label: "60+", probability: 0.555 },
            { threshold_label: "70+", probability: 0.430 },
            { threshold_label: "80+", probability: 0.285 },
            { threshold_label: "100+", probability: 0.135 },
          ],
        },
        {
          player: "Chase Brown",
          team_abbr: "CIN",
          stat_label: "Rushing Yards (7 milestones)",
          headshot: PLAYER_HEADSHOT("4362238"),
          milestones: [
            { threshold_label: "20+", probability: 0.820 },
            { threshold_label: "30+", probability: 0.695 },
            { threshold_label: "40+", probability: 0.530 },
            { threshold_label: "50+", probability: 0.365 },
            { threshold_label: "60+", probability: 0.260 },
            { threshold_label: "70+", probability: 0.165 },
          ],
        },
        {
          player: "Joe Burrow",
          team_abbr: "CIN",
          stat_label: "Rushing Yards (3 milestones)",
          headshot: PLAYER_HEADSHOT("3915511"),
          milestones: [
            { threshold_label: "10+", probability: 0.345 },
            { threshold_label: "15+", probability: 0.230 },
            { threshold_label: "20+", probability: 0.145 },
          ],
        },
      ] satisfies NflPlayerMilestoneLadder[],
    },
    touchdowns: {
      label: "Touchdowns (47)",
      ladders: [
        {
          player: "Ja'Marr Chase",
          team_abbr: "CIN",
          stat_label: "Touchdown Milestones",
          headshot: PLAYER_HEADSHOT("4362628"),
          milestones: [
            { threshold_label: "1+ TD", probability: 0.525 },
            { threshold_label: "2+ TDs", probability: 0.135 },
            { threshold_label: "1st TD", probability: 0.125 },
          ],
        },
        {
          player: "Chase Brown",
          team_abbr: "CIN",
          stat_label: "Touchdown Milestones",
          headshot: PLAYER_HEADSHOT("4362238"),
          milestones: [
            { threshold_label: "1+ TD", probability: 0.460 },
            { threshold_label: "1st TD", probability: 0.115 },
            { threshold_label: "2+ TDs", probability: 0.110 },
          ],
        },
        {
          player: "Jaylen Warren",
          team_abbr: "PIT",
          stat_label: "Touchdown Milestones",
          headshot: PLAYER_HEADSHOT("4569987"),
          milestones: [
            { threshold_label: "1+ TD", probability: 0.445 },
            { threshold_label: "1st TD", probability: 0.115 },
            { threshold_label: "2+ TDs", probability: 0.095 },
          ],
        },
        {
          player: "Tee Higgins",
          team_abbr: "CIN",
          stat_label: "Touchdown Milestones",
          headshot: PLAYER_HEADSHOT("4239993"),
          milestones: [
            { threshold_label: "1+ TD", probability: 0.445 },
            { threshold_label: "1st TD", probability: 0.100 },
            { threshold_label: "2+ TDs", probability: 0.100 },
          ],
        },
      ] satisfies NflPlayerMilestoneLadder[],
    },
    lines: {
      label: "Margins & Totals (261)",
      ladders: [
        {
          player: "Cincinnati Bengals Winning Margin Ladder",
          team_abbr: "GAME",
          stat_label: "87 alternate & period margin lines collapsed into 1 ladder",
          milestones: [
            { threshold_label: "CIN by 2+", probability: 0.600 },
            { threshold_label: "CIN by 4+", probability: 0.485 },
            { threshold_label: "CIN by 8+ (1H)", probability: 0.260 },
            { threshold_label: "CIN by 20+", probability: 0.165 },
          ],
        },
        {
          player: "Full-Game Total Points Ladder",
          team_abbr: "GAME",
          stat_label: "32 game total + 32 team total lines collapsed into 1 ladder",
          milestones: [
            { threshold_label: "Over 24.5", probability: 0.920 },
            { threshold_label: "Over 26.5", probability: 0.916 },
            { threshold_label: "CIN 10.5+ pts", probability: 0.940 },
          ],
        },
      ] satisfies NflPlayerMilestoneLadder[],
    },
  } as Record<
    NflPropDrawerCategoryKey,
    { label: string; ladders: NflPlayerMilestoneLadder[] }
  >,
};

// ============================================================================
// Look-Sheet Item Specifications (Positions 1..7)
// ============================================================================

export interface NflLookSheetItemSpec {
  position: number;
  item_key: string;
  section_number: number;
  title: string;
  subtitle: string;
  why_it_exists: string;
  form: NflLookSheetContract;
}

export const NFL_PLAYOFFS_LOOK_SHEET_ITEMS: NflLookSheetItemSpec[] = [
  {
    position: 1,
    item_key: "nfl-section-1-playoffs-to-super-bowl-paired-bars",
    section_number: 1,
    title:
      "Section 1 · Make the Playoffs % beside Win the Super Bowl % (Top 6 + Expander for All 12 Clubs in the Hunt)",
    subtitle:
      "The NFL version of look sheet 2's NHL card ('amazing'): two related numbers per club with official ESPN crests, Resolves Feb 14, 2027",
    why_it_exists:
      "Pairs Pro Football Playoff Qualifiers (#62679) beside the unified Super Bowl Winner board (#86832 / #12530). Shows the top 6 Super Bowl contenders by default with a full-width primary expander to reveal all 12 clubs at >=4% title chance, and flips Stage 1 to ✓ Clinched / ✗ Eliminated once the regular season ends.",
    form: {
      form_id: "paired_bars_top6_expandable",
      form_name: "Stacked Dual Bars with Team Crests (Top 6 + Full-Width Expander)",
      data_shape: "two related numbers per club (Make Playoffs % + Win Super Bowl %), plus a verified team crest",
      parts_vocabulary: ["pictures", "bars", "strips", "ticks"] as FormVocabularyPart[],
      slots: ["team_crest", "club_and_record", "playoff_bar_or_tick", "super_bowl_bar", "expand_all_button"],
      missing_number_rule:
        "Clubs missing from either board print an explicit 'Not listed' badge in that bar slot.",
      settled_step_rule:
        "Once playoff berths clinch in January, Stage 1 flips from '<N>%' to '✓ Clinched' or '✗ Eliminated' while Super Bowl % stays live.",
      domain_agnostic: true,
    },
  },
  {
    position: 2,
    item_key: "nfl-section-2-afc-nfc-conference-paths",
    section_number: 2,
    title:
      "Section 2 · AFC & NFC Conference Championship Conversion Funnels (Reach Conference Final % → Win Conference %)",
    subtitle:
      "Adjacent section switches form from dual bars to a two-step conversion track split by conference (AFC vs NFC)",
    why_it_exists:
      "Draws each conference race as a nested conversion funnel (outer bar = Reach AFC/NFC Title Game %, inner fill = Win Conference %), exposing high-floor teams vs high-conversion favorites (49ers 45% reach → 28% win NFC; Bills 49% reach → 25% win AFC).",
    form: {
      form_id: "step_conversion_path_conference",
      form_name: "Two-Conference Step Conversion Funnel",
      data_shape: "a two-step bracket path per conference (Reach Title Game % → Win Conference %) + team crest",
      parts_vocabulary: ["pictures", "strips", "bars", "ticks"] as FormVocabularyPart[],
      slots: ["conference_column", "team_crest", "outer_reach_bar", "inner_win_fill"],
      missing_number_rule:
        "Shows outer reach bar with 'Not listed to win conference' if absent from the conference winner board.",
      settled_step_rule:
        "In Divisional / Conference Championship week, eliminated clubs collapse to ✗ and the two Championship Game finalists lock at ✓.",
      domain_agnostic: true,
    },
  },
  {
    position: 3,
    item_key: "nfl-section-3-division-races-by-shape",
    section_number: 3,
    title:
      "Section 3 · Division Races Chosen by Distribution Shape (4-Way Scrambles vs 2-Team Duels vs 90% Locks)",
    subtitle:
      "Applies the Container B grammar ('the shape of the numbers picks the form'): NFC North & South 4-way grids, AFC West / NFC East / AFC North duels, and AFC South / East lock pills",
    why_it_exists:
      "Prevents eight identical division tables. Wide-open 4-team divisions (NFC North: Bears 38%, Lions 27%, Vikings 25%, Packers 13%) get 4-club comparison grids; 2-horse divisions (AFC North: Bengals 64% vs Steelers 31%) get head-to-head tug-of-war bars; 89–90% runaways (Jaguars 90%, Bills 89%) compress into compact lock chips.",
    form: {
      form_id: "shape_driven_division_contrast",
      form_name: "Distribution-Shape Division Selector (Scramble Grid · Duel Bar · Lock Chip)",
      data_shape: "multi-outcome division winner boards grouped by leader share (<45% scramble, 45–80% duel, >=85% lock)",
      parts_vocabulary: ["pictures", "tiles", "bars", "strips"] as FormVocabularyPart[],
      slots: ["scramble_4up_cards", "two_team_duel_bars", "runaway_lock_chips"],
      missing_number_rule:
        "Clubs below 2% are summarized in the division footer rather than cluttering 2-horse duel bars.",
      settled_step_rule:
        "Clinched divisions move into the '✓ Division Clinched' rail automatically.",
      domain_agnostic: true,
    },
  },
  {
    position: 4,
    item_key: "nfl-section-4-mvp-and-awards-spotlight",
    section_number: 4,
    title:
      "Section 4 · NFL MVP & Offensive Player of the Year Spotlight (Circular Player Headshots + Finalist % beside Win %)",
    subtitle:
      "Adjacent section switches from team crests to verified ESPN player headshots: Top-3 MVP Podium (Burrow 32%, Allen 22%, Purdy 16%) + Finalist-Lock Chasers + OPOY 3-Up Strip",
    why_it_exists:
      "Uses circular player headshots where identity is verified (#12523) and pairs MVP Finalist % (#59164988) with MVP Winner % (#40532) so readers immediately spot high-probability finalists who are longshots to win (Jared Goff: 79% finalist · 1% win; Caleb Williams: 69% finalist · 3% win) alongside the OPOY race (Gibbs 30%, Smith-Njigba 25%, Walker 18%).",
    form: {
      form_id: "podium_and_headshot_tiles",
      form_name: "Player Headshot Podium + Paired Finalist/Winner Strip",
      data_shape: "two related numbers per player (Finalist % + Winner %), plus a verified circular player headshot",
      parts_vocabulary: ["pictures", "tiles", "strips", "ticks"] as FormVocabularyPart[],
      slots: ["mvp_top3_podium", "mvp_finalist_chaser_strip", "opoy_3up_tiles"],
      missing_number_rule:
        "When Finalist % is not listed for an OPOY contender, the tile prints 'Win OPOY %' alone without inventing a finalist number.",
      settled_step_rule:
        "When AP announces finalists in January, Finalist % flips to ✓ Finalist / ✗ Missed.",
      domain_agnostic: true,
    },
  },
  {
    position: 5,
    item_key: "nfl-section-5-games-that-move-the-picture",
    section_number: 5,
    title:
      "Section 5 · This Week's Games That Move the Playoff Picture Most (Win % + Playoff Stakes)",
    subtitle:
      "Four real Week 10/11 matchups ranked by division & wild-card leverage: Steelers at Bengals (36%/64%), Vikings at Packers (40%/61%), 49ers at Cowboys (66%/35%), Patriots at Lions (42%/59%)",
    why_it_exists:
      "Connects Sunday's live slate to the season-long container: each game card pairs the game win probability with each club's live playoff berth % and division stakes.",
    form: {
      form_id: "matchup_swing_cards",
      form_name: "2-Up Matchup Swing Cards with Playoff Stakes Badges",
      data_shape: "head-to-head game win probability + each club's season playoff berth % and stakes callout",
      parts_vocabulary: ["pictures", "tiles", "bars"] as FormVocabularyPart[],
      slots: ["stakes_header", "away_home_crests", "win_prob_tug_bar", "playoff_berth_context"],
      missing_number_rule:
        "If game win probability is not yet posted, displays kickoff time and each club's playoff berth %.",
      settled_step_rule:
        "Once a game goes Final, the winner receives ✓ and the updated playoff berth % is shown.",
      domain_agnostic: true,
    },
  },
  {
    position: 6,
    item_key: "nfl-section-6-too-many-props-steelers-bengals",
    section_number: 6,
    title:
      "Section 6 · The 'Too Many Props' Section on a Real Full NFL Prop Board (Steelers at Bengals — 681 Live Markets)",
    subtitle:
      "Fable's 11:39 AM addition (#12609): turns 394 player props + 287 game/special lines into a calm 11-number first screen (The Script · 50/50 Coin-Flips · First TD) + one category milestone drawer for the rest",
    why_it_exists:
      "Solves the big-container overload problem (Super Bowl LXI, Oscars, NBA playoffs, elections): instead of dumping 681 flat rows, the first screen highlights 3 lenses a reader can take in at a glance, while one toggle opens a category-tabbed drawer that collapses 8–10 alternate yardage lines per player into a single horizontal Milestone Ladder.",
    form: {
      form_id: "curated_prop_board_with_drawer",
      form_name: "Three-Lens Prop Digest + Player Milestone Ladder Drawer",
      data_shape: "hundreds of game/player props ranked into (1) >=50% Star Script, (2) ~50% Coin-Flips, (3) First TD strip + (4) expandable Milestone Ladders by category",
      parts_vocabulary: ["pictures", "tiles", "bars", "strips"] as FormVocabularyPart[],
      slots: [
        "star_script_2x2_headshots",
        "coin_flip_50_50_bars",
        "first_td_strip",
        "category_milestone_drawer_toggle",
      ],
      missing_number_rule:
        "Withholds props without a current probability and groups alternate thresholds under one player row.",
      settled_step_rule:
        "Settled props grade inline as ✓ Hit or ✗ Missed ('What Hit').",
      domain_agnostic: true,
    },
  },
  {
    position: 7,
    item_key: "nfl-container-full-rhythm-preview",
    section_number: 7,
    title:
      "Full Container Rhythm · How All 6 Sections Compose into One Self-Building 390 px NFL Playoffs & Super Bowl Container",
    subtitle:
      "Shows the complete vertical rhythm (never repeating a form on adjacent sections) + how the selector transitions from 'Race to Get In (Nov)' → 'The Bracket (Jan)' → 'Super Bowl LXI (Feb 14, 2027)'",
    why_it_exists:
      "Lets Alex grade the whole container as one continuous 390 px scroll where every section earns its place and changes form based on the shape of its numbers.",
    form: {
      form_id: "self_building_season_container",
      form_name: "Self-Building Multi-Form Season Container",
      data_shape: "selector-driven multi-section container where form[i] !== form[i-1] and stage transitions follow the calendar",
      parts_vocabulary: ["pictures", "bars", "tiles", "strips", "ticks"] as FormVocabularyPart[],
      slots: [
        "season_stage_banner",
        "playoffs_to_super_bowl_section",
        "conference_paths_section",
        "division_shapes_section",
        "awards_spotlight_section",
        "swing_games_section",
        "curated_prop_board_section",
      ],
      missing_number_rule:
        "Each section applies its own form contract's missing-number rule independently.",
      settled_step_rule:
        "As regular season, wild card, divisional, and conference rounds settle, settled stages flip to ✓/✗ and the active round moves to the top.",
      domain_agnostic: true,
    },
  },
];
