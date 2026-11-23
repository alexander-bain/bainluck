import { builderLanes, factoryEventKinds, factoryMoods, isBuilder, type Change, type ChecksQueue, type CrewHabits, type FactoryData, type FactoryPicture, type FloorEvent } from "./types";
import { pacificDay, recentLaneUpdate, stationNames, stations, transferId } from "./activity";

export const FACTORY_DATA_URL =
  "https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json";
export const FACTORY_PICTURE_BASE = FACTORY_DATA_URL.slice(0, FACTORY_DATA_URL.lastIndexOf("/") + 1);
const MAX_CACHE_AGE_MS = 2 * 60_000;

export interface FactoryRead {
  data: FactoryData | null;
  lastGoodAt: string | null;
  readAt?: string;
  readFailed: boolean;
}

interface VerifiedRead {
  data: FactoryData;
  checkedAt: number;
}

type LoadVerifiedRead = () => Promise<VerifiedRead>;

function isProgress(done?: number, total?: number) {
  return typeof done === "number" && typeof total === "number" &&
    Number.isSafeInteger(done) && Number.isSafeInteger(total) &&
    done >= 0 && total > 0 && done <= total;
}

function verifiedChecksQueue(queue?: ChecksQueue): ChecksQueue | undefined {
  if (!queue || !Number.isSafeInteger(queue.machines) || queue.machines <= 0) return;
  const isCount = (value: unknown) =>
    typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
  if (
    queue.unavailable ||
    ![queue.running, queue.waiting, queue.queued_without_jobs].every(isCount) ||
    (queue.longest_wait_minutes !== null &&
      (queue.waiting === 0 || !isCount(queue.longest_wait_minutes)))
  ) {
    return { machines: queue.machines, unavailable: true };
  }
  const { machines_busy: busy, ...reading } = queue;
  return isCount(busy) ? queue : reading;
}

function isEvent(event: FloorEvent) {
  return event && /^[a-f0-9]{20}$/.test(event.id) &&
    factoryEventKinds.includes(event.kind) &&
    Number.isSafeInteger(event.number) && event.number > 0 &&
    ["Server", "Website", "Apps"].includes(event.line) &&
    isBuilder(event.builder) &&
    stations.includes(event.station) &&
    (event.from === undefined
      ? event.kind !== "move" && event.kind !== "returned"
      : stations.includes(event.from)) &&
    Number.isFinite(Date.parse(event.at)) &&
    Number.isFinite(Date.parse(event.observed_at)) &&
    (event.kind !== "check" ||
      (isProgress(event.done, event.total) &&
        ["passed", "failed", "finished"].includes(event.outcome ?? "")));
}

function verifiedReplay(payload: FactoryData) {
  const replay = payload.day_replay;
  if (!replay || !Array.isArray(replay.events) ||
      !Number.isFinite(Date.parse(replay.through)) || Date.parse(replay.through) > Date.parse(payload.generated_at) ||
      replay.date !== pacificDay(replay.through) || replay.date !== pacificDay(payload.generated_at)) return;
  if (replay.events.every(event => event && (event.kind === "move" || event.kind === "returned") &&
      ["Server", "Website", "Apps"].includes(event.line) &&
      Number.isSafeInteger(event.number) && event.number > 0 &&
      (event.builder === undefined || isBuilder(event.builder)) &&
      event.from !== undefined && stations.includes(event.from) && stations.includes(event.station) &&
      event.from !== event.station &&
      Date.parse(event.at) <= Date.parse(event.observed_at) &&
      Date.parse(event.observed_at) <= Date.parse(replay.through) &&
      pacificDay(event.at) === replay.date && event.id === transferId(event))) return replay;
}

function validHabits(habits: CrewHabits, through: number) {
  return habits && Number.isSafeInteger(habits.changes) && habits.changes >= 0 &&
    Array.isArray(habits.stations) && habits.stations.length <= stations.length &&
    habits.stations.every(station => stations.includes(station)) &&
    Array.isArray(habits.hours) && habits.hours.length <= 24 &&
    habits.hours.every(hour => Number.isSafeInteger(hour) && hour >= 0 && hour < 24) &&
    (habits.longest === undefined || habits.longest && Number.isSafeInteger(habits.longest.number) &&
      habits.longest.number > 0 && Date.parse(habits.longest.since) <= through);
}

function verifiedCrew(payload: FactoryData) {
  const week = payload.crew_week;
  const through = Date.parse(payload.generated_at);
  if (!week?.builders || !(Date.parse(week.since) <= through)) return;
  const builders: NonNullable<FactoryData["crew_week"]>["builders"] = {};
  for (const member of [...builderLanes, "Fable"] as const) {
    const habits = week.builders[member];
    if (habits && validHabits(habits, through)) builders[member] = habits;
  }
  if (Object.keys(builders).length) return { since: week.since, builders };
}

function verifiedCrewPosts(payload: FactoryData) {
  const posts: NonNullable<FactoryData["crew_posts"]> = {};
  for (const lane of builderLanes) {
    const post = payload.crew_posts?.[lane];
    if (typeof post?.at !== "string" || !recentLaneUpdate(post.at, payload.generated_at)) continue;
    const { waiting_on, comment_id } = post;
    posts[lane] = { at: new Date(post.at).toISOString() };
    if (typeof waiting_on === "number" && Number.isSafeInteger(waiting_on) && waiting_on > 0)
      posts[lane].waiting_on = waiting_on;
    if (typeof comment_id === "number" && Number.isSafeInteger(comment_id) && comment_id > 0)
      posts[lane].comment_id = comment_id;
  }
  if (Object.keys(posts).length) return posts;
}

function verifiedLaneUpdates(payload: FactoryData) {
  const updates: NonNullable<FactoryData["lane_updates"]> = {};
  for (const lane of builderLanes) {
    const update = payload.lane_updates?.[lane];
    if (update && typeof update.at === "string" && recentLaneUpdate(update.at, payload.generated_at) &&
        typeof update.text === "string" && [...update.text].length <= 80 &&
        /^[\p{L}\p{N}_ #%,'’!.?()+-]+$/u.test(update.text) &&
        !/(?:[a-z0-9-]+\.)+[a-z]{2,}\b/i.test(update.text)) {
      updates[lane] = { at: update.at, text: update.text };
    }
  }
  return Object.keys(updates).length ? updates : undefined;
}

function verifiedPictures(payload: FactoryData) {
  if (!Array.isArray(payload.pictures)) return;
  const count = (value: number) => Number.isSafeInteger(value) && value >= 0;
  const seen = new Map<string, FactoryPicture>();
  for (const picture of payload.pictures) {
    if (!picture || !/^\d{4}-\d{2}-\d{2}$/.test(picture.day) ||
        !(Date.parse(picture.as_of) <= Date.parse(payload.generated_at)) ||
        pacificDay(picture.as_of) !== picture.day || !count(picture.floor) || !count(picture.shipped)) continue;
    seen.set(picture.day, { day: picture.day, as_of: picture.as_of, floor: picture.floor, shipped: picture.shipped });
  }
  return [...seen.values()].sort((a, b) => b.day.localeCompare(a.day)).slice(0, 7);
}

function notesForSnapshot(payload: FactoryData) {
  const note = payload.notes;
  const plain = (text: unknown, cap: number) =>
    typeof text === "string" &&
    /^[A-Za-z0-9 #_,.'’!?-]+$/.test(text) &&
    text.split(/\s+/).length <= cap;
  if (
    !note ||
    note.snapshot_at !== payload.generated_at ||
    !["counts", "model"].includes(note.source) ||
    !plain(note.floor, 30) ||
    !note.stations ||
    !Object.entries(note.stations).every(
      ([station, text]) =>
        Object.values(stationNames).includes(station) && plain(text, 16),
    )
  )
    return undefined;
  return {
    snapshot_at: note.snapshot_at,
    source: note.source,
    floor: note.floor,
    stations: note.stations,
  };
}

function speechForSnapshot(payload: FactoryData): FactoryData["speech"] {
  const speech: FactoryData["speech"] = {};
  for (const lane of builderLanes) {
    const line = payload.speech?.[lane];
    if (
      line && typeof line.text === "string" && line.text.length <= 140 &&
      /^[A-Za-z0-9 #%_,.'’!?-]+$/.test(line.text) && factoryMoods.includes(line.mood) &&
      (line.source === "model" || line.source === "facts")
    ) speech[lane] = { text: line.text, mood: line.mood, source: line.source };
  }
  return Object.keys(speech).length ? speech : undefined;
}

function withVerifiedJourney(change: Change, through: number): Change {
  const { journey, ...rest } = change;
  let latest = -Infinity;
  if (!Array.isArray(journey) || !journey.length || !journey.every((visit, index) => {
    if (!visit || !stations.includes(visit.station)) return false;
    const first = Date.parse(visit.first_seen_at);
    const last = visit.last_seen_at === undefined ? through : Date.parse(visit.last_seen_at);
    if (!(first >= latest && first <= last && last <= through)) return false;
    if (visit.last_seen_at === undefined && (index !== journey.length - 1 || visit.station !== change.station)) return false;
    latest = last;
    return true;
  })) return rest;
  return change;
}

export function validateSnapshot(payload: FactoryData): FactoryData {
  if (
    payload.schema_version !== 1 ||
    !Array.isArray(payload.changes) ||
    !Array.isArray(payload.jams) ||
    !Array.isArray(payload.coverage) ||
    !payload.coverage.every((note: unknown) => typeof note === "string") ||
    !payload.signals ||
    (payload.injury_clock !== undefined &&
      (!payload.injury_clock ||
        !Number.isFinite(Date.parse(payload.injury_clock.from)) ||
        typeof payload.injury_clock.available !== "boolean" ||
        !Array.isArray(payload.injury_clock.events) ||
        !payload.injury_clock.events.every((event) =>
          event &&
          ["switched-off", "wrong-number"].includes(event.kind) &&
          Number.isSafeInteger(event.number) &&
          event.number > 0 &&
          Number.isFinite(Date.parse(event.at)),
        ))) ||
    !Array.isArray(payload.events ?? []) ||
    !(payload.events ?? []).every(isEvent) ||
    !Array.isArray(payload.transitions ?? []) ||
    !(payload.transitions ?? []).every(
      (transfer: NonNullable<FactoryData["transitions"]>[number]) =>
        Number.isSafeInteger(transfer.number) &&
        ["Server", "Website", "Apps"].includes(transfer.line) &&
        ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
          transfer.from,
        ) &&
        ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
          transfer.to,
        ) &&
        Number.isFinite(Date.parse(transfer.at)) &&
        (transfer.observed_at === undefined ||
          Number.isFinite(Date.parse(transfer.observed_at))),
    ) ||
    !Array.isArray(payload.stops ?? []) ||
    !(payload.stops ?? []).every(
      (stop: NonNullable<FactoryData["stops"]>[number]) =>
        [
          "line-stalled",
          "announced",
          "hold",
          "master",
          "review-waiting",
        ].includes(stop.kind) &&
        (stop.line === null ||
          ["Server", "Website", "Apps"].includes(stop.line)) &&
        ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
          stop.station,
        ) &&
        ["red", "amber"].includes(stop.level) &&
        Number.isSafeInteger(stop.count) &&
        stop.count >= 0 &&
        Number.isFinite(Date.parse(stop.since)) &&
        (stop.number === undefined ||
          (Number.isSafeInteger(stop.number) && stop.number > 0)) &&
        (stop.waiting_since === undefined ||
          Number.isFinite(Date.parse(stop.waiting_since))),
    ) ||
    !payload.changes.every(
      (change: FactoryData["changes"][number]) =>
        Number.isSafeInteger(change.number) &&
        change.number > 0 &&
        typeof change.title === "string" &&
        (change.check_progress === undefined ||
          (change.check_progress !== null &&
            isProgress(change.check_progress.done, change.check_progress.total))) &&
        (change.approvals === undefined ||
          (change.approvals !== null &&
            [change.approvals.bot, change.approvals.fable].every(
              (at) => at === undefined || Number.isFinite(Date.parse(at)),
            ))) &&
        (change.held_for_108 === undefined ||
          typeof change.held_for_108 === "boolean") &&
        ["Server", "Website", "Apps"].includes(change.line) &&
        ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
          change.station,
        ) &&
        Array.isArray(change.reasons) &&
        Number.isFinite(Date.parse(change.last_activity)) &&
        isBuilder(change.builder) &&
        (change.testflight_build === undefined ||
          (Number.isSafeInteger(change.testflight_build) &&
            change.testflight_build > 0)) &&
        [
          change.merge_announced_at,
          change.live_posted_at,
          change.live_post_observed_at,
          change.bench_seen_at,
        ].every((at) => at === undefined || Number.isFinite(Date.parse(at))),
    ) ||
    !Number.isFinite(Date.parse(payload.generated_at)) ||
    (payload.read_expires_at !== undefined &&
      !Number.isFinite(Date.parse(payload.read_expires_at))) ||
    !Number.isFinite(Date.parse(payload.observed_since))
  )
    throw new Error("Snapshot incomplete");
  const notes = notesForSnapshot(payload);
  const speech = speechForSnapshot(payload);
  const replay = verifiedReplay(payload);
  const crew = verifiedCrew(payload);
  const posts = verifiedCrewPosts(payload);
  const laneUpdates = verifiedLaneUpdates(payload);
  const pictures = verifiedPictures(payload);
  const { checks_queue: rawQueue, testflight_post: postedBuild, ...signals } = payload.signals;
  const checksQueue = verifiedChecksQueue(rawQueue);
  const testFlight = postedBuild && Number.isSafeInteger(postedBuild.build) && postedBuild.build > 0 &&
    /^[a-f0-9]{40}$/.test(postedBuild.commit) && Date.parse(postedBuild.at) <= Date.parse(payload.generated_at)
    ? { build: postedBuild.build, at: postedBuild.at, commit: postedBuild.commit } : undefined;
  const usage = payload.model_usage;
  const modelUsage = usage && /^\d{4}-\d{2}-\d{2}$/.test(usage.day) &&
    Number.isSafeInteger(usage.calls) && usage.calls >= 0 && usage.calls <= 200
    ? { day: usage.day, calls: usage.calls } : undefined;
  return {
    schema_version: payload.schema_version,
    generated_at: payload.generated_at,
    observed_since: payload.observed_since,
    ...(payload.read_expires_at
      ? { read_expires_at: payload.read_expires_at }
      : {}),
    ...(payload.transitions ? { transitions: payload.transitions } : {}),
    ...(payload.events ? { events: payload.events } : {}),
    ...(replay ? { day_replay: replay } : {}),
    ...(crew ? { crew_week: crew } : {}),
    ...(posts ? { crew_posts: posts } : {}),
    ...(laneUpdates ? { lane_updates: laneUpdates } : {}),
    ...(pictures?.length ? { pictures } : {}),
    ...(payload.injury_clock ? { injury_clock: payload.injury_clock } : {}),
    ...(payload.stops ? { stops: payload.stops } : {}),
    ...(notes ? { notes } : {}),
    ...(speech ? { speech } : {}),
    ...(modelUsage ? { model_usage: modelUsage } : {}),
    changes: payload.changes.map((change) => withVerifiedJourney(change, Date.parse(payload.generated_at))),
    jams: payload.jams,
    signals: {
      ...signals,
      ...(checksQueue ? { checks_queue: checksQueue } : {}),
      ...(testFlight ? { testflight_post: testFlight } : {}),
    },
    coverage: payload.coverage,
  };
}

async function readSnapshot(fetcher: typeof fetch, attempt: 1 | 2) {
  const startedAt = performance.now();
  // Cloud reads took up to 620 ms, and five production reads exceeded 800 ms.
  const signal = AbortSignal.timeout(4000);
  let outcome = "success";
  let status: number | undefined;
  try {
    const response = await fetcher(FACTORY_DATA_URL, {
      cache: "no-store",
      signal,
    });
    status = response.status;
    if (!response.ok) throw new Error("Snapshot unavailable");
    return validateSnapshot(await response.json());
  } catch (error) {
    outcome =
      signal.aborted ||
      (error instanceof Error && error.name === "TimeoutError")
        ? "timeout"
        : "failed";
    throw error;
  } finally {
    const receipt = {
      attempt,
      durationMs: Math.round(performance.now() - startedAt),
      outcome,
      status,
    };
    if (outcome === "success") console.info("Factory live read", receipt);
    else console.warn("Factory live read", receipt);
  }
}

export function createFactoryReader(
  fetcher: typeof fetch = (...args) => fetch(...args),
  cacheVerifiedRead: (load: LoadVerifiedRead) => LoadVerifiedRead = (load) =>
    load,
) {
  let lastGood: VerifiedRead | null = null;
  let lastFailureAt: number | null = null;
  let pending: Promise<VerifiedRead> | null = null;

  async function fetchWithRetry() {
    try {
      return await readSnapshot(fetcher, 1);
    } catch {
      return readSnapshot(fetcher, 2);
    }
  }

  function refresh(): Promise<VerifiedRead> {
    pending ??= fetchWithRetry()
      .then(
        (data) => {
          lastGood = { data, checkedAt: Date.now() };
          lastFailureAt = null;
          return lastGood;
        },
        (error) => {
          lastFailureAt = Date.now();
          throw error;
        },
      )
      .finally(() => {
        pending = null;
      });
    return pending;
  }

  // A rejected refresh leaves the previous verified entry in Next's Data Cache.
  const load = cacheVerifiedRead(refresh);

  return async (): Promise<FactoryRead> => {
    let readFailed: boolean;
    try {
      const read = await load();
      if (!lastGood || read.checkedAt >= lastGood.checkedAt) lastGood = read;
      // Next can return its old entry while refreshing. Wait for that same
      // refresh before rendering after a quiet spell.
      const verified =
        Date.now() - lastGood.checkedAt > MAX_CACHE_AGE_MS
          ? await refresh()
          : lastGood;
      readFailed =
        lastFailureAt !== null && lastFailureAt >= verified.checkedAt;
    } catch {
      readFailed = true;
    }
    return {
      data: lastGood?.data ?? null,
      lastGoodAt: lastGood?.data.generated_at ?? null,
      ...(lastGood ? { readAt: new Date(lastGood.checkedAt).toISOString() } : {}),
      readFailed,
    };
  };
}
