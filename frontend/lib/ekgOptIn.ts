'use client';

/**
 * #10090 — THE EVENT PAGE'S HEARTBEAT ("EKG"), ON BY DEFAULT (Alex decision 66).
 *
 * Alex tried it behind `?ekg=1`, then: "I absolutely love the ekg" — and the
 * hero's three confidence bars went so the live number has one signal. So:
 *
 *   * with no remembered choice it is ON;
 *   * `?ekg=0` turns it off and remembers that in localStorage, so it survives
 *     navigation between event pages and reloads;
 *   * `?ekg=1` turns it back on (and remembers that too);
 *   * a store that throws reads the URL alone, defaulting ON.
 *
 * This only resolves the reader's choice. The page still draws the heartbeat
 * only for a quote-eligible live game with no terminal connection label that
 * is not finished. The hook starts `false` so the server render and the first
 * client render agree; the effect turns it on after mount.
 */
import { useEffect, useState } from 'react';

export const EKG_STORAGE_KEY = 'bl:ekg';

/** Pure: whether the reader wants the heartbeat, from this URL query and store. Only a remembered or asked `0` is off. */
export function resolveEkgOptIn(
  search: string,
  storage: Pick<Storage, 'getItem' | 'setItem'> | null,
): boolean {
  const asked = new URLSearchParams(search).get('ekg');
  try {
    if (asked === '1') {
      storage?.setItem(EKG_STORAGE_KEY, '1');
      return true;
    }
    if (asked === '0') {
      storage?.setItem(EKG_STORAGE_KEY, '0');
      return false;
    }
    return storage?.getItem(EKG_STORAGE_KEY) !== '0';
  } catch {
    return asked !== '0';
  }
}

export function useEkgOptIn(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    let storage: Storage | null = null;
    try {
      storage = window.localStorage;
    } catch {
      storage = null;
    }
    if (resolveEkgOptIn(window.location.search, storage)) setOn(true);
  }, []);
  return on;
}
