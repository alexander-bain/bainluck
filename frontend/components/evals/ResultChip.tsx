import { CHIP_SHAPE, RESULT_TONE } from "@/components/evals/chipStyles";
import { RESULT_WORD, type ResultKind } from "@/lib/evals/truth";

/**
 * PASS · FAIL · HELD · NOT RUN · NOT ELIGIBLE · UNKNOWN.
 *
 * The chip prints the record's verdict; nothing here decides one. A FAIL record
 * shows FAIL everywhere it appears, and partial passes sit under it, never
 * instead of it.
 */
export default function ResultChip({ result }: { result: ResultKind }) {
  return (
    <span data-result={result} className={`${CHIP_SHAPE} ${RESULT_TONE[result]}`}>
      {RESULT_WORD[result]}
    </span>
  );
}
