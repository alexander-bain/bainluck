import { Factory } from "lucide-react";
import { duration, recentlyActive, stationNames, time } from "./activity";
import type { CrewIdentity, NameableBuilder } from "./builderNames";
import type { Change, CrewHabits, CrewPost, LaneSpeech, LaneUpdate, Station } from "./types";
import Worker, { type WorkerState } from "./Worker";
import styles from "./factory.module.css";

const temperament: Record<NameableBuilder, string> = {
  S: "Keeps a steady pace and saves a little cheer for the finish.",
  B: "Has a sign handy to tell you what is happening.",
  C: "Keeps the bench tidy and takes a quiet moment when it is clear.",
  D: "Gives a change one last look before it heads out.",
  E: "Likes a running start when the next station opens.",
  F: "Brings a little color to the end of the line.",
  W: "Keeps a tool handy for whichever station needs help.",
  Fable: "Looks each crate over before waving it through.",
};

const poses: Record<WorkerState, string> = {
  alarmed: "Needs attention",
  asleep: "Asleep",
  carrying: "Carrying",
  celebrating: "Celebrating",
  idle: "Idle",
  stuck: "Stuck",
  waiting: "Waiting",
  working: "Working",
};

const locations: Record<Station, string> = {
  Write: "At the bench",
  Test: "At Checks",
  Review: "At Inspection",
  "Merge line": "At the loading dock",
  Ship: "On the truck",
  Live: "Live",
};

function stationDetail(change?: Change) {
  switch (change?.station) {
    case "Test": return change.checks_running ? "Tests are running." : null;
    case "Review": return "Waiting for a look.";
    case "Live": return change.live_at ? `Went live at ${time(change.live_at)} PT.` : null;
    default: return null;
  }
}

function hourLabel(hour: number) {
  return `${hour % 12 || 12} ${hour < 12 ? "AM" : "PM"}`;
}

export default function CrewCard({ identity, name, pose, clockedIn, station, change, post, update, voice, habits, now, titleId }: {
  identity: CrewIdentity;
  name: string;
  pose: WorkerState;
  clockedIn: boolean;
  station?: Station;
  change?: Change;
  post?: CrewPost;
  update?: LaneUpdate;
  voice?: LaneSpeech;
  habits?: CrewHabits;
  now: string;
  titleId?: string;
}) {
  const longest = habits?.longest;
  const recentPost = post && recentlyActive(post.at, now) ? post : undefined;
  const checkIn = post ? `Posted on NOW at ${time(post.at)} PT` : undefined;
  const detail = stationDetail(change);
  return (
    <div className={styles.builderCard} data-crew={identity} data-pose={pose}>
      {identity === "Factory"
        ? <Factory size={42} aria-hidden="true" />
        : <Worker identity={identity} state={pose} />}
      <strong className={styles.nameTag} id={titleId}>{name}</strong>
      {identity !== "Factory" && (
        <div className={styles.crewLocation}>
          <p data-card-station={station ?? "rest"} data-card-change={change?.number}>
            {station ? locations[station] : "At the rest bench"}{change && ` · #${change.number}`}
          </p>
          {detail && <p className={styles.crewStationDetail}>{detail}</p>}
        </div>
      )}
      {identity === "W" && <small>Spare hand</small>}
      {identity === "Fable" && <small>Foreman at Inspection</small>}
      {update ? (
        <>
          <span>Posted at {time(update.at)} PT</span>
          <p className={styles.crewSpeech} data-source="lane">{update.text}</p>
        </>
      ) : checkIn ? (
        <p className={styles.crewSpeech} data-source="check-in">
          {post?.comment_id ? (
            <a href={`https://github.com/alexander-bain/bainluck/issues/12779#issuecomment-${post.comment_id}`}
              target="_blank" rel="noreferrer">{checkIn}</a>
          ) : checkIn}
        </p>
      ) : <span>{clockedIn ? "Clocked in" : "Quiet for 15 minutes"}</span>}
      {(!update || change) && (
        <span>{recentPost?.waiting_on ? `Waiting on #${recentPost.waiting_on}` : <>{poses[pose]}{identity === "Factory" && change && ` #${change.number}`}</>}</span>
      )}
      {voice && !update && !checkIn && (
        <p className={styles.crewSpeech} data-source={voice.source}>{voice.text}</p>
      )}
      {identity !== "Factory" && <p className={styles.temperament}>{temperament[identity]}</p>}
      {habits ? (
        <dl className={styles.crewHabits}>
          <div>
            <dt>{identity === "Fable" ? "Recorded looks this week" : "Recorded changes shipped this week"}</dt>
            <dd>{habits.changes}</dd>
          </div>
          <div>
            <dt>Longest timed station</dt>
            <dd>{habits.stations.map(station => stationNames[station]).join(", ") || "No timed visits yet"}</dd>
          </div>
          <div>
            <dt>Busiest hour</dt>
            <dd>{habits.hours.length ? `${habits.hours.map(hourLabel).join(", ")} PT` : "No activity recorded"}</dd>
          </div>
          <div>
            <dt>{identity === "Fable" ? "Longest current inspection wait" : "Longest-running open change"}</dt>
            <dd>{longest ? `#${longest.number} · ${duration((Date.parse(now) - Date.parse(longest.since)) / 1000)}` : "None recorded"}</dd>
          </div>
        </dl>
      ) : <p className={styles.crewRecordNote}>Weekly records are missing from this read.</p>}
    </div>
  );
}
