/**
 * #5470 — the `/admin` clock tile, the verification step for moving the
 * `scheduler` dyno off the site app.
 *
 * YOUR-TURN's attended step asks Alex to read "one clock, on the background
 * app" off this tile and gives him `heroku ps:scale scheduler=0 -a bainluck`
 * for the case where it says two. The tile has to be able to SAY two, and it
 * has to be unable to say "one clock" when it could not read the census — celery
 * beat has no distributed lock, so two beats is every scheduled task in the
 * system running twice, and a quiet tile over an unreadable instrument is the
 * failure that matters here (gotcha #53).
 *
 * The payloads below are the live shapes of `/api/admin/celery/beat-instances`,
 * the SINGLE one read verbatim from production at 05:45Z on 2026-09-13.
 */
import { renderToStaticMarkup } from "react-dom/server";
import {
  appLabel,
  clockReading,
  instanceApps,
  ClockTile,
} from "@/components/admin/ClockCard";

const LIVE_SINGLE_ON_SITE_APP = {
  status: "ok",
  instances: ["bainluck/scheduler.1/2"],
  count: 1,
  verdict: "SINGLE",
  slugs: ["d17dbec2"],
  ttl_s: 180,
};

const AFTER_THE_MOVE = {
  status: "ok",
  instances: ["bainluck-heavy/scheduler.1/2"],
  count: 1,
  verdict: "SINGLE",
  slugs: ["d17dbec2"],
  ttl_s: 180,
};

const MID_HANDOVER = {
  status: "ok",
  instances: ["bainluck-heavy/scheduler.1/2", "bainluck/scheduler.1/2"],
  count: 2,
  verdict: "MULTIPLE",
  slugs: ["d17dbec2"],
  ttl_s: 180,
};

describe("#5470 clockReading — the verdict a human reads", () => {
  test("the production reading today: one clock, and it names the SITE app", () => {
    const r = clockReading(LIVE_SINGLE_ON_SITE_APP);
    expect(r.headline).toBe("One clock, on the site app.");
    // Not an alarm — one clock is one clock — but not the finished state
    // either, which is the whole point of the attended move.
    expect(r.tone).toBe("warn");
    expect(r.detail).toBe("Still on the site app, so a site release restarts it.");
    expect(r.fix).toBe("");
  });

  test("after the move it is the healthy tone and names the BACKGROUND app", () => {
    const r = clockReading(AFTER_THE_MOVE);
    expect(r.headline).toBe("One clock, on the background app.");
    expect(r.tone).toBe("ok");
    expect(r.detail).toBe("");
  });

  test("two clocks is the alarm, names both apps, and carries the undo command", () => {
    const r = clockReading(MID_HANDOVER);
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("2 clocks");
    expect(r.headline).toContain("running twice");
    expect(r.detail).toBe("Running on the site app and the background app.");
    expect(r.fix).toBe("heroku ps:scale scheduler=0 -a bainluck");
  });

  test("NONE is not the good one — no clock is an alarm, not a quiet tile", () => {
    const r = clockReading({ verdict: "NONE", count: 0, instances: [] });
    expect(r.tone).toBe("bad");
    expect(r.headline).toBe("No clock — nothing is scheduling anything.");
    expect(r.fix).toBe("heroku ps:scale scheduler=1:Standard-1X -a bainluck-heavy");
  });

  test("an unreadable census can never render as a healthy clock", () => {
    for (const census of [
      { verdict: "INCONCLUSIVE", status: "unreadable" },
      undefined,
      {},
    ]) {
      const r = clockReading(census);
      expect(r.tone).not.toBe("ok");
      expect(r.headline).not.toContain("One clock");
      expect(r.fix).toBe("");
    }
    expect(clockReading({ verdict: "INCONCLUSIVE" }).detail).toBe(
      "This is not proof that one is running."
    );
  });
});

describe("#5470 instanceApps / appLabel — the machine name never reaches the eye alone", () => {
  test("the app is the segment before the first slash, deduped and sorted", () => {
    expect(instanceApps(["bainluck/scheduler.1/2"])).toEqual(["bainluck"]);
    expect(
      instanceApps(["bainluck/scheduler.1/2", "bainluck/scheduler.1/9"])
    ).toEqual(["bainluck"]);
    expect(instanceApps(MID_HANDOVER.instances)).toEqual([
      "bainluck",
      "bainluck-heavy",
    ]);
  });

  test("no instances and a malformed identity do not invent an app", () => {
    expect(instanceApps(undefined)).toEqual([]);
    expect(instanceApps([])).toEqual([]);
    expect(instanceApps(["/scheduler.1/2"])).toEqual([]);
  });

  test("an app we have not been taught prints verbatim rather than guessed", () => {
    expect(appLabel("bainluck")).toBe("the site app");
    expect(appLabel("bainluck-heavy")).toBe("the background app");
    expect(appLabel("bainluck-staging")).toBe("bainluck-staging");
  });
});

describe("#5470 ClockTile — the rendered output, since /admin cannot be screenshotted by a lane", () => {
  test("the healthy tile prints the sentence YOUR-TURN tells Alex to look for", () => {
    const html = renderToStaticMarkup(<ClockTile census={AFTER_THE_MOVE} />);
    expect(html).toContain("One clock, on the background app.");
    expect(html).toContain("SINGLE");
    expect(html).toContain("bainluck-heavy/scheduler.1/2");
    expect(html).toContain("text-accent-live");
    // Nothing to do, so no command is offered.
    expect(html).not.toContain("ps:scale");
  });

  test("the two-clock tile prints the count, the apps and the fix", () => {
    const html = renderToStaticMarkup(<ClockTile census={MID_HANDOVER} />);
    expect(html).toContain("2 clocks");
    expect(html).toContain("heroku ps:scale scheduler=0 -a bainluck");
    expect(html).toContain("text-accent-danger");
    expect(html).toContain("MULTIPLE");
  });

  test("pre-fetch renders neither a verdict badge nor a claim about the clock", () => {
    const html = renderToStaticMarkup(<ClockTile census={undefined} />);
    expect(html).toContain("Reading the clock…");
    expect(html).not.toContain("One clock");
    expect(html).not.toContain("SINGLE");
  });

  test("only design-system tokens are used — no raw palette class reaches the DOM", () => {
    for (const census of [AFTER_THE_MOVE, MID_HANDOVER, LIVE_SINGLE_ON_SITE_APP]) {
      const html = renderToStaticMarkup(<ClockTile census={census} />);
      // `colors` in tailwind.config.ts REPLACES the default palette, so a
      // `green-400` here would emit no CSS at all and the tone would be
      // invisible — the failure mode is silent, which is why it is asserted.
      expect(html).not.toMatch(/\b(?:text|bg)-(?:green|red|amber|yellow|emerald)-\d{3}\b/);
    }
  });
});
