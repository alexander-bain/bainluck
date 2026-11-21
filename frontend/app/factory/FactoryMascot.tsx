import type { CSSProperties } from "react";
import { stations } from "./activity";
import type { FloorEvent } from "./types";
import type { FloorVerdict } from "./verdict";
import styles from "./factory.module.css";

export type MascotAction = "walking" | "pushing" | "jumping";

export function mascotAction(event: FloorEvent): MascotAction | undefined {
  if (event.kind === "live") return "jumping";
  if (event.from && event.from !== event.station) return "pushing";
  if (event.kind === "commit") return "walking";
}

export default function FactoryMascot({ level, pose, moving = false }: {
  level?: FloorVerdict["level"];
  pose: MascotAction | "standing" | "asleep";
  moving?: boolean;
}) {
  return (
    <span
      className={styles.mascot}
      aria-hidden="true"
      data-mascot={level}
      data-mascot-pose={pose}
      data-mascot-motion={moving || undefined}
    />
  );
}

export function MascotMove({ event, clipMs, pose, alongside }: {
  event: FloorEvent;
  clipMs: number;
  pose: MascotAction;
  alongside?: boolean;
}) {
  const end = stations.indexOf(event.station);
  const start = pose === "pushing" && event.from ? stations.indexOf(event.from) : end;
  return (
    <div
      className={styles.mascotRoute}
      aria-hidden="true"
      data-mascot-action={pose}
      data-alongside={alongside || undefined}
      data-reverse={end < start || undefined}
      style={{
        "--event-start": start,
        "--event-steps": end - start,
        "--event-length": `${clipMs}ms`,
      } as CSSProperties}
    >
      <div className={styles.mascotAction}>
        <FactoryMascot pose={pose} moving />
        {pose === "pushing" && <span className={styles.mascotCrate}>#{event.number}</span>}
      </div>
    </div>
  );
}
