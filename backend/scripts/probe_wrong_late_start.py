"""Does a wrong-LATE start admit an in-game price as a 'final pre-event' leg?

codex's local correctness check 2 (0148Z directive): *"A late wrong start can
admit in-game prices before eventual resolution; LEAST(start, resolution) alone
doesn't catch that."* This runs the real ``classify_pair`` against that specimen
and its control rather than arguing from the source.

Run: cd backend && python3 -m scripts.probe_wrong_late_start

🪤 THE EXIT CODE IS INVERTED FROM A TEST'S, because this is a REPRODUCTION, not a
gate: **exit 1 = the defect is present** (that is what it prints on
``origin/master`` before CAL-P1333) and **exit 0 = it is gone**. Do not read the
0 this returns on a fixed tree as "the probe passed and found nothing to see" —
read the last line, which says which of the two happened in words.
"""

from datetime import datetime, timedelta, timezone

from app.utils.calibration_paired_prestart import (
    PAIR_PAIRED,
    classify_pair,
    start_refusal,
)

H = timedelta(hours=1)

# One real occasion. The game starts at 19:00 and ends around 22:00; the market
# settles at 22:30. Nothing about these three facts is in dispute.
REAL_START = datetime(2026, 1, 10, 19, 0, tzinfo=timezone.utc)
SETTLEMENT = datetime(2026, 1, 10, 22, 30, tzinfo=timezone.utc)

# The stored start is the market's CLOSE time, not the kickoff (gotcha #14:
# "Kalshi commence_time is often close time, not start"). It is LATE by 4h.
WRONG_LATE_START = datetime(2026, 1, 10, 23, 0, tzinfo=timezone.utc)


class Ev:
    def __init__(self, commence, *, source="espn", completed=None):
        self.commence_time = commence
        self.commence_time_source = source
        self.created_at = (REAL_START - 30 * timedelta(days=1)).replace(tzinfo=None)
        self.completed_at = completed


def snaps():
    """A price a day out, and one taken at 21:45 — deep INSIDE the game."""
    return [
        (REAL_START - 25 * H, 0.50, None, None, "kalshi", REAL_START - 24 * H),
        (
            datetime(2026, 1, 10, 21, 45, tzinfo=timezone.utc),
            0.94,
            0.93,
            0.95,
            "kalshi",
            None,
        ),
    ]


def run(label, event):
    refusal = start_refusal(event, resolution_date=SETTLEMENT)
    klass, early, final = classify_pair(
        snaps(),
        event=event,
        market_source="kalshi",
        resolution_date=SETTLEMENT,
    )
    print(f"  {label}")
    print(f"    commence_time   : {event.commence_time}")
    print(f"    completed_at    : {event.completed_at}")
    print(f"    start_refusal   : {refusal}")
    print(f"    pair_class      : {klass}")
    print(f"    early / final   : {early} / {final}")
    return klass, final


def main():
    print(__doc__.splitlines()[0])
    print(
        f"\n  real start {REAL_START:%H:%M}Z, settles {SETTLEMENT:%H:%M}Z, "
        f"the 21:45Z price is IN-GAME\n"
    )

    print("A. CONTROL — the stored start is the true one:")
    ctrl_class, ctrl_final = run("correct start 19:00Z", Ev(REAL_START))

    print("\nB. SPECIMEN — the stored start is the market CLOSE time, 4h late,")
    print("   and completed_at is NULL (nothing contradicts it):")
    spec_class, spec_final = run("wrong-late start 23:00Z", Ev(WRONG_LATE_START))

    print("\nC. SPECIMEN + completed_at set (the arm that DOES fire):")
    run(
        "wrong-late start, completed_at 22:00Z",
        Ev(
            WRONG_LATE_START,
            completed=datetime(2026, 1, 10, 22, 0, tzinfo=timezone.utc),
        ),
    )

    print("\n" + "=" * 70)
    admitted = spec_class == PAIR_PAIRED and spec_final == 0.94
    if admitted and ctrl_class != PAIR_PAIRED:
        print("DEFECT REPRODUCED: the control refuses the in-game price; the")
        print("wrong-late start ADMITS it as a final PRE-EVENT forecast of 0.94,")
        print("scored against a result that was already all but known.")
        return 1
    print(f"NOT reproduced (control={ctrl_class}, specimen={spec_class}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
