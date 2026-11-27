/** @jest-environment jsdom */

// /guess — A LINK OPENS THE SET IT WAS MADE ON (445: A).
//
// Found Fri Nov 27, 2026: a player opened a link made on Wednesday's set after
// Friday's set had replaced it. The page showed the new cards and started them
// alone, so the two scores could not be compared. The whole value of the game is
// that comparison. Rules this file holds:
//
//   1. Every set that has been live stays in `GUESS_PACKS`, newest first.
//   2. A link names its set, and the page opens that set with the sender on the board.
//   3. A visit with no link, or a link to a set we do not hold, gets the newest set.
//   4. A game in progress on one set is not wiped by opening a link to another.
//   5. Two quick taps on a button are two taps: the game never zooms on a double tap,
//      and dragging a slider moves only the slider.

import fs from "fs";
import path from "path";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import GuessPage from "@/app/guess/page";
import { emptyEntry, fullGuess } from "@/lib/guess/engine";
import { decodeGroup, encodeGroup } from "@/lib/guess/link";
import { GUESS_PACK } from "@/lib/guess/pack";
import { GUESS_PACK_C1 } from "@/lib/guess/packC1";
import { codeInHash, GUESS_PACKS, LATEST_PACK, packForHash } from "@/lib/guess/packs";
import { clearGame, loadGame, saveGame, type SavedGame } from "@/lib/guess/storage";
import type { GamePack, PlayerEntry } from "@/lib/guess/types";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

const ROOT = path.join(__dirname, "..", "..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");

function finished(pack: GamePack, name: string): PlayerEntry {
  const entry = emptyEntry(pack, name, "here");
  return { ...entry, guesses: pack.cards.map((card) => fullGuess(card)), times: pack.steps.map(() => 30) };
}

function linkFor(pack: GamePack, name: string): string {
  return `#${encodeGroup(pack, [finished(pack, name)])}`;
}

function saved(pack: GamePack, name: string): SavedGame {
  return { packId: pack.id, phase: "play", index: 3, turn: 0, here: [finished(pack, name)], link: [] };
}

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let host: HTMLElement | null = null;

/** Put the page in the browser at `/guess<hash>` and let its effects run. */
async function open(hash: string) {
  window.history.replaceState(null, "", `/guess${hash}`);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root?.render(<GuessPage />);
  });
}

const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
  window.localStorage.clear();
  window.history.replaceState(null, "", "/guess");
});

describe("/guess — the sets", () => {
  it("keeps every set that has been live, newest first, each with its own code and id", () => {
    expect(GUESS_PACKS[0]).toBe(GUESS_PACK);
    expect(LATEST_PACK).toBe(GUESS_PACK);
    expect(GUESS_PACKS).toContain(GUESS_PACK_C1);
    expect(new Set(GUESS_PACKS.map((p) => p.code)).size).toBe(GUESS_PACKS.length);
    expect(new Set(GUESS_PACKS.map((p) => p.id)).size).toBe(GUESS_PACKS.length);
    // Wednesday's set and Friday's set were both live; a link to either must open it.
    expect(GUESS_PACKS.map((p) => p.code)).toEqual(expect.arrayContaining(["c1", "d1"]));
  });

  it("reads the set a link names, and nothing from a fragment that is not a game link", () => {
    expect(codeInHash(linkFor(GUESS_PACK_C1, "Ann"))).toBe("c1");
    expect(packForHash(linkFor(GUESS_PACK_C1, "Ann"))).toBe(GUESS_PACK_C1);
    expect(packForHash(linkFor(GUESS_PACK, "Ann"))).toBe(GUESS_PACK);
    expect(packForHash("#g=zz.Ann-000")).toBeNull();
    expect(packForHash("")).toBeNull();
    expect(packForHash("#top")).toBeNull();
    expect(packForHash("#g=../../etc.x")).toBeNull();
  });

  it("a link made on an earlier set carries its player on that set, and nobody on the newest", () => {
    const link = linkFor(GUESS_PACK_C1, "Ann");
    const onItsOwnSet = decodeGroup(GUESS_PACK_C1, link);
    expect(onItsOwnSet.ok && onItsOwnSet.players.map((p) => p.name)).toEqual(["Ann"]);
    // This is the fault the page had: read against the newest set, the sender is gone.
    expect(decodeGroup(LATEST_PACK, link)).toEqual({ ok: false, reason: "other-edition" });
  });
});

describe("/guess — the page opens the link's own set", () => {
  it("a link from an earlier set shows its sender and says which set this is", async () => {
    await open(linkFor(GUESS_PACK_C1, "Ann"));
    expect(byId("earlier-players")?.textContent).toContain("Ann has already played");
    expect(byId("set-note")?.textContent).toContain("the set this link was made on");
    expect(byId("link-note")).toBeNull();
    expect(document.body.textContent).toContain(`Numbers as of ${GUESS_PACK_C1.asOf}`);
    // The way back to today's cards is a plain link to the page with no group on it.
    expect(byId("set-note")?.querySelector("a")?.getAttribute("href")).toBe("/guess");
  });

  it("a link from the newest set shows its sender and no note about sets", async () => {
    await open(linkFor(LATEST_PACK, "Bo"));
    expect(byId("earlier-players")?.textContent).toContain("Bo has already played");
    expect(byId("set-note")).toBeNull();
    expect(document.body.textContent).toContain(`Numbers as of ${LATEST_PACK.asOf}`);
  });

  it("no link gets the newest set", async () => {
    await open("");
    expect(byId("earlier-players")).toBeNull();
    expect(byId("set-note")).toBeNull();
    expect(document.body.textContent).toContain(`Numbers as of ${LATEST_PACK.asOf}`);
  });

  it("a link to a set we do not hold opens the newest and says the link is from an earlier set", async () => {
    await open("#g=zz.Ann-000");
    expect(byId("link-note")?.textContent).toContain("earlier set");
    expect(document.body.textContent).toContain(`Numbers as of ${LATEST_PACK.asOf}`);
  });

  it("follows the address when the group in it changes without a reload", async () => {
    await open("");
    await act(async () => {
      window.history.replaceState(null, "", `/guess${linkFor(GUESS_PACK_C1, "Cy")}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(byId("earlier-players")?.textContent).toContain("Cy has already played");
  });
});

describe("/guess — a game in progress, one per set", () => {
  it("opening another set does not wipe the game kept for this one", () => {
    saveGame(saved(LATEST_PACK, "Ann"));
    saveGame(saved(GUESS_PACK_C1, "Bo"));
    expect(loadGame(LATEST_PACK)?.here[0].name).toBe("Ann");
    expect(loadGame(GUESS_PACK_C1)?.here[0].name).toBe("Bo");
    clearGame(GUESS_PACK_C1.id);
    expect(loadGame(GUESS_PACK_C1)).toBeNull();
    expect(loadGame(LATEST_PACK)?.here[0].name).toBe("Ann");
  });

  it("still finds a game kept before sets sat side by side, and clears it with its own set only", () => {
    window.localStorage.setItem("bainluck_guess_v1", JSON.stringify(saved(LATEST_PACK, "Dee")));
    expect(loadGame(LATEST_PACK)?.here[0].name).toBe("Dee");
    expect(loadGame(GUESS_PACK_C1)).toBeNull();
    clearGame(GUESS_PACK_C1.id);
    expect(loadGame(LATEST_PACK)?.here[0].name).toBe("Dee");
    clearGame(LATEST_PACK.id);
    expect(loadGame(LATEST_PACK)).toBeNull();
  });
});

describe("/guess — taps and drags on a phone", () => {
  it("the whole game treats two quick taps as two taps, never a zoom", async () => {
    await open("");
    expect(byId("guess-root")?.className).toContain("touch-manipulation");
    expect(byId("guess-root")?.contains(byId("name-input"))).toBe(true);
  });

  it("every slider keeps a drag to itself", () => {
    const source = read("app/guess/CardFace.tsx");
    const sliders = source.split('type="range"').slice(1);
    expect(sliders.length).toBeGreaterThanOrEqual(2);
    for (const after of sliders) {
      const tag = after.slice(0, after.indexOf("/>"));
      expect(tag).toContain("touch-none");
    }
  });

  it("prints nothing smaller than 12 px in the game's own screens", () => {
    for (const file of ["app/guess/ChanceGame.tsx", "app/guess/CardFace.tsx", "app/guess/CardReveal.tsx", "app/guess/GameCharts.tsx"]) {
      expect(read(file)).not.toMatch(/text-\[(?:[0-9]|1[01])px\]/);
    }
  });
});
