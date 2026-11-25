import { duration, stationNames } from "./activity";
import styles from "./factory.module.css";
import type { Change } from "./types";

const pacificRead = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export default function CrateJourney({ changes, through }: { changes: Change[]; through: string }) {
  return (
    <section className={styles.crateJourney} aria-labelledby="crate-journey-title">
      <h4 id="crate-journey-title">Crate journey</h4>
      <p>Times show the first and last reads at each recorded station.</p>
      {changes.map(({ line, journey }) => (
        <div key={line}>
          <h5>{line}</h5>
          {journey?.length ? (
            <ol>
              {journey.map((visit) => {
                const first = new Date(visit.first_seen_at);
                const last = new Date(visit.last_seen_at ?? through);
                const seconds = (last.getTime() - first.getTime()) / 1000;
                return (
                  <li key={`${visit.station}/${visit.first_seen_at}`}>
                    <strong>{stationNames[visit.station]}</strong>
                    <span>
                      {visit.station === "Live" || seconds <= 0
                        ? `Seen ${pacificRead.format(first)} PT`
                        : `${duration(seconds)} between reads · ${pacificRead.formatRange(first, last)} PT`}
                    </span>
                  </li>
                );
              })}
            </ol>
          ) : <p>Station times are missing for this line.</p>}
        </div>
      ))}
    </section>
  );
}
