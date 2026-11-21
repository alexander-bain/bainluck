"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronRight,
  CircleCheck,
  ClipboardCheck,
  Cog,
  Hammer,
  ListChecks,
  PackageOpen,
  Pause,
  Server,
  Smartphone,
  Truck,
  Wind,
  X,
  Monitor,
} from "lucide-react";
import { usePageTracking } from "@/hooks/usePageTracking";
import { useScrollDepth } from "@/hooks/useScrollDepth";
import { useEngagementTime } from "@/hooks/useEngagementTime";
import type { Builder, Change, FactoryData, Jam, Line, Station, Stop } from "./types";
import styles from "./factory.module.css";
import Worker, { type WorkerState } from "./Worker";
import EventScene from "./EventScene";
import InjurySign from "./InjurySign";
import { clipboard, median } from "./signs";
import { useDayReplay } from "./useDayReplay";
import { useReplayJournal } from "./replayJournal";
import { LIVE_TRANSITION_MS, remainingEvents, transfersSince } from "./liveTransfers";
import { crossesSegment, eventText, useEventPlayer } from "./playback";
import { factoryTabTitle, floorVerdict, type FloorVerdict } from "./verdict";
import {
  stations,
  stationNames,
  pacificDay,
  time,
  duration,
  readerBehind,
  stopText,
  stopWaitText,
  bayActivity,
  crewActivity,
  machineText,
  beltFlowing,
  shownStops,
  knownOrigin,
  onActiveFloor,
  recentlyActive,
} from "./activity";

const lines: Line[] = ["Server", "Website", "Apps"];
const PAGE_REFRESH_MS = 60_000;
const SPEECH_INTERVAL_MS = 8_000;
type NamedBuilder = Exclude<Builder, "Other">;
const builders: { key: NamedBuilder; name: string }[] = [
  { key: "S", name: "Speed" },
  { key: "B", name: "Builder B" },
  { key: "C", name: "Builder C" },
  { key: "D", name: "Atlas" },
  { key: "E", name: "Builder E" },
  { key: "F", name: "Apple" },
  { key: "W", name: "Wee-Bey" },
];
const names = {
  ...Object.fromEntries(builders.map(({ key, name }) => [key, name])),
  Other: "Earlier work",
} as Record<Builder, string>;
const lineIcons = { Server, Website: Monitor, Apps: Smartphone };
const stationIcons = {
  Write: Hammer,
  Test: ListChecks,
  Review: ClipboardCheck,
  "Merge line": PackageOpen,
  Ship: Truck,
  Live: Check,
};
const engineering: Record<Station, string> = {
  Write: "writing",
  Test: "automated tests",
  Review: "review",
  "Merge line": "merge queue",
  Ship: "deploying",
  Live: "in readers’ hands",
};
const bayLimit = 2;
const shelfKeys = ["held", "parked", "bot", "side"] as const;
type Shelf = (typeof shelfKeys)[number];
type CrateGroup =
  | { line: Line; station: Station }
  | { shelf: Shelf };

function crateKey(line: Line, number: number) {
  return `${line}/${number}`;
}

function uniqueChanges(changes: Change[]) {
  const seen = new Set<number>();
  return changes.filter((change) => {
    if (seen.has(change.number)) return false;
    seen.add(change.number);
    return true;
  });
}

function bayCrates(changes: Change[], line: Line, station: Station) {
  return changes
    .filter((c) => c.line === line && c.station === station)
    .sort((a, b) =>
      station === "Live"
        ? (b.live_at ?? "").localeCompare(a.live_at ?? "")
        : (a.station_since ?? a.last_activity).localeCompare(
            b.station_since ?? b.last_activity,
          ),
    );
}

function HoldOrigin({ stop }: { stop: Stop }) {
  if (!stop.source) return null;
  return (
    <small className={styles.stopOrigin}>
      <a
        href={`https://github.com/alexander-bain/bainluck/issues/12779#issuecomment-${stop.source.id}`}
      >
        NOW · stuck
      </a>
      {` · ${time(stop.since)} PT · ${stop.source.author}`}
    </small>
  );
}

function notice(stop: Stop, now: string) {
  return (
    <p key={`${stop.kind}-${stop.line}`} data-level={stop.level}>
      <span aria-hidden="true">{stop.level === "red" ? "■" : "▲"}</span>{" "}
      {stopText(stop, now)}
      {stop.test && <code className={styles.stopOrigin}>{stop.test}</code>}
      {stop.machines && (
        <small className={styles.stopOrigin}>{machineText(stop.machines)}</small>
      )}
      {stop.kind === "hold" && <HoldOrigin stop={stop} />}
    </p>
  );
}

function StackLight({
  verdict,
  hold,
  now,
}: {
  verdict: FloorVerdict;
  hold?: Stop;
  now: string;
}) {
  const waited = hold && stopWaitText(hold, now);
  return (
    <div
      className={styles.verdict}
      data-verdict={verdict.level}
      data-level={hold && "red"}
      role="status"
    >
      <div className={styles.stackLight} aria-hidden="true">
        <i data-light="red" />
        <i data-light="amber" />
        <i data-light="green" />
      </div>
      <div>
        <strong>{verdict.text}</strong>
        {waited && <small className={styles.stopOrigin}>{waited}</small>}
        {hold && <HoldOrigin stop={hold} />}
      </div>
    </div>
  );
}

function jamTitle(jam: Jam) {
  if (jam.kind === "crowd")
    return `${stationNames[jam.station]} held ten or more changes`;
  if (jam.kind === "master") return "Tests failed on the shared version";
  if (jam.kind === "testflight")
    return "An Apps build stopped before TestFlight";
  if (jam.kind === "line-stalled") return `${jam.line} waited for a merge`;
  if (jam.kind === "announced")
    return `${jam.line} announced a turn without merging`;
  if (jam.kind === "hold") return `${jam.line} was put on hold`;
  if (jam.kind === "review-waiting")
    return `${jam.line} waited over two hours for review`;
  return `${jam.line} had an empty merge line with changes waiting`;
}

export default function FactoryFloor({
  data: snapshot,
  lastGoodAt,
  readAt,
  readFailed = false,
  renderedAt,
}: {
  data: FactoryData | null;
  lastGoodAt: string | null;
  readAt?: string;
  readFailed?: boolean;
  renderedAt: string;
}) {
  usePageTracking({ pageType: "home", pageTitle: "The Factory" });
  useScrollDepth({ pageType: "home" });
  useEngagementTime({ pageType: "home" });
  const router = useRouter();
  const [now, setNow] = useState(renderedAt);
  const [selectedCrate, selectCrate] = useState<string | null>(null);
  const [selectedGroup, selectGroup] = useState<CrateGroup | null>(null);
  const [speaker, setSpeaker] = useState<NamedBuilder>();
  const [knownGoodAt, setKnownGoodAt] = useState(lastGoodAt);
  const [lastShown, setLastShown] = useState(snapshot);
  // Keep the open page intact if a refresh lands on a server with an empty cache.
  const data =
    snapshot &&
    (!lastShown ||
      Date.parse(snapshot.generated_at) >= Date.parse(lastShown.generated_at))
      ? snapshot
      : lastShown;
  const detail = useRef<HTMLDialogElement>(null);
  const [tabVisible, setTabVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState<boolean | null>(null);
  const lastRefresh = useRef(Date.parse(renderedAt));
  const behind = data !== null && (readFailed || readerBehind(data, now));
  const motion = !behind && tabVisible && reducedMotion === false;
  const verdict = floorVerdict(data, readFailed, now);
  const tabTitle = factoryTabTitle(verdict);
  const today = pacificDay(now);
  const journal = useReplayJournal(data, today);
  const replay = useDayReplay(motion);
  const speech = data?.speech;
  const speakers = useMemo(() => builders.filter(({ key }) => speech?.[key]), [speech]);
  const currentSpeaker = speakers.find(({ key }) => key === speaker) ?? speakers[0];
  const currentSpeech = currentSpeaker && speech?.[currentSpeaker.key];
  const firstTransferRead = useRef(data?.generated_at);
  firstTransferRead.current ??= data?.generated_at;
  const firstRead = firstTransferRead.current;
  const moves = useMemo(() => transfersSince(data, firstRead), [data, firstRead]);
  const tape = useMemo(() => remainingEvents(data?.events, moves), [data?.events, moves]);
  const transfer = useEventPlayer(
    data?.generated_at, moves, motion && !replay.session,
    LIVE_TRANSITION_MS * Math.max(1, moves.length),
  );
  const livePlaying = useEventPlayer(
    data?.generated_at, tape, motion && !replay.session && !transfer,
  );
  const playing = replay.session ? replay.playing : transfer ?? livePlaying;

  useEffect(() => {
    document.title = tabTitle;
  }, [tabTitle]);

  useEffect(() => {
    if (!motion || !currentSpeaker || speakers.length < 2 || replay.session || selectedCrate || selectedGroup) return;
    const next = speakers[(speakers.indexOf(currentSpeaker) + 1) % speakers.length];
    const timer = window.setTimeout(() => setSpeaker(next.key), SPEECH_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [motion, currentSpeaker, speakers, replay.session, selectedCrate, selectedGroup]);

  useEffect(() => {
    if (data) setLastShown(data);
  }, [data]);

  useEffect(() => {
    try {
      const timestamp =
        data?.generated_at ||
        lastGoodAt ||
        localStorage.getItem("factory-last-good-at");
      if (timestamp && Number.isFinite(Date.parse(timestamp))) {
        setKnownGoodAt(timestamp);
        if (data) localStorage.setItem("factory-last-good-at", timestamp);
      }
    } catch {
      setKnownGoodAt(lastGoodAt);
    }
  }, [data, lastGoodAt]);

  useEffect(() => {
    if (
      (selectedCrate !== null || selectedGroup) &&
      detail.current &&
      !detail.current.open
    ) {
      detail.current.showModal();
    }
  }, [selectedCrate, selectedGroup]);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const preferenceChanged = () => setReducedMotion(preference.matches);
    const refresh = () => {
      const visible = document.visibilityState === "visible";
      setTabVisible(visible);
      if (visible) {
        setNow(new Date().toISOString());
        if (Date.now() - lastRefresh.current >= PAGE_REFRESH_MS) {
          lastRefresh.current = Date.now();
          router.refresh();
        }
      }
    };
    preferenceChanged();
    refresh();
    preference.addEventListener("change", preferenceChanged);
    document.addEventListener("visibilitychange", refresh);
    const interval = window.setInterval(refresh, PAGE_REFRESH_MS);
    return () => {
      preference.removeEventListener("change", preferenceChanged);
      document.removeEventListener("visibilitychange", refresh);
      window.clearInterval(interval);
    };
  }, [router]);

  if (!data) {
    return (
      <article
        className={styles.factory}
        data-factory="true"
        data-motion="paused"
      >
        <header className={styles.heading}>
          <h1>The Factory</h1>
        </header>
        <StackLight verdict={verdict} now={now} />
        <section className={styles.unavailable}>
          <h2>{"The floor can't be read right now"}</h2>
          <p>
            {knownGoodAt
              ? `Last good copy from ${new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", month: "short", day: "numeric" }).format(new Date(knownGoodAt))} at ${time(knownGoodAt)} PT.`
              : "No successful copy has been read yet."}
          </p>
          <p>This page will try again on its next update.</p>
        </section>
      </article>
    );
  }

  const shipped = data.changes.filter(
    (c) => c.station === "Live" && c.live_at && pacificDay(c.live_at) === today,
  );
  const onFloor = data.changes.filter(onActiveFloor);
  const recordTime = behind ? data.generated_at : now;
  const clockedIn = new Set(
    data.changes
      .filter((c) => c.builder !== "Other" && recentlyActive(c.last_activity, recordTime))
      .map((c) => c.builder),
  );
  const engineeringRecords = clipboard(recordTime, shipped, onFloor);
  const mergesToday = new Set(
    data.changes
      .filter((c) => c.merged_at && pacificDay(c.merged_at) === today)
      .map((c) => c.number),
  );
  const held = uniqueChanges(data.changes.filter((c) => c.held_for_108));
  const sideTrack = uniqueChanges(
    data.changes.filter(
      (c) => c.side_track && !c.bot_update && !c.parked && !c.held_for_108,
    ),
  );
  const parked = uniqueChanges(
    data.changes.filter((c) => c.parked && !c.held_for_108),
  );
  const botUpdates = uniqueChanges(
    data.changes.filter((c) => c.bot_update && !c.merged_at && !c.held_for_108),
  );
  const shelves: Record<
    Shelf,
    { title: string; changes: Change[]; note?: string }
  > = {
    held: { title: "Held for 1.0.8", changes: held },
    parked: {
      title: "Parked",
      changes: parked,
      note: "Drafts and changes that passed checks sit here after 48 quiet hours.",
    },
    bot: { title: "Bot updates", changes: botUpdates },
    side: {
      title: "Side track",
      changes: sideTrack,
      note: "Changes with no activity for three days.",
    },
  };
  const stops = behind ? [] : shownStops(data);
  const holds = stops.filter((stop) => stop.kind === "hold");
  const waits = stops.filter((stop) => stop.kind !== "hold");
  const serverHold = holds.find((stop) => stop.line === "Server");
  const notes =
    data.notes?.snapshot_at === data.generated_at ? data.notes : null;
  const noteCredit =
    notes?.source === "model"
      ? "Written by a model from the counts on this page"
      : "From the counts on this page";
  const floorNote = notes && `${verdict.text} ${notes.floor}`.trim().split(/\s+/).length <= 30
    ? notes.floor
    : null;
  const visible = [...onFloor, ...shipped];
  const jams = data.jams.filter(
    (jam) =>
      Date.parse(jam.qualifies_at) <= Date.parse(now) &&
      (jam.kind !== "hold" || knownOrigin(jam.source)) &&
      (!jam.ended_at || pacificDay(jam.ended_at) === today),
  );
  const activeJams = jams.filter((j) => !j.ended_at);
  const selected = data.changes.find(
    (c) => crateKey(c.line, c.number) === selectedCrate,
  );
  const selectedLines = selected
    ? lines.filter((line) =>
        data.changes.some((change) => change.number === selected.number && change.line === line),
      )
    : [];
  const group = selectedGroup && (
    "shelf" in selectedGroup
      ? shelves[selectedGroup.shelf]
      : {
          title: `${selectedGroup.line} · ${stationNames[selectedGroup.station]}`,
          changes: bayCrates(
            visible,
            selectedGroup.line,
            selectedGroup.station,
          ).slice(bayLimit),
          note: undefined,
        }
  );

  function closeDetail() {
    detail.current?.close();
    selectCrate(null);
    selectGroup(null);
  }

  function workerFigure(id: NamedBuilder, station: Station, fallback: WorkerState) {
    const voice = data?.speech?.[id];
    const figure = <Worker identity={id} station={station} state={voice?.mood ?? fallback} />;
    if (!voice) return figure;
    return (
      <button
        type="button"
        className={styles.voiceButton}
        aria-label={`Read ${names[id]}’s speech`}
        aria-pressed={currentSpeaker?.key === id}
        aria-controls="factory-speech"
        onClick={() => setSpeaker(id)}
      >
        {figure}
      </button>
    );
  }

  function crate(change: Change) {
    const key = crateKey(change.line, change.number);
    const arriving = motion && !replay.session && !selectedCrate && !selectedGroup &&
      transfer?.event.line === change.line && transfer.event.number === change.number &&
      transfer.event.station === change.station;
    return (
      <button
        key={key}
        data-arriving={arriving || undefined}
        type="button"
        className={`${styles.crate} ${styles[`builder${change.builder}`]}`}
        data-crate={change.number}
        data-station={`${change.line}/${change.station}`}
        data-line={change.line}
        title={change.title}
        aria-label={`${names[change.builder]}, change ${change.number}, ${change.title}${change.testflight_build ? `, TestFlight build ${change.testflight_build}` : ""}${change.sent_back ? ", sent back" : ""}${change.unsure ? ", unsure" : ""}`}
        aria-pressed={selectedCrate === key}
        onClick={() => selectCrate(key)}
      >
        <span className={styles.crateLetter}>
          {change.builder === "Other" ? "O" : change.builder}
        </span>
        <span className={styles.crateNumber}>#{change.number}</span>
        {change.sent_back && (
          <span className={styles.sentBack} title="Sent back" aria-hidden="true" />
        )}
        {change.unsure && change.station !== "Ship" && (
          <span className={styles.unsureMark} aria-hidden="true">
            ?
          </span>
        )}
      </button>
    );
  }

  return (
    <article
      className={styles.factory}
      data-factory="true"
      data-reader={behind ? "behind" : "current"}
      data-motion={motion ? "running" : "paused"}
    >
      <header className={styles.heading}>
        <div className={styles.workshopIdle} aria-hidden="true">
          <Cog className={styles.idleGear} size={27} />
          <Wind className={styles.idleSteam} size={22} />
        </div>
        <div className={styles.titlePlate}>
          <h1>The Factory</h1>
          <p className={styles.intro}>
            Every change, from its first lines to going live.
          </p>
        </div>
        <InjurySign reading={data.injury_clock} through={data.generated_at} />
        <div className={styles.updated}>
          <span className={styles.statusDot} aria-hidden="true" />
          <div>
            <strong>
              {behind ? "Not updating" : readAt ? `Read at ${time(readAt)} PT` : "Read from GitHub"}
            </strong>
            <span title="Published snapshot">
              {new Intl.DateTimeFormat("en-US", {
                timeZone: "America/Los_Angeles",
                month: "short",
                day: "numeric",
              }).format(new Date(data.generated_at))}
              {(behind || !readAt || time(readAt) !== time(data.generated_at)) &&
                ` at ${time(data.generated_at)} PT`}
            </span>
          </div>
        </div>
      </header>

      <StackLight verdict={verdict} hold={holds[0]} now={now} />
      {replay.session && (
        <div className={styles.replayBar}>
            <button type="button" onClick={replay.close}>Close replay</button>
            <strong>
              {replay.clock && `${time(replay.clock)} PT`}
              {replay.finished ? " · Replay finished" : replay.playing ? ` · ${eventText(replay.playing.event)}` : ""}
            </strong>
            {replay.finished && (
              <button type="button" onClick={replay.restart}>
                Play again
              </button>
            )}
        </div>
      )}
      {replay.session && (
        <details className={styles.eventLog} open={reducedMotion || behind || undefined}>
          <summary className={styles.summary}>
            <ChevronRight size={13} aria-hidden="true" />
            Recorded transfers
          </summary>
          <p>
            Transfers this browser saw today, starting at {time(replay.session.journal.events[0].at)} PT.
            The replay may cover part of the day.
          </p>
          <ol>
            {replay.session.journal.events.map((event) => (
              <li key={event.id}>{time(event.at)} PT · {event.line} · {eventText(event)}</li>
            ))}
          </ol>
        </details>
      )}
      {behind && (
        <div className={styles.readerWarning} role="status">
          <Pause size={20} aria-hidden="true" />
          <p>
            Last read {time(data.generated_at)} PT,{" "}
            {duration((Date.parse(now) - Date.parse(data.generated_at)) / 1000)}{" "}
            ago. Updates have stopped.
          </p>
        </div>
      )}

      <aside className={styles.foremanNote} aria-label="Foreman’s note">
        <ClipboardCheck size={21} aria-hidden="true" />
        <div>
          <strong>Foreman’s note</strong>
          <p>
            <b>{verdict.text}</b>
            {floorNote && ` ${floorNote}`}
          </p>
          {(floorNote || Object.keys(notes?.stations ?? {}).length > 0) && <small>{noteCredit}</small>}
        </div>
      </aside>

      <section className={styles.floorCard} aria-labelledby="floor-heading">
        <div className={styles.sectionHeading}>
          <h2 id="floor-heading">The floor</h2>
          {currentSpeaker && currentSpeech && (
            <div className={styles.floorSpeech} id="factory-speech" data-floor-speech={currentSpeaker.key}>
              <Worker identity={currentSpeaker.key} state={currentSpeech.mood} />
              <p className={styles.speechBubble} data-source={currentSpeech.source}>
                <strong>{currentSpeaker.name}</strong>{" "}{currentSpeech.text}
              </p>
            </div>
          )}
          <div className={styles.floorActions}>
            <span className={styles.tapHint}>
              Tap a crate or worker <ArrowDown size={14} />
            </span>
            {!replay.session && (
              journal?.events.length ? (
                <button
                  type="button"
                  className={styles.replayButton}
                  onClick={() => replay.open(journal)}
                >
                  Replay today
                </button>
              ) : (
                <span className={styles.tapHint}>
                  {journal ? "No transfers seen in this browser today" : "Today’s replay is missing"}
                </span>
              )
            )}
          </div>
        </div>
        {holds.length > 1 && (
          <div className={styles.stopNotices} role="status">
            {holds.slice(1).map((stop) => notice(stop, now))}
          </div>
        )}
        {waits.length > 0 && (
          <details className={styles.waitNotices}>
            <summary className={styles.summary}>
              <ChevronRight size={13} aria-hidden="true" />
              {waits.length} floor {waits.length === 1 ? "alert" : "alerts"}
            </summary>
            <div className={styles.stopNotices}>
              {waits.map((stop) => notice(stop, now))}
            </div>
          </details>
        )}
        <div className={styles.scrollHint}>
          <ArrowRight size={14} /> Scroll across to follow the line
        </div>
        <div
          className={styles.floorScroll}
          tabIndex={0}
          role="region"
          aria-label="Factory floor, scroll horizontally to see all six stations"
        >
          <div className={styles.floorGrid}>
            <div className={styles.stationHeadings}>
              <span />
              {stations.map((station) => {
                const Icon = stationIcons[station];
                return (
                  <div key={station}>
                    <Icon className={styles.stationIcon} size={14} aria-hidden="true" />
                    <strong>{stationNames[station]}</strong>
                    <span>{engineering[station]}</span>
                    {station === "Review" && (
                      <div className={styles.inspectionDesk}>
                        <Worker station="Review" identity="Fable" state="idle" />
                        <span>Foreman</span>
                      </div>
                    )}
                    {notes?.stations[stationNames[station]] && (
                      <div className={styles.stationNote}>
                        <p>{notes.stations[stationNames[station]]}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {lines.map((line) => {
              const LineIcon = lineIcons[line];
              const lineShipped = shipped.filter((c) => c.line === line);
              const last = lineShipped.reduce<string | null>(
                (value, c) =>
                  !value || c.live_at! > value ? c.live_at : value,
                null,
              );
              return (
                <div
                  key={line}
                  className={styles.lineRow}
                  data-factory-row={line}
                >
                  <div className={styles.lineName}>
                    <LineIcon size={20} strokeWidth={1.6} />
                    <strong>{line}</strong>
                    {line === "Apps" && data.signals.testflight_post && (
                      <span className={styles.buildPlate}>
                        TestFlight build {data.signals.testflight_post.build}
                      </span>
                    )}
                  </div>
                  <div className={styles.machines}>
                    {stations.map((station) => {
                      const Icon = stationIcons[station];
                      const changes = bayCrates(visible, line, station);
                      const crates = changes.slice(0, bayLimit);
                      const more = changes.length - crates.length;
                      const check = station === "Test" ? changes.find((c) => c.check_progress) : undefined;
                      const inspection = station === "Review" ? changes.find((c) => c.approvals) : undefined;
                      const bayAlerts = verdict.bays.filter(
                        (alert) => alert.station === station &&
                          (alert.line === null || alert.line === line),
                      );
                      const bayAlert = bayAlerts.find((alert) => alert.level === "red") ?? bayAlerts[0];
                      const activity = bayActivity(
                        data,
                        line,
                        station,
                        now,
                        changes,
                      );
                      const crew = crewActivity(data, now, changes);
                      const worker = crew.change ?? changes[0];
                      const workerId = worker?.builder === "Other" ? undefined : worker?.builder;
                      const workerState = (workerId && data.speech?.[workerId]?.mood) ||
                        (changes.length ? crew.pose : activity.worker);
                      const dockBuilders =
                        station === "Merge line"
                          ? [
                              ...new Set(
                                changes
                                  .map((c) => c.builder)
                                  .filter(
                                    (builder): builder is NamedBuilder =>
                                      builder !== "Other",
                                  ),
                              ),
                            ]
                          : [];
                      const lastPost =
                        station === "Live"
                          ? changes.reduce<string | null>(
                              (at, c) =>
                                c.live_posted_at &&
                                (!at || c.live_posted_at > at)
                                  ? c.live_posted_at
                                  : at,
                              null,
                            )
                          : null;
                      const backup = bayAlerts.some((alert) => alert.crowded);
                      const jammed = activeJams.some(
                        (j) =>
                          j.station === station &&
                          (j.kind === "crowd" ? backup : j.line === line),
                      );
                      return (
                        <div
                          key={station}
                          className={`${styles.machine} ${station === "Live" ? styles.liveMachine : ""} ${backup ? styles.backedUp : ""} ${jammed ? styles.jammed : ""}`}
                          data-line={line}
                          data-bay={station}
                          data-alert={bayAlert?.level}
                          data-waiting={changes.length}
                          data-worker-state={workerState}
                        >
                          {station === "Merge line" && line === "Server" && (
                            <div
                              className={styles.dockSign}
                              data-held={Boolean(serverHold)}
                            >
                              <i
                                className={styles.dockLight}
                                aria-hidden="true"
                              />
                              <strong>{serverHold ? "HOLD" : "Server dock"}</strong>
                            </div>
                          )}
                          <div className={styles.machineTop}>
                            {dockBuilders.length ? (
                              <ul
                                className={styles.dockCrew}
                                aria-label={`${line} loading dock queue: ${dockBuilders.map((builder) => names[builder]).join(", ")}`}
                              >
                                {dockBuilders.slice(0, 3).map((builder) => (
                                  <li key={builder} title={names[builder]}>
                                    {workerFigure(builder, station, "waiting")}
                                  </li>
                                ))}
                                {dockBuilders.length > 3 && (
                                  <li>+{dockBuilders.length - 3}</li>
                                )}
                              </ul>
                            ) : workerId ? (
                              workerFigure(workerId, station, workerState)
                            ) : (
                              <Icon
                                className={styles.stationObject}
                                size={22}
                                strokeWidth={1.4}
                                aria-hidden="true"
                              />
                            )}
                            <span
                              className={styles.baySignals}
                              title={bayAlert?.text}
                            >
                              <span
                                className={styles.lamp}
                                data-state={
                                  bayAlert?.level === "red"
                                    ? "stopped"
                                    : bayAlert?.level === "amber"
                                      ? backup ? "crowded" : "caution"
                                      : !behind && activity.flowing
                                        ? "flowing"
                                        : "idle"
                                }
                                aria-hidden="true"
                              />
                              <span>
                                {behind
                                  ? "Paused"
                                  : station === "Ship" &&
                                      changes.some((c) => c.merge_announced_at)
                                    ? "Merge announced"
                                    : bayAlert && !activity.stop
                                      ? "Needs attention"
                                      : activity.label}
                              </span>
                            </span>
                          </div>
                          {workerId && !dockBuilders.length && (
                            <span className={styles.bayWorkerName}>{names[workerId]}</span>
                          )}
                          <div className={styles.crates}>
                            {crates.map(crate)}
                            {!changes.length && (
                              <span className={styles.emptySlot}>
                                {station === "Live" ? (
                                  <Check size={19} />
                                ) : (
                                  <span />
                                )}
                              </span>
                            )}
                          </div>
                          <div className={styles.machineCaption}>
                            <div className={styles.machineSummary}>
                              {station === "Live" ? (
                                <strong className={styles.liveTally}>
                                  {changes.length} shipped
                                </strong>
                              ) : (
                                <span>{changes.length ? `${changes.length} here` : "Clear"}</span>
                              )}
                              {more > 0 && (
                                <button
                                  type="button"
                                  className={styles.more}
                                  aria-haspopup="dialog"
                                  onClick={() => selectGroup({ line, station })}
                                >
                                  +{more} more
                                </button>
                              )}
                            </div>
                            {station === "Live" && last && (
                              <span title={lastPost ? `Live posted at ${time(lastPost)} PT` : undefined}>
                                Last {time(last)} PT
                              </span>
                            )}
                            {check?.check_progress && (
                              <span>#{check.number} · {check.check_progress.done} of {check.check_progress.total} checks</span>
                            )}
                            {inspection?.approvals?.bot && <span>Bot approved #{inspection.number}</span>}
                            {inspection?.approvals?.fable && <span>Fable cleared #{inspection.number}</span>}
                          </div>
                        </div>
                      );
                    })}
                    {reducedMotion === false && !behind && playing?.event.line === line && (
                      <EventScene key={playing.event.id} {...playing} />
                    )}
                    <div
                      className={styles.belts}
                      data-belts="true"
                      aria-hidden="true"
                    >
                      {stations.slice(0, -1).map((station, segment) => {
                        const moving = playing?.event.line === line && crossesSegment(playing.event, segment);
                        return (
                        <span
                          key={station}
                          className={styles.beltSegment}
                          data-flowing={
                            !behind && beltFlowing(data, line, segment, now)
                          }
                          data-moving={moving}
                        >
                          <i key={moving ? playing?.event.id : "still"} />
                          <ChevronRight size={14} />
                        </span>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <p className={styles.floorKey}>A crate is one change.</p>
        {(selected || group) && (
          <dialog
            className={styles.detail}
            aria-labelledby="factory-change-title"
            ref={detail}
            onCancel={closeDetail}
          >
            {selected ? (
              <div>
                {group && (
                  <button className={styles.backToList} type="button" onClick={() => selectCrate(null)}>
                    <ArrowLeft size={14} aria-hidden="true" /> Back to {group.title}
                  </button>
                )}
                <span className={styles.detailMeta}>
                  Change #{selected.number} · {names[selected.builder]} ·{" "}
                  {selected.line} /{" "}
                  {selected.held_for_108
                    ? "Held for 1.0.8"
                    : selected.parked
                      ? "Parked"
                      : selected.bot_update
                        ? "Bot updates"
                        : stationNames[selected.station]}
                </span>
                <h3 id="factory-change-title">{selected.title}</h3>
                {selectedLines.length > 1 && (
                  <p>
                    This change appears on the{" "}
                    {new Intl.ListFormat("en-US").format(selectedLines)} lines.
                  </p>
                )}
                {selected.sent_back && <p>Sent back by Fable.</p>}
                {selected.testflight_build && (
                  <p>TestFlight build {selected.testflight_build} was posted.</p>
                )}
                {selected.check_progress && (
                  <p>{selected.check_progress.done} of {selected.check_progress.total} checks finished.</p>
                )}
                {selected.approvals?.bot && <p>Bot approved.</p>}
                {selected.approvals?.fable && <p>Fable cleared.</p>}
                {selected.unsure && <p>Unsure. {selected.reasons.join(" ")}</p>}
                <a
                  href={`https://github.com/alexander-bain/bainluck/pull/${selected.number}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  See the change on GitHub <ArrowRight size={15} />
                </a>
              </div>
            ) : group && (
              <div>
                <h3 id="factory-change-title">{group.title}</h3>
                {group.note && <p>{group.note}</p>}
                {group.changes.length ? (
                  <div className={styles.groupCrates}>{group.changes.map(crate)}</div>
                ) : <p>No changes here.</p>}
              </div>
            )}
            <button
              type="button"
              aria-label="Close change details"
              onClick={closeDetail}
            >
              <X size={18} />
            </button>
          </dialog>
        )}
        <section className={styles.shelf} aria-label="Side shelves">
          {shelfKeys.map((shelf) => (
            <button
              key={shelf}
              type="button"
              aria-haspopup="dialog"
              onClick={() => selectGroup({ shelf })}
            >
              {shelves[shelf].title} <strong>{shelves[shelf].changes.length}</strong>
            </button>
          ))}
        </section>
      </section>

      <div className={styles.records}>
        <details className={styles.panel} aria-labelledby="jams-heading">
          <summary className={styles.summary}>
            <ChevronRight size={14} aria-hidden="true" />
            <h2 id="jams-heading">Where it jammed today</h2>
            <span className={styles.sectionNote}>{jams.length}</span>
          </summary>
          {jams.length ? (
            <div className={styles.jams}>
              {jams.map((jam) => (
                <div key={`${jam.key}-${jam.started_at}`} className={styles.jam}>
                  <span
                    className={`${styles.jamDot} ${!jam.ended_at ? styles.pulse : ""}`}
                  />
                  <div>
                    <strong>{jamTitle(jam)}</strong>
                    <span>
                      {time(jam.started_at)} PT{" "}
                      {jam.ended_at ? `to ${time(jam.ended_at)} PT` : "to now"} ·{" "}
                      {duration(
                        (Date.parse(jam.ended_at || now) -
                          Date.parse(jam.started_at)) /
                          1000,
                      )}
                    </span>
                  </div>
                  <span
                    className={jam.ended_at ? styles.cleared : styles.ongoing}
                  >
                    {jam.ended_at ? (
                      <>
                        <CheckCheck size={14} /> Cleared
                      </>
                    ) : (
                      "Ongoing"
                    )}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className={styles.noJams}>
              <CircleCheck size={22} />
              <div>
                <strong>No jams recorded today</strong>
                <span>
                  Recording began{" "}
                  {new Intl.DateTimeFormat("en-US", {
                    timeZone: "America/Los_Angeles",
                    month: "short",
                    day: "numeric",
                  }).format(new Date(data.observed_since))}{" "}
                  at {time(data.observed_since)} PT.
                </span>
              </div>
            </div>
          )}
        </details>

        <details className={styles.panel} aria-labelledby="builders-heading">
          <summary className={styles.summary}>
            <ChevronRight size={14} aria-hidden="true" />
            <h2 id="builders-heading">Time clock</h2>
            <span className={styles.sectionNote}>
              {clockedIn.size} clocked in
            </span>
          </summary>
          <div className={styles.builders}>
            {builders.map((builder) => {
              const crew = crewActivity(
                data,
                now,
                visible.filter((c) => c.builder === builder.key),
              );
              const voice = data.speech?.[builder.key];
              const mood = voice?.mood ?? crew.pose;
              const pose = {
                carrying: "Carrying",
                waiting: "Waiting",
                working: "Working",
                celebrating: "Celebrating",
                stuck: "Stuck",
                asleep: "Asleep",
              }[mood];
              return (
                <div
                  key={builder.key}
                  className={styles.builderCard}
                  data-crew={builder.key}
                  data-pose={mood}
                >
                  <Worker identity={builder.key} state={mood} />
                  <strong className={styles.nameTag}>{builder.name}</strong>
                  {builder.key === "W" && <small>Spare hand</small>}
                  <span>{clockedIn.has(builder.key) ? "Clocked in" : "Quiet for 15 minutes"}</span>
                  <span>{pose}{!voice && crew.change && ` #${crew.change.number}`}</span>
                  <p className={styles.crewSpeech} data-source={voice?.source}>
                    {voice?.text ?? "This lane’s speech is missing from this read."}
                  </p>
                </div>
              );
            })}
          </div>
        </details>

        <details className={styles.panel} aria-labelledby="last-step-heading">
          <summary className={styles.summary}>
            <ChevronRight size={14} aria-hidden="true" />
            <h2 id="last-step-heading">Engineer clipboard</h2>
          </summary>
          <dl className={styles.clipboard}>
            <div>
              <dt>Median from Bench to Live</dt>
              <dd>{engineeringRecords.benchMedian === null ? "No complete trips timed yet" : duration(engineeringRecords.benchMedian)}</dd>
            </div>
            <div>
              <dt>Longest known wait</dt>
              <dd>{engineeringRecords.longest
                ? `#${engineeringRecords.longest.change.number} · ${duration(engineeringRecords.longest.seconds)}`
                : "No wait time recorded"}</dd>
            </div>
            <div>
              <dt>Merges today</dt>
              <dd>{mergesToday.size}</dd>
            </div>
          </dl>
          <p className={styles.timingNote}>Bench timing starts when the change is first seen there.</p>
          <div className={styles.delivery}>
            {lines.map((line) => {
              const delivered = shipped.filter(
                (c) =>
                  c.line === line &&
                  c.merged_at &&
                  c.live_at &&
                  Date.parse(c.merged_at) >= Date.parse(data.observed_since),
              );
              const timings = delivered.map(
                (c) => (Date.parse(c.live_at!) - Date.parse(c.merged_at!)) / 1000,
              );
              const elapsed = median(timings);
              const upperBound = delivered.some((c) => c.timing === "observed");
              const last = [...delivered].sort((a, b) =>
                b.live_at!.localeCompare(a.live_at!),
              )[0];
              return (
                <div key={line}>
                  <span className={styles.deliveryLabel}>
                    {line} <ArrowRight size={15} /> Live
                  </span>
                  <strong>
                    {elapsed !== null
                      ? `${upperBound ? "Within " : ""}${duration(elapsed)}`
                      : "Not timed yet"}
                  </strong>
                  <span>
                    {timings.length
                      ? `Median of ${timings.length} ${timings.length === 1 ? "change" : "changes"}`
                      : "Timing starts with an observed merge"}
                  </span>
                  {last && (
                    <span className={styles.lastDelivery}>
                      Last at {time(last.live_at!)} PT · #{last.number}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <p className={styles.timingNote}>
            Only changes merged since recording began are timed. “Within” uses the
            first confirmed sighting.
          </p>
        </details>
        <details className={styles.eventLog}>
          <summary className={styles.summary}>
            <ChevronRight size={13} aria-hidden="true" />
            {livePlaying && !replay.session ? `${livePlaying.event.line} · ${eventText(livePlaying.event)}` : "Events from the last read"}
            {data.events && <span className={styles.sectionNote}>{data.events.length}</span>}
          </summary>
          {data.events?.length ? (
            <ol>
              {data.events.map((event) => (
                <li key={event.id}>{time(event.at)} PT · {event.line} · {eventText(event)}</li>
              ))}
            </ol>
          ) : <p>{data.events ? "No new events in this read." : "Event details are missing from this read."}</p>}
        </details>
      </div>
      <footer className={styles.notes}>
        <p>
          The floor is re-read after CI finishes and when master changes, with a
          five-minute timer as a backstop. This page refreshes once a minute
          while visible. All times are Pacific.
        </p>
        {data.coverage.map((note) => (
          <p key={note}>{note}</p>
        ))}
        <details>
          <summary>About this floor</summary>
          <p>
            {data.model_usage?.day === today
              ? `${data.model_usage.calls} of 200 model calls made today.`
              : "Today’s model call count is missing."}
          </p>
          <p>
            Open changes include drafts. A change stays at the earlier station
            whenever the evidence is incomplete.
          </p>
          <p>
            Jam times begin and end with observed updates. A quiet page can cross
            a waiting-time threshold between updates.
          </p>
        </details>
      </footer>
    </article>
  );
}
