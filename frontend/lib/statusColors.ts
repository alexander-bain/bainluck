/**
 * Event Status Color Mapping
 *
 * Centralizes status → color/label logic for event statuses
 * (live, scheduled, completed, closed). Use this when you need
 * status-based styling outside of individual components.
 *
 * Statuses from the API:
 *   "live"      — game in progress
 *   "scheduled" — not started yet
 *   "completed" — finished (confirmed by Scores API)
 *   "closed"    — finished (inferred from stale odds)
 */

export type EventStatus = "live" | "scheduled" | "completed" | "closed";

export interface StatusStyle {
  /** Short display label */
  label: string;
  /** Tailwind bg class */
  bgClass: string;
  /** Tailwind text class */
  textClass: string;
  /** Tailwind border class */
  borderClass: string;
  /** Dot/indicator color class (solid bg) */
  dotClass: string;
  /** Hex color for charts / non-Tailwind contexts */
  hex: string;
  /** RGB string for CSS custom property usage: "34 197 94" */
  rgb: string;
  /** Whether this status indicates the game is currently active */
  isActive: boolean;
  /** Whether this status indicates the game is finished */
  isFinished: boolean;
}

const STATUS_MAP: Record<EventStatus, StatusStyle> = {
  live: {
    label: "LIVE",
    bgClass: "bg-green-500/15",
    textClass: "text-green-400",
    borderClass: "border-green-500/30",
    dotClass: "bg-green-500",
    hex: "#22c55e",
    rgb: "34 197 94",
    isActive: true,
    isFinished: false,
  },
  scheduled: {
    label: "Upcoming",
    bgClass: "bg-blue-500/15",
    textClass: "text-blue-400",
    borderClass: "border-blue-500/30",
    dotClass: "bg-blue-500",
    hex: "#3b82f6",
    rgb: "59 130 246",
    isActive: false,
    isFinished: false,
  },
  completed: {
    label: "Final",
    bgClass: "bg-gray-500/15",
    textClass: "text-gray-400",
    borderClass: "border-gray-500/30",
    dotClass: "bg-gray-500",
    hex: "#6b7280",
    rgb: "107 114 128",
    isActive: false,
    isFinished: true,
  },
  closed: {
    label: "Final",
    bgClass: "bg-gray-600/15",
    textClass: "text-gray-500",
    borderClass: "border-gray-600/30",
    dotClass: "bg-gray-600",
    hex: "#4b5563",
    rgb: "75 85 99",
    isActive: false,
    isFinished: true,
  },
};

/**
 * Get the full status style for a given event status.
 *
 * @param status - Event status string from the API
 * @returns StatusStyle with label, colors, and Tailwind classes
 */
export function getStatusStyle(status: string): StatusStyle {
  const key = status.toLowerCase() as EventStatus;
  return STATUS_MAP[key] ?? STATUS_MAP.completed;
}

/**
 * Get the hex color for a given event status.
 * Convenience wrapper for chart rendering.
 */
export function getStatusColor(status: string): string {
  return getStatusStyle(status).hex;
}

/**
 * Get the Tailwind classes for a status badge.
 * Returns a string like "bg-green-500/15 text-green-400".
 */
export function getStatusClasses(status: string): string {
  const style = getStatusStyle(status);
  return `${style.bgClass} ${style.textClass}`;
}

/**
 * Check if an event status indicates the game is currently active.
 */
export function isLiveStatus(status: string): boolean {
  return getStatusStyle(status).isActive;
}

/**
 * Check if an event status indicates the game is finished.
 */
export function isFinishedStatus(status: string): boolean {
  return getStatusStyle(status).isFinished;
}
