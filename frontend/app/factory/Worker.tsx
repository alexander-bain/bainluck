import type { Builder, FactoryMood, Station } from "./types";
import styles from "./factory.module.css";

export type WorkerState = FactoryMood | "idle" | "alarmed";
type Identity = Exclude<Builder, "Other"> | "Fable";
const hats: Record<Identity, string> = {
  S: "M35 26q9-16 25-5l-1 6H35m22-3 13 2-5 3",
  B: "M35 26V20l7-6h12l7 6v6zM33 26h31",
  C: "M36 26v-7q12-12 23 0v7zM33 25h5v12h-5zm25 0h5v12h-5z",
  D: "M32 28l2-10q14-14 28 0l2 10zM49 13v14M30 28h36",
  E: "M35 27v-5h26v5zM36 24l-9 8 2-7-6-1 12-4",
  F: "M36 26q1-15 18-14l9 14zm24-2h12l-6 4H52",
  W: "M35 26v-6q4-13 13-13t13 13v6zM35 24h26M44 13v8m8-8v8",
  Fable: "M35 24l5-9h16l5 9zm-4 1h34",
};

/** Original workshop figures. Recent crate activity or a transfer animates their hands. */
export default function Worker({
  station,
  state,
  identity,
}: {
  station?: Station;
  state: WorkerState;
  identity: Identity;
}) {
  const concerned = state === "alarmed" || state === "stuck";
  const scene = state === "celebrating" ? "Live" : station;
  return (
    <svg
      viewBox="0 0 100 76"
      className={styles.worker}
      aria-hidden="true"
      data-worker={state}
      data-identity={identity}
    >
      <g className={styles.workerBody}>
        <path d="M36 66l3-22h18l5 22M40 65v8m16-8v8" />
        <path d="M38 46l9 7 11-7v21H37z" className={styles.overalls} />
        <circle cx="48" cy="31" r="12" className={styles.workerFace} />
        <path d={hats[identity]} className={styles.workerHat} />
        {(identity === "B" || identity === "Fable") && (
          <path d="M37 28h9v7h-9zm13 0h9v7h-9zm-4 3h4" />
        )}
        {state === "asleep" ? (
          <path d="M41 32h4m8 0h4m-11 7h4" />
        ) : (
          <>
            <path d="M42 31v2m12-2v2" />
            <path
              d={concerned ? "M46 39q3-5 6 0" : "M45 38q4 3 8 0"}
            />
          </>
        )}
      </g>
      {state === "carrying" ? (
        <g className={styles.workerHands}>
          <path d="M39 47 29 56m28-9 11 9" />
          <rect
            x="28"
            y="46"
            width="42"
            height="22"
            rx="2"
            className={styles.workerBox}
          />
          <path d="M45 46v22m8-22v22" />
        </g>
      ) : state === "waiting" ? (
        <path d="M39 47 35 60m22-13 4 13" className={styles.workerHands} />
      ) : concerned ? (
        <path
          d="M39 47L26 31l-4-9m35 24 14-15 4-9"
          className={styles.workerHands}
        />
      ) : (
        <g className={styles.workerHands}>
          {!scene && (
            <path d="M39 47 30 51m27-4 11 5" className={styles.workerArm} />
          )}
          {scene === "Write" && (
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
          {scene === "Test" && (
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
          {scene === "Review" && (
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
          {scene === "Merge line" && (
            <>
              <path d="M39 48 27 56m30-9 14 5" className={styles.workerArm} />
              <path d="M63 72h26v-9H63zm12-9L69 41" className={styles.lever} />
              <circle cx="69" cy="40" r="4" className={styles.workerHat} />
            </>
          )}
          {scene === "Ship" && (
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
          {scene === "Live" && (
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
      {concerned && (
        <text x="77" y="17" className={styles.alarmText}>
          !
        </text>
      )}
    </svg>
  );
}
