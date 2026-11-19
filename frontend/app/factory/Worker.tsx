import type { Station } from "./types";
import styles from "./factory.module.css";

type WorkerState = "working" | "idle" | "asleep" | "alarmed";

/** Original workshop figures. Recent crate activity or a transfer animates their hands. */
export default function Worker({
  station,
  state,
}: {
  station: Station;
  state: WorkerState;
}) {
  return (
    <svg
      viewBox="0 0 100 76"
      className={styles.worker}
      role="img"
      aria-label={`${station} worker, ${state}`}
      data-worker={state}
    >
      <g className={styles.workerBody}>
        <path d="M36 66l3-22h18l5 22M40 65v8m16-8v8" />
        <path d="M38 46l9 7 11-7v21H37z" className={styles.overalls} />
        <circle cx="48" cy="31" r="12" className={styles.workerFace} />
        {station === "Live" ? (
          <path
            d="M34 25q14-16 28 0v3H33m27-3h9"
            className={styles.workerHat}
          />
        ) : (
          <path
            d="M35 27q2-16 16-12 10 1 11 13z"
            className={styles.workerHat}
          />
        )}
        {state === "asleep" ? (
          <path d="M41 32h4m8 0h4m-11 7h4" />
        ) : (
          <>
            <path d="M42 31v2m12-2v2" />
            <path
              d={state === "alarmed" ? "M46 39q3-5 6 0" : "M45 38q4 3 8 0"}
            />
          </>
        )}
      </g>
      {state === "alarmed" ? (
        <path
          d="M39 47L26 31l-4-9m35 24 14-15 4-9"
          className={styles.workerHands}
        />
      ) : (
        <g className={styles.workerHands}>
          {station === "Write" && (
            <>
              <path
                d="M39 47 29 53h28m-1-6 11 9"
                className={styles.workerArm}
              />
              <path d="M18 59h64M25 59v15m50-15v15" />
              <path d="M49 58l5-12 18 7-3 5" className={styles.paper} />
              <path d="m62 47 5 9" />
            </>
          )}
          {station === "Test" && (
            <>
              <path
                d="M39 47 28 55l9 5m20-13 15 5"
                className={styles.workerArm}
              />
              <rect
                x="60"
                y="43"
                width="20"
                height="28"
                rx="2"
                className={styles.paper}
              />
              <path d="M66 42h8v5h-8zm-1 12 3 3 6-7m-9 13h10" />
            </>
          )}
          {station === "Review" && (
            <>
              <path
                d="M39 47 28 59h-7m36-12 9-9"
                className={styles.workerArm}
              />
              <path d="M10 65h26l-4-10H14z" className={styles.paper} />
              <g className={styles.workerArm}>
                <circle cx="74" cy="31" r="12" className={styles.lens} />
                <path d="m66 40-8 10" />
              </g>
            </>
          )}
          {station === "Merge line" && (
            <>
              <path d="M39 48 27 56m30-9 14 5" className={styles.workerArm} />
              <path d="M63 72h26v-9H63zm12-9L69 41" className={styles.lever} />
              <circle cx="69" cy="40" r="4" className={styles.workerHat} />
            </>
          )}
          {station === "Ship" && (
            <>
              <path d="M39 47 31 58m26-11 7 12" className={styles.workerArm} />
              <rect
                x="29"
                y="56"
                width="40"
                height="18"
                rx="2"
                className={styles.workerBox}
              />
              <path d="M43 56v18m13-18v18m-27-9h40" />
            </>
          )}
          {station === "Live" && (
            <>
              <path d="M39 47 24 54m33-7 15-10" className={styles.workerArm} />
              <path d="M71 37V17l15 5-15 7" className={styles.dispatchFlag} />
              <path d="M18 58h21l-2 10H20z" className={styles.paper} />
            </>
          )}
        </g>
      )}
      {state === "asleep" && (
        <text x="70" y="17" className={styles.sleepText}>
          Zzz
        </text>
      )}
      {state === "alarmed" && (
        <text x="77" y="17" className={styles.alarmText}>
          !
        </text>
      )}
    </svg>
  );
}
