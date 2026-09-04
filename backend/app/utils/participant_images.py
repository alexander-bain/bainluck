"""A face — or an honest flag — for a participant in a one-on-one fixture.

#2879 follow-up, ux/1052 item 5. Alex, shopping /sports on 2026-09-03:

    "Player images on /sports. Tennis cards show initials (HS / CB / TM).
     Render a headshot wherever the payload has one; where it has none, write
     the data need into runner-inbox/lane1/ ... do not fetch images from the
     browser."

The renderer was never the problem. The **event card payload has no image field
of any kind**, so a live tennis card had nothing to render and fell back to
initials beside soccer cards drawing real crests. The client's two existing
resolvers cannot help and never will: ``espnTeamLogoByName()`` is a static TEAM
id map and a person is not in it, and ``flagUrl()`` wants a COUNTRY and is
handed ``"Cristina Bucsa"``. This module is the third path, resolved on the
server where the answer is already known.

═══ WHY THE REGISTER, AND NOT A LOOKUP ═══

**A bare-name image lookup returns the wrong person, with a photo, at HTTP
200** — indistinguishable from success at the render. Measured over the 378
registered US Open players (UX-P142): 17 wrong subjects — ``Aleksandar
Kovacevic`` resolved to a Serbian footballer, ``Andrew Johnson`` to the 17th US
President, ``Yue Yuan`` to a beach volleyball player — plus 14 disambiguation
pages. So no lookup happens here. The tournament register already holds a
per-player ``image`` block that was pinned offline and carries
``verified_subject``; ``validate_player_image`` refuses one that does not. This
module only *joins* a fixture's participant name to that decided answer.

The browser-side alternative is closed by measurement too, not just by Alex's
instruction: UX-P032 (#1600) is one tennis draw firing ~600 failing Wikipedia
requests in a single page load.

═══ THE FLAG IS NOT A CONSOLATION PRIZE ═══

Coverage on the committed US Open register, measured 2026-09-03: **334 faces
and 356 flags of 378 players — 376 of 378 have at least one, and two (Joel
Schwaerzler, Tomas Barrios) have neither and keep their initials.** ESPN's own
athlete headshots are thin for tennis (40% men / 28% women, measured
2026-08-27 — the endpoint genuinely returns ``headshot: null``), which is why
the register's faces come from a verified census rather than from ESPN, and why
the flag is carried beside the face rather than instead of it.

A country flag is what every tennis draw sheet has printed for fifty years.
``tournament_slate.py`` made exactly this call for exactly this reason (see its
``"No face:"`` note); this module makes the same one rather than a different
one, so the two surfaces cannot come to disagree about what a faceless player
looks like.

═══ SCOPE ═══

Individual sports only. A team name and a player name live in the same string
field, and ``Iva Buse`` is a person while ``Bayern`` is not — resolving names
against a player index for a football fixture is how a club ends up wearing
somebody's headshot. The gate is :func:`is_individual_sport`, the same
prefix tuple the search dedup uses.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from app.utils.search_fixture_dedup import is_individual_sport
from app.utils.slugify import slugify
from app.utils.tournament_register import (
    REGISTER_DIR,
    player_image,
    validate_player_image,
)

logger = logging.getLogger(__name__)

#: How often the on-disk registers are re-stat'ed. A register is a committed
#: file, so it changes at deploy speed, not at request speed — but "never
#: re-read until the dyno restarts" is how a corrected photo stays wrong for a
#: day. Bounded re-check rather than a permanent cache, and the check is two
#: ``stat`` calls, not a re-parse.
INDEX_RECHECK_S = 300.0

_cache: dict[str, Any] = {"signature": None, "index": {}, "checked_at": 0.0}


def _register_paths(directory: Path) -> list[Path]:
    """Committed registers, in a deterministic order.

    Files whose name starts with ``_`` are fixtures, not committed registers —
    the same convention ``registered_market_ids`` follows one module over. A
    synthetic draw winning a name collision against the real register would put
    a test photo on a live card.
    """
    try:
        return sorted(p for p in directory.glob("*.json") if not p.name.startswith("_"))
    except OSError as exc:  # noqa: BLE001 — a missing directory is "no faces"
        logger.warning("participant image registers unreadable: %s", exc)
        return []


def _signature(paths: list[Path]) -> tuple:
    sig = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        sig.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(sig)


def _build_index(paths: list[Path]) -> dict[str, dict[str, Optional[str]]]:
    """``entity_key -> {"image_url", "flag_url"}`` across every register.

    First file wins a collision, which is only reachable when the same player
    appears in two tournaments — the same person, so the same face. Recorded as
    a rule anyway so the answer does not depend on directory order.
    """
    index: dict[str, dict[str, Optional[str]]] = {}
    for path in paths:
        try:
            document = json.loads(path.read_text())
        except (OSError, ValueError) as exc:  # noqa: BLE001
            # Same posture as `load_register`: a broken register contributes
            # nothing and never raises. A card falls back to initials, which is
            # today's behaviour, rather than the feed falling over.
            logger.error("participant image register %s unreadable: %s", path, exc)
            continue
        players = document.get("players")
        if not isinstance(players, list):
            continue
        for player in players:
            if not isinstance(player, dict):
                continue
            key = player.get("entity_key")
            if not isinstance(key, str) or not key or key in index:
                continue
            # VALIDATE ON READ, not merely in the prose. The register is
            # validated where it is written, but this module is a second reader
            # of the same bytes and its whole licence to render a photo is that
            # the block passed `verified_subject` and the host allowlist. A
            # reader that only *says* it relies on that check would go on
            # rendering an unverified block the day one appears — which is the
            # 17-wrong-subjects failure, arriving through the side door.
            findings = validate_player_image(player.get("image"))
            if findings:
                logger.warning(
                    "participant image for %s refused by the register's own "
                    "validator (%s) — that player keeps their initials",
                    key, ",".join(findings),
                )
                continue
            image = player_image(player)
            if image is None:
                continue
            index[key] = {
                "image_url": image.get("url"),
                "flag_url": image.get("flag_url"),
            }
    return index


def _index(directory: Path | None = None) -> dict[str, dict[str, Optional[str]]]:
    # The window check comes FIRST, before the glob. One feed page asks this
    # ~120 times; a directory listing per participant would put the filesystem
    # on the hot path of `/api/feed` to re-learn something that changes at
    # deploy speed.
    now = time.monotonic()
    if _cache["signature"] is not None and now - _cache["checked_at"] < INDEX_RECHECK_S:
        return _cache["index"]
    paths = _register_paths(directory or REGISTER_DIR)
    signature = _signature(paths)
    if signature != _cache["signature"]:
        _cache["index"] = _build_index(paths)
        _cache["signature"] = signature
    _cache["checked_at"] = now
    return _cache["index"]


def reset_index_cache() -> None:
    """Drop the cached index. For tests and for a register hot-swap."""
    _cache["signature"] = None
    _cache["index"] = {}
    _cache["checked_at"] = 0.0


def participant_image(
    name: Any, *, sport_key: Any, directory: Path | None = None
) -> Optional[dict[str, Optional[str]]]:
    """``{"image_url", "flag_url"}`` for one participant, or ``None``.

    ``None`` means "we have no pinned answer for this person" and the card keeps
    its initials — the honest fallback, and the one already on screen. Either
    URL may individually be ``None``: measured 2026-09-03, **42 of 378**
    registered players have a flag and no face and **20** have a face and no
    flag, so neither field may be treated as implying the other.
    """
    if not is_individual_sport(sport_key):
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    return _index(directory).get(slugify(name))


def participant_images_for_event(
    *, home_team: Any, away_team: Any, sport_key: Any, directory: Path | None = None
) -> dict[str, Optional[str]]:
    """The four card fields, always all four, each possibly ``None``.

    Served even when every value is ``None``, deliberately: absent keys read as
    "this payload predates the field" and a client cannot tell that from
    "we looked and there is no photo of this player". Same reasoning as the
    ``card_sum_reason`` note in ``feed.py`` (#2088).
    """
    home = participant_image(home_team, sport_key=sport_key, directory=directory) or {}
    away = participant_image(away_team, sport_key=sport_key, directory=directory) or {}
    return {
        "home_image_url": home.get("image_url"),
        "away_image_url": away.get("image_url"),
        "home_flag_url": home.get("flag_url"),
        "away_flag_url": away.get("flag_url"),
    }
