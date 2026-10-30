'use client';

/**
 * #10090 — THE EVENT PAGE'S HEARTBEAT ("EKG"), OPT-IN WHILE ALEX TRIES IT.
 *
 * Off by default. The same runtime pattern the tenths trial used:
 *
 *   * `?ekg=1` turns it on and remembers that in localStorage, so it survives
 *     navigation between event pages and reloads;
 *   * `?ekg=0` turns it off and forgets it;
 *   * anything else reads the remembered choice, and with none it is OFF.
 *
 * The hook starts `false`, so the server render and every reader who never
 * asked print exactly today's page.
 */
import { useEffect, useState } from 'react';

export const EKG_STORAGE_KEY = 'bl:ekg';

/** Pure: whether the heartbeat draws for this URL query and store. A store that throws reads as no choice. */
export function resolveEkgOptIn(
  search: string,
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null,
): boolean {
  const asked = new URLSearchParams(search).get('ekg');
  try {
    if (asked === '1') {
      storage?.setItem(EKG_STORAGE_KEY, '1');
      return true;
    }
    if (asked === '0') {
      storage?.removeItem(EKG_STORAGE_KEY);
      return false;
    }
    return storage?.getItem(EKG_STORAGE_KEY) === '1';
  } catch {
    return asked === '1';
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
