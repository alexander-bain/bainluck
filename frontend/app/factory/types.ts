export type Line = "Server" | "Website" | "Apps";
export type Station =
  "Write" | "Test" | "Review" | "Merge line" | "Ship" | "Live";
export type Builder = "S" | "B" | "C" | "D" | "E" | "F" | "Other";

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
}

export interface Transfer {
  number: number;
  line: Line;
  from: Station;
  to: Station;
  at: string;
}

export interface Stop {
  kind: "line-stalled" | "announced" | "hold" | "master" | "review-waiting";
  line: Line | null;
  station: Station;
  since: string;
  count: number;
  level: "red" | "amber";
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
}

export interface FactoryData {
  schema_version: number;
  generated_at: string;
  observed_since: string;
  read_expires_at?: string;
  transitions?: Transfer[];
  stops?: Stop[];
  changes: Change[];
  jams: Jam[];
  signals: {
    tests: string;
    testflight: string;
    tests_at?: string;
    last_merged_at?: Partial<Record<Line, string>>;
  };
  coverage: string[];
}
