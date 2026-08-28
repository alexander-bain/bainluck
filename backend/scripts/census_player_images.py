"""Pin a verified image for every registered player (UX-P142, Alex's ruling 8).

    RULING 8, verbatim: "Player images: census ESPN (or other) headshot
    coverage for both draws first. Enable ONLY if coverage is ~complete per
    draw — half-covered looks worse than none."

    ALEX, on his phone, 2026-08-27: "Players have no images."

THE CENSUS THE RULING ASKED FOR, run 2026-08-27 over the 222 named main-draw
players ESPN publishes for this tournament.

| source                                  | men's        | women's      |
|-----------------------------------------|--------------|--------------|
| ESPN headshot (`/i/headshots/tennis/…`) | 44/110 (40%) | 31/112 (28%) |
| ESPN country flag                       | 110/110      | 112/112      |
| Wikipedia thumbnail, bare name          | 99/110 (90%) | 106/112 (95%)|
| Wikipedia thumbnail, + `(tennis)` title | 103/110(94%) | 107/112 (96%)|

**ESPN headshots fail Alex's own gate and are not enabled.**  40% and 28% is
not "~complete"; it is exactly the half-covered column he named.  The 404s are
real absences, not a wrong URL pattern — ESPN's athlete endpoint returns
``headshot: null`` for every one of them.

**Wikipedia clears it, and it is the mechanism this repo already uses** for
person images (``lib/images.getWikipediaImage``, shipped for UFC fighters in
``FighterAvatar``).  What is NOT reused is the request-time lookup, and this is
the whole reason this script exists rather than a component:

    Bare-name Wikipedia for `Aleksandar Kovacevic` returns a SERBIAN
    FOOTBALLER — 200, with a photo, indistinguishable from success.

A wrong face is the worst kind of wrong number: instant, confident and
unfalsifiable by the reader.  So an image is decided the same way every other
identity on this page is decided — once, offline, against evidence, into a
committed file — and the register REFUSES a block that cannot show the check
(``PLAYER_IMAGE_NOT_VERIFIED``).

THE VERIFICATION.  A candidate title is accepted only if the source's own
one-line description of the subject says tennis.  ``Aleksandar Kovacevic`` ->
"Serbian footballer" -> rejected; ``Aleksandar Kovacevic (tennis)`` ->
"American tennis player (born 1998)" -> accepted.  Disambiguation pages
("Topics referred to by the same term") are rejected by the same rule, since
they describe a term rather than a person.

THE FALLBACK IS A FLAG, and it is why no row is blank.  ESPN carries a country
per athlete on the same record as the name — 100% on both draws — so the ~6% of
players with no photograph anywhere still render a real image rather than a
grey hole.  A flag is not a claim about a face; it is the same badge every
tennis draw sheet and broadcast scoreboard has printed for fifty years.

USAGE:

    cd backend && python3 scripts/census_player_images.py \\
      --register data/tournament_registers/us-open-2026.json \\
      --version 9 --supersedes-version 8 \\
      --observed-at 2026-08-27T18:30:00+00:00 \\
      --payload /tmp/espn_atp.json --payload /tmp/espn_wta.json \\
      --out /tmp/proposed-v9.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.espn_tennis import DRAW_SLUGS, normalize_name  # noqa: E402
from app.utils.tournament_register import (  # noqa: E402
    TournamentRegister,
    classify,
    us_open_2026_contract,
    validate_register,
    validate_transition,
)

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"

#: Identifies us to Wikimedia, which is their stated condition of use and also
#: what keeps the 429s down. A contact address, not a browser lie.
USER_AGENT = "bainluck-player-image-census/1.0 (https://bainluck.com)"

#: Title shapes tried, in order.  Bare name first because it is right ~90% of
#: the time and costs one request; the disambiguated forms are the fix for the
#: cases where the bare name is a footballer or a disambiguation page.
TITLE_FORMS = ("{name}", "{name} (tennis)", "{name} (tennis player)")

#: The word the subject's own description must contain.  Deliberately one word
#: and deliberately not a name match: we are checking WHAT the article is
#: about, and "tennis player" / "tennis coach" / "wheelchair tennis" all
#: qualify while "Serbian footballer" does not.
SUBJECT_TOKEN = "tennis"


def wiki_summary(title: str, *, tries: int = 4) -> Optional[dict[str, Any]]:
    """One Wikipedia REST summary, with 429 backoff.  ``None`` on 404.

    The backoff is not politeness padding.  A throttled request returns a body
    that parses to no thumbnail, which is indistinguishable from "this player
    has no photograph" — the false-null shape.  A census that silently absorbed
    them would under-report coverage and then be used to decide whether to ship
    the feature at all.
    """
    url = WIKI_SUMMARY + urllib.parse.quote(title.replace(" ", "_"))
    for attempt in range(tries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None)
            if code == 404:
                return None
            if code == 429 and attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"wikipedia refused {title!r} after {tries} attempts")


def subject_is_tennis(summary: dict[str, Any]) -> bool:
    """Is this article about a tennis player?  The gate that killed the footballer."""
    if str(summary.get("type") or "") == "disambiguation":
        return False
    haystack = " ".join(
        str(summary.get(field) or "") for field in ("description", "extract")
    ).lower()
    return SUBJECT_TOKEN in haystack


def resolve_face(name: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """``(thumbnail_url, evidence)`` for a player, or ``(None, evidence)``.

    Evidence is returned even on a miss, because "we looked on this date and
    Wikipedia has no photograph of this person" is a census result and the
    register's posture is that a censused absence is written down.
    """
    attempts: list[dict[str, Any]] = []
    for form in TITLE_FORMS:
        title = form.format(name=name)
        summary = wiki_summary(title)
        if summary is None:
            attempts.append({"title": title, "verdict": "404"})
            continue
        description = summary.get("description")
        if not subject_is_tennis(summary):
            attempts.append(
                {
                    "title": title,
                    "verdict": "wrong-subject",
                    "description": description,
                }
            )
            continue
        thumbnail = (summary.get("thumbnail") or {}).get("source")
        if not thumbnail:
            attempts.append(
                {
                    "title": title,
                    "verdict": "no-thumbnail",
                    "description": description,
                }
            )
            continue
        return thumbnail, {
            "title": title,
            "verdict": "accepted",
            "description": description,
            "attempts": attempts,
        }
        # (no break needed — the return is the accept path)
    return None, {"verdict": "no-image", "attempts": attempts}


def espn_flags(
    payloads: list[dict[str, Any]], *, event_name: str
) -> dict[tuple[str, str], dict]:
    """``(draw, normalized name) -> {flag_url, country, espn_athlete_id}``.

    Read off the same competitor records the draw ingest reads, so the flag and
    the fixture cannot disagree about who a player is.
    """
    out: dict[tuple[str, str], dict] = {}
    for payload in payloads:
        for event in (payload or {}).get("events") or []:
            if event_name not in str(event.get("name") or ""):
                continue
            for grouping in event.get("groupings") or []:
                slug = ((grouping.get("grouping") or {}).get("slug")) or ""
                draw = DRAW_SLUGS.get(slug)
                if draw is None:
                    continue
                for competition in grouping.get("competitions") or []:
                    for competitor in competition.get("competitors") or []:
                        athlete = competitor.get("athlete") or {}
                        name = str(athlete.get("displayName") or "").strip()
                        raw_id = str(competitor.get("id") or "")
                        if not name or not raw_id.isdigit() or int(raw_id) <= 0:
                            continue
                        flag = athlete.get("flag") or {}
                        if not flag.get("href"):
                            continue
                        out.setdefault(
                            (draw, normalize_name(name)),
                            {
                                "flag_url": flag.get("href"),
                                "country": flag.get("alt"),
                                "espn_athlete_id": int(raw_id),
                            },
                        )
    return out


def census(
    register: dict[str, Any],
    flags: dict[tuple[str, str], dict],
    *,
    observed_at: str,
    delay: float = 0.12,
    limit: Optional[int] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposed = json.loads(json.dumps(register))
    stats: dict[str, Any] = {
        "looked_up": 0,
        "faces": 0,
        "flags": 0,
        "rejected_subject": 0,
    }
    rejected: list[str] = []

    players = [p for p in proposed.get("players", []) if isinstance(p, dict)]
    if limit is not None:
        players = players[:limit]

    for player in players:
        name = str(player.get("display_name") or "").strip()
        if not name:
            continue
        draw = str(player.get("draw") or "")
        flag = flags.get((draw, normalize_name(name))) or {}

        stats["looked_up"] += 1
        url, evidence = resolve_face(name)
        if url:
            stats["faces"] += 1
        if any(
            a.get("verdict") == "wrong-subject" for a in evidence.get("attempts", [])
        ):
            stats["rejected_subject"] += 1
            rejected.append(
                f"{name}: "
                + "; ".join(
                    f"{a['title']} -> {a.get('description')!r}"
                    for a in evidence["attempts"]
                    if a.get("verdict") == "wrong-subject"
                )
            )
        if flag.get("flag_url"):
            stats["flags"] += 1

        block: dict[str, Any] = {
            "url": url,
            "flag_url": flag.get("flag_url"),
            "country": flag.get("country") or player.get("country"),
            "evidence": {
                "kind": "player-image-census",
                "observed_at": observed_at,
                "face_source": "wikipedia" if url else None,
                "flag_source": "espn" if flag.get("flag_url") else None,
                "espn_athlete_id": flag.get("espn_athlete_id"),
                "lookup": evidence,
            },
        }
        if url:
            # Only a FACE carries a verification claim: a flag is a claim about
            # a country, read off the same record as the name, with no
            # wrong-person failure mode to guard against.
            block["verified_subject"] = True
            block["subject_title"] = evidence.get("title")
            block["subject_description"] = evidence.get("description")
        player["image"] = block
        if flag.get("country") and not player.get("country"):
            player["country"] = flag["country"]
        time.sleep(delay)

    stats["rejected_examples"] = rejected[:10]
    return proposed, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--event-name", default="US Open")
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--supersedes-version", type=int, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--payload", action="append", default=[], required=True)
    parser.add_argument("--out", help="defaults to --register (in place)")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=0.12)
    args = parser.parse_args()

    register = json.loads(Path(args.register).read_text())
    payloads = [json.loads(Path(p).read_text()) for p in args.payload]
    flags = espn_flags(payloads, event_name=args.event_name)
    print(f"espn flag index: {len(flags)} athletes")

    proposed, stats = census(
        register,
        flags,
        observed_at=args.observed_at,
        delay=args.delay,
        limit=args.limit,
    )
    proposed["version"] = args.version
    proposed["supersedes_version"] = args.supersedes_version
    proposed["images_observed_at"] = args.observed_at

    print(f"census: { {k: v for k, v in stats.items() if k != 'rejected_examples'} }")
    if stats["rejected_examples"]:
        print(
            "\nSUBJECT REJECTIONS — a photo we refused because it is the wrong person:"
        )
        for line in stats["rejected_examples"]:
            print(f"  {line}")

    reg = TournamentRegister(proposed)
    print("\nCOVERAGE (Alex's ruling 8 gate):")
    for draw in ("mens-singles", "womens-singles"):
        coverage = reg.image_coverage(draw)
        total = coverage["players"] or 1
        print(
            f"  {draw}: {coverage['faces']}/{coverage['players']} faces "
            f"({coverage['faces'] / total:.0%}) · "
            f"{coverage['any']}/{coverage['players']} any image "
            f"({coverage['any'] / total:.0%})"
        )

    contract = us_open_2026_contract()
    findings = validate_register(proposed, contract)
    transition = validate_transition(register, proposed, contract)
    print(f"\nfindings:   {findings or 'none'}")
    print(f"transition: {transition or 'clean'}")
    print(f"verdict:    {classify(findings)}")
    if findings or transition:
        print("\nREFUSING TO WRITE — not a clean transition.", file=sys.stderr)
        return 1

    out = Path(args.out or args.register)
    out.write_text(json.dumps(proposed, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
