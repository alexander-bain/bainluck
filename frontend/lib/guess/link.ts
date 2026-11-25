// THE LINK CARRIES THE GROUP.
//
// There is no table behind /guess. Everything a group shares rides in the part
// of the address after the `#`, which a browser never sends to a server. A
// person plays, the page builds a link holding every player's name and guesses,
// and the next person who opens it plays the same cards against them. They can
// send it on in turn: each link holds everyone so far.
//
// The shape, kept to characters that survive being pasted into a chat:
//
//   #g=<edition>.<player>.<player>…
//   <player> = <name>-<guesses>-<ratings>-<good>
//     name     percent-encoded, with `-` and `.` encoded too
//     guesses  two hex digits a card, `xx` for a card not answered
//     ratings  one digit a card, 0 to 5
//     good     one digit a card, 0 or 1
//
// A link is DATA FROM A STRANGER. Decoding never throws, drops anything that is
// not a valid guess for its card, cleans every name, and caps the number of
// players it will read.

import { cleanName, isValidGuess } from "./engine";
import type { GamePack, PlayerEntry } from "./types";

export const MAX_LINK_PLAYERS = 24;

function encodeName(name: string): string {
  return encodeURIComponent(name).replace(/[-._~!*'()]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

function encodeEntry(pack: GamePack, entry: PlayerEntry): string {
  const guesses = pack.cards
    .map((card, i) => {
      const g = entry.guesses[i] ?? null;
      return isValidGuess(card, g) ? g.toString(16).padStart(2, "0") : "xx";
    })
    .join("");
  const ratings = pack.cards.map((_, i) => String(Math.max(0, Math.min(5, Math.trunc(entry.ratings[i] ?? 0))))).join("");
  const good = pack.cards.map((_, i) => (entry.good[i] ? "1" : "0")).join("");
  return `${encodeName(entry.name)}-${guesses}-${ratings}-${good}`;
}

/** The fragment for a group, without the leading `#`. House entries are never written. */
export function encodeGroup(pack: GamePack, entries: PlayerEntry[]): string {
  const people = entries.filter((e) => e.from !== "house" && e.guesses.some((g) => g !== null));
  return `g=${pack.code}.${people.slice(0, MAX_LINK_PLAYERS).map((e) => encodeEntry(pack, e)).join(".")}`;
}

export type DecodedGroup =
  | { ok: true; players: PlayerEntry[] }
  | { ok: false; reason: "none" | "other-edition" | "unreadable" };

/** Read a fragment (with or without the `#`). Never throws. */
export function decodeGroup(pack: GamePack, fragment: string): DecodedGroup {
  const raw = fragment.replace(/^#/, "");
  if (!raw.startsWith("g=")) return { ok: false, reason: "none" };
  const parts = raw.slice(2).split(".");
  const code = parts.shift() ?? "";
  if (!/^[a-z0-9]{1,6}$/i.test(code)) return { ok: false, reason: "unreadable" };
  if (code !== pack.code) return { ok: false, reason: "other-edition" };

  const n = pack.cards.length;
  const players: PlayerEntry[] = [];
  const taken = new Set<string>();
  for (const part of parts.slice(0, MAX_LINK_PLAYERS)) {
    const fields = part.split("-");
    if (fields.length !== 4) continue;
    const [rawName, rawGuesses, rawRatings, rawGood] = fields;
    if (rawGuesses.length !== n * 2 || rawRatings.length !== n || rawGood.length !== n) continue;
    let name = "";
    try {
      name = cleanName(decodeURIComponent(rawName));
    } catch {
      continue;
    }
    if (!name) continue;
    const guesses = pack.cards.map((card, i) => {
      const hex = rawGuesses.slice(i * 2, i * 2 + 2);
      if (!/^[0-9a-f]{2}$/i.test(hex)) return null;
      const value = parseInt(hex, 16);
      return isValidGuess(card, value) ? value : null;
    });
    if (guesses.every((g) => g === null)) continue;
    const ratings = pack.cards.map((_, i) => {
      const value = Number(rawRatings[i]);
      return Number.isInteger(value) && value >= 0 && value <= 5 ? value : 0;
    });
    const good = pack.cards.map((_, i) => rawGood[i] === "1");
    players.push({ name: uniqueName(name, taken), guesses, ratings, good, from: "link" });
  }
  if (players.length === 0) return { ok: false, reason: "unreadable" };
  return { ok: true, players };
}

/** A name nobody in `taken` has, adding " 2", " 3"… when needed. Records the name it returns. */
export function uniqueName(name: string, taken: Set<string>): string {
  let candidate = name;
  let n = 2;
  while (taken.has(candidate.toLowerCase())) {
    candidate = `${name.slice(0, 10)} ${n}`;
    n += 1;
  }
  taken.add(candidate.toLowerCase());
  return candidate;
}

function sameGuesses(a: PlayerEntry, b: PlayerEntry): boolean {
  const upTo = Math.min(a.guesses.length, b.guesses.length);
  let compared = 0;
  for (let i = 0; i < upTo; i += 1) {
    if (a.guesses[i] === null || b.guesses[i] === null) continue;
    if (a.guesses[i] !== b.guesses[i]) return false;
    compared += 1;
  }
  return compared > 0;
}

/**
 * The players from a link, less anyone who is already on this phone. A person
 * who opens a link holding their own earlier game (same name, same guesses) is
 * not shown twice; a different person with the same name gets a number.
 */
export function mergeFromLink(here: PlayerEntry[], fromLink: PlayerEntry[]): PlayerEntry[] {
  const taken = new Set(here.map((p) => p.name.toLowerCase()));
  const out: PlayerEntry[] = [];
  for (const p of fromLink) {
    const twin = here.find((h) => h.name.toLowerCase() === p.name.toLowerCase());
    if (twin && sameGuesses(twin, p)) continue;
    out.push({ ...p, name: uniqueName(p.name, taken) });
  }
  return out;
}

/**
 * The message a player sends. Short, in the sender's own voice, and the link is
 * on its own line so chat apps make it tappable. `players` are the people on
 * this phone, with their points.
 */
export function shareMessage(players: { name: string; points: number }[], coinPoints: number, url: string): string {
  if (players.length === 0) return `Guess the Chance. Your turn:\n${url}`;
  if (players.length === 1) {
    const by = players[0].points - coinPoints;
    const coin = by > 0 ? `That beats a coin flip by ${by}.` : by < 0 ? `A coin flip beat me by ${-by}.` : "I tied a coin flip.";
    return `I scored ${players[0].points} on Guess the Chance. ${coin} Your turn:\n${url}`;
  }
  const best = players.reduce((a, b) => (b.points > a.points ? b : a));
  return `We played Guess the Chance. ${best.name} won with ${best.points}. Your turn:\n${url}`;
}
