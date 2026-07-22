// L2-154 Item 1 — eval-promote kill switch. The render + 404 decisions are pure
// functions (jest env is 'node'), so the required states are asserted here:
// enabled (Disable + confirm), disabled (Enable + no confirm), hidden when the
// field is absent, hidden on a 404 (feature-detect), and the toggle-status map.

import {
  killSwitchView,
  interpretToggleStatus,
  DISABLE_CONFIRM,
} from "@/lib/evalPromoteSwitch";

describe("killSwitchView — visible states", () => {
  it("enabled → Disable button with a confirm message", () => {
    const v = killSwitchView(true, false);
    expect(v.visible).toBe(true);
    expect(v.enabled).toBe(true);
    expect(v.label).toBe("Disable");
    expect(v.confirmMessage).toBe(DISABLE_CONFIRM);
    expect(v.confirmMessage).toContain("zeroes");
  });

  it("disabled → Enable button with NO confirm (enabling is safe)", () => {
    const v = killSwitchView(false, false);
    expect(v.visible).toBe(true);
    expect(v.enabled).toBe(false);
    expect(v.label).toBe("Enable");
    expect(v.confirmMessage).toBeNull();
  });
});

describe("killSwitchView — hidden states (no crash)", () => {
  it("field absent (#231 not deployed) → button hidden", () => {
    const v = killSwitchView(undefined, false);
    expect(v.visible).toBe(false);
  });

  it("404 feature-detect (#232 not deployed) → button hidden even when enabled known", () => {
    const v = killSwitchView(true, true);
    expect(v.visible).toBe(false);
  });
});

describe("interpretToggleStatus", () => {
  it("404 → unavailable (hide the button)", () => {
    expect(interpretToggleStatus(404)).toBe("unavailable");
  });

  it("2xx → ok (apply + refetch)", () => {
    expect(interpretToggleStatus(200)).toBe("ok");
    expect(interpretToggleStatus(204)).toBe("ok");
  });

  it("other errors → error (leave state, next refresh reconciles)", () => {
    expect(interpretToggleStatus(500)).toBe("error");
    expect(interpretToggleStatus(401)).toBe("error");
    expect(interpretToggleStatus(403)).toBe("error");
  });
});
