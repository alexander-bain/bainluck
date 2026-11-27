// Where finished and unfinished games wait on this phone, keyed by packId
// so multiple editions (`c1`, `d1`, daily PT packs) never overwrite each other.
// Browser storage only: it never leaves the device on its own, and the game
// works without it by simply not remembering.

import { isValidGuess, MAX_CARD_SECONDS } from "./engine";
import type { GamePack, PlayerEntry } from "./types";

export type Phase = "home" | "play" | "reveal" | "round" | "results";

export interface SavedGame {
  packId: string;
  groupCode?: string | null;
  joinedGroups?: string[];
  phase: Phase;
  index: number;
  turn: number;
  here: PlayerEntry[];
  link: PlayerEntry[];
}

// The name of the browser-storage slot this game uses. A name, not a secret.
const SLOT = "bainluck_guess_v1";

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

function readStoreMap(): Record<string, unknown> {
  try {
    const text = window.localStorage.getItem(SLOT);
    if (!text) return {};
    const parsed = JSON.parse(text) as Record<string, unknown>;
    if (parsed && typeof parsed.byPack === "object" && parsed.byPack !== null && !Array.isArray(parsed.byPack)) {
      return { ...(parsed.byPack as Record<string, unknown>) };
    }
    if (typeof parsed?.packId === "string" && parsed.packId) {
      return { [parsed.packId]: parsed };
    }
    return {};
  } catch {
    return {};
  }
}

export function loadGame(pack: GamePack): SavedGame | null {
  try {
    const map = readStoreMap();
    const raw = map[pack.id] as Record<string, unknown> | undefined;
    if (!raw || typeof raw !== "object" || raw.packId !== pack.id) return null;
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
    const groupCode = typeof raw.groupCode === "string" && raw.groupCode ? raw.groupCode : null;
    const joinedGroups = Array.isArray(raw.joinedGroups)
      ? raw.joinedGroups.filter((g): g is string => typeof g === "string" && g.length > 0)
      : phase === "results" && groupCode
        ? [groupCode]
        : [];
    return { packId: pack.id, groupCode, joinedGroups, phase, index, turn, here, link };
  } catch {
    return null;
  }
}

export function saveGame(game: SavedGame): void {
  try {
    const map = readStoreMap();
    map[game.packId] = game;
    window.localStorage.setItem(SLOT, JSON.stringify({ byPack: map }));
  } catch {
    // Storage is a convenience. A phone that refuses it still plays.
  }
}

export function clearGame(packId?: string): void {
  try {
    if (!packId) {
      window.localStorage.removeItem(SLOT);
      return;
    }
    const map = readStoreMap();
    if (!(packId in map)) return;
    delete map[packId];
    if (Object.keys(map).length === 0) {
      window.localStorage.removeItem(SLOT);
    } else {
      window.localStorage.setItem(SLOT, JSON.stringify({ byPack: map }));
    }
  } catch {
    // Nothing to clear.
  }
}
