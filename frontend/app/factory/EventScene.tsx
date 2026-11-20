import type { CSSProperties } from "react";
import { Check, Minus, Truck, X } from "lucide-react";
import Worker from "./Worker";
import { stations } from "./activity";
import type { FloorEvent } from "./types";
import styles from "./factory.module.css";

export default function EventScene({
  event,
  clipMs,
}: {
  event: FloorEvent;
  clipMs: number;
}) {
  const start = stations.indexOf(event.from ?? event.station);
  const end = stations.indexOf(event.station);
  const color = event.builder ? styles[`builder${event.builder}`] : undefined;
  return (
    <div
      aria-hidden="true"
      className={styles.eventScene}
      data-event={event.kind}
      data-event-id={event.id}
      data-transfer={start !== end || undefined}
      style={{
        "--event-start": start,
        "--event-steps": end - start,
        "--event-length": `${clipMs}ms`,
      } as CSSProperties}
    >
      <div className={styles.eventAction}>
        {event.kind === "commit" && event.builder && event.builder !== "Other" && (
          <Worker state="working" station="Write" identity={event.builder} />
        )}
        {(event.kind === "live" || event.kind === "deploy" || event.kind === "merge") && (
          <Truck size={20} />
        )}
        {event.kind === "check" && (
          event.outcome === "failed" ? <X size={15} /> :
            event.outcome === "passed" ? <Check size={15} /> : <Minus size={15} />
        )}
        {(event.kind === "bot" || event.kind === "fable") && (
          <Check size={15} />
        )}
        <span className={`${styles.eventCrate} ${color ?? ""}`}>
          #{event.number}
        </span>
        {event.kind === "check" && <span>{event.done} of {event.total}</span>}
        {event.kind === "bot" && <span>Bot</span>}
        {event.kind === "fable" && <span>Fable</span>}
        {event.kind === "returned" && <span>Sent back</span>}
      </div>
    </div>
  );
}
