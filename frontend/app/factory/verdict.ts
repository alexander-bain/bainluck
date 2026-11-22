import {
  duration,
  knownOrigin,
  onActiveFloor,
  readerBehind,
  shownStops,
  stationNames,
  time,
} from "./activity";
import { MACHINE_WAIT_MS, type GitHubActivity } from "./githubActivity";
import type { FactoryData, Line, Station, Stop } from "./types";

type BayAlert = {
  line: Line | null;
  station: Station;
  level: "amber" | "red";
  text: string;
  crowded?: true;
};

export type FloorVerdict = {
  level: "green" | BayAlert["level"];
  text: string;
  bays: BayAlert[];
};

const ACTIVITY_GRACE_MS = 15 * 60_000;
const MAX_ACTIVITY_AGE_MS = 10 * 60_000;

export function floorReadingState(
  data: FactoryData,
  readFailed: boolean,
  now: string,
  activity?: GitHubActivity,
) {
  const published = Date.parse(data.generated_at);
  const clock = Date.parse(now);
  const activityAge = clock - Date.parse(activity?.checkedAt ?? "");
  const recent = activityAge >= 0 && activityAge <= MAX_ACTIVITY_AGE_MS ? activity : undefined;
  const masterAt = Date.parse(recent?.masterAt ?? "");
  const ciAt = recent?.ciAt === null ? -Infinity : Date.parse(recent?.ciAt ?? "");
  const collectorAt = Date.parse(recent?.collector?.at ?? "");
  if (recent?.collector?.failed && collectorAt > published && collectorAt <= clock) return "failed";
  const queuedAt = Date.parse(recent?.collectorQueuedAt ?? "");
  if (clock - queuedAt > MACHINE_WAIT_MS) return "waiting";
  if ([masterAt, ciAt].some(at => at > published + ACTIVITY_GRACE_MS && at <= clock)) return "failed";
  if (readFailed) return "last-known";
  if (!readerBehind(data, now)) return "current";
  if (collectorAt <= clock && masterAt <= published && ciAt <= published)
    return "quiet";
  return "last-known";
}

function elapsed(now: string, since: string) {
  const seconds = (Date.parse(now) - Date.parse(since)) / 1000;
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 && minutes < 60
    ? `${minutes} ${minutes === 1 ? "minute" : "minutes"}`
    : duration(seconds);
}

function place(station: Station, line: Line | null) {
  return line ? `${stationNames[station]}, ${line}` : stationNames[station];
}

function stopReason(stop: Stop, now: string) {
  switch (stop.kind) {
    case "hold":
      return `on hold since ${time(stop.since)} PT${stop.test ? ` after ${stop.test} failed` : ""}`;
    case "master":
      return `shared tests failed at ${time(stop.since)} PT`;
    case "line-stalled":
      return `${stop.number ? `#${stop.number} is` : "changes are"} waiting for a merge`;
    case "announced":
      return `${stop.number ? `#${stop.number} is` : "a change is"} still waiting after its announced merge`;
    case "review-waiting":
      return `${stop.number ? `#${stop.number}` : "a change"} has waited ${elapsed(now, stop.waiting_since ?? stop.since)} for review`;
  }
}

export function floorVerdict(
  data: FactoryData | null,
  readFailed: boolean,
  now: string,
  activity?: GitHubActivity,
): FloorVerdict {
  if (!data) return { level: "amber", text: "The floor can't be read right now.", bays: [] };
  const state = floorReadingState(data, readFailed, now, activity);
  if (state === "failed") {
    return { level: "amber", text: "Not updating.", bays: [] };
  }
  if (state === "waiting") {
    return { level: "amber", text: "The next reading is waiting for a machine.", bays: [] };
  }
  if (state === "last-known") {
    return { level: "amber", text: "Showing the last published floor.", bays: [] };
  }

  const through = state === "quiet" ? data.generated_at : now;
  const bays: BayAlert[] = shownStops(data).map((stop) => ({
    line: stop.line,
    station: stop.station,
    level: stop.kind === "hold" ? "red" : "amber",
    text: `${place(stop.station, stop.line)}: ${stopReason(stop, through)}.`,
  }));

  function add(line: Line | null, station: Station, reason: string) {
    bays.push({ line, station, level: "amber", text: `${place(station, line)}: ${reason}.` });
  }

  for (const stop of data.stops ?? []) {
    if (stop.kind === "hold" && !knownOrigin(stop.source))
      add(stop.line, stop.station, "the hold source is missing");
  }

  if (data.signals.tests === "unknown" || !data.signals.tests)
    add("Server", "Test", "the shared test result is missing");
  if (data.signals.tests === "failing" && !bays.some((bay) => bay.station === "Test"))
    add("Server", "Test", "the shared tests failed");
  if (["failure", "cancelled", "timed_out", "error"].includes(data.signals.testflight))
    add("Apps", "Ship", "the TestFlight build stopped");
  if (data.signals.testflight === "unknown" || !data.signals.testflight)
    add("Apps", "Ship", "the TestFlight result is missing");

  const clock = Date.parse(through);
  const crowdedStations = new Set(
    data.jams
      .filter((jam) => jam.kind === "crowd" && !jam.ended_at && Date.parse(jam.qualifies_at) <= clock)
      .map((jam) => jam.station),
  );
  const counts = new Map<string, { line: Line; station: Station; count: number }>();
  for (const change of data.changes) {
    if (!crowdedStations.has(change.station) || !onActiveFloor(change)) continue;
    const key = `${change.line}/${change.station}`;
    const bay = counts.get(key) ?? { line: change.line, station: change.station, count: 0 };
    bay.count++;
    counts.set(key, bay);
  }
  for (const { line, station, count } of counts.values()) {
    if (count >= 10) {
      bays.push({
        line,
        station,
        level: "amber",
        text: `${place(station, line)}: ${count} changes are backed up here.`,
        crowded: true,
      });
    }
  }

  const first = bays.find((bay) => bay.level === "red") ?? bays[0];
  if (state === "quiet") {
    return { level: first?.level ?? "green", text: "The floor is quiet.", bays };
  }
  if (first) return { level: first.level, text: first.text, bays };
  if (!Array.isArray(data.stops) || data.coverage.length) {
    return {
      level: "amber",
      text: data.coverage[0] ?? "The floor’s status reading is missing.",
      bays,
    };
  }
  return { level: "green", text: "All clear.", bays };
}

export function factoryTabTitle(verdict: FloorVerdict) {
  return `${verdict.text} | The Factory`;
}
