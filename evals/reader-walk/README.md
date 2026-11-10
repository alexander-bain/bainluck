# The reader walk (#12528)

The walk asks the live site what a reader would ask and sorts every answer. It exists
because nothing else in the repo checks a reader's journey end to end: tests check code,
sentinels check data, and a search that returns nothing for "celtics next three games"
passes both.

## What's here

- `queries/search-v1.json`: 37 searches in six classes (a team by name, an alias or typo,
  a team plus a market, a set, other topics, and honesty about ambiguous or nonsense
  asks). Each one says what the reader expects, carries a check that names that object,
  and gives an example answer row that must pass.
- `tools/reader_walk/walk.py`: the runner. Stdlib only, GET only, public pages only. It
  never signs in and reads no secret.
- `backend/tests/test_reader_walk_12528.py`: the checks and the sorting, tested offline
  on canned answers with the clock passed in. CI never calls the live site.

## Four states, never two

| State | Meaning |
|---|---|
| pass | a clean answer that holds the thing the reader asked for |
| fail | a clean answer that does not |
| degraded | the API said part of the answer is missing, and still said so on one retry |
| error | no HTTP 200 after one retry |

A degraded or failed read is never counted as an empty answer and never as a speed
sample (Builder B's point on #12290). "asdfgh" passes only on a clean, empty answer.

## A check names the object, not a word in its title

The first draft matched words in titles. Builder B's review (#12541) showed six searches
where an unrelated answer passed: "nba champion" passed on "NBA Finals MVP", and "nba
tonight" passed on a Premier League match. So every check now names what was asked for:

- a team by its `slug`, and where it must rank inside the teams list;
- a collection by its `slug`, or an event by its `key`;
- a market by its `id`, and for a team-plus-market search, that team among the card's
  outcomes;
- games by sport and by a start window around the run's clock ("tonight" is from six
  hours ago to eighteen hours ahead).

A check that only matches words is still allowed, and is reported apart as `words`: a
heuristic, never proof, never counted toward an acceptance number. Today no committed
check is words-only, and a test fails if one is added without saying so.

Two tests keep this honest: no committed check passes on an unrelated answer, and every
committed check passes on its own example row.

Market ids and week numbers move, so those searches carry a `refresh` note. They get
moved forward at the weekly look.

## What a pass does not say

It does not say where on the page the thing lands. The order a reader sees is decided by
the Search page, not by the API's lists, and it is the browser walk's job. Until that
exists, "at the top" is judged by hand and says so.

## Running it

```
python3 tools/reader_walk/walk.py --out /tmp/reader-walk.json
```

It prints the counts, how many passes are proved by fields, the speed of clean first
calls and of repeats, and every search that didn't pass. The `--out` file keeps the raw
answer for anything that isn't a pass, so a wrong or empty answer comes with its payload.

Runs are posted on #12528. There is no workflow that reads production from CI
(decision 115-A); Fable runs the walk and posts the result.

## Two speed numbers, kept apart

The walk reports what the reader's network sees: the first (cold) call and a repeat.
Server-side time is a different number with its own targets (#11933). They are reported
side by side and never mixed.

## The first runs (Tue Nov 10, 2026, from one client with about 125 ms of network travel)

| Run | Checks | Pass | Fail | Degraded | Cold, median | Cold, 95th |
|---|---|---|---|---|---|---|
| 7:40 AM PT | words in titles, two states | 28 | 9 | counted as pass or fail | 1.5 s | not kept |
| 8:36 AM PT | words in titles | 22 | 10 | 5 | 1.8 s | 4.2 s |
| 9:02 AM PT | words in titles | 27 | 10 | 0 | 1.6 s | 3.6 s |
| 9:25 AM PT | the object by its fields | 22 | 10 | 5 | 1.9 s | 4.4 s |

The first three rows are history, not a baseline: their checks could pass on the wrong
answer. The baseline is the last row.

The same search can change state between runs with no deploy in between. "super bowl
patriots" passed at 7:40 AM, then came back as a clean, empty answer at 8:36, 9:03 and
9:26 AM, and returned its card when asked again two minutes after the 9:03 run (#12540).
That is why a run keeps the raw answer for anything that isn't a pass, and why an
acceptance has to hold on every run of a day, not on a good one.

"games tonight" is the search the stricter checks caught: it returns games, but none
that start tonight.

## Next

- The browser walk: where the thing lands on the rendered Search page.
- Open and back: search, open a card, go back, land where you were.
- Watch a number change: hold a live page and see the number move without a reload.
