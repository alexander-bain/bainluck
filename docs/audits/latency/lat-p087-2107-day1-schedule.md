# LAT-P087 item 2 — #2107 day 1 cannot be scheduled: there is no deploy-free date

The directive says *"scheduled for the next deploy-free date with `--counts-as-day` and
`--last-release-at`, exactly as you set up. Do not force it."* I did not force it. I went to pick
the date and **there isn't one**, and the reason is measurable rather than a matter of waiting a
bit longer.

## What the instrument requires

`grade_window` (`backend/scripts/watch_2107_feed_500s.py:436-515`) marks a window `INCONCLUSIVE`
whenever arm A's 24 h Sentry lookback contains a release — ruling 130, straddle. `--last-release-at`
does **not** relax that; it *decides* it exactly (`:337-350`): under 24 h ⇒ `STRADDLED`, over ⇒
`CLEAR`. And `summarize` (`:525-600`) requires **seven consecutive UTC calendar dates**, where a
single FAILED window anywhere on a date disqualifies that date and a calendar gap ends the streak.

So one bankable day needs **a ≥24 h production deploy pause ending inside that day**, and seven
consecutive ones need an unbroken pause of roughly **eight days**.

## The measured cadence, 2026-08-17T22:51Z → 2026-08-24T21:40Z

```
code deploys      : 57
intervals         : 56
intervals >= 24h  : 1        (2026-08-21T18:37Z, 51.2h)
median gap        : 0.61h    (37 minutes)
UTC dates with a deploy: 08-17 08-18 08-19 08-20 08-21 08-23 08-24   (6 of 7)
```

**One interval in fifty-six clears the bar, and that one is not natural.** The 51.2 h gap across
2026-08-22 exists only because of the deploy freeze imposed for this program's own integration.
The single deploy-free UTC date in the window is an artifact of the lane, not of how this repository
normally ships.

At a 37-minute median, the probability of an organic 24 h pause is not small — it is zero over the
observed week.

## So the schedule is: unschedulable, pending a decision that is not mine

Two exits, and both are rulings rather than repairs:

**A. Freeze production deploys for ~8 days** and run the window daily with the command below. This
buys a real seven-day falsifier at the price of eight days of no shipping. That is a large bill and
it is Alex's to accept, not mine to assume.

**B. Re-specify arm A** to `max(deploy_time, window_start)` instead of a flat 24 h, and record both
counts so the narrowing is visible in the artifact. This is the proposal already written up in
`lat-p085-2107-day1.md` §"Proposed for a ruling" and still unruled.

There is a real argument for B that I want on the record, because it is not merely convenience: a
**zero** count from arm A under a straddle is arguably still attributable to the live slug. Zero
events over the post-release exposure is zero events, whatever the pre-release hours contained.
The straddle only genuinely poisons a **non-zero** count, where a reader cannot tell which slug
produced it. Day 1's actual failure was exactly that shape — one BAINLUCK-ZK event that fired
10 h 48 m *before* the fix deployed, failing a window measuring the hour *after* it.

I did not implement B. It **relaxes a falsifier guarding a P1's closure**, and this lane's standing
bar is that closure needs measured evidence; widening the gate that enforces that bar is not a
change I make on my own authority. It is also worth being precise that B is not free — it trades a
guarantee ("no events in 24 h") for a weaker one ("no events since the deploy"), and on a
short post-deploy window that weaker claim can be satisfied by a bug that simply has not been hit
yet. B should carry a minimum-exposure floor if it is adopted.

## Current state, read not assumed

```
windows recorded: 1   day-windows: 0   distinct UTC dates: 0
NOTE: 1 window(s) recorded with is_day=false — these can NEVER bank.
consecutive clean days: 0/7
VERDICT: OPEN — 7 more clean day(s) required.
```

`--summarize` EXIT CODE 1. **Streak 0/7. Day 1 has still not happened.** Merge is not closure;
neither is a schedule.

## The exact command, ready for the first qualifying date

Nothing about it is blocked — it is the *date* that does not exist. When one does:

```bash
source ~/.claude/.env
python3 backend/scripts/watch_2107_feed_500s.py \
  --minutes 60 --counts-as-day \
  --last-release-at "$(heroku releases -a bainluck -n 30 --json \
      | python3 -c "import sys,json;print(max(r['created_at'] for r in json.load(sys.stdin) if r.get('description','').startswith('Deploy')))")"
echo "EXIT CODE: $?"
```

Read `counts_toward_seven` out of the recorded row. Bank only on a true.
`--last-release-at` is computed from Heroku rather than typed, so the window cannot be certified
against a release time someone remembered wrong — but note it will correctly return `STRADDLED` and
grade the window `INCONCLUSIVE` on any of the dates above, which is the whole finding.
