import { ArrowRight, ListChecks } from "lucide-react";
import type { ChecksQueue as QueueReading } from "./types";
import styles from "./factory.module.css";

export default function ChecksQueue({ queue }: { queue?: QueueReading }) {
  const minutes = queue?.longest_wait_minutes;
  const longest = minutes == null
    ? queue?.waiting === 0 ? "No wait" : "Time missing"
    : `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
  return (
    <section className={styles.checksQueue} aria-labelledby="checks-queue-heading">
      <div className={styles.queueHeading}>
        <ListChecks size={16} aria-hidden="true" />
        <h3 id="checks-queue-heading">Waiting line at Checks</h3>
      </div>
      {queue ? (
        <>
          <div className={styles.queueTrack} data-queue-waiting={queue.waiting} aria-hidden="true">
            <span style={{ width: `${100 * queue.waiting / (queue.waiting + queue.machines)}%` }} />
            <ArrowRight size={15} />
          </div>
          <dl className={styles.queueCounts}>
            <div><dt>Runs waiting</dt><dd>{queue.waiting}</dd></div>
            <div><dt>Runs running</dt><dd>{queue.running}</dd></div>
            <div><dt>Borrowed machines</dt><dd>{queue.machines}</dd></div>
            <div><dt>Longest wait</dt><dd>{longest}</dd></div>
          </dl>
        </>
      ) : <p>Queue details are missing from this read.</p>}
      <p className={styles.queueHelp}>Every change has to pass checks on a borrowed machine, so when more changes arrive than there are machines, they wait here.</p>
      {queue && queue.queued_without_jobs > 0 && (
        <small>GitHub lists {queue.queued_without_jobs} {queue.queued_without_jobs === 1 ? "queued run" : "queued runs"} with no job details.</small>
      )}
    </section>
  );
}
