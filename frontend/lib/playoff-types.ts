// ---------------------------------------------------------------------------
// Shared types for TeamPlayoffCard and ChampionshipGrid
// ---------------------------------------------------------------------------

export interface StageSource {
  source: string;
  probability: number;
}

export interface PlayoffStage {
  key: string;
  label: string;
  order: number;
  probability: number; // 0–1
  change24h: number; // e.g. +0.015 or -0.02
  sources: StageSource[];
  status: "pending" | "clinched" | "eliminated";
}

export interface PlayoffTeam {
  name: string;
  short: string;
  logo: string;
  color: string;
  record: string;
  conference: string;
  stages: PlayoffStage[];
}

export interface LeagueTab {
  slug: string;
  label: string;
  emoji: string;
}

export interface ChampionshipGridData {
  league: string;
  emoji: string;
  season: string;
  stageKeys: string[];
  stageLabels: string[];
  teams: PlayoffTeam[];
}
