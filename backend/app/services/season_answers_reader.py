"""T2-1 (#5058): read the season-answer projection onto a team suggestion.

The write side is ``app/tasks/season_answers_projection.py``, an hourly beat.
This is the reader, and it has one job the writer does not: it must be
UNCONDITIONALLY SAFE ON THE KEYSTROKE PATH. Every failure — Redis down, key
absent, key expired, a payload from a future schema, a team nobody projected —
resolves to "this row has no season answers", which is exactly the row
``/typeahead`` served before T2-1 existed.

TWO LOOKUP KEYS, AND THE SECOND ONE IS NOT BELT AND BRACES. The projection is
keyed by the team id the championship grid used, and that is not always the id
the search pool uses: measured 2026-09-11, the NFL grid resolves the Chargers to
team ``17736`` and the Steelers to ``17757``, both rows in
``americanfootball_nfl_preseason``, while the dropdown offers ``556`` and
``540`` in ``americanfootball_nfl`` (#5120). Keying on the id alone would have
left two of thirty-two NFL teams permanently blank for a reason no reader could
see. The folded team NAME is the same on both rows, so it is the index that
survives a duplicate-row defect this ship does not own.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.tasks.season_answers_projection import (
    SEASON_ANSWERS_SCHEMA,
    season_answers_key,
)
from app.utils.season_answers import normalize_team_key

logger = logging.getLogger(__name__)


def _index(payload: dict[str, Any]) -> tuple[dict[int, list], dict[str, list]]:
    by_id: dict[int, list] = {}
    by_name: dict[str, list] = {}
    for entry in payload.get("teams") or []:
        if not isinstance(entry, dict):
            continue
        answers = entry.get("answers")
        if not isinstance(answers, list) or not answers:
            continue
        team_id = entry.get("team_id")
        if isinstance(team_id, int):
            by_id[team_id] = answers
        name_key = entry.get("name_key") or normalize_team_key(entry.get("name"))
        if name_key:
            # First writer wins. A projection carrying one league's thirty
            # distinct clubs cannot collide here; if a future one does, the
            # earlier entry is the grid's own order and the later is the
            # surprise, so the surprise is the one that loses.
            by_name.setdefault(name_key, answers)
    return by_id, by_name


def _load(rc: Any, sport_key: str) -> tuple[dict[int, list], dict[str, list]] | None:
    raw = rc.get(season_answers_key(sport_key))
    if not raw:
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != SEASON_ANSWERS_SCHEMA:
        # A shape this reader was not written against. Refusing it is the
        # point: a projection whose answers moved is not a projection whose
        # answers can be guessed at.
        logger.warning(
            "Season answers for %s carry schema %r, not %r — ignoring",
            sport_key, payload.get("schema"), SEASON_ANSWERS_SCHEMA,
        )
        return None
    return _index(payload)


def attach_season_answers(rc: Any, suggestions: list[dict]) -> int:
    """Attach ``season_answers`` to every team row that has any. Returns the count.

    ``rc`` is the route's synchronous Redis client. Called with the rows the
    reader will actually SEE — after the slice, not before it — so a query whose
    seven visible rows contain no team costs one dictionary scan and no Redis
    call at all.
    """
    teams = [
        s for s in suggestions
        if isinstance(s, dict) and s.get("type") == "team" and s.get("sport_key")
    ]
    if not teams:
        return 0

    attached = 0
    loaded: dict[str, tuple[dict[int, list], dict[str, list]] | None] = {}
    for suggestion in teams:
        sport_key = suggestion["sport_key"]
        if sport_key not in loaded:
            try:
                loaded[sport_key] = _load(rc, sport_key)
            except Exception:
                # Redis unreachable or a corrupt entry. Both already mean "no
                # answers" on every other cache read in this route, and a team
                # row without its two facts is the pre-T2-1 row, not a defect.
                logger.debug("Season answers unavailable for %s", sport_key, exc_info=True)
                loaded[sport_key] = None
        index = loaded[sport_key]
        if index is None:
            continue
        by_id, by_name = index
        answers = by_id.get(suggestion.get("team_id"))
        if answers is None:
            answers = by_name.get(normalize_team_key(suggestion.get("text")))
        if answers:
            suggestion["season_answers"] = answers
            attached += 1
    return attached
