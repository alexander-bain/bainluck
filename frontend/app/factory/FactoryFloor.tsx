"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Box,
  Check,
  CheckCheck,
  ChevronRight,
  CircleCheck,
  ClipboardCheck,
  Clock3,
  Hammer,
  ListChecks,
  PackageOpen,
  PackageCheck,
  Pause,
  Server,
  Smartphone,
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
import {
  stations,
  stationNames,
  time,
  duration,
  readerBehind,
  stopText,
  bayActivity,
  crewActivity,
  machineText,
  beltFlowing,
  recentTransfers,
  shownStops,
  knownOrigin,
  onActiveFloor,
} from "./activity";

const lines: Line[] = ["Server", "Website", "Apps"];
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
const descriptions = [
  "Taking shape",
  "Checking it works",
  "Fable’s inspection desk",
  "Ready for a turn",
  "On its way",
  "In your hands",
];
const bayLimit = 2;
const shelfKeys = ["held", "parked", "bot", "side"] as const;
type Shelf = (typeof shelfKeys)[number];
type CrateGroup =
  | { line: Line; station: Station }
  | { shelf: Shelf };

function pacificDay(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

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

function notice(stop: Stop, now: string) {
  return (
    <p key={`${stop.kind}-${stop.line}`} data-level={stop.level}>
      <span aria-hidden="true">{stop.level === "red" ? "■" : "▲"}</span>{" "}
      {stopText(stop, now)}
      {stop.test && <code className={styles.stopOrigin}>{stop.test}</code>}
      {stop.machines && (
        <small className={styles.stopOrigin}>{machineText(stop.machines)}</small>
      )}
      {stop.level === "red" && stop.source && (
        <small className={styles.stopOrigin}>
          <a
            href={`https://github.com/alexander-bain/bainluck/issues/12779#issuecomment-${stop.source.id}`}
          >
            NOW · stuck
          </a>
          {` · ${time(stop.since)} PT · ${stop.source.author}`}
        </small>
      )}
    </p>
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
  readFailed = false,
  renderedAt,
}: {
  data: FactoryData | null;
  lastGoodAt: string | null;
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
  const [knownGoodAt, setKnownGoodAt] = useState(lastGoodAt);
  const [lastShown, setLastShown] = useState(snapshot);
  // Keep the open page intact if a refresh lands on a server with an empty cache.
  const data =
    snapshot &&
    (!lastShown ||
      Date.parse(snapshot.generated_at) >= Date.parse(lastShown.generated_at))
      ? snapshot
      : lastShown;
  const floor = useRef<HTMLDivElement>(null);
  const oldPositions = useRef(
    new Map<string, { rect: DOMRect; station: Station }>(),
  );
  const detail = useRef<HTMLDialogElement>(null);
  const [tabVisible, setTabVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [shippingLines, setShippingLines] = useState<Line[]>([]);
  const [departingLines, setDepartingLines] = useState<Line[]>([]);
  const lastPublication = useRef<string | null>(null);
  const lastRefresh = useRef(Date.parse(renderedAt));
  const behind = data !== null && (readFailed || readerBehind(data, now));
  const motion = !behind && tabVisible && !reducedMotion;

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
        if (Date.now() - lastRefresh.current >= 60_000) {
          lastRefresh.current = Date.now();
          router.refresh();
        }
      }
    };
    preferenceChanged();
    refresh();
    preference.addEventListener("change", preferenceChanged);
    document.addEventListener("visibilitychange", refresh);
    const interval = window.setInterval(refresh, 60_000);
    return () => {
      preference.removeEventListener("change", preferenceChanged);
      document.removeEventListener("visibilitychange", refresh);
      window.clearInterval(interval);
    };
  }, [router]);

  useLayoutEffect(() => {
    const nextPositions = new Map<string, { rect: DOMRect; station: Station }>();
    floor.current
      ?.querySelectorAll<HTMLButtonElement>("[data-crate]")
      .forEach((button) => {
        const number = Number(button.dataset.crate);
        const line = button.dataset.line as Line;
        const id = crateKey(line, number);
        const rect = button.getBoundingClientRect();
        const station = button.dataset.station!.split("/")[1] as Station;
        const previous = oldPositions.current.get(id);
        button.classList.remove(styles.travelling);
        if (
          previous &&
          previous.station !== station &&
          motion &&
          data &&
          recentTransfers(data, now).some(
            (t) => t.number === number && t.line === line && t.to === station,
          )
        ) {
          const from = stations.indexOf(previous.station);
          const to = stations.indexOf(station);
          const stopped = shownStops(data).some(
            (stop) =>
              stop.level === "red" &&
              (stop.line === null || stop.line === line) &&
              stations.indexOf(stop.station) >= Math.min(from, to) &&
              stations.indexOf(stop.station) <= Math.max(from, to),
          );
          if (!stopped) {
            const row = button.closest("[data-factory-row]");
            const belt = row
              ?.querySelector("[data-belts]")
              ?.getBoundingClientRect();
            button.style.setProperty(
              "--travel-x",
              `${previous.rect.left - rect.left}px`,
            );
            button.style.setProperty(
              "--travel-y",
              `${previous.rect.top - rect.top}px`,
            );
            button.style.setProperty(
              "--belt-y",
              `${(belt?.top ?? rect.bottom) - rect.top}px`,
            );
            void button.offsetWidth;
            button.classList.add(styles.travelling);
          }
        }
        nextPositions.set(id, { rect, station });
      });
    oldPositions.current = nextPositions;
  }, [data, motion, now]);

  useEffect(() => {
    if (!data || lastPublication.current === data.generated_at) return;
    const previous = lastPublication.current;
    lastPublication.current = data.generated_at;
    if (!previous) return;
    const since = Date.parse(previous);
    const departures = data.changes.filter(
      (c) =>
        c.station === "Live" &&
        c.live_posted_at &&
        Date.parse(c.live_post_observed_at ?? c.live_posted_at) > since,
    );
    const arrivals = recentTransfers(data, data.generated_at).filter(
      (move) =>
        move.to === "Live" && Date.parse(move.observed_at ?? move.at) > since,
    );
    setShippingLines([
      ...new Set([...departures, ...arrivals].map((c) => c.line)),
    ]);
    setDepartingLines([...new Set(departures.map((c) => c.line))]);
  }, [data]);

  useEffect(() => {
    if (!shippingLines.length && !departingLines.length) return;
    const timer = window.setTimeout(() => {
      setShippingLines([]);
      setDepartingLines([]);
    }, 2600);
    return () => window.clearTimeout(timer);
  }, [shippingLines, departingLines]);

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
        <section className={styles.unavailable} role="status">
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

  const today = pacificDay(now);
  const shipped = data.changes.filter(
    (c) => c.station === "Live" && c.live_at && pacificDay(c.live_at) === today,
  );
  const shippedCount = uniqueChanges(shipped).length;
  const onFloor = data.changes.filter(onActiveFloor);
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
  const stops = shownStops(data);
  const holds = stops.filter((stop) => stop.level === "red");
  const waits = stops.filter((stop) => stop.level === "amber");
  const serverHold = holds.find((stop) => stop.line === "Server");
  const notes =
    data.notes?.snapshot_at === data.generated_at ? data.notes : null;
  const noteCredit =
    notes?.source === "model"
      ? "Written by a model from the counts on this page"
      : "From the counts on this page";
  const visible = [...onFloor, ...shipped];
  const stationCounts = stations.slice(0, -1).map((station) => ({
    station,
    count: uniqueChanges(onFloor.filter((c) => c.station === station)).length,
  }));
  const busiest = stationCounts.reduce((best, current) =>
    current.count > best.count ? current : best,
  );
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

  function crate(change: Change) {
    const key = crateKey(change.line, change.number);
    return (
      <button
        key={key}
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
        <div>
          <h1>The Factory</h1>
          <p className={styles.intro}>
            Every change, from its first lines to going live.
          </p>
        </div>
        <div className={styles.updated}>
          <span className={styles.statusDot} aria-hidden="true" />
          <div>
            <strong>{behind ? "Not updating" : "Read from GitHub"}</strong>
            <span>
              {new Intl.DateTimeFormat("en-US", {
                timeZone: "America/Los_Angeles",
                month: "short",
                day: "numeric",
              }).format(new Date(data.generated_at))}{" "}
              at {time(data.generated_at)} PT
            </span>
          </div>
        </div>
      </header>

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

      {notes && (
        <aside className={styles.foremanNote} aria-label="Foreman’s note">
          <ClipboardCheck size={21} aria-hidden="true" />
          <div>
            <strong>Foreman’s note</strong>
            <p>{notes.floor}</p>
            <small>{noteCredit}</small>
          </div>
        </aside>
      )}

      <section className={styles.numbers} aria-label="The factory at a glance">
        <div>
          <span className={styles.numberLabel}>
            <PackageCheck size={17} /> Shipped today
          </span>
          <strong
            key={shippedCount}
            className={`${styles.shippedNumber} ${shippingLines.length ? styles.numberTick : ""}`}
          >
            {shippedCount}
          </strong>
          <span>Changes in your hands</span>
        </div>
        <div>
          <span className={styles.numberLabel}>
            <Box size={17} /> On the floor now
          </span>
          <strong>{uniqueChanges(onFloor).length}</strong>
          <span>Making their way to live</span>
        </div>
        <div>
          <span className={styles.numberLabel}>
            <Clock3 size={17} /> Busiest station ·{" "}
            {stationNames[busiest.station]}
          </span>
          <strong
            className={busiest.count >= 10 ? styles.amberNumber : undefined}
          >
            {busiest.count}
          </strong>
          <span>
            {busiest.count ? "Changes at this station" : "The floor is clear"}
          </span>
        </div>
      </section>

      <section className={styles.floorCard} aria-labelledby="floor-heading">
        <div className={styles.sectionHeading}>
          <h2 id="floor-heading">The floor</h2>
          <span className={styles.tapHint}>
            Tap a crate to see the change <ArrowDown size={14} />
          </span>
        </div>
        {holds.length > 0 && (
          <div className={styles.stopNotices} role="status">
            {holds.map((stop) => notice(stop, now))}
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
          ref={floor}
        >
          <div className={styles.floorGrid}>
            <div className={styles.stationHeadings}>
              <span />
              {stations.map((station, index) => (
                <div key={station}>
                  <strong>{stationNames[station]}</strong>
                  <span>{descriptions[index]}</span>
                  {station === "Review" && (
                    <div className={styles.inspectionDesk}>
                      <Worker station="Review" identity="Fable" state="idle" />
                      <span>Foreman</span>
                    </div>
                  )}
                  {notes?.stations[stationNames[station]] && (
                    <div className={styles.stationNote}>
                      <p>{notes.stations[stationNames[station]]}</p>
                      <small>{noteCredit}</small>
                    </div>
                  )}
                </div>
              ))}
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
                    <span>{lineShipped.length} shipped</span>
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
                      const activity = bayActivity(
                        data,
                        line,
                        station,
                        now,
                        changes,
                      );
                      const crew = crewActivity(data, now, changes);
                      const worker = crew.change ?? changes[0];
                      const workerState = changes.length
                        ? crew.pose
                        : activity.worker;
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
                      const backup = station !== "Live" && changes.length >= 10;
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
                          data-waiting={changes.length}
                          data-worker-state={workerState}
                          data-flashing={
                            station === "Live" && shippingLines.includes(line)
                          }
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
                                    <Worker identity={builder} state="waiting" />
                                  </li>
                                ))}
                                {dockBuilders.length > 3 && (
                                  <li>+{dockBuilders.length - 3}</li>
                                )}
                              </ul>
                            ) : worker && worker.builder !== "Other" ? (
                              <div className={styles.bayWorker}>
                                <Worker
                                  station={station}
                                  identity={worker.builder}
                                  state={workerState}
                                />
                                <span>{names[worker.builder]}</span>
                              </div>
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
                              title={activity.stop ? stopText(activity.stop, now) : undefined}
                            >
                              <span
                                className={styles.lamp}
                                data-state={
                                  activity.stop?.level === "red"
                                    ? "stopped"
                                    : !behind && activity.flowing
                                      ? "flowing"
                                      : backup
                                        ? "crowded"
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
                                    : activity.label}
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
                          {station === "Live" &&
                            departingLines.includes(line) && (
                              <svg
                                className={styles.dispatch}
                                viewBox="0 0 48 30"
                                aria-hidden="true"
                              >
                                <path d="M3 5h26v16H3zM29 12h10l6 6v3H29z" />
                                <circle cx="12" cy="23" r="4" />
                                <circle cx="36" cy="23" r="4" />
                              </svg>
                            )}
                          <div className={styles.machineCaption}>
                            <div className={styles.machineSummary}>
                              <span>
                                {station === "Live"
                                  ? `${changes.length} today`
                                  : changes.length
                                    ? `${changes.length} here`
                                    : "Clear"}
                              </span>
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
                          </div>
                        </div>
                      );
                    })}
                    <div
                      className={styles.belts}
                      data-belts="true"
                      aria-hidden="true"
                    >
                      {stations.slice(0, -1).map((station, segment) => (
                        <span
                          key={station}
                          className={styles.beltSegment}
                          data-flowing={
                            !behind && beltFlowing(data, line, segment, now)
                          }
                        >
                          <i />
                          <ChevronRight size={14} />
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className={styles.floorKey}>
          <span>
            <i className={styles.keyCrate} /> A change can ship on more than one line
          </span>
          <span>
            <i className={styles.keyAmber} /> Ten or more waiting
          </span>
          <span>
            <b>?</b> Evidence is incomplete
          </span>
        </div>
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
                {selected.sent_back && <p>Sent back by Fable.</p>}
                {selected.testflight_build && (
                  <p>TestFlight build {selected.testflight_build} was posted.</p>
                )}
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
            <h2 id="builders-heading">Who is on the floor</h2>
            <span className={styles.sectionNote}>
              {uniqueChanges(data.changes.filter((c) => !c.merged_at)).length} open
            </span>
          </summary>
          <div className={styles.builders}>
            {builders.map((builder) => {
              const crew = crewActivity(
                data,
                now,
                visible.filter((c) => c.builder === builder.key),
              );
              const pose = {
                carrying: "Carrying",
                waiting: "Waiting with",
                working: "Working on",
                asleep: "Asleep",
              }[crew.pose];
              return (
                <div
                  key={builder.key}
                  className={styles.builderCard}
                  data-crew={builder.key}
                  data-pose={crew.pose}
                >
                  <Worker identity={builder.key} state={crew.pose} />
                  <strong>{builder.name}</strong>
                  {builder.key === "W" && <small>Spare hand</small>}
                  <span>
                    {pose}
                    {crew.change && ` #${crew.change.number}`}
                  </span>
                </div>
              );
            })}
          </div>
        </details>

        <details className={styles.panel} aria-labelledby="last-step-heading">
          <summary className={styles.summary}>
            <ChevronRight size={14} aria-hidden="true" />
            <h2 id="last-step-heading">How long the last step takes</h2>
          </summary>
          <div className={styles.delivery}>
            {lines.map((line) => {
              const delivered = shipped.filter(
                (c) =>
                  c.line === line &&
                  c.merged_at &&
                  c.live_at &&
                  Date.parse(c.merged_at) >= Date.parse(data.observed_since),
              );
              const timings = delivered
                .map(
                  (c) =>
                    (Date.parse(c.live_at!) - Date.parse(c.merged_at!)) / 1000,
                )
                .sort((a, b) => a - b);
              const middle = Math.floor(timings.length / 2);
              const median =
                timings.length % 2
                  ? timings[middle]
                  : (timings[middle - 1] + timings[middle]) / 2;
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
                    {timings.length
                      ? `${upperBound ? "Within " : ""}${duration(median)}`
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
