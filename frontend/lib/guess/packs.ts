// EVERY SET THAT HAS BEEN LIVE AT /guess, NEWEST FIRST.
//
// A link carries the code of the set it was made on. The page opens that set,
// so the person who taps the link plays the same cards as the person who sent
// it, however many days later. A visit with no link gets the newest set.
//
// Adding a day: generate the new set into `pack.ts`, move the set it replaces
// into its own file here, and list it below. A set that leaves this list turns
// every link made on it into a dead end, so sets are only ever added.

import { GUESS_PACK } from "./pack";
import { GUESS_PACK_C1 } from "./packC1";
import type { GamePack } from "./types";

export const GUESS_PACKS: readonly GamePack[] = [GUESS_PACK, GUESS_PACK_C1];

export const LATEST_PACK: GamePack = GUESS_PACKS[0];

/** The set code a link names (`#g=<code>.…`), or "" when the fragment is not a game link. */
export function codeInHash(fragment: string): string {
  const raw = fragment.replace(/^#/, "");
  if (!raw.startsWith("g=")) return "";
  const code = raw.slice(2).split(".")[0] ?? "";
  return /^[a-z0-9]{1,6}$/i.test(code) ? code : "";
}

/** The set a link was made on. Null when the fragment names no set we hold. */
export function packForHash(fragment: string): GamePack | null {
  const code = codeInHash(fragment);
  if (!code) return null;
  return GUESS_PACKS.find((p) => p.code === code) ?? null;
}
