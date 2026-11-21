import styles from "./factory.module.css";
import type { FloorVerdict } from "./verdict";

const poses = {
  green: {
    ears: "M28 16 29 5l8 5 9-6 2 13",
    eyes: "M33 16v2m9-2v2M35 21q3 3 6 0",
    tail: "M23 27C9 31 5 21 13 15c4-3 6-2 6 1",
  },
  amber: {
    ears: "m28 16-2-9 10 4 10-5 2 11",
    eyes: "M33 18h2m6-2h2m-8 6h5",
    tail: "M23 27C9 31 6 20 15 21",
  },
  red: {
    ears: "m28 16-5-6 13 2 13-3-1 8",
    eyes: "m33 18 3 1m5 0 3-1m-9 6q3-3 6 0",
    tail: "M23 27C8 29 5 27 10 25c3-1 5 0 4 2",
  },
};

export default function FactoryMascot({ level }: { level: FloorVerdict["level"] }) {
  const pose = poses[level];
  return (
    <svg className={styles.mascot} viewBox="0 0 55 33" aria-hidden="true" data-mascot={level}>
      <title>Workshop cat</title>
      <path d={pose.tail} />
      <path d="M21 28q-4-9 4-12l7 1q7 1 10 12H20z" fill="var(--paper)" />
      <path d={pose.ears} fill="var(--paper)" />
      <path d="M28 16q6-10 20 0v5q0 5-10 5t-10-5z" fill="var(--paper)" />
      <path d={pose.eyes} />
      <path d="M29 26l9 2" stroke="var(--workshop-copper)" />
      <circle cx="32" cy="28" r="2" fill="currentColor" stroke="none" />
    </svg>
  );
}
