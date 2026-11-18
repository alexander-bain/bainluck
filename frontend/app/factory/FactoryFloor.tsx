"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowDown,
  ArrowRight,
  Box,
  Check,
  CheckCheck,
  ChevronRight,
  CircleCheck,
  Clock3,
  PackageCheck,
  Pause,
  Server,
  Smartphone,
  X,
  Monitor,
} from "lucide-react";
import { usePageTracking } from "@/hooks/usePageTracking";
import { useScrollDepth } from "@/hooks/useScrollDepth";
import { useEngagementTime } from "@/hooks/useEngagementTime";
import type { Builder, Change, FactoryData, Jam, Line } from "./types";
import styles from "./factory.module.css";
import Worker from "./Worker";
import {
  stations,
  time,
  duration,
  readerBehind,
  stopText,
  bayActivity,
  beltFlowing,
  recentTransfers,
} from "./activity";

const lines: Line[] = ["Server", "Website", "Apps"];
const builders: { key: Builder; name: string }[] = [
  { key: "S", name: "Speed" },
  { key: "B", name: "Builder B" },
  { key: "C", name: "Builder C" },
  { key: "D", name: "Atlas" },
  { key: "E", name: "Builder E" },
  { key: "F", name: "Builder F" },
  { key: "Other", name: "Earlier work" },
];
const lineIcons = { Server, Website: Monitor, Apps: Smartphone };
const descriptions = [
  "Taking shape",
  "Checking it works",
  "A second look",
  "Ready for a turn",
  "On its way",
  "In your hands",
];

function pacificDay(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

function jamTitle(jam: Jam) {
  if (jam.kind === "crowd") return `${jam.station} held ten or more changes`;
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
  const [selectedNumber, selectNumber] = useState<number | null>(null);
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
    new Map<string, { rect: DOMRect; station: string }>(),
  );
  const detail = useRef<HTMLDialogElement>(null);
  const [tabVisible, setTabVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [shippingLines, setShippingLines] = useState<Line[]>([]);
  const lastRefresh = useRef(Date.parse(renderedAt));
  const behind =
    data !== null &&
    (readFailed || data !== snapshot || readerBehind(data, now));
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
    if (selectedNumber !== null && detail.current && !detail.current.open) {
      detail.current.showModal();
    }
  }, [selectedNumber]);

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
    const nextPositions = new Map<string, { rect: DOMRect; station: string }>();
    const shipments = new Set<Line>();
    floor.current
      ?.querySelectorAll<HTMLButtonElement>("[data-crate]")
      .forEach((button) => {
        const id = button.dataset.crate!;
        const rect = button.getBoundingClientRect();
        const station = button.dataset.station!;
        const previous = oldPositions.current.get(id);
        button.classList.remove(styles.travelling);
        if (
          previous &&
          previous.station !== station &&
          motion &&
          data &&
          recentTransfers(data, now).some((t) => t.number === Number(id))
        ) {
          const line = button.dataset.line as Line;
          const from = stations.indexOf(
            previous.station.split("/")[1] as (typeof stations)[number],
          );
          const to = stations.indexOf(
            station.split("/")[1] as (typeof stations)[number],
          );
          const stopped = (data?.stops ?? []).some(
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
            if (to === stations.length - 1) shipments.add(line);
          }
        }
        nextPositions.set(id, { rect, station });
      });
    oldPositions.current = nextPositions;
    if (shipments.size) setShippingLines([...shipments]);
    const timer = window.setTimeout(() => setShippingLines([]), 3000);
    return () => window.clearTimeout(timer);
  }, [data, motion, now]);

  if (!data) {
    return (
      <article
        className={styles.factory}
        data-factory="true"
        data-motion="paused"
      >
        <header className={styles.heading}>
          <div>
            <p className={styles.eyebrow}>Bain Luck, in the making</p>
            <h1>The Factory</h1>
          </div>
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
  const open = data.changes.filter((c) => !c.merged_at);
  const onFloor = data.changes.filter(
    (c) => c.station !== "Live" && !c.side_track,
  );
  const sideTrack = data.changes.filter((c) => c.side_track);
  const visible = [...onFloor, ...shipped];
  const stationCounts = stations.slice(0, -1).map((station) => ({
    station,
    count: onFloor.filter((c) => c.station === station).length,
  }));
  const busiest = stationCounts.reduce((best, current) =>
    current.count > best.count ? current : best,
  );
  const jams = data.jams.filter(
    (jam) =>
      Date.parse(jam.qualifies_at) <= Date.parse(now) &&
      (!jam.ended_at || pacificDay(jam.ended_at) === today),
  );
  const activeJams = jams.filter((j) => !j.ended_at);
  const selected = data.changes.find((c) => c.number === selectedNumber);

  function choose(change: Change) {
    selectNumber(change.number);
  }

  function crate(change: Change) {
    return (
      <button
        key={change.number}
        type="button"
        className={`${styles.crate} ${styles[`builder${change.builder}`]}`}
        data-crate={change.number}
        data-station={`${change.line}/${change.station}`}
        data-line={change.line}
        aria-label={`${builders.find((b) => b.key === change.builder)?.name}, change ${change.number}, ${change.title}${change.unsure ? ", unsure" : ""}`}
        aria-pressed={selectedNumber === change.number}
        onClick={() => choose(change)}
      >
        <span className={styles.crateLetter}>
          {change.builder === "Other" ? "O" : change.builder}
        </span>
        <span className={styles.crateNumber}>#{change.number}</span>
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
          <p className={styles.eyebrow}>
            <Box size={15} aria-hidden="true" /> Bain Luck, in the making
          </p>
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

      <section className={styles.numbers} aria-label="The factory at a glance">
        <div>
          <span className={styles.numberLabel}>
            <PackageCheck size={17} /> Shipped today
          </span>
          <strong
            key={shipped.length}
            className={`${styles.shippedNumber} ${shippingLines.length ? styles.numberTick : ""}`}
          >
            {shipped.length}
          </strong>
          <span>Changes in your hands</span>
        </div>
        <div>
          <span className={styles.numberLabel}>
            <Box size={17} /> On the floor now
          </span>
          <strong>{onFloor.length}</strong>
          <span>Making their way to live</span>
        </div>
        <div>
          <span className={styles.numberLabel}>
            <Clock3 size={17} /> Waiting at {busiest.station}
          </span>
          <strong
            className={busiest.count >= 10 ? styles.amberNumber : undefined}
          >
            {busiest.count}
          </strong>
          <span>
            {busiest.count ? "The busiest station" : "The floor is clear"}
          </span>
        </div>
      </section>

      <section className={styles.floorCard} aria-labelledby="floor-heading">
        <div className={styles.sectionHeading}>
          <div>
            <h2 id="floor-heading">The floor</h2>
            <p>Three lines. One journey.</p>
          </div>
          <span className={styles.tapHint}>
            Tap a crate to see the change <ArrowDown size={14} />
          </span>
        </div>
        {!!data.stops?.length && (
          <div className={styles.stopNotices} role="status">
            {data.stops.map((stop) => (
              <p key={`${stop.kind}-${stop.line}`} data-level={stop.level}>
                <span aria-hidden="true">
                  {stop.level === "red" ? "■" : "▲"}
                </span>{" "}
                {stopText(stop, now)}
              </p>
            ))}
          </div>
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
                  <strong>{station}</strong>
                  <span>{descriptions[index]}</span>
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
                  </div>
                  <div className={styles.machines}>
                    {stations.map((station) => {
                      const changes = visible.filter(
                        (c) => c.line === line && c.station === station,
                      );
                      changes.sort((a, b) =>
                        (b.live_at ?? "").localeCompare(a.live_at ?? ""),
                      );
                      const crates =
                        station === "Live" ? changes.slice(0, 8) : changes;
                      const activity = bayActivity(
                        data,
                        line,
                        station,
                        now,
                        changes,
                      );
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
                          data-worker-state={activity.worker}
                        >
                          <div className={styles.machineTop}>
                            <Worker station={station} state={activity.worker} />
                            <span className={styles.baySignals}>
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
                              <span>{behind ? "Paused" : activity.label}</span>
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
                          {station === "Live" && changes.length > 8 && (
                            <span className={styles.earlierToday}>
                              +{changes.length - 8} earlier today
                            </span>
                          )}
                          {station === "Live" &&
                            shippingLines.includes(line) && (
                              <svg
                                className={styles.dispatch}
                                viewBox="0 0 48 30"
                                role="img"
                                aria-label="A change just shipped"
                              >
                                <path d="M3 5h26v16H3zM29 12h10l6 6v3H29z" />
                                <circle cx="12" cy="23" r="4" />
                                <circle cx="36" cy="23" r="4" />
                              </svg>
                            )}
                          {activity.stop && (
                            <span className={styles.bayReason}>
                              {stopText(activity.stop, now)}
                            </span>
                          )}
                          <div className={styles.machineCaption}>
                            {station === "Live" ? (
                              <>
                                {changes.length} today
                                {last && <span>Last at {time(last)} PT</span>}
                              </>
                            ) : changes.length ? (
                              `${changes.length} waiting`
                            ) : (
                              "Clear"
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
            <i className={styles.keyCrate} /> One crate = one change
          </span>
          <span>
            <i className={styles.keyAmber} /> Ten or more waiting
          </span>
          <span>
            <b>?</b> Evidence is incomplete
          </span>
        </div>
        {selected && (
          <dialog
            className={styles.detail}
            aria-labelledby="factory-change-title"
            ref={detail}
            onCancel={() => selectNumber(null)}
          >
            <div>
              <span className={styles.detailMeta}>
                Change #{selected.number} ·{" "}
                {builders.find((b) => b.key === selected.builder)?.name} ·{" "}
                {selected.line} / {selected.station}
              </span>
              <h3 id="factory-change-title">{selected.title}</h3>
              {selected.unsure && <p>Unsure. {selected.reasons.join(" ")}</p>}
              <a
                href={`https://github.com/alexander-bain/bainluck/pull/${selected.number}`}
                target="_blank"
                rel="noreferrer"
              >
                See the change on GitHub <ArrowRight size={15} />
              </a>
            </div>
            <button
              type="button"
              aria-label="Close change details"
              onClick={() => {
                detail.current?.close();
                selectNumber(null);
              }}
            >
              <X size={18} />
            </button>
          </dialog>
        )}
        <details className={styles.sideTrack}>
          <summary>
            <Pause size={15} /> Side track <span>{sideTrack.length}</span>
            <small>No activity for three days</small>
            <ChevronRight size={15} />
          </summary>
          <div className={styles.sideCrates}>
            {sideTrack.map(crate)}
            {!sideTrack.length && <p>No changes on the side track.</p>}
          </div>
        </details>
      </section>

      <section className={styles.panel} aria-labelledby="jams-heading">
        <div className={styles.sectionHeading}>
          <h2 id="jams-heading">Where it jammed today</h2>
          <span className={styles.sectionNote}>Pacific time</span>
        </div>
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
      </section>

      <section className={styles.panel} aria-labelledby="builders-heading">
        <div className={styles.sectionHeading}>
          <h2 id="builders-heading">Who is on the floor</h2>
          <span className={styles.sectionNote}>
            {open.length} open changes, including the side track
          </span>
        </div>
        <div className={styles.builders}>
          {builders.map((builder) => {
            const working = open.filter((c) => c.builder === builder.key);
            return (
              <div key={builder.key} className={styles.builderCard}>
                <span
                  className={`${styles.builderAvatar} ${styles[`builder${builder.key}`]}`}
                >
                  {builder.key === "Other" ? "O" : builder.key}
                </span>
                <strong>{builder.name}</strong>
                <span>
                  {working.length} {working.length === 1 ? "change" : "changes"}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section className={styles.panel} aria-labelledby="last-step-heading">
        <div className={styles.sectionHeading}>
          <div>
            <h2 id="last-step-heading">How long the last step takes</h2>
            <p>From merge to live, for today’s changes.</p>
          </div>
        </div>
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
      </section>
      <footer className={styles.notes}>
        <p>
          The floor is re-read after CI finishes and when master changes, with a
          five-minute timer as a backstop. This page refreshes once a minute
          while visible. All times are Pacific.
        </p>
        {data.coverage.map((note) => (
          <p key={note}>{note}</p>
        ))}
        <p>
          Open changes include drafts. A change stays at the earlier station
          whenever the evidence is incomplete.
        </p>
        <p>
          Jam times begin and end with observed updates. A quiet page can cross
          a waiting-time threshold between updates.
        </p>
      </footer>
    </article>
  );
}
