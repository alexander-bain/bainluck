import {
  BUILDER_NAME_LIMIT,
  defaultNames,
  nameableBuilders,
  type NameableBuilder,
} from "./builderNames";
import styles from "./factory.module.css";

export default function BuilderNamePanel({ custom, changeName, resetNames }: {
  custom: Partial<Record<NameableBuilder, string>>;
  changeName: (key: NameableBuilder, value: string) => void;
  resetNames: () => void;
}) {
  return (
    <details className={styles.builderNamePanel}>
      <summary>Name the builders</summary>
      <p>Names stay in this browser.</p>
      <div className={styles.builderNameInputs}>
        {nameableBuilders.map(key => (
          <label key={key}>
            <span>{defaultNames[key]}</span>
            <input
              type="text"
              value={custom[key] ?? ""}
              maxLength={BUILDER_NAME_LIMIT}
              autoComplete="off"
              spellCheck={false}
              onChange={event => changeName(key, event.currentTarget.value)}
            />
          </label>
        ))}
      </div>
      <button type="button" onClick={resetNames}>Reset names</button>
    </details>
  );
}
