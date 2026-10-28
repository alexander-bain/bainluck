'use client';

/**
 * #10090 — ONE-DECIMAL HEADLINES, OFF FOR EVERYONE BUT A READER WHO ASKS.
 *
 * Alex chose "let me try it first" (Speed, 2026-10-28): he lives with tenths on
 * real live games before deciding, and nobody else sees a change. So this is a
 * runtime opt-in, not a build flag:
 *
 *   * `?tenths=fit` turns it on and remembers it in localStorage, so it
 *     survives navigation and reloads;
 *   * `?tenths=off` turns it off and forgets it;
 *   * anything else reads the remembered choice, and with none it is OFF.
 *
 * OFF IS TODAY, BYTE FOR BYTE. The hook starts `false` (so the server render and
 * first paint are today's) and only ever sets state to `true`, so a reader who
 * never opted in gets no extra render, no request and no analytics event.
 * `tenthsOptInOffIsMaster10090.test.tsx` pins the hero and chart markup against
 * master's own.
 *
 * Rules for the digits:
 *   * tenths come from the adopted probability (6 decimals on the wire); no
 *     invented digit.
 *   * a complement pair is normalised by its total (as `renderedCardPercents`
 *     does) and the second side is DERIVED, so the pair sums to 100.0.
 *   * the existing `<1` / `>99` bands stay (symmetric about the pair; see
 *     `partsFromTenths`).
 */
import { useEffect, useState } from 'react';
import { probabilityParts, type ProbabilityParts } from './probabilityDisplay';

export const TENTHS_STORAGE_KEY = 'bl:tenths';
const ON = 'fit';

/**
 * Pure: what the opt-in is for this URL query and store, applying the URL's
 * instruction to the store. A store that throws (Safari private mode, a
 * blocked cookie policy) reads as no remembered choice.
 */
export function resolveTenthsOptIn(
  search: string,
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null,
): boolean {
  const asked = new URLSearchParams(search).get('tenths');
  try {
    if (asked === ON) {
      storage?.setItem(TENTHS_STORAGE_KEY, ON);
      return true;
    }
    if (asked === 'off') {
      storage?.removeItem(TENTHS_STORAGE_KEY);
      return false;
    }
    return storage?.getItem(TENTHS_STORAGE_KEY) === ON;
  } catch {
    return asked === ON;
  }
}

export function useTenthsOptIn(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    let storage: Storage | null = null;
    try {
      storage = window.localStorage;
    } catch {
      storage = null;
    }
    if (resolveTenthsOptIn(window.location.search, storage)) setOn(true);
  }, []);
  return on;
}

export interface TenthsParts {
  marker: ProbabilityParts['marker'];
  whole: string;
  /** `.4`, or '' when a band marker replaces the decimal. */
  decimal: string;
}

function tenthsInt(p: number): number {
  return Math.round(Number((p * 1000).toFixed(6)));
}

// The same `<1` / `>99` bands the whole-number headline prints, and the band is
// symmetric: 0.5 through 99.5 print, anything nearer a boundary takes the
// marker. A one-sided `t >= 995` printed `0.5% | >99%` for one complement pair
// (home 5 tenths, away 995): one side a number, the other a band. The whole
// headline already bands from 99.5, so the one value that differs is a printed
// `99.5`, which is the true tenth and claims no certainty. Exact 0 / 1 print
// plainly, as they do today. The band's spelling is `probabilityParts`'s own
// (one home for it, guarded in `probabilityDisplay.test.ts`).
function partsFromTenths(t: number, p: number): TenthsParts {
  if (p <= 0) return { marker: null, whole: '0', decimal: '' };
  if (p >= 1) return { marker: null, whole: '100', decimal: '' };
  if (t < 5 || t > 995) {
    const band = probabilityParts(p, { rendered: t < 5 ? 0 : 100 });
    return { marker: band.marker, whole: band.digits, decimal: '' };
  }
  return { marker: null, whole: `${Math.floor(t / 10)}`, decimal: `.${t % 10}` };
}

export function tenthsPair(
  homeProb: number | null,
  awayProb: number | null,
): { home: TenthsParts | null; away: TenthsParts | null } {
  if (homeProb === null || !Number.isFinite(homeProb)) return { home: null, away: null };
  const total =
    awayProb !== null && Number.isFinite(awayProb) ? homeProb + awayProb : null;
  const complement = total !== null && total >= 0.99 && total <= 1.01;
  const pHome = complement ? homeProb / (total as number) : homeProb;
  const tHome = tenthsInt(pHome);
  const home = partsFromTenths(tHome, pHome);
  if (awayProb === null || !Number.isFinite(awayProb)) return { home, away: null };
  if (!complement) return { home, away: partsFromTenths(tenthsInt(awayProb), awayProb) };
  return { home, away: partsFromTenths(1000 - tHome, 1 - pHome) };
}

export function tenthsText(parts: TenthsParts): string {
  return `${parts.marker ?? ''}${parts.whole}${parts.decimal}%`;
}

/**
 * The chart end label for one side, from the SAME derived pair the headline
 * prints — rounding `1 - p` on its own printed 36.8 / 63.3 at p = 0.3675.
 */
export function tenthsSideLabel(homeProb: number, away: boolean): string {
  const pair = tenthsPair(homeProb, 1 - homeProb);
  const parts = away ? pair.away : pair.home;
  return parts ? tenthsText(parts) : '';
}
