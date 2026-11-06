"use client";

import { CHIP_SHAPE, RESULT_TONE } from "@/components/evals/chipStyles";
import EvalsSection from "@/components/evals/EvalsSection";
import RepoRefLink from "@/components/evals/RepoRefLink";
import ResultChip from "@/components/evals/ResultChip";
import TruthChip from "@/components/evals/TruthChip";
import { useNow } from "@/components/evals/useNow";
import { WATCHERS_COPY as COPY } from "@/lib/evals/copy";
import {
  issueRef,
  pacificClockLabel,
  pacificDayLabel,
  pullRef,
  type MeasuredTruth,
  type Truth,
} from "@/lib/evals/truth";
import {
  cadence,
  cronRuns,
  pacificMinuteOfDay,
  utcInstantOn,
  type Watcher,
  type WatcherList,
  type WatcherVerdict,
} from "@/lib/evals/watchers";

const pad = (n: number) => String(n).padStart(2, "0");

/** The strip's scale: Pacific midnight to midnight. Scale labels, not figures. */
const AXIS: readonly { at: string; label: string }[] = [
  { at: "00:00", label: "12 AM" },
  { at: "06:00", label: "6 AM" },
  { at: "12:00", label: "12 PM" },
  { at: "18:00", label: "6 PM" },
  { at: "00:00", label: "12 AM" },
];

function Axis() {
  return (
    <div aria-hidden="true" className="flex justify-between text-micro text-text-tertiary" data-day-axis="">
      {AXIS.map((tick, i) => (
        <time key={i} dateTime={tick.at}>
          {tick.label}
        </time>
      ))}
    </div>
  );
}

/**
 * A dot for every run in a Pacific day. The dots wait for the browser's clock:
 * the server does not know the reader's date, and the date decides whether a
 * UTC run lands at 11:10 PM or at 12:10 AM.
 */
function DayStrip({ watcher, now }: { watcher: Watcher; now: Date | null }) {
  const runs = now ? cronRuns(watcher.cron) ?? [] : [];
  return (
    <div
      aria-hidden="true"
      data-day-strip={watcher.id}
      data-runs={now ? runs.length : undefined}
      className="relative mt-2 h-2.5 w-full rounded-full bg-surface-elevated"
    >
      {now &&
        runs.map(({ hour, minute }) => {
          const at = pacificMinuteOfDay(utcInstantOn(now, hour, minute));
          return (
            <span
              key={`${hour}:${minute}`}
              data-run-minute={at}
              className="absolute top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent-brand"
              style={{ left: `${(100 * at) / 1440}%` }}
            />
          );
        })}
    </div>
  );
}

/** "Every 15 minutes" · "Every 2 hours" · "Every day at 11:10 PM PT" (UTC until the browser has a clock). */
function ScheduleLine({ watcher, now }: { watcher: Watcher; now: Date | null }) {
  const c = cadence(watcher.cron);
  if (!c) return null;
  if (c.kind === "minutes") {
    return (
      <>
        {COPY.every}{" "}
        <time dateTime={`PT${c.every}M`}>
          {c.every} {COPY.minutes}
        </time>
      </>
    );
  }
  if (c.kind === "hours") {
    return (
      <>
        {COPY.every}{" "}
        <time dateTime={`PT${c.every}H`}>
          {c.every} {COPY.hours}
        </time>
      </>
    );
  }
  if (!now) {
    return (
      <>
        {COPY.everyDayAt}{" "}
        <time dateTime={`${pad(c.hour)}:${pad(c.minute)}`}>
          {pad(c.hour)}:{pad(c.minute)} {COPY.utc}
        </time>
      </>
    );
  }
  const instant = utcInstantOn(now, c.hour, c.minute).toISOString();
  return (
    <>
      {COPY.everyDayAt} <time dateTime={instant}>{pacificClockLabel(instant)}</time>
    </>
  );
}

function verdictTruth(v: WatcherVerdict): MeasuredTruth {
  return { kind: "last_run", asOf: v.runAt, source: v.receipt };
}

const STATE_WORDS: Record<WatcherVerdict["state"], string> = {
  red_reporting: COPY.stateRedReporting,
  red_stopped: COPY.stateRedStopped,
  closed_fixed: COPY.stateClosedFixed,
};

function StateChip({ v }: { v: WatcherVerdict }) {
  // A run that only closed issues is not green: it is neutral, and red stays red.
  const tone = v.state === "closed_fixed" ? RESULT_TONE.not_run : RESULT_TONE.fail;
  return (
    <span data-verdict-chip={v.state} className={`${CHIP_SHAPE} ${tone}`}>
      {STATE_WORDS[v.state]}
    </span>
  );
}

function Issues({ numbers }: { numbers: number[] }) {
  return (
    <>
      {numbers.map((n, i) => (
        <span key={n}>
          {i > 0 && " "}
          <RepoRefLink repoRef={issueRef(n)} />
        </span>
      ))}
    </>
  );
}

/** What the newest run on record did, in a sentence, with its receipt. */
function VerdictDetail({ v }: { v: WatcherVerdict }) {
  const day = pacificDayLabel(v.runAt);
  const clock = pacificClockLabel(v.runAt);
  return (
    <div className="space-y-1">
      <p>
        {COPY.runBefore} <time dateTime={v.runAt}>{day && clock ? `${day}, ${clock}` : day}</time>,{" "}
        {v.state === "red_reporting" ? (
          <>
            {COPY.filedAfter} <Issues numbers={v.issues} />.
          </>
        ) : v.state === "closed_fixed" ? (
          <>
            {v.closed.length === 1 ? COPY.closedOneAfter : COPY.closedManyAfter} <Issues numbers={v.closed} />.
          </>
        ) : (
          <>
            {COPY.stoppedAfter} <Issues numbers={v.issues} />.
          </>
        )}
      </p>
      {v.state !== "closed_fixed" && v.closed.length > 0 && (
        <p>
          {COPY.alsoClosedBefore} <Issues numbers={v.closed} />{" "}
          {v.closed.length === 1 ? COPY.alsoClosedOneAfter : COPY.alsoClosedManyAfter}
        </p>
      )}
      {v.earlier !== null && (
        <p>
          {COPY.earlierBefore} <RepoRefLink repoRef={issueRef(v.earlier)} />.
        </p>
      )}

      {v.fix !== null && (
        <p>
          {COPY.fixBefore} <RepoRefLink repoRef={pullRef(v.fix)} />.
        </p>
      )}
      <p>
        <a
          href={v.receipt.href}
          target="_blank"
          rel="noopener noreferrer"
          data-verdict-receipt=""
          className="text-accent-brand hover:underline"
        >
          {v.receipt.label}
        </a>
      </p>
    </div>
  );
}

function WatcherRow({ watcher, now }: { watcher: Watcher; now: Date | null }) {
  const v = watcher.verdict;
  return (
    <li data-watcher={watcher.id} data-verdict-state={v?.state ?? "unknown"} className="py-3">
      <details className="group">
        <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
          <span className="flex items-baseline justify-between gap-3">
            <span className="flex items-center gap-1.5 text-caption-strong text-text-primary">
              <span className="text-text-tertiary group-open:rotate-90 transition-transform" aria-hidden="true">
                ›
              </span>
              {watcher.name}
            </span>
            <span className="text-micro text-text-secondary whitespace-nowrap" data-schedule={watcher.id}>
              <ScheduleLine watcher={watcher} now={now} />
            </span>
          </span>
          <DayStrip watcher={watcher} now={now} />
          <span
            className="mt-2 flex flex-wrap items-center gap-2"
            data-truth-scope={v ? "last_run" : undefined}
          >
            {v ? (
              <>
                <StateChip v={v} />
                <TruthChip truth={verdictTruth(v)} linked={false} />
              </>
            ) : (
              <>
                <ResultChip result="unknown" />
                <span className="text-micro text-text-secondary">{COPY.unknown}</span>
              </>
            )}
          </span>
        </summary>
        <div className="mt-2 space-y-1.5 pl-4 text-caption text-text-secondary">
          <p>{watcher.checks}</p>
          {v && <VerdictDetail v={v} />}
          <p>
            <a href={watcher.source} target="_blank" rel="noopener noreferrer" data-watcher-source="" className="text-accent-brand hover:underline">
              {COPY.code}
            </a>
          </p>
        </div>
      </details>
    </li>
  );
}

/** "Checks that run on their own" — the watchers, their schedules in Pacific time, and their newest verdicts. */
export default function Watchers({ list }: { list: WatcherList }) {
  const now = useNow();
  const truth: Truth = { kind: "reviewed", asOf: list.reviewedAt, source: list.scheduleSource };
  const group = (key: "day" | "night", heading: string) => {
    const rows = list.watchers.filter((w) => w.group === key);
    if (rows.length === 0) return null;
    return (
      <div data-watcher-group={key}>
        <h3 className="text-micro uppercase tracking-wide text-text-tertiary mb-1">{heading}</h3>
        <Axis />
        <ul className="divide-y divide-surface-border">
          {rows.map((w) => (
            <WatcherRow key={w.id} watcher={w} now={now} />
          ))}
        </ul>
      </div>
    );
  };
  return (
    <EvalsSection id="watchers" title={COPY.title} lead={COPY.lead} detail={COPY.detail} truth={truth}>
      <div className="space-y-5">
        <p className="text-micro text-text-tertiary">{COPY.timesNote}</p>
        {group("day", COPY.dayGroup)}
        {group("night", COPY.nightGroup)}
        <a
          href={list.alertsHref}
          target="_blank"
          rel="noopener noreferrer"
          data-alerts-link=""
          className="inline-block text-caption text-accent-brand hover:underline"
        >
          {COPY.alerts}
        </a>
      </div>
    </EvalsSection>
  );
}
