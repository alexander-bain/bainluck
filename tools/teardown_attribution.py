#!/usr/bin/env python3
"""Name the release that tore a task down — across BOTH Heroku apps, over EVERY task.

WHAT THIS IS. The reading half of ``tools/why-was-it-killed.sh``, lifted out of
that script's heredoc so it can be imported and asserted on. The rule itself
still lives in ``app.utils.task_verdict.attribute_teardown`` and is not
re-implemented here; what is here is the two things the rule needs handed to it
correctly, and which the shell got wrong.

WHY IT EXISTS (LAT-P389). Measured on production 2026-09-14 04:1xZ:

* ``tools/why-was-it-killed.sh`` read its task population from
  ``/api/admin/ops-snapshot``'s ``coverage`` block. That block carries exactly
  TWO tasks — ``poll_kalshi`` and ``poll_polymarket``. The fleet runs 120.
  So the tool printed ``2 tasks in coverage, 0 interrupted`` / "No task's last
  run was interrupted. Nothing to attribute." and exited 0, while
  ``futures_price_refresh`` (torn down 03:51:03Z) and ``polymarket_winners``
  (torn down 2026-09-13T23:47:35Z) sat on production reading
  ``terminal: "interrupted"``. A zero produced by the wrong population reads
  exactly like a clean bill of health.

* Since the heavy split (2026-09-11) a task's killer release lives in one of
  TWO apps, and the tool took a single ``--app``. ``futures_price_refresh``
  dies on ``worker-heavy.1``, whose killer ``v18`` exists only in
  ``bainluck-heavy``'s release list; ``polymarket_winners`` dies on
  ``worker-background.1``, whose killer ``v4508`` exists only in ``bainluck``'s.
  Either list alone attributes one and prints "Nothing was deployed in the
  window, so the cause is elsewhere" for the other — an EXONERATION, in the
  direction this whole tool was written to stop being wrong in. That sentence
  is the one LAT-P329's own docstring says the old prose got backwards; a
  single-app read reintroduces it by a different route.

THE DYNO HINT IS A HINT, NOT A KEY. The summary carries the dyno that died
(``worker-heavy.1``), which usually names the app. It is used to search the
likely app FIRST, and then — if that app has no candidate — the other one is
searched anyway, and a hit there is reported with the mismatch stated out loud.
Keying hard on the dyno would bake in a fact that has already moved once: celery
beat ran as ``scheduler`` on the main app until 2026-09-11 and runs on
``bainluck-heavy`` now. An unrecognised dyno therefore searches everything and
says so, rather than picking an app and exonerating the other.

USAGE (as a CLI, called by the shell wrapper):
    teardown_attribution.py <tasks.json> <window_s> <app>=<releases.txt> [...]
    teardown_attribution.py --self-check
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from typing import Any

_REPO_ROOT_ADDED = False


def _ensure_backend_on_path() -> None:
    """Put ``backend/`` on ``sys.path`` so ``app.utils`` imports.

    Done lazily and idempotently rather than at import time: the self-check and
    the CLI both need it, but a caller that has already arranged its own
    ``PYTHONPATH`` (the shell wrapper does) must not get a second entry.
    """
    global _REPO_ROOT_ADDED
    if _REPO_ROOT_ADDED:
        return
    import os

    backend = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"
    )
    if backend not in sys.path:
        sys.path.insert(0, backend)
    _REPO_ROOT_ADDED = True


#: The two apps a scheduled task can die on, main first so a tie in the
#: cross-app search reports the main app's release rather than an arbitrary one.
APPS: tuple[str, ...] = ("bainluck", "bainluck-heavy")

#: Dyno prefix -> app. A HINT for search order (see the module docstring); an
#: absent entry is never an answer, it just means "search everything".
#: ``scheduler`` is deliberately NOT in here: it moved apps on 2026-09-11 and a
#: map that asserts where it lives would be wrong again the next time it moves.
_DYNO_APP: dict[str, str] = {
    "worker-heavy": "bainluck-heavy",
    "web": "bainluck",
    "worker-background": "bainluck",
    "worker-realtime": "bainluck",
    "worker-ws": "bainluck",
}

#: ``  v4511   Deploy 1ed93bb4   alex@…   2026/09/14 03:07:32 +0000 (~ 1h ago)``
#: The stamp keeps its offset so the comparison happens on real instants; the
#: CLI prints in the caller's local timezone, which on this fleet is not UTC.
_RELEASE_ROW = re.compile(
    r"^\s*(v\d+)\s+.*?(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})"
)


def app_for_dyno(dyno: Any) -> str | None:
    """The app a dyno belongs to, or ``None`` when we do not recognise it.

    ``None`` is a real answer and the callers treat it as one — it means "search
    every app", not "assume the default".
    """
    if not isinstance(dyno, str) or not dyno.strip():
        return None
    prefix = dyno.strip().split(".", 1)[0]
    return _DYNO_APP.get(prefix)


def parse_releases(table_text: str) -> list[dict[str, Any]]:
    """Rows of ``heroku releases`` as ``{version, created_at}``.

    ``created_at`` stays an aware datetime: the CLI prints local time with an
    offset, and reformatting it to a naive string here is how an attribution
    lands hours off. Unparseable lines are skipped — the table has a header and
    a rule line and neither is a release.

    🔴 NO ``app`` FIELD, AND THE OMISSION IS DELIBERATE. An earlier draft stamped
    each row with the app it came from; a mutation run found the field survived
    being hardcoded wrong, because nothing reads it — the app a verdict reports
    is the KEY of the per-app list in :func:`attribute_across_apps`, which is
    the only place it can come from without re-finding the row. A field carried
    for no reader is a second answer waiting to disagree with the first.
    """
    releases: list[dict[str, Any]] = []
    for line in (table_text or "").splitlines():
        match = _RELEASE_ROW.match(line)
        if not match:
            continue
        try:
            stamp = datetime.strptime(match.group(2), "%Y/%m/%d %H:%M:%S %z")
        except ValueError:
            continue
        releases.append({"version": match.group(1), "created_at": stamp})
    return releases


def interrupted_tasks(payload: Any) -> dict[str, dict[str, Any]]:
    """Every task whose LAST run reads ``terminal: "interrupted"``.

    Reads both shapes the admin surface serves, because the population is the
    whole defect here and a tool that understands one shape is one endpoint
    rename away from reporting zero again:

    * ``/api/admin/celery/dashboard`` -> ``{"tasks": [{"task": name, ...}]}``
      (120 rows — the real fleet)
    * ``/api/admin/ops-snapshot`` -> ``{"coverage": {name: {...}}}``
      (2 rows — what this tool used to read, kept only so an old capture still
      parses)

    A bare list or a bare mapping of name -> meta is accepted too. Anything
    whose ``last_result_summary`` is not a dict is skipped rather than crashed
    on: some tasks store a string there.
    """
    rows: list[tuple[str | None, Any]] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("tasks"), list):
            rows = [(None, item) for item in payload["tasks"]]
        elif isinstance(payload.get("coverage"), dict):
            rows = list(payload["coverage"].items())
        else:
            rows = [(k, v) for k, v in payload.items() if isinstance(v, dict)]
    elif isinstance(payload, list):
        rows = [(None, item) for item in payload]

    found: dict[str, dict[str, Any]] = {}
    for key, meta in rows:
        if not isinstance(meta, dict):
            continue
        summary = meta.get("last_result_summary")
        if not isinstance(summary, dict):
            continue
        if summary.get("terminal") != "interrupted":
            continue
        name = key or meta.get("task") or meta.get("name")
        if not name:
            continue
        found[str(name)] = summary
    return found


def attribute_across_apps(
    summary: dict[str, Any],
    releases_by_app: dict[str, list[dict[str, Any]]],
    *,
    window_s: int = 180,
) -> dict[str, Any]:
    """``attribute_teardown`` run against each app's list, honestly combined.

    The rule is not re-implemented — it is called once per app, so both of its
    halves ("created in the window before the interrupt" and "newer than the
    release the worker was running") apply within the list where the version
    numbers are actually comparable. Mixing two apps' releases into one list
    would put ``v18`` and ``v4508`` in the same pool, where a collision of
    version strings is a matter of time.

    Returns ``attribute_teardown``'s own verdict dict, plus ``app`` naming where
    the winner came from, ``apps_searched``, and — when they apply —
    ``dyno_app_mismatch`` and ``ambiguous_apps``. A negative verdict names every
    app it looked in, so "the cause is elsewhere" can never again mean "I only
    had one of the two lists".
    """
    _ensure_backend_on_path()
    from app.utils.task_verdict import attribute_teardown

    hint = app_for_dyno(summary.get("dyno"))
    ordered = [a for a in (hint,) if a in releases_by_app]
    ordered += [a for a in releases_by_app if a not in ordered]

    hits: list[tuple[int, str, dict[str, Any]]] = []
    last_negative: dict[str, Any] = {}
    for app in ordered:
        verdict = attribute_teardown(
            summary, releases_by_app.get(app) or (), window_s=window_s
        )
        if verdict.get("killed_by_release"):
            hits.append((int(verdict.get("lead_s", 0)), app, verdict))
        else:
            last_negative = verdict

    if not hits:
        verdict = dict(last_negative) or {
            "killed_by_release": None,
            "basis": "no_releases_to_compare",
        }
        verdict["apps_searched"] = ordered
        if ordered:
            verdict["detail"] = (
                f"Nothing was deployed in the {window_s}s before the teardown in "
                f"{' or '.join(ordered)}, so the cause is elsewhere — dyno cycle, "
                f"memory quota, manual restart."
            )
        return verdict

    hits.sort(key=lambda h: (h[0], APPS.index(h[1]) if h[1] in APPS else 99))
    lead, app, verdict = hits[0]
    result = dict(verdict)
    result["app"] = app
    result["apps_searched"] = ordered
    if hint is not None and hint != app:
        result["dyno_app_mismatch"] = (
            f"the dyno {summary.get('dyno')!r} points at {hint}, but the only "
            f"release in the window is on {app} — read this before trusting the "
            f"dyno map"
        )
    if hint is None:
        result["dyno_app_hint"] = (
            f"dyno {summary.get('dyno')!r} is not in the dyno->app map, so every "
            f"app was searched"
        )
    if len(hits) > 1:
        result["ambiguous_apps"] = [
            f"{h[1]}:{h[2]['killed_by_release']}(+{h[0]}s)" for h in hits[1:]
        ]
    del lead
    return result


def render(
    interrupted: dict[str, dict[str, Any]],
    releases_by_app: dict[str, list[dict[str, Any]]],
    *,
    window_s: int,
    task_total: int,
) -> list[str]:
    """The operator-facing report, as lines. Pure, so the self-check can read it."""
    counts = ", ".join(f"{a} {len(r)}" for a, r in releases_by_app.items())
    out = [
        f"releases read: {counts} · window {window_s}s · "
        f"{task_total} tasks read, {len(interrupted)} interrupted",
        "",
    ]
    if not interrupted:
        out.append(
            f"No task's last run was interrupted, across all {task_total} tasks. "
            "Nothing to attribute."
        )
        return out

    for name, summary in sorted(interrupted.items()):
        verdict = attribute_across_apps(summary, releases_by_app, window_s=window_s)
        age = summary.get("running_release_age_s", summary.get("release_age_s"))
        out.append(f"── {name}   (dyno {summary.get('dyno', '?')})")
        out.append(
            f"   running release   {summary.get('release_version')} "
            f"(live {age}s at teardown — NOT the killer's age)"
        )
        out.append(f"   interrupted at    {verdict.get('interrupted_at', '(unknown)')}")
        if verdict.get("killed_by_release"):
            out.append(
                f"   KILLED BY         {verdict['killed_by_release']} on "
                f"{verdict.get('app')}, created {verdict['killer_created_at']} "
                f"({verdict['lead_s']}s before the teardown)"
            )
            for key in ("dyno_app_mismatch", "dyno_app_hint"):
                if verdict.get(key):
                    out.append(f"   NOTE              {verdict[key]}")
            if verdict.get("ambiguous_apps"):
                out.append(
                    "   ALSO IN WINDOW    "
                    + ", ".join(verdict["ambiguous_apps"])
                    + "  (nearest wins; read both)"
                )
        else:
            out.append(f"   NOT A DEPLOY      {verdict.get('basis')}")
            out.append(f"                     {verdict.get('detail', '')}")
        out.append("")
    return out


# ─────────────────────────── self-check ───────────────────────────
# Notice 10's scripts/tools clause wants a no-op invocation on the exact sha.
# These are the assertions a pytest file would carry; they live here so the
# whole diff stays under `tools/` (Tier A, no Heroku release). Every specimen
# below is a VERBATIM production read taken 2026-09-14 04:0xZ–04:1xZ, not a
# hand-built shape — the two summaries are what the admin surface served and the
# two release tables are what the CLI printed.

_PROD_FUTURES = {
    "terminal": "interrupted",
    "reason": "SystemExit(-241)",
    "exception_class": "SystemExit",
    "exit_code": -241,
    "interrupted_at": "2026-09-14T03:51:03Z",
    "release_version": "v17",
    "slug_commit": "cad8529b",
    "dyno": "worker-heavy.1",
    "release_created_at": "2026-09-13T23:49:59Z",
    "running_release_age_s": 14464,
}

_PROD_WINNERS = {
    "terminal": "interrupted",
    "reason": "SystemExit(-241)",
    "interrupted_at": "2026-09-13T23:47:35Z",
    "release_version": "v4507",
    "dyno": "worker-background.1",
    "release_created_at": "2026-09-13T22:52:28Z",
    "running_release_age_s": 3307,
}

_PROD_MAIN_TABLE = """=== bainluck Releases - Current: v4511

  v       description       user                  created_at
 ────────────────────────────────────────────────────────────────────
  v4511   Deploy 1ed93bb4   alex.bain@gmail.com   2026/09/14 03:07:32 +0000 (~ 1h ago)
  v4510   Deploy 631384d0   alex.bain@gmail.com   2026/09/14 02:34:57 +0000 (~ 1h ago)
  v4509   Deploy a928ade5   alex.bain@gmail.com   2026/09/14 01:47:25 +0000 (~ 2h ago)
  v4508   Deploy cad8529b   alex.bain@gmail.com   2026/09/13 23:47:19 +0000 (~ 4h ago)
  v4507   Deploy 7802d821   alex.bain@gmail.com   2026/09/13 22:52:28 +0000 (~ 5h ago)
"""

_PROD_HEAVY_TABLE = """=== bainluck-heavy Releases - Current: v18

  v     description       user                  created_at
 ────────────────────────────────────────────────────────────────────
  v18   Deploy 1ed93bb4   alex.bain@gmail.com   2026/09/14 03:50:46 +0000 (~ 21m ago)
  v17   Deploy cad8529b   alex.bain@gmail.com   2026/09/13 23:49:59 +0000 (~ 4h ago)
  v16   Deploy 17285f44   alex.bain@gmail.com   2026/09/13 20:44:25 +0000 (~ 7h ago)
"""


def _both_lists() -> dict[str, list[dict[str, Any]]]:
    return {
        "bainluck": parse_releases(_PROD_MAIN_TABLE),
        "bainluck-heavy": parse_releases(_PROD_HEAVY_TABLE),
    }


def self_check() -> int:  # noqa: C901 — a flat list of assertions reads better
    checks = 0

    def ok(cond: Any, label: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise AssertionError(label)

    # ── the population, which is the whole defect ──────────────────────────
    old_shape = {
        "coverage": {
            "poll_kalshi": {"last_result_summary": {"terminal": "complete"}},
            "poll_polymarket": {"last_result_summary": {"terminal": "complete"}},
        }
    }
    ok(interrupted_tasks(old_shape) == {}, "ops-snapshot coverage: 0 interrupted")

    new_shape = {
        "tasks": [
            {"task": "poll_odds", "last_result_summary": {"events": 0}},
            {"task": "futures_price_refresh", "last_result_summary": _PROD_FUTURES},
            {"task": "polymarket_winners", "last_result_summary": _PROD_WINNERS},
            {"task": "warm_typeahead", "last_result_summary": "a string, not a dict"},
            {"task": "grid_sentinel"},
        ]
    }
    found = interrupted_tasks(new_shape)
    ok(set(found) == {"futures_price_refresh", "polymarket_winners"},
       "dashboard shape: both real teardowns found, nothing else")
    ok(found["futures_price_refresh"]["dyno"] == "worker-heavy.1",
       "the summary travels with the name")

    # The strawman: the old population over the SAME fleet finds nothing. If this
    # ever passes with a non-empty set the fix has stopped being load-bearing.
    ok(interrupted_tasks({"coverage": {k: {"last_result_summary": {"terminal": "complete"}}
                                       for k in ("poll_kalshi", "poll_polymarket")}}) == {},
       "strawman: the two-task block cannot see either teardown")

    # ── release parsing ────────────────────────────────────────────────────
    # NOT named `main` — that is this module's entry point and a local of that
    # name shadows it for the rest of the function (gotcha #7).
    main_rows = parse_releases(_PROD_MAIN_TABLE)
    heavy_rows = parse_releases(_PROD_HEAVY_TABLE)
    ok(len(main_rows) == 5 and len(heavy_rows) == 3,
       "header and rule lines are not releases")
    ok(set(main_rows[0]) == {"version", "created_at"},
       "a release row carries exactly what the rule reads — no app field")
    ok(main_rows[0]["version"] == "v4511", "the newest row parses")
    ok(main_rows[0]["created_at"].utcoffset().total_seconds() == 0,
       "the offset survives parsing")
    ok(parse_releases("not a release table at all") == [],
       "junk parses to nothing rather than raising")

    # A local-time stamp must land on its UTC instant, not its wall clock. This
    # is the specimen LAT-P329 found by running the tool on a laptop in EDT.
    local = parse_releases(
        "  v4427   Deploy ef337836   a@b.c   2026/09/11 01:47:28 -0700 (~ 53m ago)"
    )
    ok(local[0]["created_at"].astimezone().utcoffset() is not None, "aware stamp")
    ok(local[0]["created_at"].timestamp()
       == datetime.fromisoformat("2026-09-11T08:47:28+00:00").timestamp(),
       "local time is compared as its UTC instant")

    # ── the dyno hint ──────────────────────────────────────────────────────
    ok(app_for_dyno("worker-heavy.1") == "bainluck-heavy", "heavy dyno")
    ok(app_for_dyno("worker-background.1") == "bainluck", "background dyno")
    ok(app_for_dyno("scheduler.1") is None,
       "scheduler is deliberately unmapped — it changed apps on 2026-09-11")
    ok(app_for_dyno(None) is None and app_for_dyno("") is None, "no dyno, no guess")

    # ── attribution, on both live specimens ────────────────────────────────
    both = _both_lists()

    v = attribute_across_apps(_PROD_FUTURES, both)
    ok(v["killed_by_release"] == "v18", "futures_price_refresh killed by v18")
    ok(v["app"] == "bainluck-heavy", "…and v18 is a bainluck-heavy release")
    ok(v["lead_s"] == 17, "…17s before the teardown")
    ok("dyno_app_mismatch" not in v, "the dyno hint agreed, so no mismatch note")

    v = attribute_across_apps(_PROD_WINNERS, both)
    ok(v["killed_by_release"] == "v4508", "polymarket_winners killed by v4508")
    ok(v["app"] == "bainluck", "…a main-app release")
    ok(v["lead_s"] == 16, "…16s before the teardown")

    # ── the single-app read, which is what we are fixing ───────────────────
    # Asserted in BOTH directions (gotcha #43): each app's list alone attributes
    # its own task and EXONERATES the other's. This is the pre-fix behaviour and
    # it must stay visible here, or nobody can tell why two lists are read.
    only_main = {"bainluck": both["bainluck"]}
    only_heavy = {"bainluck-heavy": both["bainluck-heavy"]}
    v = attribute_across_apps(_PROD_FUTURES, only_main)
    ok(v["killed_by_release"] is None,
       "main-app list alone cannot see the heavy release")
    ok("bainluck" in " ".join(v.get("apps_searched", [])),
       "…and the negative verdict names what it searched")
    v = attribute_across_apps(_PROD_WINNERS, only_heavy)
    ok(v["killed_by_release"] is None,
       "heavy list alone cannot see the main-app release")
    v = attribute_across_apps(_PROD_WINNERS, only_main)
    ok(v["killed_by_release"] == "v4508", "…each list still answers its own task")
    v = attribute_across_apps(_PROD_FUTURES, only_heavy)
    ok(v["killed_by_release"] == "v18", "…in both directions")

    # ── the hint is a hint ─────────────────────────────────────────────────
    # An unrecognised dyno must not pick an app and exonerate the other.
    unknown = dict(_PROD_FUTURES, dyno="scheduler.1")
    v = attribute_across_apps(unknown, both)
    ok(v["killed_by_release"] == "v18", "an unmapped dyno still gets attributed")
    ok("dyno_app_hint" in v, "…and the report says the map did not recognise it")

    # A WRONG hint must be overridden by the evidence and the conflict printed.
    wrong = dict(_PROD_FUTURES, dyno="worker-background.1")
    v = attribute_across_apps(wrong, both)
    ok(v["killed_by_release"] == "v18", "a wrong hint does not win over a release")
    ok("dyno_app_mismatch" in v, "…and the mismatch is stated out loud")

    # ── two apps deploying together ────────────────────────────────────────
    # SYNTHETIC, and labelled so: tonight's two real deploys are 43 minutes
    # apart, so no production specimen exercises the combination rule. It still
    # has to be right — paired deploys happen — and without this the "nearest
    # wins" sort is a branch no assertion reaches.
    paired = dict(both)
    paired["bainluck"] = parse_releases(
        "  v9999   Deploy deadbeef   a@b.c   2026/09/14 03:50:30 +0000 (~ 1m ago)"
    )
    together = dict(_PROD_FUTURES, dyno="scheduler.1",
                    interrupted_at="2026-09-14T03:50:59Z",
                    release_created_at="2026-09-14T00:00:00Z",
                    running_release_age_s=13859)
    v = attribute_across_apps(together, paired)
    ok(v["killed_by_release"] == "v18" and v["lead_s"] == 13,
       "when both apps deploy into the window the NEAREST release wins")
    ok(v["app"] == "bainluck-heavy", "…and it is reported with its own app")
    ok(v.get("ambiguous_apps") == ["bainluck:v9999(+29s)"],
       "…and the other candidate is printed, not swallowed")
    lines = render({"t": together}, paired, window_s=180, task_total=1)
    ok("ALSO IN WINDOW" in "\n".join(lines),
       "…and a reader of the report sees there were two")

    # ── honest negatives ───────────────────────────────────────────────────
    quiet = dict(_PROD_FUTURES, interrupted_at="2026-09-14T02:00:00Z")
    v = attribute_across_apps(quiet, both)
    ok(v["killed_by_release"] is None, "a quiet window is not a deploy")
    ok(set(v["apps_searched"]) == {"bainluck", "bainluck-heavy"},
       "…and it says it looked in both before saying so")
    ok("bainluck-heavy" in v["detail"], "…by name, in the sentence a reader reads")

    # A release AFTER the interrupt is never the cause, in either app.
    early = dict(_PROD_FUTURES, interrupted_at="2026-09-13T20:00:00Z",
                 release_created_at="2026-09-13T19:00:00Z",
                 running_release_age_s=3600)
    ok(attribute_across_apps(early, both)["killed_by_release"] is None,
       "a later release did not cause an earlier teardown")

    # ── the rendered report ────────────────────────────────────────────────
    lines = render(interrupted_tasks(new_shape), both, window_s=180, task_total=120)
    text = "\n".join(lines)
    ok("120 tasks read, 2 interrupted" in text, "the header counts the real fleet")
    ok("v18 on bainluck-heavy" in text, "the heavy killer is named with its app")
    ok("v4508 on bainluck" in text, "the main killer is named with its app")
    ok("Nothing to attribute" not in text, "a real teardown is never an all-clear")

    empty = render({}, both, window_s=180, task_total=120)
    ok("all 120 tasks" in "\n".join(empty),
       "an all-clear states the population it is an all-clear over")

    # ── the CLI's own refusal ──────────────────────────────────────────────
    # An unparseable release table must exit non-zero rather than report every
    # teardown innocent. Exercised through main(), because that is where the
    # branch lives and a guard over the helper alone would not reach it.
    import contextlib
    import io
    import tempfile

    # main() prints its report; swallow it so the self-check's own output stays
    # a verdict and not a second report a reader has to tell apart from a real
    # one. The RETURN CODE is what is being asserted.
    quiet = contextlib.redirect_stdout(io.StringIO())

    with tempfile.TemporaryDirectory() as tmp, quiet:
        tasks_json = f"{tmp}/tasks.json"
        junk_table = f"{tmp}/rels.txt"
        with open(tasks_json, "w", encoding="utf-8") as fh:
            json.dump(new_shape, fh)
        with open(junk_table, "w", encoding="utf-8") as fh:
            fh.write("the heroku CLI changed its table format\n")
        ok(main(["prog", tasks_json, "180", f"bainluck={junk_table}"]) == 1,
           "0 parsed releases is a refusal, not an all-clear")
        good_table = f"{tmp}/good.txt"
        with open(good_table, "w", encoding="utf-8") as fh:
            fh.write(_PROD_MAIN_TABLE)
        ok(main(["prog", tasks_json, "180", f"bainluck={good_table}"]) == 0,
           "…and a readable table still reports")

    print(f"SELF-CHECK PASS · {checks} assertions · "
          f"two live production teardowns attributed across two apps")
    return 0


def main(argv: list[str]) -> int:
    if "--self-check" in argv:
        return self_check()
    if len(argv) < 3:
        print(__doc__)
        return 2

    tasks_path, window = argv[1], int(argv[2])
    releases_by_app: dict[str, list[dict[str, Any]]] = {}
    for spec in argv[3:]:
        app, _, path = spec.partition("=")
        with open(path, encoding="utf-8", errors="replace") as handle:
            releases_by_app[app] = parse_releases(handle.read())

    if not any(releases_by_app.values()):
        print("!! parsed 0 releases from every app — the CLI table format changed.")
        print("   Refusing to report 'cause is elsewhere' off an empty list: with no")
        print("   releases to compare against, every teardown would read as innocent.")
        return 1

    with open(tasks_path, encoding="utf-8", errors="replace") as handle:
        payload = json.load(handle)

    tasks = payload.get("tasks") if isinstance(payload, dict) else payload
    total = len(tasks) if isinstance(tasks, (list, dict)) else 0
    interrupted = interrupted_tasks(payload)
    print("\n".join(render(interrupted, releases_by_app,
                           window_s=window, task_total=total)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
