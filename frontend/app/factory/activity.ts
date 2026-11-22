import type { Change, FactoryData, FloorEvent, Line, Station, Stop } from "./types";

export const stations: Station[] = [
  "Write",
  "Test",
  "Review",
  "Merge line",
  "Ship",
  "Live",
];

export const stationNames: Record<Station, string> = {
  Write: "Bench",
  Test: "Checks",
  Review: "Inspection",
  "Merge line": "Loading dock",
  Ship: "Truck",
  Live: "Live",
};

const pacificDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Los_Angeles",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const pacificHour = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  hour: "numeric",
  hourCycle: "h23",
});

export function workshopLight(value: string) {
  const hour = Number(pacificHour.format(new Date(value)));
  return hour >= 6 && hour < 18 ? "day" : "night";
}

export function pacificDay(value: string) {
  return pacificDate.format(new Date(value));
}

export function transferId(event: Omit<FloorEvent, "id">) {
  return `transfer:${event.line}:${event.number}:${event.from}:${event.station}:${Date.parse(event.at)}:${Date.parse(event.observed_at)}`;
}

export function time(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function duration(seconds: number) {
  const minutes = Math.max(0, Math.floor(seconds / 60));
  if (minutes === 0) return "under a minute";
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440)
    return `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
  const days = Math.floor(minutes / 1440);
  return `${days} ${days === 1 ? "day" : "days"}`;
}

const nowAuthors = [
  "Repository owner",
  "Alex",
  "Fable",
  "Speed",
  "Builder B",
  "Builder C",
  "Atlas",
  "Builder E",
  "Builder F",
  "Apple",
  "Wee-Bey",
];

export function knownOrigin(source: Stop["source"]) {
  return Boolean(
    source &&
      Number.isSafeInteger(source.id) &&
      source.id > 0 &&
      nowAuthors.includes(source.author),
  );
}

export function shownStops(data: FactoryData) {
  return (data.stops ?? []).flatMap((stop): Stop[] => {
    if (stop.kind === "hold") return knownOrigin(stop.source) ? [stop] : [];
    return [{ ...stop, level: "amber" }];
  });
}

export function readerBehind(data: FactoryData, now: string) {
  const deadline = data.read_expires_at
    ? Date.parse(data.read_expires_at)
    : Date.parse(data.generated_at) + 15 * 60_000;
  return Date.parse(now) > deadline;
}

export function stopWaitText(stop: Stop, now: string) {
  const minutes = stop.waiting_since
    ? Math.max(
        0,
        Math.floor((Date.parse(now) - Date.parse(stop.waiting_since)) / 60_000),
      )
    : null;
  return stop.number && minutes !== null
    ? `#${stop.number} has waited ${minutes < 60 ? `${minutes} ${minutes === 1 ? "minute" : "minutes"}` : duration(minutes * 60)} for ${stop.station === "Review" ? "inspection" : "a merge"}.`
    : null;
}

export function stopText(stop: Stop, now: string) {
  const age = duration((Date.parse(now) - Date.parse(stop.since)) / 1000);
  const waited = stopWaitText(stop, now);
  if (stop.kind === "line-stalled")
    return waited
      ? `${stop.line}: nothing merged for ${age}. ${waited}`
      : `${stop.line} loading dock is waiting for a merge.`;
  if (stop.kind === "announced")
    return stop.number
      ? `#${stop.number} was announced for a merge at ${time(stop.since)} PT and is still waiting.`
      : `${stop.line} announced a merge at ${time(stop.since)} PT.`;
  if (stop.kind === "hold")
    return `${stop.line} on HOLD since ${time(stop.since)} PT.${waited ? ` ${waited}` : ""}`;
  if (stop.kind === "master")
    return `Shared checks failed at ${time(stop.since)} PT.`;
  return waited ?? `${stop.line} inspection needs attention.`;
}

export function recentlyActive(at: string, now: string) {
  const age = Date.parse(now) - Date.parse(at);
  return age >= 0 && age <= 15 * 60_000;
}

export function recentLaneUpdate(at: string, now: string) {
  const age = Date.parse(now) - Date.parse(at);
  return age >= 0 && age <= 3 * 60 * 60_000;
}

export function recentTransfers(data: FactoryData, now: string) {
  if (readerBehind(data, now)) return [];
  return (data.transitions ?? []).filter((t) =>
    recentlyActive(t.observed_at ?? t.at, now),
  );
}

export function onActiveFloor(change: Change) {
  return (
    change.station !== "Live" &&
    !change.side_track &&
    !change.bot_update &&
    !change.parked &&
    !change.held_for_108
  );
}

export function crewActivity(
  data: FactoryData,
  now: string,
  changes: Change[],
) {
  const moves = recentTransfers(data, now).filter(
    (move) => (move.observed_at ?? move.at) === data.generated_at,
  );
  const carrying = changes.find((change) =>
    moves.some(
      (move) =>
        move.number === change.number &&
        move.line === change.line &&
        move.to === change.station,
    ),
  );
  if (carrying) return { pose: "carrying", change: carrying } as const;
  const waiting = changes.find((change) => change.station === "Merge line");
  if (waiting) return { pose: "waiting", change: waiting } as const;
  const working = changes.find((change) =>
    recentlyActive(change.last_activity, now),
  );
  if (working) return { pose: "working", change: working } as const;
  return { pose: "asleep", change: null } as const;
}

export function bayActivity(
  data: FactoryData,
  line: Line,
  station: Station,
  now: string,
  changes: Change[],
) {
  const stops = shownStops(data).filter(
    (s) => (s.line === null || s.line === line) && s.station === station,
  );
  const stop =
    stops.find((s) => s.level === "red") ??
    stops.find((s) => s.kind === "announced") ??
    stops[0];
  const flowing =
    !stop &&
    recentTransfers(data, now).some(
      (t) => t.line === line && (t.from === station || t.to === station),
    );
  const activeCrate = changes.some((change) =>
    recentlyActive(change.last_activity, now),
  );
  const working = changes.length > 0 && (activeCrate || flowing);
  const checking =
    station === "Test" && changes.some((change) => change.checks_running);
  const waiting = changes.length > 0 && station !== "Live";
  const worker =
    stop?.level === "red"
      ? "alarmed"
      : working
        ? "working"
        : waiting
          ? "asleep"
          : "idle";
  return {
    stop,
    flowing,
    worker,
    label: stop
      ? stop.level === "red"
        ? "Stopped"
        : "Long wait"
      : flowing
        ? "Flowing"
        : checking
          ? "Checks running"
          : working
            ? "Working"
            : waiting
              ? "Waiting"
              : "Idle",
  } as const;
}

export function beltFlowing(
  data: FactoryData,
  line: Line,
  segment: number,
  now: string,
) {
  if (readerBehind(data, now)) return false;
  if (
    segment < 2 &&
    data.changes.some(
      (change) =>
        change.line === line &&
        change.station === "Test" &&
        change.checks_running &&
        onActiveFloor(change),
    )
  )
    return true;
  const blocked = shownStops(data).some(
    (s) =>
      s.level === "red" &&
      (s.line === null || s.line === line) &&
      [segment, segment + 1].includes(stations.indexOf(s.station)),
  );
  return (
    !blocked &&
    recentTransfers(data, now).some((t) => {
      const ends = [stations.indexOf(t.from), stations.indexOf(t.to)];
      return (
        t.line === line &&
        Math.min(...ends) <= segment &&
        Math.max(...ends) > segment
      );
    })
  );
}
