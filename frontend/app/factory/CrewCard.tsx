import { duration, recentlyActive, stationNames, time } from "./activity";
import type { NameableBuilder } from "./builderNames";
import type { CrewHabits, CrewPost, LaneSpeech } from "./types";
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

function hourLabel(hour: number) {
  return `${hour % 12 || 12} ${hour < 12 ? "AM" : "PM"}`;
}

export default function CrewCard({ identity, name, pose, clockedIn, number, post, voice, habits, now, titleId }: {
  identity: NameableBuilder;
  name: string;
  pose: WorkerState;
  clockedIn: boolean;
  number?: number;
  post?: CrewPost;
  voice?: LaneSpeech;
  habits?: CrewHabits;
  now: string;
  titleId?: string;
}) {
  const longest = habits?.longest;
  const recentPost = post && recentlyActive(post.at, now) ? post : undefined;
  return (
    <div className={styles.builderCard} data-crew={identity} data-pose={pose}>
      <Worker identity={identity} state={pose} />
      <strong className={styles.nameTag} id={titleId}>{name}</strong>
      {identity === "W" && <small>Spare hand</small>}
      {identity === "Fable" && <small>Foreman at Inspection</small>}
      <p className={styles.temperament}>{temperament[identity]}</p>
      <span>{recentPost ? `Active at ${time(recentPost.at)} PT` : clockedIn ? "Clocked in" : "Quiet for 15 minutes"}</span>
      <span>{recentPost?.waiting_on ? `Waiting on #${recentPost.waiting_on}` : <>{poses[pose]}{number && ` #${number}`}</>}</span>
      {voice && !(recentPost && voice.mood === "asleep") && (
        <p className={styles.crewSpeech} data-source={voice.source}>{voice.text}</p>
      )}
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
