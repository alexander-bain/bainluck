# The reader walk (#12528)

The walk asks the live site what a reader would ask and sorts every answer. It exists
because nothing else in the repo checks a reader's journey end to end: tests check code,
sentinels check data, and a search that returns nothing for "celtics next three games"
passes both.

## What's here

- `queries/search-v1.json`: 37 searches in six classes (a team by name, an alias or typo,
  a team plus a market, a set, other topics, and honesty about ambiguous or nonsense
  asks). Each one says what the reader expects and carries a small check.
- `tools/reader_walk/walk.py`: the runner. Stdlib only, GET only, public pages only. It
  never signs in and reads no secret.
- `backend/tests/test_reader_walk_12528.py`: the checks and the sorting, tested offline
  on canned answers. CI never calls the live site.

## Four states, never two

| State | Meaning |
|---|---|
| pass | a clean answer whose first screen holds what the reader meant |
| fail | a clean answer that does not |
| degraded | the API said part of the answer is missing, and still said so on one retry |
| error | no HTTP 200 after one retry |

A degraded or failed read is never counted as an empty answer and never as a speed
sample (Builder B's point on #12290). "asdfgh" passes only on a clean, empty answer.

## Running it

```
python3 tools/reader_walk/walk.py --out /tmp/reader-walk.json
```

It prints the counts, the speed of clean first calls and of repeats, and every search
that didn't pass. The `--out` file keeps the raw answer for anything that isn't a pass,
so a wrong or empty answer comes with its payload.

Runs are posted on #12528. There is no workflow that reads production from CI
(decision 115-A); Fable runs the walk and posts the result.

## Two speed numbers, kept apart

The walk reports what the reader's network sees: the first (cold) call and a repeat.
Server-side time is a different number with its own targets (#11933). They are reported
side by side and never mixed.

## The first three runs (Tue Nov 10, 2026, from one client with about 125 ms of network travel)

| Run | Pass | Fail | Degraded | Cold, median | Cold, 95th |
|---|---|---|---|---|---|
| 7:40 AM PT (version 0, two states) | 28 | 9 | counted as pass or fail | 1.5 s | not kept |
| 8:36 AM PT (version 1) | 22 | 10 | 5 | 1.8 s | 4.2 s |
| 9:02 AM PT (this tool) | 27 | 10 | 0 | 1.6 s | 3.6 s |

By hand, the 7:40 AM run put what the reader meant at the very top for 23 of 37.

The same search can change state between runs with no deploy in between. "super bowl patriots"
passed at 7:40 AM, then came back as a clean, empty answer at 8:36 AM and again at 9:03 AM,
and returned its card two minutes after each (#12540). That is why a run keeps the raw
answer for anything that isn't a pass.

## What the checks are, and are not

The checks are the **lenient** reading: the expected thing is somewhere on the first
screen. The acceptance for search that opens sets (#12290) is the **strict** reading, 34
of 37 with the thing the reader meant at the top. Strict needs the order a reader
actually sees, which the Search page decides, not the API's lists. It arrives with the
browser walk; until then the strict count is judged by hand and says so.

One search is tied to the calendar ("nfl week 10") and is marked `refresh`. It gets
moved forward at the weekly look.

## Next

- Open-and-back: search, open a card, go back, land where you were.
- Watch a number change: hold a live page and see the number move without a reload.
- The strict checks, from the rendered Search page.
