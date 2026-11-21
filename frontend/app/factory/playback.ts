import { useEffect, useRef, useState } from "react";
import type { FloorEvent } from "./types";
import { stationNames, stations } from "./activity";

const PLAYBACK_WINDOW_MS = 5 * 60_000;

type TimerState = {
  reading: string;
  events: FloorEvent[];
  step: number;
  remaining: number;
};

export function eventText(event: FloorEvent, foreman = "Fable") {
  const number = `#${event.number}`;
  switch (event.kind) {
    case "commit": return `${number} gets a new commit`;
    case "check":
      return `${number} ${event.outcome === "failed" ? "fails" : event.outcome === "passed" ? "passes" : "finishes"} a check · ${event.done} of ${event.total}`;
    case "bot": return `Bot approves ${number}`;
    case "fable": return `${foreman} clears ${number}`;
    case "returned": return `${foreman} sends ${number} back to the bench`;
    case "move": return `${number} moves to ${stationNames[event.station]}`;
    case "merge": return `${number} merges`;
    case "deploy": return `The deploy job starts for ${number}`;
    case "live": return `${number} goes live`;
  }
}

export function crossesSegment(event: FloorEvent | undefined, segment: number) {
  if (!event?.from) return false;
  const left = stations.indexOf(event.from);
  const right = stations.indexOf(event.station);
  return Math.min(left, right) <= segment && Math.max(left, right) > segment;
}

export function playbackStep(count: number, durationMs: number) {
  return durationMs / Math.max(1, count);
}

/** Timers advance only while visible. A repeated read never plays an event twice. */
export function useEventPlayer(
  reading: string | undefined,
  events: FloorEvent[] | undefined,
  running: boolean,
  durationMs = PLAYBACK_WINDOW_MS,
  remember = true,
) {
  const seen = useRef(new Set<string>());
  const batch = useRef<TimerState>();
  const [active, setActive] = useState<{ event: FloorEvent; clipMs: number } | null>(null);

  useEffect(() => {
    if (reading === undefined) return;
    if (batch.current?.reading !== reading) {
      const current = new Set(events?.map((event) => event.id));
      seen.current = new Set(remember ? [...seen.current].filter((id) => current.has(id)) : []);
      const queue = (events ?? []).filter((event) => !seen.current.has(event.id));
      batch.current = {
        reading,
        events: queue,
        step: playbackStep(queue.length, durationMs),
        remaining: 0,
      };
      setActive(null);
    }
    const state = batch.current;
    if (!running) return;

    let timer: number;
    let dueAt: number;
    function schedule(wait: number) {
      dueAt = performance.now() + wait;
      timer = window.setTimeout(advance, wait);
    }
    function advance() {
      const event = state.events.shift();
      if (!event) {
        setActive(null);
        return;
      }
      seen.current.add(event.id);
      const clipMs = Math.min(1200, state.step * 0.85);
      setActive({ event, clipMs });
      schedule(state.events.length ? state.step : clipMs);
    }
    schedule(state.remaining);
    return () => {
      window.clearTimeout(timer);
      state.remaining = Math.max(0, dueAt - performance.now());
    };
  }, [reading, events, running, durationMs, remember]);

  return batch.current?.reading === reading ? active : null;
}
