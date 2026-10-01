import { Fragment } from "react";

/**
 * #10108 — a doubles pair written without spaces ("Harris/Hsieh") is ONE
 * unbreakable word, so its min-content width is the whole pair. In the event
 * hero the side columns are `flex-1` and cannot shrink below that, so a long
 * pair widened both side columns, squeezed the centre, and the 48px
 * probability pair spilled over both crests: the hero read "HAR25%".
 *
 * A `<wbr>` after each slash is the only change: the pair may now wrap at the
 * slash ("Harris/" · "Hsieh"), the column's min-content falls to its longest
 * half, and the column is sized by its crest again. The text a reader copies
 * is unchanged (`<wbr>` adds no character), and a name with no slash renders
 * exactly as before.
 */
export default function SlashBreakableName({ text }: { text: string }) {
  if (!text.includes("/")) return <>{text}</>;
  const parts = text.split("/");
  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {part}
          {i < parts.length - 1 && (
            <>
              /<wbr />
            </>
          )}
        </Fragment>
      ))}
    </>
  );
}
