#!/usr/bin/env python3
"""Generate an explicit championship-grid register (Queue 295).

The grids used to decide *at request time* which market feeds each cell, by
fuzzy matching tickers, names, and team spellings. That guessing is what let a
settled Genesis Scottish Open market feed a live Rocket Classic make-cut cell
(83% of golf cells were fed by the wrong tournament on 2026-08-01). This script
does the matching ONCE, records the evidence for every decision, and writes a
versioned file the serving path then reads dumbly.

Two rules govern the output:

1. **Never guess.** An outcome that cannot be resolved to exactly one canonical
   entity, or a cell with two competing candidates, is NOT written as a mapping.
   It goes in the ``--report`` file as an unresolved question for a human. A
   register with a wrong entry is worse than one with a missing entry, because
   ``missing`` renders an honest empty cell.
2. **Deterministic.** Same database state in, byte-identical file out — entries
   are sorted and keys are dumped sorted; the only non-reproducible field is
   ``generated_at``. That is what makes ``--diff`` meaningful.

The observation logic itself lives in ``app/services/grid_register_source.py``,
shared with the daily drift sentinel so the two can never disagree about what
the sources currently say.

Usage:
    heroku run --app bainluck python3 backend/scripts/generate_grid_register.py --league nba --dry-run
    heroku run --app bainluck python3 backend/scripts/generate_grid_register.py --league nba --write
    heroku run --app bainluck python3 backend/scripts/generate_grid_register.py --league nba --diff
"""
import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.league_configs import get_all_league_slugs, get_league_config  # noqa: E402
from app.services.database import async_session_maker  # noqa: E402
from app.services.grid_register_source import generate_register  # noqa: E402
from app.utils.grid_register import (  # noqa: E402
    REGISTER_DIR,
    build_contract,
    register_filename,
    validate_register,
)


async def _generate(league_slug: str):
    config = get_league_config(league_slug)
    if not config:
        raise SystemExit(f"unknown league {league_slug!r}; have {get_all_league_slugs()}")
    async with async_session_maker() as session:
        register, unresolved = await generate_register(session, config)
    return config, register, unresolved


def _write_atomic(register: dict, directory: Path) -> Path:
    """Write via temp + rename so a crash can never leave a half register."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / register_filename(register["league"], register["season"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(register, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    return path


def _diff(register: dict, directory: Path) -> None:
    path = directory / register_filename(register["league"], register["season"])
    if not path.is_file():
        print(f"no committed register at {path}")
        return
    old = json.loads(path.read_text())
    key = lambda e: (e["stage"], e["entity_key"], e["source"])  # noqa: E731
    old_cells = {key(e): e for e in old.get("entries", [])}
    new_cells = {key(e): e for e in register["entries"]}
    added = sorted(set(new_cells) - set(old_cells))
    removed = sorted(set(old_cells) - set(new_cells))
    ident = lambda e: (e.get("market_id"), e.get("outcome_id"), e.get("status"))  # noqa: E731
    changed = sorted(
        k for k in set(old_cells) & set(new_cells)
        if ident(old_cells[k]) != ident(new_cells[k])
    )
    print(f"diff vs v{old.get('version')}: +{len(added)} -{len(removed)} ~{len(changed)}")
    for k in changed[:20]:
        print(f"  ~ {k}: {ident(old_cells[k])} -> {ident(new_cells[k])}")
    for k in added[:10]:
        print(f"  + {k}")
    for k in removed[:10]:
        print(f"  - {k}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    parser.add_argument("--write", action="store_true", help="persist the register file")
    parser.add_argument("--dry-run", action="store_true", help="summarise only")
    parser.add_argument("--diff", action="store_true", help="diff against the committed register")
    parser.add_argument("--report", type=Path, help="write unresolved mappings here")
    parser.add_argument("--dir", type=Path, default=REGISTER_DIR)
    args = parser.parse_args()

    config, register, unresolved = asyncio.run(_generate(args.league))

    contract = build_contract({
        config.slug: {
            "season": config.season_pattern,
            "stages": [c.key for c in config.columns],
        },
    })
    findings = validate_register(register, contract)

    counts: dict[str, int] = defaultdict(int)
    for entry in register["entries"]:
        counts[entry["status"]] += 1
    reasons: dict[str, int] = defaultdict(int)
    for row in unresolved:
        reasons[row["reason"]] += 1

    print(
        f"league={register['league']} season={register['season']} "
        f"entries={len(register['entries'])} {dict(sorted(counts.items()))} "
        f"unresolved={len(unresolved)} {dict(sorted(reasons.items()))}"
    )

    if args.report:
        args.report.write_text(json.dumps(unresolved, indent=2, sort_keys=True) + "\n")
        print(f"unresolved report -> {args.report}")

    if findings:
        # Never write an invalid register — the committed baseline is the thing
        # the serving path trusts blindly.
        print("INVALID — refusing to write:", ", ".join(findings))
        return 1

    if args.diff:
        _diff(register, args.dir)

    if args.write and not args.dry_run:
        print(f"wrote {_write_atomic(register, args.dir)}")
    elif not args.diff:
        print("(dry run — pass --write to persist)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
