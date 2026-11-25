import { transferEvents } from "./replayJournal";
import type { FactoryData, FloorEvent } from "./types";

export function transfersSince(data: FactoryData | null, since: string | undefined): FloorEvent[] {
  if (!data || !since) return [];
  const first = Date.parse(since);
  const read = Date.parse(data.generated_at);
  return transferEvents(data).filter((event) => {
    const observed = Date.parse(event.observed_at);
    return observed > first && observed <= read && read - observed <= 15 * 60_000;
  }).sort((a, b) =>
    Date.parse(a.observed_at) - Date.parse(b.observed_at) ||
    Date.parse(a.at) - Date.parse(b.at) || a.id.localeCompare(b.id),
  );
}

export function remainingEvents(events: FloorEvent[] | undefined, transfers: FloorEvent[]) {
  return events?.filter((event) => {
    if (!["move", "returned", "merge", "live"].includes(event.kind)) return true;
    return !transfers.some((transfer) =>
      event.number === transfer.number && event.line === transfer.line &&
      event.station === transfer.station &&
      Date.parse(event.observed_at) === Date.parse(transfer.observed_at),
    );
  });
}
