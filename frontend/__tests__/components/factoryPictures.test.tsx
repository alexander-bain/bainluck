/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { validateSnapshot } from "@/app/factory/data";
import DailyPictures from "@/app/factory/DailyPictures";
import type { FactoryData, FactoryPicture } from "@/app/factory/types";

const last: FactoryPicture = { day: "2026-11-20", as_of: "2026-11-21T03:00:00Z", floor: 1, shipped: 6 };
const prior: FactoryPicture = { day: "2026-11-19", as_of: "2026-11-20T03:00:00Z", floor: 3, shipped: 1 };

it("ignores unverified picture dates, URLs and counts in the read", () => {
  const snapshot: FactoryData = {
    schema_version: 1,
    generated_at: "2026-11-21T22:00:00Z",
    observed_since: "2026-11-19T03:00:00Z",
    changes: [], jams: [], signals: { tests: "passing", testflight: "success" }, coverage: [],
    pictures: [
      { ...last, ...{ url: "https://invalid.example/a.webp" } },
      { ...last, day: "2026-11-23" },
      { ...prior, shipped: -2 },
      prior,
    ],
  };
  expect(validateSnapshot(snapshot).pictures).toEqual([last, prior]);
});

it("keeps the previous dated picture and its factual caption when the latest cannot load", async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    await act(async () => root.render(<DailyPictures artist="Builder F" />));
    expect(host.querySelector("details")).toBeNull();
    await act(async () => root.render(<DailyPictures artist="Builder F" pictures={[last, prior]} />));
    expect(host.querySelector("figcaption")?.textContent).toContain("Nov 20, 2026");
    expect(host.querySelector("figcaption")?.textContent).toContain("6 changes went live.");
    const image = host.querySelector("img")!;
    expect(image.src).toMatch(/factory-picture-2026-11-20\.webp$/);
    await act(async () => image.dispatchEvent(new Event("error")));
    expect(host.querySelector("figcaption")?.textContent).toContain("Nov 19, 2026");
    expect(host.querySelector("figcaption")?.textContent).toContain("1 change went live.");
  } finally {
    await act(async () => root.unmount());
  }
});
