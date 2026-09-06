#!/usr/bin/env python3
"""Capture the authority record that proves which tennis names are one player.

#2907 / authority/036, D69 = A. **The rule Alex ruled: identity is the
authority's id, never a name string; a re-ordering aliases when the authority
record proves it and nothing in that record contradicts it; nobody is asked
about a name.** This script is the measurement half — it reads StatPal's own
tennis endpoints (standing notice 26a: the venue's API, by enumeration, not our
tables), pairs each fixture against our register for the same day, and writes
the proven slots out as a generated Python module the matcher imports.

WHAT A SLOT IS, AND WHY IT IS NOT A NAME COMPARISON

A single name agreeing with a single name is a coincidence waiting to happen —
the field has 572 contested keys. A SLOT is both sides of one match agreeing on
one day: StatPal's `Q. Zheng` vs `M. Keys` and our `Qinwen Zheng` vs
`Madison Keys`, 2026-09-05, `tennis_wta_us_open`. The opponent is the
disambiguator, and it is why `ProvenSlot` refuses a record whose opponents do
not agree.

WHAT IT PROVES

StatPal's singles form is `{initial}. {Surname}`, so a slot names the SURNAME
outright — the one thing our own column never records. `Q. Zheng` says the
surname is `Zheng` and the given name starts with Q; it does not say it in
prose, it says it in the shape of the string, in a slot with an opponent and a
date behind it. That is the evidence D69 asks for, and it is why the answer does
not depend on anybody's knowledge of how Chinese names are written.

Doubles are surnames only — `Bublik/ Shang` — so a doubles slot proves a surname
TOKEN and no person. **It therefore authorises nothing**: CERT-2017 found the
first cut folding `Juncheng Shang` on exactly that, and independently folding an
unrelated `Alice Shang` beside him. Doubles slots are still captured, because
their surnames belong in the contradiction vocabulary, but only an id-backed
singles slot can fold a class.

USAGE

    STATPAL_API_KEY=... ADMIN_TOKEN=... BAINLUCK_API=... \
        python3 scripts/capture_tennis_slot_proofs.py > \
        app/utils/authority_tennis_capture.py

The output is a generated module; regenerate it, never hand-edit it. The alias
set is DERIVED from it by `authority_tennis_names.slot_proven_order_aliases` at
import, so a hand-edited capture would be a hand-written answer wearing the
clothes of a measurement.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.authority_tennis_names import (  # noqa: E402
    doubles_key,
    fold_tennis_name,
    is_doubles_name,
    keys_agree,
    our_tennis_keys,
    statpal_tennis_key,
)

#: The venue's whole tennis window. `daily` serves d-7…d-1 and d1…d7 and has no
#: d0 — today's play is `livescores` (ARTIFACT-AUTHORITY-20260903-TENNIS §1a) —
#: so this is every fixture StatPal will show us, not a sample of it.
TENNIS_PATHS = (
    [f"v1/tennis/daily/d{off}" for off in list(range(-7, 0)) + list(range(1, 8))]
    + ["v1/tennis/livescores"]
)


def _venue(path: str) -> dict:
    key = os.environ["STATPAL_API_KEY"]
    url = f"https://statpal.io/api/{path}?" + urllib.parse.urlencode({"access_key": key})
    return json.loads(urllib.request.urlopen(url, timeout=60).read())


def _iso(ddmmyyyy: str) -> str:
    parts = str(ddmmyyyy).split(".")
    return f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else ""


def sweep_venue() -> list[dict]:
    """Every tennis fixture the venue serves, with both sides' ids and names."""
    fixtures = []
    for path in TENNIS_PATHS:
        try:
            body = _venue(path)
        except Exception as exc:
            # FAIL CLOSED. This used to warn and carry on, and that is a
            # fail-open in the one direction that fuses two people: the surname
            # VOCABULARY is the contradiction guard's evidence, a short sweep
            # makes it smaller, and a token missing from a smaller vocabulary
            # reads as "not a family name anywhere" — which is precisely the
            # licence to fold. A capture is only as safe as it is complete, so a
            # path that does not answer ends the run instead of quietly
            # shrinking what the guard can see.
            raise SystemExit(
                f"# {path} did not answer ({exc}); refusing to write a PARTIAL "
                "capture — a short surname vocabulary silently WIDENS the alias "
                "rule. Re-run when the venue is healthy."
            ) from exc
        section = body.get("scores") or body.get("livescores") or {}
        tournaments = section.get("tournament") or []
        if isinstance(tournaments, dict):
            tournaments = [tournaments]
        for tournament in tournaments:
            if not isinstance(tournament, dict):
                continue
            matches = tournament.get("match") or []
            if isinstance(matches, dict):
                matches = [matches]
            for match in matches:
                if not isinstance(match, dict):
                    continue
                sides = match.get("player")
                if not isinstance(sides, list) or len(sides) < 2:
                    continue
                a, b = sides[0], sides[1]
                if not (isinstance(a, dict) and isinstance(b, dict)):
                    continue
                fixtures.append({
                    "date": _iso(match.get("date", "")),
                    "tournament": tournament.get("name", ""),
                    "sides": [
                        {"id": str(a.get("id", "")), "name": a.get("name", "")},
                        {"id": str(b.get("id", "")), "name": b.get("name", "")},
                    ],
                })
        time.sleep(0.3)
    return fixtures


#: How far back `OUR_SPELLINGS` reaches. The slot pairing can only ever cover the
#: venue's own 15-day window, but the contradiction check must not: the whole
#: point of it is "has our register ever held the reversed order", and
#: `Garcia Perez` / `Perez-Garcia` — the pair this module refuses on purpose —
#: last co-occurred on 2026-07-13, eight weeks outside the venue window. A guard
#: that can only see ten days would have called that class unspelled and folded
#: two people into one.
SPELLINGS_LOOKBACK_DAYS = 365


def our_register(first_day: str, last_day: str) -> list[dict]:
    """Our tennis rows for the window, paged — `db-query` caps a page at 1,000."""
    api, token = os.environ["BAINLUCK_API"], os.environ["ADMIN_TOKEN"]
    rows, offset = [], 0
    while True:
        sql = (
            "SELECT e.id, e.home_team_name, e.away_team_name, "
            "e.commence_time::date::text AS d, s.key FROM events e "
            "JOIN sports s ON s.id = e.sport_id WHERE s.key LIKE 'tennis%' "
            f"AND e.commence_time::date BETWEEN DATE '{first_day}' AND DATE '{last_day}' "
            f"ORDER BY e.id OFFSET {offset}"
        )
        req = urllib.request.Request(
            f"{api}/api/admin/db-query",
            data=json.dumps({"sql": sql, "limit": 1000}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        page = json.loads(urllib.request.urlopen(req, timeout=90).read())
        rows += [dict(zip(page["columns"], r)) for r in page["rows"]]
        if not page.get("truncated"):
            return rows
        offset += 1000


def our_spellings(first_day: str, last_day: str) -> list[str]:
    """Every DISTINCT tennis name our register held over the lookback.

    Distinct rather than paged rows: the guard only ever asks whether a spelling
    exists, so `SELECT DISTINCT` is the whole answer and a year of rows never has
    to cross the wire.

    Chunked into 90-day windows because a year in one statement hits
    `statement_timeout` — `events` carries ~437% dead tuples (#3370), so a date
    range that reads a year of it is a sequential scan of several times that. A
    timeout here is not a slow answer, it is NO answer, and a `SELECT DISTINCT`
    that quietly returned the first chunk would make every unseen spelling look
    absent — which is the direction that FOLDS two people into one.
    """
    api, token = os.environ["BAINLUCK_API"], os.environ["ADMIN_TOKEN"]
    names: set[str] = set()
    start, last = date.fromisoformat(first_day), date.fromisoformat(last_day)
    while start <= last:
        stop = min(start + timedelta(days=89), last)
        for column in ("home_team_name", "away_team_name"):
            offset = 0
            while True:
                # The server caps a page at 1,000 rows whatever `limit` asks for,
                # so the page is walked rather than requested whole. ORDER BY is
                # not decoration here: OFFSET without it is undefined paging, and
                # a name skipped between pages reads to the guard as a name our
                # register never held.
                sql = (
                    f"SELECT DISTINCT e.{column} AS n FROM events e "
                    "JOIN sports s ON s.id = e.sport_id WHERE s.key LIKE 'tennis%' "
                    f"AND e.commence_time::date BETWEEN DATE '{start}' AND DATE '{stop}' "
                    f"ORDER BY 1 OFFSET {offset}"
                )
                req = urllib.request.Request(
                    f"{api}/api/admin/db-query",
                    data=json.dumps({"sql": sql, "limit": 1000}).encode(),
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                )
                try:
                    page = json.loads(urllib.request.urlopen(req, timeout=120).read())
                except urllib.error.HTTPError as exc:
                    # A refusal has to name the statement it refused: a bare
                    # "400 Bad Request" over a paged sweep says nothing about
                    # WHICH page died, and a sweep that loses a page silently
                    # reports absent names that are merely unread.
                    raise SystemExit(
                        f"# db-query refused {column} {start}…{stop} offset {offset}: "
                        f"{exc.code} {exc.read().decode('utf8', 'replace')[:400]}"
                    ) from exc
                names.update(r[0] for r in page["rows"] if r[0])
                if not page.get("truncated"):
                    break
                offset += len(page["rows"])
        start = stop + timedelta(days=1)
    return sorted(names)


def _singles_hit(their_name: str, our_name: str):
    """The key an authority singles name proves about one of our names, or None."""
    theirs = statpal_tennis_key(their_name)
    if theirs is None:
        return None
    for ours in our_tennis_keys(our_name):
        if keys_agree(ours, theirs):
            return theirs
    return None


def pair_slots(fixtures: list[dict], rows: list[dict]) -> list[dict]:
    """Fixtures where BOTH sides agree with both sides of one of our rows."""
    by_day: dict[str, list[dict]] = {}
    for row in rows:
        by_day.setdefault(row["d"], []).append(row)

    slots = []
    for fixture in fixtures:
        a, b = fixture["sides"]
        doubles = is_doubles_name(a["name"]) and is_doubles_name(b["name"])
        for row in by_day.get(fixture["date"], []):
            ours = (row["home_team_name"], row["away_team_name"])
            matched = None
            if doubles:
                theirs_pair = (doubles_key(a["name"]), doubles_key(b["name"]))
                ours_pair = (doubles_key(ours[0]), doubles_key(ours[1]))
                if all(theirs_pair) and all(ours_pair) and set(theirs_pair) == set(ours_pair):
                    # Orient our two sides onto theirs; a doubles team is unordered.
                    matched = (a, b) if theirs_pair[0] == ours_pair[0] else (b, a)
            else:
                for cand in ((a, b), (b, a)):
                    if _singles_hit(cand[0]["name"], ours[0]) and \
                       _singles_hit(cand[1]["name"], ours[1]):
                        matched = cand
                        break
            if matched is None:
                continue
            for side, (them, us) in enumerate(zip(matched, ours)):
                other_them, other_us = matched[1 - side], ours[1 - side]
                slots.append({
                    "authority_id": them["id"],
                    "authority_name": them["name"],
                    "our_name": us,
                    "slot_date": fixture["date"],
                    "tour": row["key"],
                    "authority_opponent": other_them["name"],
                    "our_opponent": other_us,
                    "doubles": doubles,
                })
            break
    return slots


def surname_vocabulary(fixtures: list[dict]) -> set[str]:
    """Every token the authority itself used AS a surname, across the sweep.

    This is the contradiction check's evidence and the reason it is not an
    opinion: a re-ordering only folds when the authority never used the class's
    OTHER token as a surname. `zheng` is in here 13 times over; `qinwen` is not
    in it at all, and that asymmetry is the whole proof.
    """
    vocabulary: set[str] = set()
    for fixture in fixtures:
        for side in fixture["sides"]:
            name = side["name"]
            if is_doubles_name(name):
                pair = doubles_key(name)
                if pair:
                    vocabulary.update(pair)
            else:
                key = statpal_tennis_key(name)
                if key:
                    vocabulary.add(key[0])
    return vocabulary


def main() -> int:
    fixtures = sweep_venue()
    days = sorted({f["date"] for f in fixtures if f["date"]})
    if not days:
        print("# the venue served no tennis fixtures — refusing to write an empty capture",
              file=sys.stderr)
        return 1
    #: A floor, not a target. The 2026-09-06 sweep saw 372 fixtures and 424
    #: surnames mid-US-Open; a quiet week is smaller, but an order of magnitude
    #: smaller is a broken sweep wearing a valid response, and it would ship a
    #: vocabulary too thin for the contradiction guard to refuse anything with.
    if len(fixtures) < 100:
        print(f"# only {len(fixtures)} fixtures came back — too thin to base an "
              "alias rule on; refusing to write", file=sys.stderr)
        return 1
    rows = our_register(days[0], days[-1])
    slots = pair_slots(fixtures, rows)
    vocabulary = sorted(surname_vocabulary(fixtures))

    lookback = (datetime.fromisoformat(days[0]).date()
                - timedelta(days=SPELLINGS_LOOKBACK_DAYS)).isoformat()
    # Doubles are excluded, and the test is on the RAW string: folding replaces
    # the separator with a space, so `Bagaric/Moratelli` folds to
    # `bagaric moratelli` and is indistinguishable from a two-token singles name
    # afterwards. A vocabulary that let that through would offer the prover 1,674
    # pairs as if they were people, and `register_identity` sends a doubles row
    # down `doubles_key` anyway, so nothing here could ever use them.
    register = sorted({fold_tennis_name(n)
                       for n in our_spellings(lookback, days[-1])
                       if not is_doubles_name(n) and fold_tennis_name(n)})

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = sys.stdout.write
    out('"""GENERATED by `scripts/capture_tennis_slot_proofs.py` — do not hand-edit.\n\n')
    out("The authority record behind the tennis order-alias decisions (#2907, D69 = A).\n")
    out("Regenerate with the script; the alias set is DERIVED from this at import by\n")
    out("`authority_tennis_names.slot_proven_order_aliases`, so editing this file by hand\n")
    out("is writing the answer and calling it a measurement.\n\n")
    out(f"Captured {stamp} over StatPal tennis {TENNIS_PATHS[0]}…{TENNIS_PATHS[-1]}\n")
    out(f"({len(fixtures)} fixtures, {days[0]}…{days[-1]}) paired against {len(rows)} of our\n")
    out(f"tennis rows for the same days: {len(slots)} proven sides,\n")
    out(f"{len(vocabulary)} distinct authority surnames, {len(register)} of our spellings.\n")
    out('"""\n')
    out(f'CAPTURED_AT = "{stamp}"\n')
    out(f'CAPTURE_WINDOW = ("{days[0]}", "{days[-1]}")\n\n')
    out("#: One entry per side of every fixture where BOTH sides agreed with both\n")
    out("#: sides of one of our rows on the same day.\n")
    out("PROVEN_SIDES = (\n")
    for slot in slots:
        out("    %r,\n" % (slot,))
    out(")\n\n")
    out("#: Every token the authority itself used as a surname in the sweep.\n")
    out("AUTHORITY_SURNAMES = frozenset(%r)\n\n" % (vocabulary,))
    out("#: Every folded spelling our register held in the window, so the prover can\n")
    out("#: see whether a re-ordering is already in the field (which makes it a review\n")
    out("#: question) or has never arrived (which makes folding it a safe prediction).\n")
    out("OUR_SPELLINGS = frozenset(%r)\n" % (register,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
