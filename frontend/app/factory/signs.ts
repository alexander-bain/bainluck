import type { Builder, Change, Injury, InjuryClock } from "./types";

export function builderOfDay(shipped: readonly Change[]) {
  const delivered = new Map<Exclude<Builder, "Other">, Set<number>>();
  for (const change of shipped) {
    if (change.builder === "Other") continue;
    const changes = delivered.get(change.builder) ?? new Set<number>();
    changes.add(change.number);
    delivered.set(change.builder, changes);
  }
  const count = Math.max(0, ...Array.from(delivered.values(), (changes) => changes.size));
  if (!count) return null;
  return {
    count,
    builders: Array.from(delivered).filter(([, changes]) => changes.size === count).map(([builder]) => builder),
  };
}

export function injuryHours(read: InjuryClock | undefined, through: string) {
  if (!read?.available) return null;
  const from = Date.parse(read.from);
  const end = Date.parse(through);
  if (end < from) return null;
  let previous = from;
  let record = 0;
  let last: Injury | undefined;
  for (const event of read.events) {
    const at = Date.parse(event.at);
    if (at < previous || at > end) continue;
    record = Math.max(record, at - previous);
    previous = at;
    last = event;
  }
  const current = end - previous;
  return {
    current: Math.floor(current / 3_600_000),
    record: Math.floor(Math.max(record, current) / 3_600_000),
    last,
  };
}

export function hours(count: number) {
  if (count < 1) return "Under one hour";
  return `${count} ${count === 1 ? "hour" : "hours"}`;
}

export function median(values: number[]) {
  if (!values.length) return null;
  const ordered = [...values].sort((a, b) => a - b);
  const mid = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[mid] : (ordered[mid - 1] + ordered[mid]) / 2;
}

export function clipboard(now: string, shipped: Change[], active: Change[]) {
  const trips = shipped.flatMap((c) => {
    if (!c.bench_seen_at || !c.live_at) return [];
    const seconds = (Date.parse(c.live_at) - Date.parse(c.bench_seen_at)) / 1000;
    return seconds >= 0 ? [seconds] : [];
  });
  const waits = active.flatMap((c) => {
    if (c.station !== "Review" && c.station !== "Merge line" || !c.station_since) return [];
    const seconds = (Date.parse(now) - Date.parse(c.station_since)) / 1000;
    return seconds >= 0 ? [{ change: c, seconds }] : [];
  });
  const longest = waits.reduce<(typeof waits)[number] | null>(
    (best, wait) => best === null || best.seconds < wait.seconds ? wait : best,
    null,
  );
  return { benchMedian: median(trips), longest };
}
