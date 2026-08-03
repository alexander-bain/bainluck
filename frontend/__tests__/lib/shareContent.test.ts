// L2-235 — `shareContent`, the evaluated share predicate.
//
// The bug it replaces: `navigator.share ? "native" : "clipboard"` was read
// AFTER the branch had already run, so the reported method was a fresh guess
// rather than a record. On a browser with neither capability the old code took
// no branch at all and still logged `method: "clipboard"` — a share event for a
// share that never happened.
//
// Every case below is a state the two owned surfaces (`/daily`,
// `/challenge/[id]`) can actually be in. The two that matter most:
//   - `share` present but NOT callable — the old `if (navigator.share)` form
//     accepted it as eligible; `typeof === "function"` does not.
//   - a rejected native sheet (the user cancelling) — must stay a throw so the
//     caller reports nothing, per the rule app/discover/stats/page.tsx set.

import { shareContent } from "@/lib/share";

interface FakeNav {
  share?: unknown;
  clipboard?: { writeText?: unknown };
}

const asNav = (n: FakeNav | undefined): Navigator => n as unknown as Navigator;

function nativeNav(impl: jest.Mock = jest.fn().mockResolvedValue(undefined)) {
  const writeText = jest.fn().mockResolvedValue(undefined);
  return { nav: { share: impl, clipboard: { writeText } }, share: impl, writeText };
}

function clipboardOnlyNav(impl: jest.Mock = jest.fn().mockResolvedValue(undefined)) {
  return { nav: { clipboard: { writeText: impl } }, writeText: impl };
}

const ATTEMPT = {
  title: "Bain Luck Daily",
  text: "4/5 today.",
  url: "https://bainluck.com/daily",
};

describe("shareContent — eligible", () => {
  it("uses the native sheet and reports native", async () => {
    const { nav, share, writeText } = nativeNav();

    await expect(shareContent(ATTEMPT, asNav(nav))).resolves.toBe("native");

    expect(share).toHaveBeenCalledTimes(1);
    expect(share).toHaveBeenCalledWith({
      title: ATTEMPT.title,
      text: ATTEMPT.text,
      url: ATTEMPT.url,
    });
    // A native share must never also touch the clipboard.
    expect(writeText).not.toHaveBeenCalled();
  });

  it("falls back to the clipboard and reports clipboard", async () => {
    const { nav, writeText } = clipboardOnlyNav();

    await expect(shareContent(ATTEMPT, asNav(nav))).resolves.toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith(ATTEMPT.url);
  });

  it("copies clipboardText when the caller supplies one", async () => {
    const { nav, writeText } = clipboardOnlyNav();

    await expect(
      shareContent({ ...ATTEMPT, clipboardText: "4/5 today. Try it: …" }, asNav(nav))
    ).resolves.toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith("4/5 today. Try it: …");
  });
});

describe("shareContent — ineligible and unknown", () => {
  it("reports null when the browser can do neither", async () => {
    await expect(shareContent(ATTEMPT, asNav({}))).resolves.toBeNull();
  });

  it("reports null when clipboard exists but writeText does not", async () => {
    await expect(shareContent(ATTEMPT, asNav({ clipboard: {} }))).resolves.toBeNull();
  });

  // THE REGRESSION. `if (navigator.share)` accepted any truthy value; a
  // non-callable stub was "eligible" and then blew up on invocation.
  it("does not treat a truthy non-callable share as eligible", async () => {
    const { nav, writeText } = clipboardOnlyNav();

    await expect(
      shareContent(ATTEMPT, asNav({ ...nav, share: {} as unknown }))
    ).resolves.toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith(ATTEMPT.url);
  });

  it("reports null for a non-callable share with no clipboard", async () => {
    await expect(shareContent(ATTEMPT, asNav({ share: true }))).resolves.toBeNull();
  });

  // An unknown navigator must resolve to "nothing happened", never to a
  // reported success.
  it("reports null rather than throwing when navigator is absent", async () => {
    await expect(shareContent(ATTEMPT, asNav(undefined))).resolves.toBeNull();
  });
});

describe("shareContent — failure is not success", () => {
  it("propagates a cancelled native sheet instead of reporting a share", async () => {
    const abort = Object.assign(new Error("Share canceled"), { name: "AbortError" });
    const { nav, writeText } = nativeNav(jest.fn().mockRejectedValue(abort));

    await expect(shareContent(ATTEMPT, asNav(nav))).rejects.toBe(abort);
    // No invented fallback: cancelling the sheet must not silently copy.
    expect(writeText).not.toHaveBeenCalled();
  });

  it("propagates a rejected clipboard write", async () => {
    const denied = Object.assign(new Error("Denied"), { name: "NotAllowedError" });
    const { nav } = clipboardOnlyNav(jest.fn().mockRejectedValue(denied));

    await expect(shareContent(ATTEMPT, asNav(nav))).rejects.toBe(denied);
  });
});

describe("shareContent — repeated invocation", () => {
  it("carries no state between two shares in a row", async () => {
    const { nav, share } = nativeNav();

    await expect(shareContent(ATTEMPT, asNav(nav))).resolves.toBe("native");
    await expect(shareContent(ATTEMPT, asNav(nav))).resolves.toBe("native");
    expect(share).toHaveBeenCalledTimes(2);
  });

  it("reports the retry, not the failure before it", async () => {
    const share = jest
      .fn()
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce(undefined);
    const { nav } = nativeNav(share);

    await expect(shareContent(ATTEMPT, asNav(nav))).rejects.toThrow("transient");
    await expect(shareContent(ATTEMPT, asNav(nav))).resolves.toBe("native");
  });
});
