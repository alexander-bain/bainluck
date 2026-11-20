import { useEffect, useMemo, useRef, useState } from "react";
import { pacificDay, stations } from "./activity";
import type { DayReplay, FactoryData, FloorEvent } from "./types";

const storageKey = "factory-today-transfers-v1";

function transferId(event: Omit<FloorEvent, "id">) {
  return `transfer:${event.line}:${event.number}:${event.from}:${event.station}:${Date.parse(event.at)}:${Date.parse(event.observed_at)}`;
}

export function transferEvents(data: FactoryData): FloorEvent[] {
  const builders = new Map(data.changes.map((change) => [change.number, change.builder]));
  const through = Date.parse(data.generated_at);
  const moves: FloorEvent[] = [];
  for (const transfer of data.transitions ?? []) {
    if (
      transfer.from === transfer.to || transfer.number <= 0 ||
      Date.parse(transfer.at) > through
    ) continue;
    const observedAt = transfer.observed_at ?? transfer.at;
    const event = {
      kind: "move" as const,
      number: transfer.number,
      line: transfer.line,
      builder: builders.get(transfer.number),
      from: transfer.from,
      station: transfer.to,
      at: transfer.at,
      observed_at: observedAt,
    };
    const returned = data.events?.some((record) => record.kind === "returned" &&
      record.number === event.number && record.line === event.line &&
      record.from === event.from && record.station === event.station &&
      Date.parse(record.observed_at) === Date.parse(observedAt));
    moves.push({ ...event, id: transferId(event), kind: returned ? "returned" : "move" });
  }
  return moves;
}

export function replayReading(data: FactoryData | null, date: string): DayReplay | undefined {
  if (!data?.transitions || pacificDay(data.generated_at) !== date) return;
  return mergeReadings({
    date, through: data.generated_at,
    events: transferEvents(data).filter((event) => pacificDay(event.at) === date),
  });
}

function mergeReadings(current: DayReplay, ...history: (DayReplay | undefined)[]): DayReplay {
  const events = new Map<string, FloorEvent>();
  let through = current.through;
  for (const reading of [...history, current]) {
    if (reading?.date !== current.date) continue;
    if (Date.parse(reading.through) > Date.parse(through)) through = reading.through;
    for (const event of reading.events) {
      const previous = events.get(event.id);
      events.set(event.id, {
        ...event,
        builder: event.builder ?? previous?.builder,
        kind: previous?.kind === "returned" ? "returned" : event.kind,
      });
    }
  }
  return {
    date: current.date,
    through,
    events: [...events.values()].sort((a, b) =>
      Date.parse(a.at) - Date.parse(b.at) || Date.parse(a.observed_at) - Date.parse(b.observed_at) ||
      a.id.localeCompare(b.id)),
  };
}

function storedReading(date: string): DayReplay | undefined {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null") as DayReplay | null;
    if (saved?.date !== date || typeof saved.through !== "string" ||
        !Number.isFinite(Date.parse(saved.through)) || pacificDay(saved.through) !== date ||
        !Array.isArray(saved.events)) return;
    return { ...saved, events: saved.events.filter((event) =>
      event && (event.kind === "move" || event.kind === "returned") &&
      ["Server", "Website", "Apps"].includes(event.line) &&
      Number.isSafeInteger(event.number) && event.number > 0 &&
      (event.builder === undefined || ["S", "B", "C", "D", "E", "F", "W", "Other"].includes(event.builder)) &&
      event.from !== undefined && stations.includes(event.from) && stations.includes(event.station) &&
      event.from !== event.station &&
      typeof event.at === "string" && Number.isFinite(Date.parse(event.at)) &&
      pacificDay(event.at) === date && Date.parse(event.at) <= Date.parse(saved.through) &&
      typeof event.observed_at === "string" && Number.isFinite(Date.parse(event.observed_at)) &&
      event.id === transferId(event)),
    };
  } catch {
    return undefined;
  }
}

export function useReplayJournal(data: FactoryData | null, date: string) {
  const incoming = useMemo(() => replayReading(data, date), [data, date]);
  const previous = useRef<DayReplay>();
  const [journal, setJournal] = useState<DayReplay>();

  useEffect(() => {
    if (!incoming) return;
    const combined = mergeReadings(incoming, storedReading(date), previous.current);
    previous.current = combined;
    setJournal(combined);
    try {
      localStorage.setItem(storageKey, JSON.stringify(combined));
    } catch {
      // Keep replaying the transfers seen in this visit if storage is unavailable.
    }
  }, [incoming, date]);

  return journal?.date === date ? journal : incoming;
}
