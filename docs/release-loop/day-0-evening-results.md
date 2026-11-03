# Day 0 evening release-loop results

Historical record for November 2, 2026, as of 7:19 PM PST (UTC-8).
The [final evening record on NOW #11852](https://github.com/alexander-bain/bainluck/issues/11852#issuecomment-6594531976)
is the source for this snapshot. Current priority and status remain on NOW.

The "Final-head CI" column links to CI on each PR's final head before merge.

| PR | Delivered change | Merge commit | Final-head CI |
| --- | --- | --- | --- |
| [#11855](https://github.com/alexander-bain/bainluck/pull/11855) | Prepared protection uses `strict: false` and requires all eight backend shards (16 contexts). | `e560296d149122f0e1a4871b7ecb5ac90f7a30ac` | [41562390206](https://github.com/alexander-bain/bainluck/actions/runs/41562390206) |
| [#11895](https://github.com/alexander-bain/bainluck/pull/11895) | The policy-file approval exit requires Alex's latest label application to follow the head commit's committer date. | `5ce6ffce99245cca45cb866f2b1b341730f96156` | [41565624076](https://github.com/alexander-bain/bainluck/actions/runs/41565624076) |
| [#11898](https://github.com/alexander-bain/bainluck/pull/11898) | Alex merged the two reviewer inputs: `show_full_output: true` and `model: claude-sonnet-5-5`. The brief was untouched. | `127bdc645af9843429cdc073b8db3b033a0811d7` | [41565951989](https://github.com/alexander-bain/bainluck/actions/runs/41565951989) |
| [#11900](https://github.com/alexander-bain/bainluck/pull/11900) | Four test files address the scheduling and fixture-budget failures reported in #11893. | `448fbb66e37fb4ee38c7948bd2baa0e49da1f727` | [41567246480](https://github.com/alexander-bain/bainluck/actions/runs/41567246480) |
| [#11899](https://github.com/alexander-bain/bainluck/pull/11899) | Removed the Mac-only `.mcp.json` and `.claude/hooks.json` from the repository. | `c3847484e417ff34dc56494da789b7f60d484566` | [41566534391](https://github.com/alexander-bain/bainluck/actions/runs/41566534391) |

Fable's current-head acceptances for the Tier-B changes are recorded on
[#11855](https://github.com/alexander-bain/bainluck/pull/11855#issuecomment-6593652656),
[#11895](https://github.com/alexander-bain/bainluck/pull/11895#issuecomment-6594477623), and
[#11898](https://github.com/alexander-bain/bainluck/pull/11898#issuecomment-6594477828).
The approval-policy change passed 31 local policy tests. The affected test modules
and independent authority deadline controls passed 117 local tests; the
[four historical failure names and local attempts](https://github.com/alexander-bain/bainluck/issues/11852#issuecomment-6594437257)
are recorded on NOW.

## Follow-ups at evening close

- The reviewer still needed a real Tier-B PR event and an inspection of its full
  output. The merged inputs alone did not establish that it produced a review.
- #11893 remained open in Review / Verify for its natural master-CI observation
  window.
- Protection and auto-merge activation remained held for Alex's exact words.
  No `alex-approved` label was applied by Builder B.

The label's timestamp check uses the commit's claimed committer time. Fable
accepted backdating as a non-blocking limitation for launch; attribution also
uses Alex's shared account, so windows must never apply `alex-approved`.
