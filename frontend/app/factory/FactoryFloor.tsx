"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  CircleCheck,
  ClipboardCheck,
  Flag,
  Hammer,
  ListChecks,
  PackageOpen,
  Pause,
  Search,
  Server,
  Smartphone,
  Trophy,
  Truck,
  X,
  Monitor,
} from "lucide-react";
import { usePageTracking } from "@/hooks/usePageTracking";
import { useScrollDepth } from "@/hooks/useScrollDepth";
import { useEngagementTime } from "@/hooks/useEngagementTime";
import type { Builder, Change, FactoryData, Jam, Line, Station, Stop } from "./types";
import styles from "./factory.module.css";
import Worker from "./Worker";
import EventScene from "./EventScene";
import BuilderNamePanel from "./BuilderNamePanel";
import CrewCard from "./CrewCard";
import DailyPictures from "./DailyPictures";
import { crewAction, crewPose, placeCrew, type FloorCrew } from "./crewMotion";
import {
  builders, crewIdentities, holdAuthorName, useBuilderNames,
  type CrewIdentity, type FactoryNames, type NamedBuilder,
} from "./builderNames";
import CrateJourney from "./CrateJourney";
import ChecksQueue from "./ChecksQueue";
import FactoryMascot, { MascotMove, mascotAction } from "./FactoryMascot";
import InjurySign from "./InjurySign";
import { explainedCheck, hasFailedCheck, lessonForFloor, testDefinition } from "./lesson";
import { builderOfDay, clipboard, median } from "./signs";
import { useDayReplay } from "./useDayReplay";
import { useFactoryDisplay } from "./useFactoryDisplay";
import type { FactoryDisplayReading } from "./displayReading";
import type { GitHubActivity } from "./githubActivity";
import { validateSnapshot } from "./data";
import { useReplayJournal } from "./replayJournal";
import { remainingEvents, transfersSince } from "./liveTransfers";
import { crossesSegment, eventText, WALK_PER_STATION_MS, useEventPlayer } from "./playback";
import { factoryTabTitle, floorReadingState, floorVerdict, releaseStallText, type FloorVerdict } from "./verdict";
import {
  stations,
  stationNames,
  pacificDay,
  workshopLight,
  time,
  duration,
  stopText,
  stopWaitText,
  bayActivity,
  crewActivity,
  beltFlowing,
  shownStops,
  knownOrigin,
  onActiveFloor,
  recentLaneUpdate,
  recentlyActive,
} from "./activity";

const lines: Line[] = ["Server", "Website", "Apps"];
const SPEECH_INTERVAL_MS = 8_000;
const FOLLOWED_CRATES_KEY = "factory-followed-crates-v1";
const RELOAD_FLOOR_KEY = "factory-floor-before-reload";
const pacificPostingTime = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const lineIcons = { Server, Website: Monitor, Apps: Smartphone };
const stationIcons = {
  Write: Hammer,
  Test: ListChecks,
  Review: Search,
  "Merge line": PackageOpen,
  Ship: Truck,
  Live: BookOpen,
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
  | { shelf: Shelf }
  | { following: true };

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

function HoldOrigin({ stop, names }: { stop: Stop; names: FactoryNames }) {
  if (!stop.source) return null;
  return (
    <small className={styles.stopOrigin}>
      <a
        href={`https://github.com/alexander-bain/bainluck/issues/12779#issuecomment-${stop.source.id}`}
      >
        NOW · stuck
      </a>
      {` · ${time(stop.since)} PT · ${holdAuthorName(stop.source.author, names)}`}
    </small>
  );
}

function notice(stop: Stop, now: string, names: FactoryNames) {
  return (
    <p key={`${stop.kind}-${stop.line}`} data-level={stop.level}>
      <span aria-hidden="true">{stop.level === "red" ? "■" : "▲"}</span>{" "}
      {stopText(stop, now)}
      {stop.test && <code className={styles.stopOrigin}>{stop.test}</code>}
      {stop.kind === "hold" && <HoldOrigin stop={stop} names={names} />}
    </p>
  );
}

function StackLight({
  verdict,
  releaseWarning,
  hold,
  names,
  now,
  children,
}: {
  verdict: FloorVerdict;
  releaseWarning?: string;
  hold?: Stop;
  names: FactoryNames;
  now: string;
  children?: ReactNode;
}) {
  const waited = hold && stopWaitText(hold, now);
  return (
    <div
      className={styles.verdict}
      data-verdict={releaseWarning ? "amber" : verdict.level}
      data-level={hold && "red"}
      role="status"
    >
      <div className={styles.stackLight} aria-hidden="true">
        <i data-light="red" />
        <i data-light="amber" />
        <i data-light="green" />
      </div>
      <div>
        <strong data-release-stall={releaseWarning ? true : undefined}>{releaseWarning ?? verdict.text}</strong>
        {waited && <small className={styles.stopOrigin}>{waited}</small>}
        {hold && <HoldOrigin stop={hold} names={names} />}
      </div>
      {children}
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

export default function FactoryFloor(initial: {
  data: FactoryData | null;
  lastGoodAt: string | null;
  readAt?: string;
  readFailed?: boolean;
  buildCommit?: string | null;
  activity?: GitHubActivity;
  renderedAt: string;
}) {
  usePageTracking({ pageType: "home", pageTitle: "The Factory" });
  useScrollDepth({ pageType: "home" });
  useEngagementTime({ pageType: "home" });
  const [refresh, setRefresh] = useState<{ initialAt: string; reading: FactoryDisplayReading }>();
  const { data: snapshot, lastGoodAt, readAt, readFailed = false, activity } =
    refresh?.initialAt === initial.renderedAt ? refresh.reading : initial;
  const receiveReading = useCallback((reading: FactoryDisplayReading) => {
    setRefresh({ initialAt: initial.renderedAt, reading });
  }, [initial.renderedAt]);
  const [selectedCrate, selectCrate] = useState<string | null>(null);
  const [selectedGroup, selectGroup] = useState<CrateGroup | null>(null);
  const [selectedCrew, selectCrew] = useState<CrewIdentity | null>(null);
  const [followed, setFollowed] = useState<number[]>([]);
  const [speaker, setSpeaker] = useState<NamedBuilder>();
  const { names, ...nameEditor } = useBuilderNames();
  const [knownGoodAt, setKnownGoodAt] = useState(readAt ?? lastGoodAt);
  const [lastShown, setLastShown] = useState({ data: snapshot, readAt });
  // Keep the open page intact if a refresh lands on a server with an empty cache.
  const incomingTime = snapshot ? Date.parse(snapshot.generated_at) : -Infinity;
  const shownTime = lastShown.data ? Date.parse(lastShown.data.generated_at) : -Infinity;
  const incomingReadTime = readAt ? Date.parse(readAt) : -Infinity;
  const shownReadTime = lastShown.readAt ? Date.parse(lastShown.readAt) : -Infinity;
  const useIncoming = snapshot && (incomingTime > shownTime ||
    (incomingTime === shownTime && incomingReadTime >= shownReadTime));
  const { data, readAt: shownReadAt } = useIncoming ? { data: snapshot, readAt } : lastShown;
  const detail = useRef<HTMLDialogElement>(null);
  const rememberFloor = useCallback(() => {
    try {
      if (data) sessionStorage.setItem(RELOAD_FLOOR_KEY, JSON.stringify({ data, readAt: shownReadAt }));
    } catch {
      // The previous read time is still kept separately in local storage.
    }
  }, [data, shownReadAt]);
  const { now, tabVisible, reducedMotion } = useFactoryDisplay(
    initial.renderedAt, initial.buildCommit ?? null, rememberFloor, receiveReading,
  );
  const readingState = data && floorReadingState(data, readFailed, now, activity);
  const behind = readingState !== null && readingState !== "current";
  const pauseBays = readingState === "failed" || readingState === "last-known";
  const motion = !behind && tabVisible && reducedMotion === false;
  const verdict = floorVerdict(data, readFailed, now, activity);
  const releaseStall = data ? releaseStallText(data, now, activity) : undefined;
  const tabTitle = factoryTabTitle(verdict);
  const today = pacificDay(now);
  const light = workshopLight(now);
  const journal = useReplayJournal(data, today);
  const replay = useDayReplay(motion);
  const speech = data?.speech;
  const { laneUpdates, laneCheckIns, laneLines } = useMemo(() => {
    const updates: NonNullable<FactoryData["lane_updates"]> = {};
    const checkIns: NonNullable<FactoryData["crew_posts"]> = {};
    const lines: Partial<Record<NamedBuilder, { text: string; source: "lane" | "check-in" }>> = {};
    const lanesOnFloor = new Set(data?.changes.filter(onActiveFloor).map(change => change.builder));
    for (const lane of builders) {
      const post = data?.crew_posts?.[lane];
      const checkIn = post && recentLaneUpdate(post.at, now) ? post : undefined;
      const update = data?.lane_updates?.[lane];
      if (checkIn) checkIns[lane] = checkIn;
      if (update && recentLaneUpdate(update.at, now) &&
          (!checkIn || Date.parse(update.at) >= Date.parse(checkIn.at))) {
        updates[lane] = update;
        if (!lanesOnFloor.has(lane)) lines[lane] = { text: update.text, source: "lane" };
      } else if (checkIn && !lanesOnFloor.has(lane)) {
        lines[lane] = { text: `Posted on NOW at ${time(checkIn.at)} PT.`, source: "check-in" };
      }
    }
    return { laneUpdates: updates, laneCheckIns: checkIns, laneLines: lines };
  }, [data, now]);
  const speakers = useMemo(() => builders.filter(key => laneLines[key] || speech?.[key]), [laneLines, speech]);
  const currentSpeaker = speakers.find(key => key === speaker) ??
    speakers.find(key => laneLines[key]?.source === "lane") ??
    speakers.find(key => laneLines[key]) ?? speakers[0];
  const currentSpeech = currentSpeaker && (laneLines[currentSpeaker] ?? speech?.[currentSpeaker]);
  const firstTransferRead = useRef(data?.generated_at);
  firstTransferRead.current ??= data?.generated_at;
  const firstRead = firstTransferRead.current;
  const moves = useMemo(() => transfersSince(data, firstRead), [data, firstRead]);
  const tape = useMemo(() => remainingEvents(data?.events, moves), [data?.events, moves]);
  const transfer = useEventPlayer(
    data?.generated_at, moves, motion && !replay.session,
    WALK_PER_STATION_MS * Math.max(1, moves.length),
  );
  const livePlaying = useEventPlayer(
    data?.generated_at, tape, motion && !replay.session && !transfer,
  );
  const playing = replay.session ? replay.playing : transfer ?? livePlaying;
  const sceneVisible = motion && !selectedCrate && !selectedGroup && !selectedCrew;
  const sceneActor = sceneVisible && playing ? crewAction(playing.event)?.identity : undefined;
  const mascotMove = sceneVisible && playing ? mascotAction(playing.event) : undefined;
  const quiet = Boolean(data && !behind && !data.changes.some(change =>
    onActiveFloor(change) && (change.checks_running || recentlyActive(change.last_activity, now))) &&
    !Object.values(data.crew_posts ?? {}).some(post => recentlyActive(post.at, now)) &&
    !data.events?.some(event => recentlyActive(event.observed_at, now)) &&
    !data.transitions?.some(move => recentlyActive(move.observed_at ?? move.at, now)));
  const autoReplayDay = useRef<string>();
  const { session, finished, open: openReplay, close: closeReplay } = replay;

  useEffect(() => {
    if (session?.automatic && (!quiet || finished)) {
      closeReplay();
      return;
    }
    if (session || playing || !sceneVisible || !quiet || !data?.day_replay ||
        !journal?.events.length || autoReplayDay.current === today) return;
    autoReplayDay.current = today;
    openReplay(journal, true);
  }, [session, playing, sceneVisible, quiet, data?.day_replay, journal, today, finished, openReplay, closeReplay]);

  useEffect(() => {
    document.title = tabTitle;
  }, [tabTitle]);

  useEffect(() => {
    if (!sceneVisible || !currentSpeaker || speakers.length < 2 || replay.session) return;
    const next = speakers[(speakers.indexOf(currentSpeaker) + 1) % speakers.length];
    const timer = window.setTimeout(() => setSpeaker(next), SPEECH_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [sceneVisible, currentSpeaker, speakers, replay.session]);

  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(FOLLOWED_CRATES_KEY) ?? "[]");
      if (Array.isArray(saved)) setFollowed([...new Set(saved.filter(
        (value): value is number => typeof value === "number" && Number.isSafeInteger(value) && value > 0,
      ))]);
    } catch {
      // Following still works for this visit if storage is unavailable.
    }
  }, []);

  useEffect(() => {
    if (data) {
      setLastShown(previous =>
        previous.data === data && previous.readAt === shownReadAt
          ? previous
          : { data, readAt: shownReadAt },
      );
    }
  }, [data, shownReadAt]);

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(RELOAD_FLOOR_KEY);
      sessionStorage.removeItem(RELOAD_FLOOR_KEY);
      if (snapshot || !saved) return;
      const copy: { data: FactoryData; readAt?: string } = JSON.parse(saved);
      setLastShown({
        data: validateSnapshot(copy.data),
        readAt: typeof copy.readAt === "string" && Number.isFinite(Date.parse(copy.readAt))
          ? copy.readAt : undefined,
      });
    } catch {
      // The unreadable state handles a copy that cannot be recovered.
    }
  }, [snapshot]);

  useEffect(() => {
    try {
      const timestamp =
        shownReadAt ||
        data?.generated_at ||
        lastGoodAt ||
        localStorage.getItem("factory-last-good-at");
      if (timestamp && Number.isFinite(Date.parse(timestamp))) {
        setKnownGoodAt(timestamp);
        if (data) localStorage.setItem("factory-last-good-at", timestamp);
      }
    } catch {
      setKnownGoodAt(shownReadAt ?? lastGoodAt);
    }
  }, [data, lastGoodAt, shownReadAt]);

  useEffect(() => {
    if (
      (selectedCrate !== null || selectedGroup || selectedCrew) &&
      detail.current &&
      !detail.current.open
    ) {
      detail.current.showModal();
    }
  }, [selectedCrate, selectedGroup, selectedCrew]);

  if (!data) {
    return (
      <article
        className={styles.factory}
        data-factory="true"
        data-workshop-light={light}
        data-motion="paused"
      >
        <header className={styles.heading}>
          <div className={styles.titlePlate}>
            <h1>The Factory</h1>
          </div>
        </header>
        <StackLight verdict={verdict} names={names} now={now}>
          <FactoryMascot level={verdict.level} pose="asleep" />
        </StackLight>
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
  const lastRead = shownReadAt ?? data.generated_at;
  const publishedAge = duration((Date.parse(now) - Date.parse(data.generated_at)) / 1000);
  const readLabel = {
    failed: "Not updating",
    quiet: "Quiet floor",
    waiting: "Waiting for a machine",
    "last-known": "Last published floor",
    current: shownReadAt ? `Read at ${time(shownReadAt)} PT` : "Read from GitHub",
  }[readingState ?? "current"];
  const canRankDeliveries = !behind && pacificDay(data.generated_at) === today && data.coverage.length === 0;
  const dayLeader = canRankDeliveries ? builderOfDay(shipped) : null;
  const dayLeaders = dayLeader ? new Intl.ListFormat("en-US").format(
    builders.filter(key => dayLeader.builders.includes(key)).map(key => names[key]),
  ) : null;
  const onFloor = data.changes.filter(onActiveFloor);
  const lesson = lessonForFloor(data, now);
  const checkLesson = explainedCheck(data);
  const recordTime = behind ? data.generated_at : now;
  const clockedIn = new Set(
    data.changes
      .filter((c) => c.builder !== "Other" && (onActiveFloor(c) || c.station === "Live") &&
        recentlyActive(c.last_activity, recordTime))
      .map((c) => c.builder),
  );
  for (const lane of builders) {
    const post = data.crew_posts?.[lane];
    if (post && recentlyActive(post.at, recordTime)) clockedIn.add(lane);
  }
  const foremanPose = crewPose(data, "Fable", recordTime, []);
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
  const stops = !behind || readingState === "quiet" ? shownStops(data) : [];
  const holds = stops.filter((stop) => stop.kind === "hold");
  const waits = stops.filter((stop) => stop.kind !== "hold");
  const explained = new Set(stops.map((stop) => `${stop.line}/${stop.station}`));
  const otherAlerts = [...new Set(verdict.bays
    .filter((alert) => alert.level === "amber" && alert.text !== verdict.text &&
      (alert.crowded || !explained.has(`${alert.line}/${alert.station}`)))
    .map((alert) => alert.text))];
  const floorAlertCount = waits.length + otherAlerts.length;
  const serverHold = holds.find((stop) => stop.line === "Server");
  const headlineRelease = holds.length === 0 ? releaseStall : undefined;
  const testFlightPost = data.signals.testflight_post;
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
  const floorCrew = placeCrew(data, recordTime, visible);
  const resting = floorCrew.filter(person => !person.position);
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
  const selectedCopies = selected ? data.changes.filter((change) => change.number === selected.number) : [];
  const selectedLines = lines.filter((line) => selectedCopies.some((change) => change.line === line));
  const followingGroup = selectedGroup && "following" in selectedGroup;
  const followedChanges = followingGroup ? uniqueChanges(data.changes.filter((change) => followed.includes(change.number))) : [];
  const outsideRead = followingGroup ? followed.filter((number) => !followedChanges.some((change) => change.number === number)) : [];
  const group = selectedGroup && (
    "shelf" in selectedGroup
      ? shelves[selectedGroup.shelf]
      : "following" in selectedGroup
      ? { title: "Followed crates", changes: followedChanges, note: undefined }
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
    selectCrew(null);
  }

  function toggleFollowed(number: number) {
    const next = followed.includes(number) ? followed.filter((value) => value !== number) : [...followed, number];
    setFollowed(next);
    try {
      localStorage.setItem(FOLLOWED_CRATES_KEY, JSON.stringify(next));
    } catch {
      // The flag remains visible for this visit.
    }
  }

  function openCrewCard(id: CrewIdentity) {
    if (id !== "Fable" && (laneLines[id] || speech?.[id])) setSpeaker(id);
    selectCrew(id);
  }

  function workerFigure({ identity: id, pose }: FloorCrew) {
    const away = sceneActor === id;
    return (
      <button
        key={id}
        type="button"
        className={`${styles.voiceButton} ${styles.floorWorker}`}
        aria-label={`Meet ${names[id]}`}
        title={names[id]}
        aria-haspopup="dialog"
        aria-hidden={away || undefined}
        data-away={away || undefined}
        tabIndex={away ? -1 : undefined}
        onClick={() => openCrewCard(id)}
      >
        <Worker identity={id} state={pose} onFloor />
      </button>
    );
  }

  function crewCard(id: CrewIdentity, titleId?: string) {
    const lane = visible.filter(change => change.builder === id);
    const status = id === "Fable" ? foremanPose : crewPose(data!, id, recordTime, lane);
    return (
      <CrewCard
        key={id}
        identity={id}
        name={names[id]}
        pose={status.pose}
        clockedIn={id === "Fable" ? foremanPose.pose === "working" : clockedIn.has(id)}
        number={status.change?.number}
        post={id === "Fable" ? undefined : laneCheckIns[id]}
        update={id === "Fable" ? undefined : laneUpdates[id]}
        voice={id === "Fable" ? undefined : data?.speech?.[id]}
        habits={data?.crew_week?.builders[id]}
        now={recordTime}
        titleId={titleId}
      />
    );
  }

  function crate(change: Change) {
    const key = crateKey(change.line, change.number);
    const arriving = sceneVisible && !replay.session &&
      transfer?.event.line === change.line && transfer.event.number === change.number &&
      transfer.event.station === change.station;
    return (
      <button
        key={key}
        data-arriving={arriving || undefined}
        data-followed={followed.includes(change.number) || undefined}
        type="button"
        className={`${styles.crate} ${styles[`builder${change.builder}`]}`}
        data-crate={change.number}
        data-station={`${change.line}/${change.station}`}
        data-line={change.line}
        title={change.title}
        aria-label={`${names[change.builder]}, change ${change.number}, ${change.title}${change.testflight_build ? `, TestFlight build ${change.testflight_build}` : ""}${change.sent_back ? ", sent back" : ""}${change.unsure ? ", unsure" : ""}${followed.includes(change.number) ? ", followed" : ""}`}
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
      data-workshop-light={light}
      data-reader={pauseBays ? "behind" : "current"}
      data-reading-state={readingState}
      data-motion={motion ? "running" : "paused"}
    >
      <header className={styles.heading}>
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
            <strong>{readLabel}</strong>
            <span>
              {behind && "Published "}
              {new Intl.DateTimeFormat("en-US", {
                timeZone: "America/Los_Angeles",
                month: "short",
                day: "numeric",
              }).format(new Date(data.generated_at))}
              {(behind || !shownReadAt || time(shownReadAt) !== time(data.generated_at)) &&
                ` at ${time(data.generated_at)} PT`}
            </span>
          </div>
        </div>
      </header>

      <div className={styles.statusBand}>
        <StackLight verdict={verdict} releaseWarning={headlineRelease} hold={holds[0]} names={names} now={now}>
          {!mascotMove && (
            <FactoryMascot
              level={headlineRelease ? "amber" : verdict.level}
              pose={clockedIn.size ? "standing" : "asleep"}
              moving={sceneVisible && clockedIn.size > 0 && verdict.level !== "red"}
            />
          )}
        </StackLight>
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
      </div>
      {replay.session && (
        <div className={styles.replayBar}>
            <button type="button" onClick={replay.close}>Close replay</button>
            <strong>
              {replay.clock && `${time(replay.clock)} PT`}
              {replay.finished ? " · Replay finished" : replay.playing ? ` · ${eventText(replay.playing.event, names.Fable)}` : ""}
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
            Recorded station moves today, starting at {time(replay.session.journal.events[0].at)} PT.
            The replay may cover part of the day.
          </p>
          <ol>
            {replay.session.journal.events.map((event) => (
              <li key={event.id}>{time(event.at)} PT · {event.line} · {eventText(event, names.Fable)}</li>
            ))}
          </ol>
        </details>
      )}
      {(readingState === "failed" || readFailed) && (
        <div className={styles.readerWarning} role="status">
          <Pause size={20} aria-hidden="true" />
          <p>
            Last read {time(lastRead)} PT,{" "}
            {duration((Date.parse(now) - Date.parse(lastRead)) / 1000)}{" "}
            ago. {readingState === "failed" ? "Updates have stopped." : "The latest read failed."}
          </p>
        </div>
      )}
      {readingState === "quiet" && (
        <p className={styles.sectionNote}>Last published {publishedAge} ago. No changes landed and no shared tests finished since then.</p>
      )}
      {releaseStall && !headlineRelease && (
        <div className={styles.readerWarning} role="status" data-release-stall>
          <Truck size={20} aria-hidden="true" />
          <p>{releaseStall}</p>
        </div>
      )}
      <section className={styles.floorCard} aria-labelledby="floor-heading">
        <div className={styles.sectionHeading}>
          <h2 id="floor-heading">The floor</h2>
          <ChecksQueue queue={data.signals.checks_queue} />
          {currentSpeaker && currentSpeech && (
            <div className={styles.floorSpeech} id="factory-speech" data-floor-speech={currentSpeaker}>
              <p className={styles.speechBubble} data-source={currentSpeech.source}>
                <button type="button" onClick={() => openCrewCard(currentSpeaker)} aria-haspopup="dialog">
                  <strong>{names[currentSpeaker]}</strong>
                </button>{" "}{currentSpeech.text}
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
            {holds.slice(1).map((stop) => notice(stop, now, names))}
          </div>
        )}
        {floorAlertCount > 0 && (
          <details className={styles.waitNotices}>
            <summary className={styles.summary}>
              <ChevronRight size={13} aria-hidden="true" />
              {floorAlertCount} floor {floorAlertCount === 1 ? "alert" : "alerts"}
            </summary>
            <div className={styles.stopNotices}>
              {waits.map((stop) => notice(stop, now, names))}
              {otherAlerts.map((alert) => <p key={alert} data-level="amber">{alert}</p>)}
            </div>
          </details>
        )}
        <div className={styles.floorScroll} tabIndex={0} role="region" aria-label="Factory floor">
          <div className={styles.floorGrid}>
            <div className={styles.stationHeadings}>
              <span />
              {stations.map((station) => {
                const Icon = stationIcons[station];
                return (
                  <div key={station}>
                    <div className={styles.stationSign}>
                      <Icon size={21} aria-hidden="true" />
                      <strong>{stationNames[station]}</strong>
                      <span>{engineering[station]}</span>
                    </div>
                    {station === "Review" && (
                      <div className={styles.inspectionDesk}>
                        <span>{nameEditor.custom.Fable?.trim() ? names.Fable : "Foreman"}</span>
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
            {lines.map((line, lineIndex) => {
              const LineIcon = lineIcons[line];
              const restHere = resting.slice(lineIndex * 3, (lineIndex + 1) * 3);
              const crewHere = floorCrew.filter(person => person.position?.line === line);
              const eventHere = sceneVisible && playing?.event.line === line ? playing : null;
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
                  <div className={styles.lineRail}>
                    <div className={styles.lineName}>
                      <LineIcon size={20} strokeWidth={1.6} />
                      <strong>{line}</strong>
                      {line === "Apps" && testFlightPost && Number.isFinite(Date.parse(testFlightPost.at)) && (
                        <span className={styles.buildPlate} title="Reported from TestFlight and matched to a successful build on GitHub">
                          TestFlight build {testFlightPost.build}
                          <time dateTime={testFlightPost.at}>
                            Posted {pacificPostingTime.format(new Date(testFlightPost.at))} PT
                          </time>
                        </span>
                      )}
                    </div>
                    {restHere.length > 0 && (
                      <div className={styles.crewRest} data-rest-bench>
                        <span>Rest bench</span>
                        <div>{restHere.map(workerFigure)}</div>
                      </div>
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
                      const workerState = workerId
                        ? crewPose(data, workerId, recordTime, changes.filter(change => change.builder === workerId)).pose
                        : activity.worker;
                      const backup = bayAlerts.some((alert) => alert.crowded);
                      const jammed = activeJams.some(
                        (j) =>
                          j.station === station &&
                          (j.kind === "crowd" ? backup : j.line === line),
                      );
                      const bayState = pauseBays ? "Paused" :
                        station === "Ship" && changes.some(c => c.merge_announced_at) ? "Merge announced" :
                        bayAlert && !activity.stop ? "Needs attention" : activity.label;
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
                          <div className={styles.compactStation}>
                            <Icon size={16} aria-hidden="true" />
                            <div>
                              <strong>{stationNames[station]}</strong>
                              <span>{engineering[station]}</span>
                              {lineIndex === 0 && station === "Review" && (
                                <span>{nameEditor.custom.Fable?.trim() ? names.Fable : "Foreman"}</span>
                              )}
                              {lineIndex === 0 && notes?.stations[stationNames[station]] && (
                                <p>{notes.stations[stationNames[station]]}</p>
                              )}
                            </div>
                          </div>
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
                            {workerId ? (
                              <span className={styles.bayWorkerName}>{names[workerId]}</span>
                            ) : (
                              <Icon
                                className={styles.stationObject}
                                size={22}
                                strokeWidth={1.4}
                                aria-hidden="true"
                              />
                            )}
                            <span className={styles.baySignals}>
                              <span
                                className={styles.lamp}
                                data-state={
                                  bayAlert?.level === "red"
                                    ? "stopped"
                                    : bayAlert?.level === "amber"
                                      ? backup ? "crowded" : "caution"
                                      : !pauseBays && activity.flowing
                                        ? "flowing"
                                        : "idle"
                                }
                                aria-hidden="true"
                              />
                              <span title={bayState}>
                                {bayState === "Needs attention" ? "Attention" :
                                  bayState === "Checks running" ? "Testing" : bayState}
                              </span>
                            </span>
                          </div>
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
                              <span>Last {time(last)} PT</span>
                            )}
                            {check?.check_progress && (
                              <span>#{check.number} · {check.check_progress.done} of {check.check_progress.total} checks</span>
                            )}
                            {inspection?.approvals?.bot && <span>Bot approved #{inspection.number}</span>}
                            {inspection?.approvals?.fable && <span>{names.Fable} cleared #{inspection.number}</span>}
                          </div>
                        </div>
                      );
                    })}
                    <div className={styles.crewStrip} data-crew-strip={line} data-occupied={Boolean(crewHere.length || eventHere)}>
                      <div className={styles.crewStops}>
                        {stations.map(station => (
                          <div key={station} className={styles.crewStop} data-crew-station={station}>
                            {crewHere.filter(person => person.position?.station === station).map(workerFigure)}
                          </div>
                        ))}
                      </div>
                      {eventHere && (
                        <EventScene key={eventHere.event.id} {...eventHere} foreman={names.Fable} />
                      )}
                      {mascotMove && eventHere && (
                        <MascotMove key={`mascot-${eventHere.event.id}`} {...eventHere} pose={mascotMove} alongside={Boolean(sceneActor)} />
                      )}
                    </div>
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
        <div className={styles.floorFooter}>
          <p className={styles.floorKey}>A crate is one change.</p>
          <aside className={styles.builderDay} aria-label="Builder of the day">
            <Trophy size={14} aria-hidden="true" />
            <div>
              <strong>Builder of the day</strong>{" "}
              {dayLeader ? (
                <span>{dayLeaders} · {dayLeader.count} {dayLeader.count === 1 ? "change" : "changes"} live{dayLeader.builders.length > 1 ? " each" : ""}</span>
              ) : (
                <span>{canRankDeliveries ? "No deliveries by a named lane yet" : "Delivery records are incomplete"}</span>
              )}
            </div>
          </aside>
        </div>
        {(selected || group || selectedCrew) && (
          <dialog
            className={styles.detail}
            aria-labelledby={selectedCrew ? "factory-crew-title" : "factory-change-title"}
            ref={detail}
            onCancel={closeDetail}
          >
            {selectedCrew ? crewCard(selectedCrew, "factory-crew-title") : selected ? (
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
                <button
                  type="button"
                  className={styles.followAction}
                  aria-pressed={followed.includes(selected.number)}
                  onClick={() => toggleFollowed(selected.number)}
                >
                  <Flag size={15} aria-hidden="true" />
                  {followed.includes(selected.number) ? "Stop following" : "Follow this crate"}
                </button>
                {selectedLines.length > 1 && (
                  <p>
                    This change appears on the{" "}
                    {new Intl.ListFormat("en-US").format(selectedLines)} lines.
                  </p>
                )}
                {selected.sent_back && <p>Sent back by {names.Fable}.</p>}
                {selected.testflight_build && (
                  <p>TestFlight build {selected.testflight_build} was posted.</p>
                )}
                {selected.live_posted_at && <p>Live posted at {time(selected.live_posted_at)} PT.</p>}
                {selected.check_progress && (
                  <p>{selected.check_progress.done} of {selected.check_progress.total} checks finished.</p>
                )}
                {hasFailedCheck(selected) && (
                  <p>{testDefinition} A check flagged this change before it could go live.</p>
                )}
                {selected.approvals?.bot && <p>Bot approved.</p>}
                {selected.approvals?.fable && <p>{names.Fable} cleared.</p>}
                {selected.unsure && <p>Unsure. {selected.reasons.join(" ")}</p>}
                <CrateJourney changes={selectedCopies} through={data.generated_at} />
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
                ) : outsideRead.length === 0 && <p>No changes here.</p>}
                {outsideRead.length > 0 && (
                  <ul className={styles.outsideRead}>
                    {outsideRead.map((number) => (
                      <li key={number}>
                        <span>#{number} is outside the latest read.</span>
                        <button type="button" onClick={() => toggleFollowed(number)}>Stop following #{number}</button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <button
              type="button"
              aria-label={selectedCrew ? "Close crew card" : "Close change details"}
              onClick={closeDetail}
            >
              <X size={18} />
            </button>
          </dialog>
        )}
      </section>

      <aside className={styles.wordLesson} aria-label="Word of the day" data-factory-lesson>
        <p><strong>Word of the day</strong> <dfn>{lesson.word}</dfn> {lesson.definition}</p>
        <span>{lesson.count}</span>
        {checkLesson && <p className={styles.checkLesson} data-check-lesson>{testDefinition} {checkLesson}</p>}
      </aside>
      <div className={styles.records}>
        <div className={styles.shelfGroup}>
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
          {followed.length > 0 && (
            <button type="button" className={styles.followedCrates} aria-haspopup="dialog" onClick={() => selectGroup({ following: true })}>
              <Flag size={14} aria-hidden="true" /> Followed crates <strong>{followed.length}</strong>
            </button>
          )}
        </div>
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
          <BuilderNamePanel {...nameEditor} />
          {data.crew_week && (
            <p className={styles.crewRecordNote}>Weekly tracking started {pacificPostingTime.format(
              new Date(data.crew_week.since),
            )} PT. Busiest hours use recorded commits, deliveries and looks.</p>
          )}
          <div className={styles.builders}>
            {crewIdentities.map(id => crewCard(id))}
          </div>
        </details>

        <DailyPictures pictures={data.pictures} artist={names.F} />

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
            {livePlaying && !replay.session ? `${livePlaying.event.line} · ${eventText(livePlaying.event, names.Fable)}` : "Events from the last read"}
            {data.events && <span className={styles.sectionNote}>{data.events.length}</span>}
          </summary>
          {data.events?.length ? (
            <ol>
              {data.events.map((event) => (
                <li key={event.id}>{time(event.at)} PT · {event.line} · {eventText(event, names.Fable)}</li>
              ))}
            </ol>
          ) : <p>{data.events ? "No new events in this read." : "Event details are missing from this read."}</p>}
        </details>
      </div>
      <footer className={styles.notes}>
        <p>
          GitHub re-reads the floor after shared tests finish and when the main
          branch changes. Its timer can run between changes. This page checks for
          a new floor once a minute while visible. All times are Pacific.
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
          <p>The TestFlight number comes from a build report matched to a successful build on the main branch.</p>
        </details>
      </footer>
    </article>
  );
}
