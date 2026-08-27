#!/usr/bin/env python3
"""PLANT PASS for UX-P139 — break each new guard on purpose, one at a time.

A guard that has never failed is a guard nobody has checked.  Ruling: a plant
must hit the RENDER or the SERVING path, not only a pure helper, because a
library-only assertion stays green the day the component stops printing the
feature (`reference_plant_must_hit_the_render`).

Each plant:
  1. writes one targeted mutation into a source file,
  2. runs the test that is supposed to catch it,
  3. asserts the run came back RED with **exit code exactly 1** (gotcha #124:
     1 is a result; 2/3/4/5/127/137/143 are stories about the harness),
  4. restores the file and verifies it is byte-identical.

Usage:  python3 scripts/plant_ux_p139.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / "frontend"

#: (label, file, find, replace, command, cwd)
PLANTS: list[tuple[str, Path, str, str, list[str], Path]] = [
    # ── The amendment's core: wrong-future placement must refuse the file ────
    (
        "wrong-future: a reach-QF market in the SF cell stops being a finding",
        ROOT / "app/utils/tournament_register.py",
        'if block.get("question_round") != round_name:\n            findings.append("REACH_ROUND_MISMATCH")',
        'if False:\n            findings.append("REACH_ROUND_MISMATCH")',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    (
        "wrong-future: a market naming a different player stops being a finding",
        ROOT / "app/utils/tournament_register.py",
        'if subject != normalize_player_name(player.get("display_name")):\n                findings.append("REACH_SUBJECT_MISMATCH")',
        'if False:\n                findings.append("REACH_SUBJECT_MISMATCH")',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    (
        "wrong-future findings stop being structural (served with a warning)",
        ROOT / "app/utils/tournament_register.py",
        '    "REACH_ROUND_MISMATCH",\n    "REACH_DRAW_MISMATCH",',
        '    "REACH_DRAW_MISMATCH",',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    # ── No cell is ever blank ───────────────────────────────────────────────
    (
        "an unlinked cell silently becomes a censused absence",
        ROOT / "app/utils/tournament_grid.py",
        'return _cell(\n            CELL_UNLINKED,\n            note=f"Registered but unpriced: {\'; \'.join(unlinked)}",',
        'return _cell(\n            CELL_NO_MARKET,\n            note=f"Registered but unpriced: {\'; \'.join(unlinked)}",',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    (
        "a player with no cell for a column renders nothing instead of an alarm",
        ROOT / "app/utils/tournament_grid.py",
        'cells[name] = _cell(\n                    CELL_UNREGISTERED,',
        'cells[name] = _cell(\n                    CELL_NO_MARKET,',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    (
        "the alarm counter stops counting",
        ROOT / "app/utils/tournament_grid.py",
        "alarms = sum(counts.get(state, 0) for state in ALARM_STATES)",
        "alarms = 0",
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    # ── The two evals ───────────────────────────────────────────────────────
    (
        "the sum check silently rescales an over-summing column",
        ROOT / "app/utils/tournament_grid.py",
        'verdict = (\n                "pass"\n                if abs((ratio or 0.0) - 1.0) <= COLUMN_SUM_TOLERANCE',
        'verdict = (\n                "pass"\n                if True',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    (
        "monotonicity lets an unpriced hole bridge its two neighbours",
        ROOT / "app/utils/tournament_grid.py",
        '(key, row["cells"][key]["probability"])\n            for key in order\n            if row["cells"].get(key, {}).get("probability") is not None',
        '(key, row["cells"][key].get("probability") or 0.0)\n            for key in order\n            if True',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    # ── Freshness: the AND over contributors ────────────────────────────────
    (
        "a cell takes its freshness from the NEWEST leg instead of the oldest",
        ROOT / "app/utils/tournament_grid.py",
        "age = governing_age_hours(observed_times, now)",
        "age = _age_hours(freshest_observation(observed_times), now)",
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    # ── The committed register's properties ─────────────────────────────────
    (
        "the committed register gets a reach cell wired to the wrong player",
        ROOT / "data/tournament_registers/us-open-2026.json",
        '"question_round": "R16",\n     "question_draw": "mens-singles",\n     "question_subject": "Alejandro Tabilo",\n     "question": "Will Alejandro Tabilo advance to the Round of 16 in Men\'s Singles at the 2026 US Open?",',
        '"question_round": "R16",\n     "question_draw": "mens-singles",\n     "question_subject": "Somebody Else",\n     "question": "Will Alejandro Tabilo advance to the Round of 16 in Men\'s Singles at the 2026 US Open?",',
        ["python3", "-m", "pytest", "tests/test_tournament_grid.py", "-q"],
        ROOT,
    ),
    # ── The refresh task ────────────────────────────────────────────────────
    (
        "the price refresh stops walking reach cells (336 markets unrefreshed)",
        ROOT / "app/tasks/tournament_price_refresh.py",
        'for reach in register.get("reaches") or []:\n        if isinstance(reach, dict):\n            for block in reach.get("sources") or []:\n                add(block)',
        "for reach in []:\n        pass",
        ["python3", "-m", "pytest", "tests/test_tournament_price_refresh.py", "-q"],
        ROOT,
    ),
    (
        "the sentinel stops observing reach identities (336 unwatched)",
        ROOT / "app/tasks/tournament_register_sentinel.py",
        "for block in priced_source_blocks(register)",
        "for block in (b for p in register.get('players', []) if isinstance(p, dict) for b in (p.get('sources') or []))",
        ["python3", "-m", "pytest", "tests/test_tournament_register_sentinel.py", "-q"],
        ROOT,
    ),
    # ── The results join ────────────────────────────────────────────────────
    (
        "a result attaches on ONE name instead of the pair",
        ROOT / "app/utils/tournament_slate.py",
        "if len(entries) != 2 or any(entry is None for entry in entries):",
        "if False:",
        ["python3", "-m", "pytest", "tests/test_tournament_slate.py", "-q"],
        ROOT,
    ),
    (
        "a partial set score prints as a final one",
        ROOT / "app/services/espn_tennis.py",
        "if not a_sets or len(a_sets) != len(b_sets):\n        return None",
        "if not a_sets:\n        return None",
        ["python3", "-m", "pytest", "tests/test_espn_tennis.py", "-q"],
        ROOT,
    ),
    (
        "the score prints loser-first",
        ROOT / "app/services/espn_tennis.py",
        "winner_first = scored if a.get(\"winner\") else [scored[1], scored[0]]",
        "winner_first = scored",
        ["python3", "-m", "pytest", "tests/test_espn_tennis.py", "-q"],
        ROOT,
    ),
    # ── FRONTEND: every plant must hit the RENDER ───────────────────────────
    (
        "RENDER: the semifinal column is dropped again by a width cap",
        FRONTEND / "components/tournament/PlayoffGrid.tsx",
        "{grid.columns.map((column) => (\n              <span\n                key={column.key}",
        "{grid.columns.slice(0, 3).map((column) => (\n              <span\n                key={column.key}",
        ["npx", "jest", "--testPathPatterns=playoffGrid|usOpen", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: a no-market cell goes back to printing a dot",
        FRONTEND / "lib/playoffGrid.ts",
        'case "no_market":\n      // NOT a dot and NOT a dash.',
        'case "no_market":\n      return "\\u00b7";\n      // NOT a dot and NOT a dash.',
        ["npx", "jest", "--testPathPatterns=playoffGrid|usOpen", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the alarm banner stops rendering",
        FRONTEND / "components/tournament/PlayoffGrid.tsx",
        "{grid.alarmCells > 0 && (\n        <div",
        "{false && (\n        <div",
        ["npx", "jest", "--testPathPatterns=playoffGrid", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the sum check disappears from the page",
        FRONTEND / "components/tournament/PlayoffGrid.tsx",
        "<SumCheck grid={grid} />",
        "<></>",
        ["npx", "jest", "--testPathPatterns=playoffGrid|usOpen", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the grid drops a column instead of scrolling (ruling 5)",
        FRONTEND / "lib/playoffGrid.ts",
        "export const GRID_COLUMN_WIDTH_PX = 46;",
        "export const GRID_COLUMN_WIDTH_PX = 60;",
        ["npx", "jest", "--testPathPatterns=playoffGrid", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the draw panel stops saying WHEN (item 1)",
        FRONTEND / "components/tournament/TournamentBracket.tsx",
        '<span data-testid="draw-release-label">{drawReleaseLabel}</span>',
        "<span />",
        ["npx", "jest", "--testPathPatterns=playoffGrid|usOpen", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the chart loses its x-axis labels (item 6)",
        FRONTEND / "components/tournament/ContenderChart.tsx",
        '          data-testid="chart-axis"\n          data-ticks={ticks.length}',
        '          data-testid="chart-axis-REMOVED"\n          data-ticks={ticks.length}',
        ["npx", "jest", "--testPathPatterns=tournamentAxisAndResults", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the axis is drawn by calendar position, not domain index",
        FRONTEND / "lib/contenderChart.ts",
        "x: (index * geometry.width) / span,",
        "x: (index * geometry.width) / (span + 1),",
        ["npx", "jest", "--testPathPatterns=tournamentAxisAndResults", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the score stops printing beside the outcome (item 9)",
        FRONTEND / "components/tournament/TournamentResults.tsx",
        '            data-testid="result-score"\n          >\n            {result.score}',
        '            data-testid="result-score"\n          >\n            {null}',
        ["npx", "jest", "--testPathPatterns=tournamentAxisAndResults", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: a retirement prints as a result with a silent missing score",
        FRONTEND / "components/tournament/TournamentResults.tsx",
        '            data-testid="result-no-score"',
        '            data-testid="result-no-score-REMOVED"',
        ["npx", "jest", "--testPathPatterns=tournamentAxisAndResults", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the empty questions section goes back to a dashed whisper (item 10)",
        FRONTEND / "components/tournament/TournamentProps.tsx",
        'className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3.5"\n          data-testid="props-empty"',
        'className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-3.5 py-3.5"\n          data-testid="props-empty"',
        ["npx", "jest", "--testPathPatterns=usOpenBoardCapture", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: the click-through link renders without a registered event id (item 7)",
        FRONTEND / "components/tournament/TournamentMatches.tsx",
        "{entry.eventId !== null && (\n            <a",
        "{true && (\n            <a",
        ["npx", "jest", "--testPathPatterns=tournamentMatches", "--silent"],
        FRONTEND,
    ),
    (
        "RENDER: doubles stops being accepted as a draw (item 12)",
        FRONTEND / "lib/tournamentResults.ts",
        '  "mixed-doubles": "Mixed Doubles",\n};',
        "};",
        ["npx", "jest", "--testPathPatterns=tournamentAxisAndResults", "--silent"],
        FRONTEND,
    ),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    for index, (label, path, find, replace, command, cwd) in enumerate(PLANTS, start=1):
        original = path.read_bytes()
        before = digest(path)
        text = original.decode()

        if text.count(find) != 1:
            failures.append(
                f"{index}. {label}: anchor found {text.count(find)}x (need exactly 1) in {path.name}"
            )
            continue

        path.write_text(text.replace(find, replace))
        try:
            proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
            code = proc.returncode
        finally:
            path.write_bytes(original)

        restored = digest(path) == before
        # gotcha #124: 1 is a RESULT. Anything else is a story about the harness.
        red = code == 1
        status = "RED" if red else f"NOT-RED (exit {code})"
        print(f"{index:2d}. [{status}] {label}")
        if not red:
            failures.append(f"{index}. {label}: exit {code}\n{proc.stdout[-1500:]}")
        if not restored:
            failures.append(f"{index}. {label}: FILE NOT RESTORED — {path}")

    print()
    if failures:
        print(f"{len(failures)} PLANT(S) DID NOT BEHAVE:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"all {len(PLANTS)} plants went red at exit 1, every file restored byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
