// Client helpers for the daily /guess challenge and group boards (#12619, 443: A).
// Talks ONLY to `/api/guess/*`, sends ONLY `(day, nickname, answers, step_times)`,
// and merges stored group entries with local and `#g=` link entries without duplicates.

import { API_URL } from "../api";
import { cleanName } from "./engine";
import type { GamePack, PlayerEntry } from "./types";

export const GROUP_CODE_RE = /^[a-z0-9]{8,24}$/;
const CODE_CHARS = "0123456789abcdefghijklmnopqrstuvwxyz";

export interface DailyEditionResponse {
  day: string;
  today_day?: string;
  is_today?: boolean;
  edition_code: string;
  frozen_at: string;
  pack: GamePack;
}

export interface GroupBoardEntry {
  nickname: string;
  answers: number[];
  step_times: number[];
  points: number;
  step_points: number[];
  total_time_seconds: number;
}

export interface GroupBoardResponse {
  day: string;
  edition_code: string;
  group_code: string;
  entries: GroupBoardEntry[];
}

export interface GroupEntrySubmissionPayload {
  day: string;
  nickname: string;
  answers: number[];
  step_times: number[];
}

export class GuessApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "GuessApiError";
    this.status = status;
  }
}

export function isValidGroupCode(raw: string | null | undefined): raw is string {
  return typeof raw === "string" && GROUP_CODE_RE.test(raw);
}

/** Extract the 2-char legacy edition code from `#g=<code>...` when present in `knownCodes`. */
export function extractLegacyHashCode(fragment: string, knownCodes: Record<string, unknown>): string | null {
  const raw = fragment.replace(/^#/, "");
  if (!raw.startsWith("g=")) return null;
  const code = raw.slice(2).split(".")[0] ?? "";
  return code && Object.prototype.hasOwnProperty.call(knownCodes, code) ? code : null;
}

/** Generate a fresh 10-character lowercase alphanumeric group code. */
export function generateGroupCode(): string {
  const len = 10;
  const out: string[] = [];
  if (typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(len);
    globalThis.crypto.getRandomValues(bytes);
    for (let i = 0; i < len; i += 1) {
      out.push(CODE_CHARS[bytes[i] % CODE_CHARS.length]);
    }
    return out.join("");
  }
  for (let i = 0; i < len; i += 1) {
    out.push(CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)]);
  }
  return out.join("");
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body?.detail === "string" && body.detail.trim()) return body.detail;
  } catch {
    // Non-JSON body; keep the caller-friendly fallback message.
  }
  return fallback;
}

export async function fetchTodayPack(day?: string | null): Promise<DailyEditionResponse> {
  const qs = day ? `?day=${encodeURIComponent(day)}` : "";
  const res = await fetch(`${API_URL}/api/guess/today${qs}`, { cache: "no-store" });
  if (!res.ok) {
    throw new GuessApiError(res.status, await readErrorDetail(res, "Today's cards are not ready right now."));
  }
  const data = (await res.json()) as DailyEditionResponse;
  if (!data?.pack || !Array.isArray(data.pack.cards) || data.pack.cards.length === 0) {
    throw new GuessApiError(502, "Today's cards came back incomplete.");
  }
  return data;
}

export async function fetchGroupBoard(groupCode: string, day?: string | null): Promise<GroupBoardResponse> {
  const qs = day ? `?day=${encodeURIComponent(day)}` : "";
  const res = await fetch(`${API_URL}/api/guess/groups/${encodeURIComponent(groupCode)}${qs}`, { cache: "no-store" });
  if (!res.ok) {
    throw new GuessApiError(res.status, await readErrorDetail(res, "Could not load the group board right now."));
  }
  return (await res.json()) as GroupBoardResponse;
}

export async function submitGroupEntry(groupCode: string, payload: GroupEntrySubmissionPayload): Promise<GroupBoardResponse> {
  // Send ONLY day, nickname, answers, step_times — never a client-computed score or identifier.
  const body = {
    day: payload.day,
    nickname: payload.nickname,
    answers: payload.answers,
    step_times: payload.step_times,
  };
  const res = await fetch(`${API_URL}/api/guess/groups/${encodeURIComponent(groupCode)}/entries`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new GuessApiError(res.status, await readErrorDetail(res, "Could not save your finished game right now."));
  }
  return (await res.json()) as GroupBoardResponse;
}

export function groupEntryToPlayerEntry(pack: GamePack, row: GroupBoardEntry): PlayerEntry {
  const name = cleanName(row.nickname) || row.nickname.slice(0, 12);
  return {
    name,
    guesses: pack.cards.map((_, i) => (typeof row.answers[i] === "number" ? row.answers[i] : null)),
    ratings: pack.cards.map(() => 0),
    good: pack.cards.map(() => false),
    times: pack.steps.map((_, s) => (typeof row.step_times[s] === "number" ? row.step_times[s] : 0)),
    fun: 0,
    from: "server",
  };
}

/**
 * Merge local players (`here`), stored group board players (`stored`), and
 * `#g=` fragment players (`fromLink`) with strictly ONE row per nickname.
 */
export function mergeGroupPlayers(here: PlayerEntry[], stored: PlayerEntry[], fromLink: PlayerEntry[]): PlayerEntry[] {
  const out: PlayerEntry[] = [];
  const seen = new Set<string>();
  const add = (entry: PlayerEntry) => {
    const key = entry.name.trim().toLowerCase();
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push(entry);
  };
  for (const p of here) add(p);
  for (const p of stored) add(p);
  for (const p of fromLink) add(p);
  return out;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Format a YYYY-MM-DD day string as a short readable label without timezone shift. */
export function formatDayLabel(dayIso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dayIso.trim());
  if (!m) return dayIso;
  const monthIdx = Number(m[2]) - 1;
  const dayNum = Number(m[3]);
  const monthName = MONTHS[monthIdx];
  if (!monthName || !Number.isInteger(dayNum) || dayNum < 1 || dayNum > 31) return dayIso;
  return `${monthName} ${dayNum}`;
}

/** Decide whether a finished local player opening a group link lands on Results and needs one-tap Add. */
export function evaluateGroupVisitOnResults(
  isLegacyPack: boolean,
  saved: { phase: string; groupCode?: string | null; joinedGroups?: string[] } | null,
  initialGroupCode: string | null,
): { restoreResults: boolean; needsAddTap: boolean } {
  if (isLegacyPack || !saved || saved.phase !== "results") {
    return { restoreResults: false, needsAddTap: false };
  }
  if (!initialGroupCode) {
    return { restoreResults: true, needsAddTap: false };
  }
  const joined = new Set([...(saved.joinedGroups ?? []), ...(saved.groupCode ? [saved.groupCode] : [])]);
  return { restoreResults: true, needsAddTap: !joined.has(initialGroupCode) };
}
