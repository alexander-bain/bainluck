/**
 * 227-A point 6 — /grade/screens: ten sampled phone screens a week, graded
 * fun, fine or wall of numbers. The server serves only numbered pictures.
 */

export const SCREEN_GRADES = ["fun", "fine", "wall"] as const;
export type ScreenGrade = (typeof SCREEN_GRADES)[number];

export const SCREEN_GRADE_LABELS: Record<ScreenGrade, string> = {
  fun: "Fun",
  fine: "Fine",
  wall: "Wall of numbers",
};

export interface ScreenPicture {
  n: number;
  image: string;
}

export interface ScreenWeek {
  week: string;
  screens: ScreenPicture[];
}

const WEEK = /^[0-9]{4}-w[0-9]{2}$/;

/** ``?week=2026-w47`` when given and well formed; otherwise the newest week. */
export function weekFromSearch(search: string): string | null {
  const week = new URLSearchParams(search).get("week");
  return week && WEEK.test(week) ? week : null;
}

export function screensPath(week: string | null): string {
  const q = week ? `?${new URLSearchParams({ week }).toString()}` : "";
  return `/api/admin/ranking/screens${q}`;
}

/** The next screen after ``n`` that has no answer yet, or null when all are done. */
export function nextScreen(total: number, answered: ReadonlySet<number>, n: number): number | null {
  for (let i = n + 1; i <= total; i++) if (!answered.has(i)) return i;
  for (let i = 1; i <= n; i++) if (!answered.has(i)) return i;
  return null;
}
