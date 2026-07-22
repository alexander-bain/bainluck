// L2-154 Item 1 — pure logic for the eval-promote kill switch on the cockpit.
//
// #222 made "Accept" in the label pass steer live Discover ranking (bounded,
// 14-day TTL). This is the first human-in-the-loop ranking control, so its OFF
// switch must be one tap on the cockpit — not a Redis incantation. The toggle
// endpoint (`POST /api/admin/eval-promote/toggle`) is #232's Item 4; this lane
// may fire before #232 lands, so the button must feature-detect: a 404 from the
// toggle means the endpoint isn't deployed yet → hide the button, never crash.
//
// The rendering + 404 decisions live here as pure functions (jest env is 'node',
// no DOM) so the required states — enabled, disabled, hidden-when-absent,
// hidden-on-404 — are unit-tested deterministically.

export interface KillSwitchView {
  /** Whether to render the button at all. */
  visible: boolean;
  /** Current on/off state (only meaningful when visible). */
  enabled: boolean;
  /** Button label. */
  label: string;
  /**
   * Confirm-dialog message to show BEFORE toggling, or null for no confirm.
   * Disabling zeroes every applied boost's effect, so it always confirms;
   * enabling is safe and does not.
   */
  confirmMessage: string | null;
}

export const DISABLE_CONFIRM =
  "Disable eval-promote? This zeroes the effect of all applied boosts in Discover ranking — are you sure?";

/**
 * Decide how (and whether) to render the kill-switch button.
 * - `enabled === undefined` → the cockpit payload predates the field (#231 not
 *   deployed): hide, we don't know the state.
 * - `unavailable` → the toggle endpoint 404'd (#232 not deployed): hide.
 * - otherwise → visible; label + confirm depend on the current state.
 */
export function killSwitchView(
  enabled: boolean | undefined,
  unavailable: boolean,
): KillSwitchView {
  if (enabled === undefined || unavailable) {
    return { visible: false, enabled: false, label: "", confirmMessage: null };
  }
  if (enabled) {
    return {
      visible: true,
      enabled: true,
      label: "Disable",
      confirmMessage: DISABLE_CONFIRM,
    };
  }
  return {
    visible: true,
    enabled: false,
    label: "Enable",
    confirmMessage: null,
  };
}

export type ToggleOutcome = "ok" | "unavailable" | "error";

/**
 * Classify the toggle HTTP status: 404 → the endpoint isn't deployed yet
 * (feature-detect → hide the button), 2xx → applied, anything else → a real
 * error (leave the button, next refresh reconciles).
 */
export function interpretToggleStatus(status: number): ToggleOutcome {
  if (status === 404) return "unavailable";
  if (status >= 200 && status < 300) return "ok";
  return "error";
}
