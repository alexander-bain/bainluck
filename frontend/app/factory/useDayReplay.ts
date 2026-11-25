import { useCallback, useEffect, useRef, useState } from "react";
import { replayDuration, useEventPlayer } from "./playback";
import type { DayReplay } from "./types";

export const DAY_REPLAY_MS = 60_000;

type Session = { id: string; journal: DayReplay; automatic: boolean };

export function useDayReplay(animate: boolean) {
  const nextId = useRef(0);
  const remaining = useRef(DAY_REPLAY_MS);
  const [session, setSession] = useState<Session | null>(null);
  const [finished, setFinished] = useState(false);
  const [lastTime, setLastTime] = useState<string>();
  const playing = useEventPlayer(
    session?.id,
    session?.journal.events,
    animate && !finished,
    DAY_REPLAY_MS,
    false,
  );

  useEffect(() => {
    if (!session || finished || !animate) return;
    const due = performance.now() + remaining.current;
    const timeout = window.setTimeout(() => setFinished(true), remaining.current);
    return () => {
      window.clearTimeout(timeout);
      remaining.current = Math.max(0, due - performance.now());
    };
  }, [session, animate, finished]);

  useEffect(() => {
    if (session && playing) setLastTime(playing.event.at);
  }, [session, playing]);

  const open = useCallback((journal: DayReplay, automatic = false) => {
    remaining.current = replayDuration(journal.events, DAY_REPLAY_MS);
    setLastTime(journal.events[0]?.at ?? journal.through);
    setFinished(false);
    setSession({ journal, id: String(++nextId.current), automatic });
  }, []);
  const close = useCallback(() => setSession(null), []);

  return {
    session,
    playing: session && !finished ? playing : null,
    clock: finished ? session?.journal.through : lastTime,
    finished,
    open,
    restart: () => { if (session) open(session.journal); },
    close,
  };
}
