import { getSportLabel, servedSportNameIsRaw } from "@/lib/sportCategories";

const READER_LEAGUE_FALLBACKS: Record<string, string> = {
  americanfootball_nfl: "NFL",
  americanfootball_ncaaf: "College Football",
  basketball_nba: "NBA",
  basketball_wnba: "WNBA",
  basketball_ncaab: "Men's College Basketball",
  basketball_wncaab: "Women's College Basketball",
  icehockey_nhl: "NHL",
  baseball_mlb: "MLB",
  soccer_epl: "Premier League",
  soccer_uefa_champs_league: "Champions League",
  soccer_italy_serie_b: "Serie B",
  tennis_atp: "ATP",
  tennis_wta: "WTA",
  tennis_other: "Other Tennis",
  esports_other: "Esports",
};

export type NuggetGrade = "yes" | "no";

export interface NuggetSubject {
  name: string;
  image_url?: string | null;
  image_kind?: "headshot" | "logo" | null;
}

export interface GameNuggetItem {
  id: string;
  item_key?: string;
  position: number;
  kind: string;
  kind_label: string;
  subject: NuggetSubject;
  claim: string;
  probability: number;
  percent: number;
  change_points: number | null;
  change_since: string | null;
  pregame_percent: number | null;
  pregame_mark_source?: "kickoff_pin" | "opening" | null;
  form: string;
  rank_reason: string;
  saved_grade?: NuggetGrade;
  saved_note?: string | null;
}

export interface KindCountEntry {
  kind: string;
  label: string;
  count: number;
  target_section: string;
}

export interface GameNuggetsDeckSummaryGame {
  event_id: number;
  home_team: string;
  away_team: string;
  sport: string | null;
  sport_name?: string | null;
  status: string | null;
  commence_time: string | null;
  nugget_count?: number;
  kind_count?: number;
  graded_count?: number;
}

export interface GameNuggetsGame extends GameNuggetsDeckSummaryGame {
  nuggets: GameNuggetItem[];
  first_eight_kinds: number;
  everything_map: KindCountEntry[];
}

export interface NuggetGradeSummary {
  graded_count: number;
  yes_count: number;
  no_count: number;
  repeat_rate: number | null;
  target_rate: number;
  meets_target: boolean;
}

export interface GameNuggetsDeckResponse {
  slate_id: string;
  surface: string;
  built_at?: string | null;
  requested_limit?: number;
  games_count: number;
  games: GameNuggetsDeckSummaryGame[];
  summary: NuggetGradeSummary;
}

export interface SingleGameNuggetsResponse {
  slate_id: string;
  surface: string;
  event_id: number;
  game: GameNuggetsGame;
  summary: NuggetGradeSummary;
}

export function formatReaderLeague(
  sportKey: string | null | undefined,
  sportName?: string | null,
): string {
  const key = (sportKey || "").trim();
  const cleanName = typeof sportName === "string" ? sportName.trim() : "";
  if (cleanName && (!key || !servedSportNameIsRaw(key, cleanName))) {
    return cleanName;
  }
  if (key && key in READER_LEAGUE_FALLBACKS) {
    return READER_LEAGUE_FALLBACKS[key];
  }
  if (key) {
    return getSportLabel(key, cleanName || null);
  }
  return cleanName || "Game";
}

export function formatDeckBuiltDate(raw?: string | null): string | null {
  if (!raw) return null;
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDeckCountLine(deck: GameNuggetsDeckResponse): string {
  const target = deck.requested_limit ?? 20;
  if (deck.games_count < target) {
    return `Shorter deck: ${deck.games_count} of ${target} games qualify right now (need at least 6 items across 3+ kinds, max 4 per league).`;
  }
  return `${deck.games_count} qualifying games in deck (best-covered first, max 4 per league).`;
}
