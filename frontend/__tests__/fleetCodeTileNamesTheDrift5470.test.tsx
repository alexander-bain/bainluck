/**
 * #5470 — the `/admin` tile for "is the background app running the code the
 * site is serving?".
 *
 * Notice 48's third read, the one that counts, is
 * `/api/admin/celery/fleet-code` saying MATCHED; YOUR-TURN's attended recovery
 * step asks for the same fact and its only reader today is a lane with an admin
 * token. The tile has to be able to say BEHIND, it has to say for how long when
 * it knows and refuse to when it does not, and it must be unable to say
 * "everything is up to date" when it could not read the census (gotcha #53).
 *
 * DRIFTED_TODAY is the live payload of that endpoint, read verbatim from
 * production at 06:07Z on 2026-09-13 — heavy on `a1ba6f34` since 21:38 PT while
 * the site served `fa886187`, with `on_slug_s` null for heavy because its
 * marker predates the age stamp. That null is the specimen for the trap this
 * file exists to pin: an absent age rendered as a fresh one.
 */
import { renderToStaticMarkup } from "react-dom/server";
import {
  appLabel,
  fleetCodeReading,
  humanAge,
  workerLabel,
  FleetCodeTile,
  HEAVY_SYNC_COMMAND,
} from "@/components/admin/FleetCodeCard";

const DRIFTED_TODAY = {
  status: "ok",
  verdict: "DRIFTED",
  reader_slug: "fa886187",
  drifted: ["bainluck-heavy/worker-heavy.1"],
  matched: ["bainluck/worker-background.1", "bainluck/worker-realtime.1"],
  unknown: [],
  unstamped_expected: [],
  on_slug_s: {
    "bainluck-heavy/worker-heavy.1": null,
    "bainluck/worker-background.1": 598,
    "bainluck/worker-realtime.1": 578,
  },
  detail: {
    "bainluck/worker-background.1": { slug: "fa886187" },
    "bainluck/worker-realtime.1": { slug: "fa886187" },
    "bainluck-heavy/worker-heavy.1": { slug: "a1ba6f34" },
  },
  ttl_s: 3600,
};

/** The same shape once heavy's marker carries an age: 8h29m behind. */
const DRIFTED_WITH_AN_AGE = {
  ...DRIFTED_TODAY,
  on_slug_s: { ...DRIFTED_TODAY.on_slug_s, "bainluck-heavy/worker-heavy.1": 30540 },
};

const CONVERGED = {
  status: "ok",
  verdict: "MATCHED",
  reader_slug: "fa886187",
  drifted: [],
  matched: [
    "bainluck-heavy/worker-heavy.1",
    "bainluck/worker-background.1",
    "bainluck/worker-realtime.1",
  ],
  unknown: [],
  unstamped_expected: [],
  on_slug_s: { "bainluck-heavy/worker-heavy.1": 120 },
  detail: { "bainluck-heavy/worker-heavy.1": { slug: "fa886187" } },
  ttl_s: 3600,
};

describe("#5470 fleetCodeReading — the verdict a human reads", () => {
  test("today's production reading: one worker behind, named in English", () => {
    const r = fleetCodeReading(DRIFTED_TODAY);
    expect(r.tone).toBe("bad");
    expect(r.headline).toBe("1 worker is running other code than the site.");
    expect(r.detail).toContain("fa886187");
    expect(r.lines).toHaveLength(1);
    expect(r.lines[0].who).toBe("the background app's heavy worker");
    // The machine name never reaches the eye alone.
    expect(r.lines[0].who).not.toContain("bainluck-heavy/");
    expect(r.fix).toBe(HEAVY_SYNC_COMMAND);
  });

  test("A NULL AGE IS PRINTED AS ABSENT, NEVER AS A FRESH ONE", () => {
    // `on_slug_s` is null for heavy today. The endpoint reports a number rather
    // than minting a BEHIND verdict precisely so 40 minutes and 6 days stop
    // reading as the same word; a null silently formatted as `0m` — or as
    // "under a minute" — hands that defect straight back, and reads as the
    // healthiest possible line on the alarm that matters most.
    const r = fleetCodeReading(DRIFTED_TODAY);
    expect(r.lines[0].what).toBe("on a1ba6f34 — how long isn't known yet");
    expect(r.lines[0].what).not.toContain("0m");
    expect(r.lines[0].what).not.toContain("under a minute");
  });

  test("when the age IS known it is said, and it is the real one", () => {
    const r = fleetCodeReading(DRIFTED_WITH_AN_AGE);
    expect(r.lines[0].what).toBe("on a1ba6f34 for 8h 29m");
  });

  test("the age belongs to the worker it is printed against, whatever the key order", () => {
    // Found by mutation: reading `Object.values(on_slug_s)[0]` instead of the
    // worker's own key survived every other assertion in this file, because
    // every fixture happened to list the drifted worker first. It is not a
    // hypothetical — a healthy sibling's freshness printed against the stale
    // worker turns 8h29m into 9m on the one line that decides whether a merged
    // ship is running. So the drifted worker is deliberately LAST here, and its
    // age deliberately differs from the first entry's.
    const r = fleetCodeReading({
      ...DRIFTED_TODAY,
      on_slug_s: {
        "bainluck/worker-realtime.1": 578,
        "bainluck/worker-background.1": 598,
        "bainluck-heavy/worker-heavy.1": 30540,
      },
    });
    expect(r.lines[0].who).toBe("the background app's heavy worker");
    expect(r.lines[0].what).toBe("on a1ba6f34 for 8h 29m");
    expect(r.lines[0].what).not.toContain("9m —");
  });

  test("MATCHED is the pass, names the code, and offers no command", () => {
    const r = fleetCodeReading(CONVERGED);
    expect(r.tone).toBe("ok");
    expect(r.headline).toBe(
      "Every worker is running the code the site is serving."
    );
    expect(r.detail).toBe("Site is on fa886187.");
    expect(r.lines).toEqual([]);
    expect(r.fix).toBe("");
  });

  test("plural reads as plural when more than one worker is behind", () => {
    const r = fleetCodeReading({
      ...DRIFTED_TODAY,
      drifted: [
        "bainluck-heavy/worker-heavy.1",
        "bainluck/worker-background.1",
      ],
    });
    expect(r.headline).toBe("2 workers are running other code than the site.");
    expect(r.lines.map((l) => l.who)).toEqual([
      "the background app's heavy worker",
      "the site app's background worker",
    ]);
  });

  test("DRIFTED with no culprit named does not round down to a calm tile", () => {
    const r = fleetCodeReading({ ...DRIFTED_TODAY, drifted: [] });
    expect(r.tone).toBe("bad");
    expect(r.headline).not.toContain("Every worker");
    expect(r.detail).toBe("Treat this as behind, not as up to date.");
    expect(r.fix).toBe(HEAVY_SYNC_COMMAND);
  });

  test("UNKNOWN_VERSION is a silence, not agreement", () => {
    const r = fleetCodeReading({
      verdict: "UNKNOWN_VERSION",
      reader_slug: "fa886187",
      unknown: ["bainluck-heavy/worker-heavy.1"],
      unstamped_expected: ["bainluck/worker-realtime.1"],
    });
    expect(r.tone).not.toBe("ok");
    expect(r.headline).toBe("A worker can't say what code it is running.");
    expect(r.detail).toContain("not agreement");
    expect(r.lines).toHaveLength(2);
  });

  test("NONE is not the good one", () => {
    const r = fleetCodeReading({ verdict: "NONE", drifted: [], matched: [] });
    expect(r.tone).toBe("bad");
    expect(r.headline).toBe("No worker has reported its code at all.");
  });

  test("an unreadable census can never render as an up-to-date fleet", () => {
    for (const report of [
      { verdict: "INCONCLUSIVE", status: "unreadable" },
      undefined,
      {},
    ]) {
      const r = fleetCodeReading(report);
      expect(r.tone).not.toBe("ok");
      expect(r.headline).not.toContain("Every worker");
      expect(r.fix).toBe("");
    }
    expect(fleetCodeReading({ verdict: "INCONCLUSIVE" }).detail).toBe(
      "This is not proof the background app is up to date."
    );
  });
});

describe("#5470 humanAge — absent is absent", () => {
  test("null and undefined are the empty string, not a zero", () => {
    expect(humanAge(null)).toBe("");
    expect(humanAge(undefined)).toBe("");
  });

  test("a nonsense number is absent too, never a negative duration", () => {
    expect(humanAge(-5)).toBe("");
    expect(humanAge(NaN)).toBe("");
  });

  test("seconds, minutes and hours each read as themselves", () => {
    expect(humanAge(0)).toBe("under a minute");
    expect(humanAge(59)).toBe("under a minute");
    expect(humanAge(60)).toBe("1m");
    expect(humanAge(598)).toBe("9m");
    expect(humanAge(3599)).toBe("59m");
    expect(humanAge(3600)).toBe("1h 0m");
    expect(humanAge(30540)).toBe("8h 29m");
  });
});

describe("#5470 workerLabel / appLabel — no machine name reaches the eye alone", () => {
  test("the three real worker slots read as English", () => {
    expect(workerLabel("bainluck-heavy/worker-heavy.1")).toBe(
      "the background app's heavy worker"
    );
    expect(workerLabel("bainluck/worker-background.1")).toBe(
      "the site app's background worker"
    );
    expect(workerLabel("bainluck/worker-realtime.1")).toBe(
      "the site app's realtime worker"
    );
  });

  test("a slot or an app we have not been taught prints verbatim", () => {
    expect(workerLabel("bainluck/worker-future.1")).toBe(
      "the site app's worker-future"
    );
    expect(workerLabel("bainluck-staging/worker-heavy.1")).toBe(
      "bainluck-staging's heavy worker"
    );
    expect(appLabel("bainluck-staging")).toBe("bainluck-staging");
  });

  test("a malformed identity is not split into a fiction", () => {
    expect(workerLabel("worker-heavy.1")).toBe("worker-heavy.1");
    expect(workerLabel("/worker-heavy.1")).toBe("/worker-heavy.1");
  });
});

describe("#5470 FleetCodeTile — rendered output, since /admin cannot be screenshotted by a lane", () => {
  test("today's tile prints the drift, the age refusal and the one command", () => {
    const html = renderToStaticMarkup(<FleetCodeTile report={DRIFTED_TODAY} />);
    expect(html).toContain("1 worker is running other code than the site.");
    expect(html).toContain("the background app&#x27;s heavy worker");
    expect(html).toContain("how long isn&#x27;t known yet");
    expect(html).toContain(HEAVY_SYNC_COMMAND);
    expect(html).toContain("DRIFTED");
    expect(html).toContain("text-accent-danger");
  });

  test("the converged tile is the healthy tone and offers nothing to type", () => {
    const html = renderToStaticMarkup(<FleetCodeTile report={CONVERGED} />);
    expect(html).toContain("Every worker is running the code the site is serving.");
    expect(html).toContain("text-accent-live");
    expect(html).not.toContain("gh workflow run");
  });

  test("pre-fetch renders neither a verdict badge nor a claim about the fleet", () => {
    const html = renderToStaticMarkup(<FleetCodeTile report={undefined} />);
    expect(html).toContain("Reading the fleet…");
    expect(html).not.toContain("MATCHED");
    expect(html).not.toContain("Every worker");
  });

  test("only design-system tokens are used — no raw palette class reaches the DOM", () => {
    for (const report of [DRIFTED_TODAY, CONVERGED]) {
      const html = renderToStaticMarkup(<FleetCodeTile report={report} />);
      // `colors` in tailwind.config.ts REPLACES the default palette, so a
      // `green-400` here would emit no CSS at all and the tone would be
      // invisible — a silent failure, which is why it is asserted.
      expect(html).not.toMatch(/\b(?:text|bg)-(?:green|red|amber|yellow|emerald)-\d{3}\b/);
    }
  });
});
