export type Line = "Server" | "Website" | "Apps";
export type Station =
  | "Write"
  | "Test"
  | "Review"
  | "Merge line"
  | "Ship"
  | "Live";
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
}

export interface Jam {
  key: string;
  kind: "crowd" | "master" | "testflight" | "empty";
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
  changes: Change[];
  jams: Jam[];
  signals: { tests: string; testflight: string };
  coverage: string[];
}
