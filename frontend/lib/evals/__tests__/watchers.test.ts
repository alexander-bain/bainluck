/**
 * #12102 S5 — the checks that run on their own, as the schedule and the
 * receipts say.
 *
 * `data/watchers-2026-11-06.json` is a list kept by hand. Every schedule in it
 * is held to the beat schedule's own line (quoted verbatim from
 * `backend/app/tasks/__init__.py` at 80b7a1605c in the test-only receipts
 * file), and every verdict to the watcher's own posts on GitHub: each post's
 * first line verbatim, with GitHub's time for it. The page works out Pacific
 * times from the UTC crontab on the reader's date; these tests prove that
 * arithmetic on both sides of daylight saving.
 */

import RAW from "@/lib/evals/data/watchers-2026-11-06.json";
import RECEIPTS from "@/lib/evals/data/watchers-2026-11-06.receipts.json";
import { EVALS_SOURCES } from "@/lib/evals/sources";
import { pacificClockLabel } from "@/lib/evals/truth";
import {
  cadence,
  cronField,
  cronRuns,
  loadWatchers,
  pacificMinuteOfDay,
  utcInstantOn,
  watcherProblem,
} from "@/lib/evals/watchers";

type Quote = { quote: string; from: string; posted_at?: string; kind?: "reported" | "closed" };
const SCHEDULES = RECEIPTS.schedules as Record<string, Quote>;
const VERDICTS = RECEIPTS.verdicts as Record<string, Record<string, Quote>>;

/** The slots that quote the earlier stop or the fix; every other slot is one of the run's posts. */
const CONTEXT_SLOTS = ["earlier", "fix"];
/** The watchers' own words when a re-check finds a reported problem gone and closes its issue. */
const GREEN_WORDS = /re-checked\b.*\bGREEN|Auto-closing|^Resolved: a COMPLETE sweep|drift cleared:/i;
const postsOf = (id: string) =>
  Object.entries(VERDICTS[id] ?? {})
    .filter(([slot]) => !CONTEXT_SLOTS.includes(slot))
    .map(([, q]) => q);
const GITHUB_POST = /^https:\/\/github\.com\/alexander-bain\/bainluck\/issues\/(\d+)(#issuecomment-\d+)?$/;
const issueOf = (href: string) => Number(GITHUB_POST.exec(href)?.[1] ?? NaN);

/** The minute and hour a `crontab(...)` line sets; celery's default for an omitted field is "*". */
function crontabFields(line: string): { minute: string; hour: string } {
  const args = /crontab\(([^)]*)\)/.exec(line)?.[1] ?? "";
  const field = (name: string) => {
    const m = new RegExp(`${name}=("([^"]*)"|(\\d+))`).exec(args);
    return m ? m[2] ?? m[3] : "*";
  };
  return { minute: field("minute"), hour: field("hour") };
}

describe("the watcher list", () => {
  const list = loadWatchers();

  it("loads every row", () => {
    expect(list).not.toBeNull();
    expect(list?.watchers).toHaveLength(RAW.watchers.length);
    expect(RAW.watchers.map(watcherProblem)).toEqual(RAW.watchers.map(() => null));
  });

  it("every schedule is the beat schedule's own line", () => {
    for (const w of RAW.watchers) {
      const q = SCHEDULES[w.id];
      expect({ id: w.id, quoted: !!q }).toEqual({ id: w.id, quoted: true });
      expect(q.quote).toMatch(/^"schedule": crontab\(/);
      expect({ id: w.id, cron: crontabFields(q.quote) }).toEqual({ id: w.id, cron: w.cron });
      expect(q.from).toBe(RAW.schedule_source.href);
    }
  });

  it("reads the three shapes the list uses: every few minutes, every few hours, once a day", () => {
    const byId = Object.fromEntries(RAW.watchers.map((w) => [w.id, w.cron]));
    expect(cadence(byId["matching-reconciliation"])).toEqual({ kind: "minutes", every: 15 });
    expect(cadence(byId["data-quality-watchdog"])).toEqual({ kind: "hours", every: 2, minute: 45 });
    expect(cadence(byId["flow-sentinel-daily"])).toEqual({ kind: "daily", hour: 7, minute: 10 });
    expect(cronRuns(byId["matching-reconciliation"])).toHaveLength(96);
    expect(cronRuns(byId["data-quality-watchdog"])).toHaveLength(12);
    expect(RAW.watchers.filter((w) => w.group === "night").every((w) => cadence(w.cron)?.kind === "daily")).toBe(true);
  });

  it("a crontab this page cannot read drops the row: a range, a zero step, a minute past the hour's end", () => {
    expect(cronField("5-10", 59)).toBeNull();
    expect(cronField("*/0", 23)).toBeNull();
    expect(cronField("60", 59)).toBeNull();
    expect(cadence({ minute: "0,10,30", hour: "*" })).toBeNull(); // uneven
    expect(cadence({ minute: "0,30", hour: "1,5" })).toBeNull();
  });
});

describe("Pacific times are worked out, never typed", () => {
  const november = new Date("2026-11-05T20:00:00Z");
  const july = new Date("2026-07-15T19:00:00Z");

  it("a 07:10 UTC run is 11:10 PM in standard time and 12:10 AM in daylight time", () => {
    expect(pacificMinuteOfDay(utcInstantOn(november, 7, 10))).toBe(23 * 60 + 10);
    expect(pacificClockLabel(utcInstantOn(november, 7, 10).toISOString())).toBe("11:10 PM PT");
    expect(pacificMinuteOfDay(utcInstantOn(july, 7, 10))).toBe(10);
    expect(pacificClockLabel(utcInstantOn(july, 7, 10).toISOString())).toBe("12:10 AM PT");
  });

  it("the nightly block runs from late evening to midnight, Pacific, in November", () => {
    const minutes = RAW.watchers
      .filter((w) => w.group === "night")
      .map((w) => {
        const c = cadence(w.cron);
        return c?.kind === "daily" ? pacificMinuteOfDay(utcInstantOn(november, c.hour, c.minute)) : -1;
      });
    for (const m of minutes) expect(m === 0 || m >= 22 * 60).toBe(true);
  });
});

describe("every verdict is the watcher's own posts on GitHub", () => {
  const list = loadWatchers();
  const withVerdict = (list?.watchers ?? []).filter((w) => w.verdict);

  it("only the watchers with posts in the receipts have a verdict", () => {
    expect(withVerdict.map((w) => w.id).sort()).toEqual(Object.keys(VERDICTS).sort());
    for (const w of withVerdict) expect(postsOf(w.id).length).toBeGreaterThan(0);
  });

  it("the run's time is GitHub's time for its first post, and its posts land within twenty minutes", () => {
    for (const w of withVerdict) {
      const v = w.verdict!;
      const times = postsOf(w.id).map((q) => Date.parse(q.posted_at ?? ""));
      expect({ id: w.id, readable: times.every((t) => !Number.isNaN(t)) }).toEqual({ id: w.id, readable: true });
      expect({ id: w.id, runAt: v.runAt }).toEqual({ id: w.id, runAt: VERDICTS[w.id].run.posted_at });
      expect(Math.min(...times)).toBe(Date.parse(v.runAt));
      expect(Math.max(...times) - Math.min(...times)).toBeLessThanOrEqual(20 * 60 * 1000);
      expect(v.receipt.href).toBe(VERDICTS[w.id].run.from);
    }
  });

  it("the issues a verdict names are the ones its run reported, and the ones it closed, each in post order", () => {
    for (const w of withVerdict) {
      const of = (kind: string) =>
        Array.from(new Set(postsOf(w.id).filter((q) => q.kind === kind).map((q) => issueOf(q.from))));
      expect({ id: w.id, issues: w.verdict!.issues, closed: w.verdict!.closed }).toEqual({
        id: w.id,
        issues: of("reported"),
        closed: of("closed"),
      });
    }
  });

  it("every post is the watcher's own on GitHub; a closed post is a green re-check and a reported one never is", () => {
    for (const w of withVerdict) {
      for (const q of postsOf(w.id)) {
        expect(q.from).toMatch(GITHUB_POST);
        expect({ id: w.id, quote: q.quote, green: GREEN_WORDS.test(q.quote) }).toEqual({
          id: w.id,
          quote: q.quote,
          green: q.kind === "closed",
        });
      }
      const kinds = new Set(postsOf(w.id).map((q) => q.kind));
      if (w.verdict?.state === "closed_fixed") expect(Array.from(kinds)).toEqual(["closed"]);
      if (w.verdict?.state === "red_reporting") expect(kinds.has("reported")).toBe(true);
      if (w.verdict?.state === "red_stopped") {
        expect(Object.values(VERDICTS[w.id]).map((q) => q.quote).join(" ")).toMatch(/reporting STOPPED/);
      }
    }
  });

  it("the earlier stop and the fix each quote a comment on the issue they name", () => {
    for (const w of withVerdict) {
      const v = w.verdict!;
      for (const [slot, n] of [["earlier", v.earlier], ["fix", v.fix]] as const) {
        if (n === null) {
          expect({ id: w.id, slot, quoted: slot in (VERDICTS[w.id] ?? {}) }).toEqual({ id: w.id, slot, quoted: false });
          continue;
        }
        const q = VERDICTS[w.id][slot];
        if (slot === "fix") expect(q.quote).toContain(`#${n}`);
        else expect(q.from).toContain(`/issues/${n}#`);
      }
    }
  });

  it("a fix shows only when it merged after the run it follows", () => {
    // #12105 merged at 2026-11-06T04:22:02Z (GitHub's merge time for the pull request).
    const FIX_MERGED: Record<number, string> = { 12105: "2026-11-06T04:22:02Z" };
    for (const w of withVerdict.filter((x) => x.verdict?.fix !== null)) {
      const merged = FIX_MERGED[w.verdict!.fix!];
      expect(merged).toBeDefined();
      expect(Date.parse(merged)).toBeGreaterThan(Date.parse(w.verdict!.runAt));
    }
  });

  it("every verdict's receipt, and every stop it quotes, is a source the page lists", () => {
    const listed = EVALS_SOURCES.map((s) => s.href);
    for (const w of withVerdict) {
      expect(listed).toContain(w.verdict?.receipt.href);
      for (const slot of CONTEXT_SLOTS) if (VERDICTS[w.id][slot]) expect(listed).toContain(VERDICTS[w.id][slot].from);
    }
    expect(listed).toContain(RAW.schedule_source.href);
  });
});

describe("a malformed row drops the section, never one row", () => {
  const good = RAW.watchers.find((w) => w.verdict) as Record<string, unknown>;
  const verdict = good.verdict as Record<string, unknown>;

  it.each([
    ["an unreadable crontab", { ...good, cron: { minute: "5-10", hour: "*" } }, /crontab/],
    ["an unknown group", { ...good, group: "weekly" }, /group/],
    ["no source link", { ...good, source: "" }, /source/],
    ["an unknown verdict state", { ...good, verdict: { ...verdict, state: "green" } }, /state/],
    ["a verdict with no receipt", { ...good, verdict: { ...verdict, receipt: { label: "x", href: "" } } }, /receipt/],
    ["a verdict that names no issue", { ...good, verdict: { ...verdict, issues: [] } }, /issue/],
    ["an unreadable run time", { ...good, verdict: { ...verdict, run_at: "last night" } }, /run time/],
    ["closed issues that are not issue numbers", { ...good, verdict: { ...verdict, closed: ["#12074"] } }, /closed/],
    [
      "a run closed as fixed that also names a reported issue",
      { ...good, verdict: { ...verdict, state: "closed_fixed", issues: [1], closed: [2] } },
      /closed as fixed/,
    ],
    [
      "a run closed as fixed that names no closed issue",
      { ...good, verdict: { ...verdict, state: "closed_fixed", issues: [], closed: [] } },
      /closed as fixed/,
    ],
  ])("%s", (_label, row, why) => {
    expect(watcherProblem(row)).toMatch(why);
    expect(loadWatchers({ ...RAW, watchers: [...RAW.watchers, row] })).toBeNull();
  });
});
