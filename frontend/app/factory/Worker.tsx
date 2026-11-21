import { CircleAlert, Moon, Package, Sparkles } from "lucide-react";
import type { CrewMove } from "./crewMotion";
import type { Builder, FactoryMood } from "./types";
import styles from "./factory.module.css";

export type WorkerState = FactoryMood | "idle" | "alarmed";
type Identity = Exclude<Builder, "Other"> | "Fable";

const poseIcons = {
  alarmed: CircleAlert,
  asleep: Moon,
  carrying: Package,
  celebrating: Sparkles,
  stuck: CircleAlert,
} as const;

export default function Worker({ state, identity, move }: {
  state: WorkerState;
  identity: Identity;
  move?: CrewMove;
}) {
  const Cue = state === "working" || state === "waiting" || state === "idle"
    ? undefined
    : poseIcons[state];

  return (
    <span
      className={styles.worker}
      aria-hidden="true"
      data-worker={state}
      data-identity={identity}
      data-crew-move={move}
    >
      <span className={styles.workerFigure} />
      {Cue && <Cue className={styles.workerCue} />}
    </span>
  );
}
