import { hours, injuryHours } from "./signs";
import type { InjuryClock } from "./types";
import styles from "./factory.module.css";

const recordDate = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  month: "short",
  day: "numeric",
});

export default function InjurySign({
  reading,
  through,
}: {
  reading?: InjuryClock;
  through: string;
}) {
  const clock = injuryHours(reading, through);
  const last = clock?.last;
  const source = last &&
    (last.kind === "switched-off"
      ? `https://github.com/alexander-bain/bainluck/issues/12779#issuecomment-${last.number}`
      : `https://github.com/alexander-bain/bainluck/issues/${last.number}`);
  return (
    <aside className={styles.injurySign} aria-label="Hours without an injury">
      <span>HOURS WITHOUT AN INJURY</span>
      {clock && reading ? (
        <>
          <strong>{hours(clock.current)}</strong>
          <small>
            Record since {recordDate.format(new Date(reading.from))} · {hours(clock.record)}
          </small>
          {source ? <a href={source}>Last injury</a> : <small>No injury recorded yet.</small>}
        </>
      ) : <small>Injury records are missing from this read.</small>}
    </aside>
  );
}
