export type Line = "Server" | "Website" | "Apps";
export type Station =
  | "Write"
  | "Test"
  | "Review"
  | "Merge line"
  | "Ship"
  | "Live";
export type Builder = "S" | "B" | "C" | "D" | "E" | "F" | "W" | "Other";

export const factoryMoods = [
  "working", "carrying", "waiting", "celebrating", "stuck", "asleep",
] as const;
export type FactoryMood = (typeof factoryMoods)[number];
export interface LaneSpeech {
  text: string;
  mood: FactoryMood;
  source: "model" | "facts";
}

export interface StationVisit {
  station: Station;
  first_seen_at: string;
  last_seen_at?: string;
}

export interface Change {
  number: number;
  title: string;
  builder: Builder;
  line: Line;
  station: Station;
  unsure: boolean;
  reasons: string[];
  side_track: boolean;
  last_activity: string;
  merged_at: string | null;
  live_at: string | null;
  timing: "reported" | "observed" | null;
  merge_to_live_seconds?: number | null;
  station_since?: string;
  revision_at?: string;
  sent_back?: boolean;
  bot_update?: boolean;
  parked?: boolean;
  held_for_108?: boolean;
  checks_running?: boolean;
  merge_announced_at?: string;
  live_posted_at?: string;
  live_post_observed_at?: string;
  testflight_build?: number;
  check_progress?: { done: number; total: number };
  approvals?: { bot?: string; fable?: string };
  bench_seen_at?: string;
  journey?: StationVisit[];
}

export const factoryEventKinds = [
  "commit", "check", "bot", "fable", "returned", "move", "merge", "deploy", "live",
] as const;

export interface FloorEvent {
  id: string;
  kind: (typeof factoryEventKinds)[number];
  number: number;
  line: Line;
  builder?: Builder;
  station: Station;
  from?: Station;
  at: string;
  observed_at: string;
  done?: number;
  total?: number;
  outcome?: "passed" | "failed" | "finished";
}

export interface DayReplay {
  date: string;
  through: string;
  events: FloorEvent[];
}

export interface Injury {
  kind: "switched-off" | "wrong-number";
  number: number;
  at: string;
}

export interface InjuryClock {
  from: string;
  available: boolean;
  events: Injury[];
}

export interface Transfer {
  number: number;
  line: Line;
  from: Station;
  to: Station;
  at: string;
  observed_at?: string;
}

export interface Stop {
  kind: "line-stalled" | "announced" | "hold" | "master" | "review-waiting";
  line: Line | null;
  station: Station;
  since: string;
  count: number;
  level: "red" | "amber";
  source?: { id: number; author: string };
  test?: string;
  number?: number;
  waiting_since?: string;
  machines?: { running: number; waiting: number };
}

export interface Jam {
  key: string;
  kind:
    | "crowd"
    | "master"
    | "testflight"
    | "empty"
    | "line-stalled"
    | "announced"
    | "hold"
    | "review-waiting";
  station: Station;
  line: Line | null;
  started_at: string;
  qualifies_at: string;
  ended_at: string | null;
  count: number | null;
  source?: Stop["source"];
}

export interface FactoryData {
  schema_version: number;
  generated_at: string;
  observed_since: string;
  read_expires_at?: string;
  transitions?: Transfer[];
  speech?: Partial<Record<Exclude<Builder, "Other">, LaneSpeech>>;
  model_usage?: { day: string; calls: number };
  events?: FloorEvent[];
  injury_clock?: InjuryClock;
  stops?: Stop[];
  notes?: {
    snapshot_at: string;
    floor: string;
    stations: Record<string, string>;
    source: "model" | "counts";
  };
  changes: Change[];
  jams: Jam[];
  signals: {
    tests: string;
    testflight: string;
    tests_at?: string;
    last_merged_at?: Partial<Record<Line, string>>;
    testflight_post?: { build: number; at: string };
  };
  coverage: string[];
}
