import type { PlayoffTeam, ChampionshipGridData } from "./playoff-types";

// ---------------------------------------------------------------------------
// Stage definitions
// ---------------------------------------------------------------------------
const STAGE_KEYS = ["make_playoffs", "conf_semis", "conf_finals", "finals", "championship"];
const STAGE_LABELS = ["Playoffs", "Conf. Semis", "Conf. Finals", "Finals", "Champion"];

// ---------------------------------------------------------------------------
// Raw mock data from spec
// ---------------------------------------------------------------------------
const RAW_TEAMS = [
  {
    name: "Oklahoma City Thunder", short: "OKC",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/25.png", color: "#007AC1",
    record: "50-14", conference: "Western",
    probs: { make_playoffs: 0.99, conf_semis: 0.88, conf_finals: 0.62, finals: 0.38, championship: 0.22 },
    trends: { championship: 0.015, conf_finals: 0.02 },
    sources: { championship: [{ source: "Sportsbooks", probability: 0.22 }, { source: "Kalshi", probability: 0.20 }, { source: "Polymarket", probability: 0.24 }] },
  },
  {
    name: "Cleveland Cavaliers", short: "CLE",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/5.png", color: "#860038",
    record: "49-15", conference: "Eastern",
    probs: { make_playoffs: 0.99, conf_semis: 0.85, conf_finals: 0.55, finals: 0.32, championship: 0.18 },
    trends: { championship: -0.02 },
    sources: { championship: [{ source: "Sportsbooks", probability: 0.18 }, { source: "Polymarket", probability: 0.17 }] },
  },
  {
    name: "Boston Celtics", short: "BOS",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/2.png", color: "#007A33",
    record: "46-18", conference: "Eastern",
    probs: { make_playoffs: 0.98, conf_semis: 0.82, conf_finals: 0.50, finals: 0.28, championship: 0.16 },
    trends: { championship: 0.008 },
    sources: { championship: [{ source: "Sportsbooks", probability: 0.15 }, { source: "Kalshi", probability: 0.16 }, { source: "Polymarket", probability: 0.17 }] },
  },
  {
    name: "Denver Nuggets", short: "DEN",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/7.png", color: "#0E2240",
    record: "44-20", conference: "Western",
    probs: { make_playoffs: 0.97, conf_semis: 0.75, conf_finals: 0.42, finals: 0.22, championship: 0.12 },
    trends: { championship: -0.005 },
    sources: { championship: [{ source: "Sportsbooks", probability: 0.12 }] },
  },
  {
    name: "New York Knicks", short: "NYK",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/18.png", color: "#006BB6",
    record: "43-21", conference: "Eastern",
    probs: { make_playoffs: 0.96, conf_semis: 0.70, conf_finals: 0.35, finals: 0.18, championship: 0.09 },
    trends: { championship: 0.012 },
    sources: { championship: [{ source: "Sportsbooks", probability: 0.09 }, { source: "Polymarket", probability: 0.10 }] },
  },
  {
    name: "Dallas Mavericks", short: "DAL",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/6.png", color: "#00538C",
    record: "40-24", conference: "Western",
    probs: { make_playoffs: 0.93, conf_semis: 0.60, conf_finals: 0.30, finals: 0.15, championship: 0.07 },
    trends: { championship: -0.008 },
    sources: { championship: [{ source: "Sportsbooks", probability: 0.07 }, { source: "Kalshi", probability: 0.06 }] },
  },
  {
    name: "Milwaukee Bucks", short: "MIL",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/15.png", color: "#00471B",
    record: "39-25", conference: "Eastern",
    probs: { make_playoffs: 0.90, conf_semis: 0.55, conf_finals: 0.28, finals: 0.14, championship: 0.06 },
    trends: {},
    sources: { championship: [{ source: "Sportsbooks", probability: 0.06 }] },
  },
  {
    name: "Minnesota Timberwolves", short: "MIN",
    logo: "https://a.espncdn.com/i/teamlogos/nba/500/16.png", color: "#0C2340",
    record: "38-26", conference: "Western",
    probs: { make_playoffs: 0.88, conf_semis: 0.50, conf_finals: 0.22, finals: 0.10, championship: 0.04 },
    trends: { championship: -0.01 },
    sources: { championship: [{ source: "Sportsbooks", probability: 0.04 }] },
  },
];

// ---------------------------------------------------------------------------
// Transform raw data into the typed PlayoffTeam shape
// ---------------------------------------------------------------------------
export const MOCK_TEAMS: PlayoffTeam[] = RAW_TEAMS.map((t) => ({
  name: t.name,
  short: t.short,
  logo: t.logo,
  color: t.color,
  record: t.record,
  conference: t.conference,
  stages: STAGE_KEYS.map((key, i) => {
    const prob = (t.probs as Record<string, number>)[key] ?? 0;
    const change24h = (t.trends as Record<string, number>)[key] ?? 0;
    const stageSourceMap = t.sources as Record<string, { source: string; probability: number }[]>;
    const sources = stageSourceMap[key] ?? [];
    return {
      key,
      label: STAGE_LABELS[i],
      order: i + 1,
      probability: prob,
      change24h,
      sources,
      status: "pending" as const,
    };
  }),
}));

export const NBA_GRID: ChampionshipGridData = {
  league: "NBA Championship Grid",
  emoji: "🏀",
  season: "2025-26",
  stageKeys: STAGE_KEYS,
  stageLabels: STAGE_LABELS,
  teams: MOCK_TEAMS,
};

export const LEAGUE_TABS = [
  { slug: "nba", label: "NBA", emoji: "🏀" },
  { slug: "nfl", label: "NFL", emoji: "🏈" },
  { slug: "mlb", label: "MLB", emoji: "⚾" },
  { slug: "nhl", label: "NHL", emoji: "🏒" },
  { slug: "wnba", label: "WNBA", emoji: "🏀" },
  { slug: "ncaab", label: "NCAAB", emoji: "🏀" },
];
