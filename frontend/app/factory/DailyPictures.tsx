import { useState } from "react";
import Image from "next/image";
import { ChevronRight } from "lucide-react";
import { FACTORY_PICTURE_BASE } from "./data";
import { time } from "./activity";
import type { FactoryPicture } from "./types";
import Worker from "./Worker";
import styles from "./factory.module.css";

const pacificDate = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  month: "short",
  day: "numeric",
  year: "numeric",
});

function displayDate(picture: FactoryPicture) {
  return pacificDate.format(new Date(picture.as_of));
}

export default function DailyPictures({ pictures, artist }: {
  pictures?: FactoryPicture[];
  artist: string;
}) {
  const [selected, select] = useState<string>();
  const [unavailable, setUnavailable] = useState<string[]>([]);
  if (!pictures?.length) return null;
  const remaining = pictures.filter(picture => !unavailable.includes(picture.day));
  const active = remaining.find(picture => picture.day === selected) ?? remaining[0];

  return (
    <details className={styles.panel} data-daily-pictures>
      <summary className={styles.summary}>
        <ChevronRight size={14} aria-hidden="true" />
        <h2>Daily picture</h2>
        {active && <time className={styles.sectionNote} dateTime={active.day}>{displayDate(active)}</time>}
      </summary>
      {active ? (
        <div className={styles.dailyPictures}>
          <figure className={styles.dayPicture}>
            <Image
              key={active.day}
              width={1024}
              height={1024}
              src={`${FACTORY_PICTURE_BASE}factory-picture-${active.day}.webp`}
              alt="An illustrated Factory workshop"
              unoptimized
              onError={() => setUnavailable(older => older.includes(active.day) ? older : [...older, active.day])}
            />
            <figcaption>
              <time dateTime={active.day}>{displayDate(active)}</time>
              <p>
                {active.shipped} {active.shipped === 1 ? "change" : "changes"} went live.
                {" "}{active.floor} {active.floor === 1 ? "change was" : "changes were"} on the floor at {time(active.as_of)} PT.
              </p>
            </figcaption>
          </figure>
          <div className={styles.pictureEasel}>
            <Worker identity="F" state="idle" />
            <strong>{artist}</strong>
            {remaining.length > 1 && (
              <ul aria-label="Picture dates">
                {remaining.map(picture => (
                  <li key={picture.day}>
                    <button type="button" aria-pressed={active.day === picture.day} onClick={() => select(picture.day)}>
                      {displayDate(picture)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : <p className={styles.crewRecordNote}>The pictures could not be read.</p>}
    </details>
  );
}
