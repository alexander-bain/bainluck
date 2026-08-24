#!/usr/bin/env python3
"""What does the F3 rewrite actually MOVE, beyond the specimens it was aimed at?

The C-F3-CATEGORIZE-1 cert asks the fix to prove its guards. This asks the other
question — the one guards structurally cannot answer: over the whole frozen corpus,
which titles change category, and are the changes the intended ones?

A guard suite says "the specimens I chose now behave". A census says "and here is
everything ELSE that moved." The second is where a categorizer rewrite hides its
collateral damage, because every row it silently re-tags is a production row.

Run at each tree and diff the output:

    PYTHONPATH=<tree>/backend python3 backend/scripts/census_f3_movement.py

Prints one ``title\\tcategory`` line per corpus entry, sorted, so a plain ``diff``
of two runs IS the movement census. Exit code is always 0 — this measures, it does
not judge.
"""
from __future__ import annotations

import sys

from app.utils.futures_categorization import categorize_by_rules

# The frozen corpus, inlined rather than imported from the test module: the test file
# does not exist at the parent commit, so importing it would make the census
# un-runnable on exactly the tree it needs to compare against.
TITLES = [
    # C1 mistags — the rows F3 was filed for
    "Premier League Darts: Winner",
    "World Darts Championship winner",
    "PDC World Championship: Winner",
    "Magnus Carlsen to win the Chess World Cup",
    "Chess World Championship winner",
    "T20 World Cup: Winner",
    "ICC T20 World Cup winner",
    "Cricket World Cup: Winner",
    "The Ashes: Series Winner",
    "IPL 2026: Winner",
    "Snooker World Championship winner",
    "World Snooker Championship: Winner",
    "Tour de France: Overall Winner",
    "Giro d'Italia winner",
    "Vuelta a Espana: Winner",
    "Rugby World Cup: Winner",
    "Six Nations: Winner",
    "NRL Premiership winner",
    "AFL Grand Final winner",
    "Handball World Championship winner",
    "Volleyball Nations League winner",
    "Table Tennis World Championship winner",
    "Badminton All England Open winner",
    "Formula 1 Drivers' Championship",
    "MotoGP World Championship winner",
    "NASCAR Cup Series champion",
    "IndyCar Series champion",
    "World Athletics Championships: 100m",
    "Olympic Games: Most gold medals",
    "Winter Olympics: Medal table winner",
    # singular-Dart specimens — must NOT reach darts
    "Jaxson Dart to be drafted in the first round",
    "Jaxson Dart passing yards",
    "Harriet Dart to win her first-round match",
    "Will Harriet Dart reach the second round?",
    # ambiguous-evidence specimens — 'athletics' cuts both ways
    "Oakland Athletics to win the World Series",
    "Oakland Athletics vs Seattle Mariners",
    "World Athletics Championships: Men's 200m",
    # controls that must not regress
    "Super Bowl LX winner",
    "NBA Finals: Champion",
    "Stanley Cup champion",
    "World Series winner",
    "Premier League: Winner",
    "Champions League winner",
    "Wimbledon: Men's Singles Winner",
    "US Open: Winner",
    "The Masters: Winner",
    "Ryder Cup winner",
    "UFC Heavyweight Championship",
    "Kentucky Derby winner",
    "Who will win the 2028 presidential election?",
    "Fed decision in March",
    "Best Picture at the Oscars",
    "Will it rain in NYC tomorrow?",
]


def main() -> int:
    for title in sorted(set(TITLES)):
        try:
            category = categorize_by_rules(title)
        except Exception as exc:  # a crash is a census result, not a reason to stop
            category = f"<RAISED {type(exc).__name__}: {exc}>"
        print(f"{title}\t{category}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
