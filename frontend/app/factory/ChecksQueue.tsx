import { ArrowRight, ListChecks } from "lucide-react";
import type { ChecksQueue as QueueReading } from "./types";
import styles from "./factory.module.css";

export default function ChecksQueue({ queue }: { queue?: QueueReading }) {
  const reading = queue && !queue.unavailable ? queue : undefined;
  const limit = queue && `up to ${queue.machines} machines`;
  const minutes = reading?.longest_wait_minutes;
  const longest = minutes == null
    ? reading?.waiting === 0 ? "No wait" : "Time missing"
    : `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
  return (
    <section className={styles.checksQueue} aria-labelledby="checks-queue-heading">
      <div className={styles.queueHeading}>
        <ListChecks size={16} aria-hidden="true" />
        <h3 id="checks-queue-heading">Waiting line at Checks</h3>
      </div>
      {reading ? (
        <>
          <div className={styles.queueTrack} data-queue-waiting={reading.waiting} aria-hidden="true">
            <span style={{ width: `${100 * reading.waiting / (reading.waiting + reading.machines)}%` }} />
            <ArrowRight size={15} />
          </div>
          <dl className={styles.queueCounts}>
            <div><dt>Runs waiting</dt><dd>{reading.waiting}</dd></div>
            <div><dt>Runs running</dt><dd>{reading.running}</dd></div>
            {reading.machines_busy === undefined ? (
              <div><dt>Capacity</dt><dd>{limit}</dd></div>
            ) : (
              <div><dt>Machines busy</dt><dd>{reading.machines_busy} of {reading.machines}</dd></div>
            )}
            <div><dt>Longest wait</dt><dd>{longest}</dd></div>
          </dl>
        </>
      ) : (
        <p>Queue details are missing from this read.{limit && ` GitHub lends ${limit}.`}</p>
      )}
      <p className={styles.queueHelp}>
        Every change must pass checks on a borrowed machine, so it waits here when all the machines are busy.
        {reading && " Runs waiting counts runs with a job queued for a machine and none running."}
      </p>
      {reading && reading.queued_without_jobs > 0 && (
        <small>GitHub lists {reading.queued_without_jobs} {reading.queued_without_jobs === 1 ? "queued run" : "queued runs"} with no job details.</small>
      )}
    </section>
  );
}
