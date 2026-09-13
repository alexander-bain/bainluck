"""Time the twin fold on the biggest real page, master vs #6007.

The fold runs above everything on `/api/feed`, so a change that widens what
`_name_clusters` asks has to be priced rather than assumed cheap. #5964 measured
`soccer_other` (the largest bucket in the system) and quoted both regimes; this
does the same on the same population so the two numbers are comparable.

    python3 tools/time_6007_fold.py /tmp/pop_other.json
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "tools")
from replay_6007_date_only_fold import load  # noqa: E402


def main() -> int:
    sys.path.insert(0, "backend")
    from app.utils import event_twin_fold
    from app.utils.event_twin_fold import fold_twin_events

    rows = load(sys.argv[1:])
    print(f"{len(rows)} rows")

    def once(clear: bool) -> float:
        if clear:
            event_twin_fold._pair_matches.cache_clear()
        # Fresh objects each round: the fold stamps rows it corrects, and a
        # re-used population would time an already-recovered page.
        population = load(sys.argv[1:])
        start = time.perf_counter()
        fold_twin_events(population)
        return (time.perf_counter() - start) * 1000

    once(clear=True)  # discard: imports and first-touch pages are not the page
    for round_no in (1, 2, 3, 4):
        cold = once(clear=True)
        warm = once(clear=False)
        print(f"round {round_no}: cold {cold:.2f}ms  warm {warm:.2f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
