# #10662 / PR #10687 CI correction

PILLARS: TRUTH / FORMATTING. SHIP: eligible PM changes reach the coherent live event probability sooner.

The six failures from CI run `37598136364` were reproduced locally against `34a2aeafbfa47bc44580a5c5121748f529840d3f`, then corrected without changing the proposed PM-only opt-in behavior. The correction remains stacked on #10685 at `eeaabe1083aa556f5163d330c7955c2acb9eb40f`. Full CI and the sole reviewer's independent source acceptance remain required; Root owns the final offer and canonical status.

## Exact correction boundary

| File | Correction | Behavior boundary |
|---|---|---|
| `backend/app/tasks/polymarket_ws.py` | Rename the invalid-cadence exception binding from `exc` to `invalid_cadence`, including the explicit raise cause. | Only a local binding name changes. Float parsing, early rejection, error type/message/cause, opt-in period/floor, absent-override behavior, retries, receipt budget and snapshot policy are unchanged. |
| `backend/tests/test_delivery_receipt_10090.py` | PM `_Recording` writes the existing 0.01-second fixture floor into `kw`, then calls the real superclass once. | Retains this test's intended throttle without supplying the same keyword twice when the real PM consumer passes its configured floor. Receipt assertions are unchanged. The Kalshi fixture is untouched. |
| `backend/tests/test_live_blend_tail_receipt_837.py` | `_Recording` writes the existing fixture `throttle` into `kw`, then calls the real superclass once. | Retains the test's existing quiet-tail / repeated-price timing. It does not change the application floor or weaken the receive-mark and receipt assertions. |

The mutation scanner's target-integrity pass was already green. Its broad pass mistook the new parser's generic exception-handler line for `futures_categories_warm_mutations:M9` outside that harness's target. No mutation harness, scanner, ambiguity baseline, allowlist or assertion was changed to make it green.

There is no correction to `live_blend_refresh.py`, Kalshi, bulk writes, publication, snapshot or the consumer price/flush loop. The application delta from the failed head is exactly the two occurrences of one exception-local variable. No private PG/Redis performance or application experiment was repeated: prior private application controls remain evidence at their recorded source boundary, rather than being relabeled as newly executed exact-head integration acceptance.

## Executed author gates

- Red first: the six exact failing tests produced six failures, exit 1 (`red-first.txt`).
- Expanded affected controls: **124 passed**, exit 0 (`controls.txt`): mutation guard 26; delivery receipts 15; live blend tail receipts 24; PM opt-in 19; shared flush cadence 13; consumer stop 7; flush retry 16; startup 4. Existing PM guards cover absent/custom legacy settings, one-second and fractional opt-in, invalid values before I/O, unchanged Kalshi, independent failed-write retry delay, and stop handling.
- Frontend build: exit 0 (`build.txt`). `NEXT_PUBLIC_API_URL=http://127.0.0.1:9` kept build-time API reads local and refused; no served-data or UI acceptance is claimed by this gate. Frontend source is unchanged.
- Frontend typecheck after build: exit 0, **66 errors against baseline 66** (`typecheck.txt`); the baseline was not edited.

One initial combined pytest invocation misspelled the stop-test filename and exited 4 before running tests. It was a harness error; the corrected invocation above ran all 124 controls. Full exact-head CI is pending following the corrected branch push. No merge, deploy, production configuration write, production query, provider collection, new lab, helper or capacity acquisition occurred. Root holds reservation 68331 for this delivery correction.

Gate logs retain the complete output beside this report, with line endings and trailing whitespace normalized. Normalized artifact hashes and original output hashes are in `gate-manifest.json`. The final residue scan also passes both target integrity and the broad sweep after staging the correction. The source and test correction are directly reviewable against the failed head.
