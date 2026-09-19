#!/usr/bin/env python3
"""Q477 mutation battery: a fixture token is an identity, and only a fixture's.

The suite passing proves the code runs. It does not prove the code is PINNED,
and on this change the unsafe direction is not a broken page — it is an
ABSORPTION, one fixture claiming another's identity (ruling 048, gotcha #32).
So most mutants below read as a tidy-up: drop a length comparison, widen a
table, let a collision do the obvious thing. A SURVIVOR is a hole in the suite
and the fix is the missing assertion, never a deleted mutant.

The defect this pins, in one line: every Kalshi series that prices one football
match carries the SAME fixture token, `is_kalshi_game_level_ticker()` said no
about all of them, so each became a `market` anchor keyed on its own unique
ticker and `/api/leagues/soccer_epl` served eight cards for four games.

Three files are mutated, because the ship spans three:

  app/utils/sport_keys.py            the table and its predicate
  app/utils/provider_anchor_keys.py  the key builder that consults it
  app/services/anchor_channel.py     the link-side writer that never absorbs

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY, never while another pytest is in flight:
a source edit under a running suite produces phantom failures that read as real
reds.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose
NEEDLE is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/kalshi_soccer_match_anchor_mutations.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
KEYS = ROOT / "app" / "utils" / "sport_keys.py"
ANCHOR = ROOT / "app" / "utils" / "provider_anchor_keys.py"
CHANNEL = ROOT / "app" / "services" / "anchor_channel.py"
SUITE = ROOT / "tests" / "test_kalshi_soccer_match_anchors_q477.py"
Q440 = ROOT / "tests" / "test_kalshi_one_ticker_predicate_q440.py"
ANCHOR_SUITE = ROOT / "tests" / "test_provider_anchor_keys.py"
CONSUMER = ROOT / "tests" / "test_anchor_channel_consumer_2213.py"

#: (id, description, old, new, target). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, str, str, str, pathlib.Path]] = [
    # --- A: revert to the blocked bytes ------------------------------------
    (
        "A",
        "the key builder stops consulting the match-series table at all — the "
        "exact bytes CERT graded before this queue",
        "        (is_kalshi_game_level_ticker(raw) or is_kalshi_match_series_ticker(raw))",
        "        is_kalshi_game_level_ticker(raw)",
        ANCHOR,
    ),
    # --- B: the table, widened in the unsafe direction ---------------------
    (
        "B",
        "'advance' joins the suffixes — a two-legged UCL tie becomes a fixture",
        '''    "2h", "2hbtts", "2hspread", "2htotal",''',
        '''    "2h", "2hbtts", "2hspread", "2htotal", "advance",''',
        KEYS,
    ),
    (
        "C",
        "the bare league stem joins the suffixes as an empty string — every "
        "season future under the stem becomes a fixture anchor",
        '''    "game", "spread", "total", "btts", "score", "ftts",''',
        '''    "", "game", "spread", "total", "btts", "score", "ftts",''',
        KEYS,
    ),
    (
        "D",
        "the Champions League stem is added back — the namespace names no sport",
        '''    "kxligue1": "soccer_france_ligue_one",
}''',
        '''    "kxligue1": "soccer_france_ligue_one",
    "kxucl": "soccer_uefa_champions_league",
}''',
        KEYS,
    ),
    (
        "E",
        "the second divisions are swept in by truncating a stem to 'kxlaliga2'",
        '''    "kxepl": "soccer_epl",
    "kxlaliga": "soccer_spain_la_liga",''',
        '''    "kxepl": "soccer_epl",
    "kxlaliga": "soccer_spain_la_liga",
    "kxlaliga2": "soccer_spain_la_liga",''',
        KEYS,
    ),
    # --- F/G: the longest-prefix rule inside the new predicate -------------
    (
        "F",
        "the futures comparison is dropped — a longer futures prefix can no "
        "longer out-rank a match-series one",
        """    if not longest_match:
        return False
    return longest_match > kalshi_futures_prefix_len(external_id)""",
        """    if not longest_match:
        return False
    return True""",
        KEYS,
    ),
    (
        "G",
        "a TIE becomes game-level — the exact rule Q440 fixed, one predicate over",
        "    return longest_match > kalshi_futures_prefix_len(external_id)",
        "    return longest_match >= kalshi_futures_prefix_len(external_id)",
        KEYS,
    ),
    (
        "H",
        "`startswith` becomes a substring test — `kxeplgame` matches anywhere",
        """            for p in KALSHI_MATCH_SERIES_TO_SPORT_KEY
            if ext_lower.startswith(p)""",
        """            for p in KALSHI_MATCH_SERIES_TO_SPORT_KEY
            if p in ext_lower""",
        KEYS,
    ),
    # --- I: the shared predicate is widened after all ----------------------
    (
        "I",
        "the shared predicate is widened too — the parked matcher change ships "
        "silently alongside the identity change",
        """    longest_game = max(
        (len(p) for p in KALSHI_GAME_TICKER_PREFIXES if ext_lower.startswith(p)),
        default=0,
    )
    if not longest_game:
        return False
    return longest_game > kalshi_futures_prefix_len(external_id)


def is_kalshi_match_series_ticker(external_id: str) -> bool:""",
        """    longest_game = max(
        (
            len(p)
            for p in (
                *KALSHI_GAME_TICKER_PREFIXES,
                *KALSHI_MATCH_SERIES_TO_SPORT_KEY,
            )
            if ext_lower.startswith(p)
        ),
        default=0,
    )
    if not longest_game:
        return False
    return longest_game > kalshi_futures_prefix_len(external_id)


def is_kalshi_match_series_ticker(external_id: str) -> bool:""",
        KEYS,
    ),
    # --- J/K: the key builder's other two conditions -----------------------
    (
        "J",
        "the fixture token stops being required — a season ticker under a "
        "match-series prefix would anchor on an empty id",
        """        and game_id
        and sport_key""",
        """        and sport_key""",
        ANCHOR,
    ),
    (
        "K",
        "the sport qualifier is dropped from the anchor id — one bare token, "
        "every league, the bare-prefix ruling reversed",
        '''            source_id=f"{sport_key}:{game_id}",''',
        '''            source_id=f"{game_id}",''',
        ANCHOR,
    ),
    # --- L/M/N: the link-side writer ---------------------------------------
    (
        "L",
        "the link writer stops refusing market-kind keys — a row per linked "
        "market, resolving nothing",
        """    key = anchor_key_for_claim(source, provider_id)
    if key is None or not key.may_anchor_absorption:""",
        """    key = anchor_key_for_claim(source, provider_id)
    if key is None:""",
        CHANNEL,
    ),
    (
        "M",
        "the link writer TAGS on collision — the real scored row is branded a "
        "duplicate of its own twin and disappears from the league rails",
        """    if result.outcome == COLLISION:
        logger.info(""",
        """    if result.outcome == COLLISION:
        from app.services.event_registry import _tag_duplicate_of

        await _tag_duplicate_of(session, event_id, result.canonical_event_id)
        logger.info(""",
        CHANNEL,
    ),
    (
        "N",
        "the link writer becomes a no-op that still reports a key — the "
        "schedule-derived row never joins the channel",
        """    result = await record_anchor(
        session,
        event_id=event_id,
        key=key,
        claim_context={"source": source, "established_by": "matcher_link"},
    )""",
        """    result = AnchorWriteResult(outcome=NO_KEY, key=key)""",
        CHANNEL,
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            str(Q440),
            str(ANCHOR_SUITE),
            str(CONSUMER),
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def _main() -> int:
    originals = {p: p.read_text() for p in (KEYS, ANCHOR, CHANNEL)}
    print(
        f"denominator: {len(MUTANTS)} mutants queued against "
        f"{KEYS.name} + {ANCHOR.name} + {CHANNEL.name}"
    )
    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    print("baseline: suite GREEN on the unmutated tree\n")

    killed, survived, broken = [], [], []
    try:
        for mid, desc, old, new, target in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is a no-op — NOT APPLIED"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED")
                continue
            target.write_text(mutated)
            # Prove the mutation is actually on disk before believing its
            # result: a mutant that failed to apply reports green as a survivor.
            if target.read_text() != mutated:
                target.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED on disk")
                continue
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:5} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:5} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      pytest exit {rc} — the gate never ran"
                )
    finally:
        for path, text in originals.items():
            path.write_text(text)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(broken)} harness failures"
    )
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    if broken:
        for mid, why in broken:
            print(f"  BROKEN {mid}: {why}")
        return 2
    return 1 if survived else 0


def main() -> int:
    with guarded_targets(
        [KEYS, ANCHOR, CHANNEL],
        "/tmp/q477_kalshi_soccer_match_anchor_guard_backups",
        "kalshi_soccer_match_anchor",
    ):
        return _main()


if __name__ == "__main__":
    sys.exit(main())
