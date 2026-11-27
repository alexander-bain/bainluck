// Where an unfinished game waits on this phone. Browser storage only: it never
// leaves the device, and the game works without it (a private window, blocked
// storage) by simply not remembering.

import { isValidGuess, MAX_CARD_SECONDS } from "./engine";
import type { GamePack, PlayerEntry } from "./types";

export type Phase = "home" | "play" | "reveal" | "round" | "results";

export interface SavedGame {
  packId: string;
  phase: Phase;
  index: number;
  turn: number;
  here: PlayerEntry[];
  link: PlayerEntry[];
}

// The name of the browser-storage slot this game uses. A name, not a secret.
// One slot per set (`<name>:<set id>`), so opening a link to an older set never
// wipes a game in progress on today's. `SLOT` alone is where a game was kept
// before sets could sit side by side; it is still read, and cleared with its set.
const SLOT = "bainluck_guess_v1";
const slotFor = (packId: string) => `${SLOT}:${packId}`;

function cleanEntry(pack: GamePack, raw: unknown, from: PlayerEntry["from"]): PlayerEntry | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.name !== "string" || !r.name) return null;
  const guesses = Array.isArray(r.guesses) ? r.guesses : [];
  const ratings = Array.isArray(r.ratings) ? r.ratings : [];
  const good = Array.isArray(r.good) ? r.good : [];
  const times = Array.isArray(r.times) ? r.times : [];
  const fun = typeof r.fun === "number" && Number.isInteger(r.fun) && r.fun >= 1 && r.fun <= pack.steps.length ? r.fun : 0;
  return {
    name: r.name.slice(0, 16),
    guesses: pack.cards.map((card, i) => {
      const g = typeof guesses[i] === "number" ? (guesses[i] as number) : null;
      return isValidGuess(card, g) ? g : null;
    }),
    ratings: pack.cards.map((_, i) => (typeof ratings[i] === "number" ? Math.max(0, Math.min(5, ratings[i] as number)) : 0)),
    good: pack.cards.map((_, i) => good[i] === true),
    times: pack.steps.map((_, s) => {
      const t = times[s];
      return typeof t === "number" && Number.isFinite(t) && t > 0 ? Math.min(pack.perRound * MAX_CARD_SECONDS, t) : 0;
    }),
    fun,
    from,
  };
}

export function loadGame(pack: GamePack): SavedGame | null {
  try {
    const text = window.localStorage.getItem(slotFor(pack.id)) ?? window.localStorage.getItem(SLOT);
    if (!text) return null;
    const raw = JSON.parse(text) as Record<string, unknown>;
    if (raw.packId !== pack.id) return null;
    const here = (Array.isArray(raw.here) ? raw.here : [])
      .map((e) => cleanEntry(pack, e, "here"))
      .filter((e): e is PlayerEntry => e !== null);
    if (here.length === 0) return null;
    const link = (Array.isArray(raw.link) ? raw.link : [])
      .map((e) => cleanEntry(pack, e, "link"))
      .filter((e): e is PlayerEntry => e !== null);
    const phases: Phase[] = ["home", "play", "reveal", "round", "results"];
    const phase = phases.includes(raw.phase as Phase) ? (raw.phase as Phase) : "home";
    const index = typeof raw.index === "number" ? Math.max(0, Math.min(pack.cards.length - 1, Math.trunc(raw.index))) : 0;
    const turn = typeof raw.turn === "number" ? Math.max(0, Math.min(here.length - 1, Math.trunc(raw.turn))) : 0;
    return { packId: pack.id, phase, index, turn, here, link };
  } catch {
    return null;
  }
}

export function saveGame(game: SavedGame): void {
  try {
    window.localStorage.setItem(slotFor(game.packId), JSON.stringify(game));
  } catch {
    // Storage is a convenience. A phone that refuses it still plays.
  }
}

export function clearGame(packId: string): void {
  try {
    window.localStorage.removeItem(slotFor(packId));
    const old = window.localStorage.getItem(SLOT);
    if (old && (JSON.parse(old) as Record<string, unknown>).packId === packId) window.localStorage.removeItem(SLOT);
  } catch {
    // Storage is blocked or the old slot is unreadable. Nothing to clear.
  }
}
