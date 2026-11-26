// THE LINK CARRIES THE GROUP.
//
// There is no table behind /guess. Everything a group shares rides in the part
// of the address after the `#`, which a browser never sends to a server. A
// person plays, the page builds a link holding every player's name and guesses,
// and the next person who opens it plays the same cards against them. They can
// send it on in turn: each link holds everyone so far. A link can be made after
// any step, so someone can send just Easy and the next person still plays on.
//
// The shape, kept to characters that survive being pasted into a chat:
//
//   #g=<edition>.<player>.<player>…
//   <player> = <name>-<guesses>-<ratings>-<good>-<times>-<fun>
//     name     percent-encoded, with `-` and `.` encoded too
//     guesses  three base-36 digits a card, `zzz` for a card not answered
//              (three, because a two-slider card holds two percents in one number)
//     ratings  one digit a card, 0 to 5
//     good     one digit a card, 0 or 1
//     times    three base-36 digits a step: whole seconds spent deciding
//     fun      one digit: the step called the most fun, 0 for none
//
// A link is DATA FROM A STRANGER. Decoding never throws, drops anything that is
// not a valid guess for its card, cleans every name, and caps the number of
// players it will read.

import { cleanName, isValidGuess, MAX_CARD_SECONDS } from "./engine";
import type { GamePack, PlayerEntry } from "./types";

export const MAX_LINK_PLAYERS = 24;

/** Characters a guess takes in a link. 36³ is 46,656, above the largest guess any card allows. */
const GUESS_WIDTH = 3;
const NO_GUESS = "z".repeat(GUESS_WIDTH);
const TIME_WIDTH = 3;

function encodeName(name: string): string {
  return encodeURIComponent(name).replace(/[-._~!*'()]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

/** The most seconds a step can honestly hold: every card at its cap. */
function maxStepSeconds(pack: GamePack): number {
  return pack.perRound * MAX_CARD_SECONDS;
}

function cleanSeconds(pack: GamePack, value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return 0;
  return Math.min(maxStepSeconds(pack), Math.round(value));
}

function encodeEntry(pack: GamePack, entry: PlayerEntry): string {
  const guesses = pack.cards
    .map((card, i) => {
      const g = entry.guesses[i] ?? null;
      return isValidGuess(card, g) ? g.toString(36).padStart(GUESS_WIDTH, "0") : NO_GUESS;
    })
    .join("");
  const ratings = pack.cards.map((_, i) => String(Math.max(0, Math.min(5, Math.trunc(entry.ratings[i] ?? 0))))).join("");
  const good = pack.cards.map((_, i) => (entry.good[i] ? "1" : "0")).join("");
  const times = pack.steps.map((_, s) => cleanSeconds(pack, entry.times[s]).toString(36).padStart(TIME_WIDTH, "0")).join("");
  const fun = Number.isInteger(entry.fun) && entry.fun >= 1 && entry.fun <= pack.steps.length ? entry.fun : 0;
  return `${encodeName(entry.name)}-${guesses}-${ratings}-${good}-${times}-${fun}`;
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
  const steps = pack.steps.length;
  const players: PlayerEntry[] = [];
  const taken = new Set<string>();
  for (const part of parts.slice(0, MAX_LINK_PLAYERS)) {
    const fields = part.split("-");
    if (fields.length !== 6) continue;
    const [rawName, rawGuesses, rawRatings, rawGood, rawTimes, rawFun] = fields;
    if (rawGuesses.length !== n * GUESS_WIDTH || rawRatings.length !== n || rawGood.length !== n) continue;
    if (rawTimes.length !== steps * TIME_WIDTH || rawFun.length !== 1) continue;
    let name = "";
    try {
      name = cleanName(decodeURIComponent(rawName));
    } catch {
      continue;
    }
    if (!name) continue;
    const guesses = pack.cards.map((card, i) => {
      const digits = rawGuesses.slice(i * GUESS_WIDTH, (i + 1) * GUESS_WIDTH).toLowerCase();
      if (digits === NO_GUESS || !/^[0-9a-z]+$/.test(digits)) return null;
      const value = parseInt(digits, 36);
      return isValidGuess(card, value) ? value : null;
    });
    if (guesses.every((g) => g === null)) continue;
    const ratings = pack.cards.map((_, i) => {
      const value = Number(rawRatings[i]);
      return Number.isInteger(value) && value >= 0 && value <= 5 ? value : 0;
    });
    const good = pack.cards.map((_, i) => rawGood[i] === "1");
    const times = pack.steps.map((_, s) => {
      const digits = rawTimes.slice(s * TIME_WIDTH, (s + 1) * TIME_WIDTH).toLowerCase();
      return /^[0-9a-z]+$/.test(digits) ? cleanSeconds(pack, parseInt(digits, 36)) : 0;
    });
    const funValue = Number(rawFun);
    const fun = Number.isInteger(funValue) && funValue >= 1 && funValue <= steps ? funValue : 0;
    players.push({ name: uniqueName(name, taken), guesses, ratings, good, times, fun, from: "link" });
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
 * The message a player sends at the end. Short, in the sender's own voice, and
 * the link is on its own line so chat apps make it tappable. `players` are the
 * people on this phone, with their points; `steps` is the one player's score
 * step by step ("Easy 4 of 5"), used when one person played.
 */
export function shareMessage(players: { name: string; points: number }[], coinPoints: number, url: string, steps: string[] = []): string {
  if (players.length === 0) return `Guess the Chance. Your turn:\n${url}`;
  if (players.length === 1) {
    const by = players[0].points - coinPoints;
    const coin = by > 0 ? `That beats a coin flip by ${by}.` : by < 0 ? `A coin flip beat me by ${-by}.` : "I tied a coin flip.";
    const detail = steps.length > 0 ? ` (${steps.join(", ")})` : "";
    return `I scored ${players[0].points} on Guess the Chance${detail}. ${coin} Your turn:\n${url}`;
  }
  const best = players.reduce((a, b) => (b.points > a.points ? b : a));
  return `We played Guess the Chance. ${best.name} won with ${best.points}. Your turn:\n${url}`;
}

/**
 * The message for one finished step, for someone who wants to send just that.
 * `players` are the people on this phone with that step's score as they read
 * it ("4 of 5", or points for a slider step). `max` is the most the step pays.
 */
export function stepShareMessage(
  stepName: string,
  isTaps: boolean,
  max: number,
  players: { name: string; label: string; points: number }[],
  url: string,
): string {
  if (players.length === 0) return `Guess the Chance, ${stepName}. Your turn:\n${url}`;
  if (players.length === 1) {
    const mine = isTaps ? `I got ${players[0].label}` : `I scored ${players[0].label} of ${max}`;
    return `${mine} on ${stepName} in Guess the Chance. Your turn:\n${url}`;
  }
  const best = players.reduce((a, b) => (b.points > a.points ? b : a));
  const top = isTaps ? `${best.name} got ${best.label}` : `${best.name} scored ${best.label} of ${max}`;
  return `We played ${stepName} on Guess the Chance. ${top}. Your turn:\n${url}`;
}
