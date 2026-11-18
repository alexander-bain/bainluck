import type { FactoryData, Line, Station, Stop } from "./types";

export const stations: Station[] = [
  "Write",
  "Test",
  "Review",
  "Merge line",
  "Ship",
  "Live",
];

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
  return `${Math.floor(minutes / 1440)} days`;
}

export function readerBehind(data: FactoryData, now: string) {
  const deadline = data.read_expires_at
    ? Date.parse(data.read_expires_at)
    : Date.parse(data.generated_at) + 15 * 60_000;
  return Date.parse(now) > deadline;
}

export function stopText(stop: Stop, now: string) {
  const age = duration((Date.parse(now) - Date.parse(stop.since)) / 1000);
  if (stop.kind === "line-stalled")
    return `${stop.line}: nothing merged for ${age}, ${stop.count} waiting.`;
  if (stop.kind === "announced")
    return `Announced at ${time(stop.since)}, not merged.`;
  if (stop.kind === "hold")
    return `${stop.line} on HOLD since ${time(stop.since)} PT, ${stop.count} waiting.`;
  if (stop.kind === "master")
    return `Shared tests failed at ${time(stop.since)} PT, ${stop.count} waiting.`;
  return `${stop.line} review waiting for ${age}, ${stop.count} waiting.`;
}

export function recentTransfers(data: FactoryData, now: string) {
  if (readerBehind(data, now)) return [];
  return (data.transitions ?? []).filter((t) => {
    const age = Date.parse(now) - Date.parse(t.at);
    return age >= 0 && age <= 15 * 60_000;
  });
}

export function bayActivity(
  data: FactoryData,
  line: Line,
  station: Station,
  now: string,
  count: number,
) {
  const stops = (data.stops ?? []).filter(
    (s) => (s.line === null || s.line === line) && s.station === station,
  );
  const stop =
    stops.find((s) => s.kind === "announced") ??
    stops.find((s) => s.level === "red") ??
    stops[0];
  const flowing =
    !stop &&
    recentTransfers(data, now).some(
      (t) => t.line === line && (t.from === station || t.to === station),
    );
  const worker =
    stop?.level === "red"
      ? stop.kind === "announced"
        ? "asleep"
        : "alarmed"
      : count === 0 || (station === "Live" && !flowing)
        ? "idle"
        : flowing
          ? "working"
          : "asleep";
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
        : count && station !== "Live"
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
  const blocked = (data.stops ?? []).some(
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
