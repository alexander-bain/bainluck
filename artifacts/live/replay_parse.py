#!/usr/bin/env python3
"""live/039 — replay `extract_matchup` over REAL market names, one arm per process.

Two arms in ONE interpreter would share `app.utils.prediction_market_matching`
in `sys.modules` and the second import would be a no-op, so the "before" arm
would silently grade the "after" code and report a clean diff no matter what
was changed. Each arm therefore runs as its own process, loading the module
under its canonical name from an explicit path before anything else can import
it.

Usage: replay_parse.py <module_path> <names.jsonl> <out.json>
"""
import importlib.util
import json
import sys


def load_under_canonical_name(path: str):
    name = "app.utils.prediction_market_matching"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec so any self-referential import resolves to this copy.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module_path, names_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    pm = load_under_canonical_name(module_path)

    seen = set()
    names = []
    for line in open(names_path):
        line = line.strip()
        if not line.startswith("{"):
            continue
        row = json.loads(line)
        key = (row["source"], row["name"])
        if key in seen:
            continue
        seen.add(key)
        names.append(key)
    names.sort()

    out = {}
    for source, name in names:
        matchup = pm.extract_matchup(name)
        out[f"{source}␟{name}"] = (
            [matchup.team_a, matchup.team_b, matchup.yes_team, matchup.format_type]
            if matchup
            else None
        )
    json.dump(out, open(out_path, "w"))
    print(f"{module_path}: parsed {len(out)} names, "
          f"{sum(1 for v in out.values() if v)} yielded a matchup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
