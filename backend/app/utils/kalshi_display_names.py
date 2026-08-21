"""Repair Kalshi's truncated team names for display (#2060 item 3).

── THE DEFECT, AS ALEX HIT IT ───────────────────────────────────────────────────

His 08-20 gold session served a card titled **"Los Angeles D vs Colorado"** whose
two outcomes were **"Los Angeles D"** and **"Colorado"**. Kalshi ships team names
truncated to a fixed width, so the Dodgers arrive as `Los Angeles D`. That is not
merely ugly — in this exact city it is AMBIGUOUS, because `Los Angeles A` is the
Angels and `Los Angeles D` prefix-matches nothing a reader can rely on.
``team_identity_resolution.py`` records the resolution actually going wrong this
way in production: *"'Los Angeles D' … stored=Los Angeles Angels ticker=Los
Angeles Dodgers"*.

── THE SOURCE OF TRUTH IS THE TICKER, AND THAT IS A STANDING RULE ───────────────

Gotcha #16: *"Prefer ticker-derived team names over market-name abbreviations."*
`KXMLBGAME-26AUG182040LADCOL` carries `LAD` and `COL` — unambiguous three-letter
codes that `prediction_market_matching._KALSHI_TEAM_ABBREVS` already maps, and that
the matching layer already trusts. This module reuses that map rather than minting a
second one.

** THE EVENT LINK IS DELIBERATELY NOT USED, EVEN THOUGH IT HOLDS FULL NAMES. **
`events.home_team_name` on the exemplar's linked event says "Colorado Rockies" /
"Los Angeles Dodgers", which looks like a free answer. It is not: that market's
`event_id` points at the **2026-08-18** game while the market resolves 08-22 — the
split-brain duplicate cohort of #2057. Reading names through a link that is known
broken for precisely this class would repair the display by importing a matching
bug, and the wrong name would be indistinguishable from a right one.

── WHAT IT WILL AND WILL NOT DO ─────────────────────────────────────────────────

It repairs ONLY a name that is actually truncated — last token 1-3 capitals, which
is the shape of the artifact — and only when exactly one ticker nickname is
consistent with that token. `Colorado` and `Seattle` are not truncated, so they ship
untouched: correct data is not rewritten, only defective data is repaired. When
nothing resolves, the caller gets an empty mapping and the card renders exactly what
Kalshi sent. **Never invent a name.** A wrong expansion is worse than a short one,
because a short one is visibly short.

The city comes from the shipped text (everything before the truncated token) and the
nickname from the ticker, so the composed name is "Los Angeles" + "Dodgers" — full,
and each half traceable to a source rather than to a lookup table someone has to
maintain.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from app.utils.prediction_market_matching import extract_team_codes_from_ticker

#: The truncation artifact: a trailing run of 1-3 capitals standing in for the
#: rest of the nickname. `Los Angeles D`, `Chicago WS`, `Los Angeles A`.
#: Anchored and narrow so it cannot catch a real one-word name — `Colorado` and
#: `Seattle` do not match, and neither does a genuine all-caps club name of four
#: or more letters.
_TRUNCATED_TAIL_RE = re.compile(r"^(?P<city>.+?)\s+(?P<tail>[A-Z]{1,3})$")

_WS = re.compile(r"\s+")


def _initials(nickname: str) -> str:
    """`White Sox` -> `WS`. Kalshi truncates multi-word nicknames to initials."""
    return "".join(word[0] for word in _WS.split(nickname.strip()) if word).upper()


def _consistent(tail: str, nickname: str) -> bool:
    """Could this truncated tail be standing in for this nickname?

    Two shapes, both observed in production: a PREFIX of the nickname's first word
    (`D` -> `Dodgers`, `A` -> `Angels`, `C` -> `Cubs`) and the INITIALS of a
    multi-word nickname (`WS` -> `White Sox`). Nothing fuzzier — every widening
    here buys a wrong name somewhere.
    """
    tail = tail.upper()
    words = _WS.split(nickname.strip())
    if not words:
        return False
    return words[0].upper().startswith(tail) or _initials(nickname) == tail


def _code_matches(code: str, shipped: str) -> bool:
    """Is this ticker code the code FOR this shipped name?

    ── THE CASE THAT FORCED THIS ────────────────────────────────────────────────

    `Los Angeles A` is the Angels, but the tail `A` is equally consistent with
    "Angels" and "Astros", so the nickname test alone abstains and the card stays
    truncated. The ticker's own codes do not have that problem: `KXMLBGAME-…LAAHOU`
    carries `laa` and `hou`, and `hou` matches only "Houston" while `laa` matches
    only "Los Angeles A". Binding codes to shipped names first, then reading the
    nickname off the bound code, resolves what the nickname could not.

    Two shapes again, mirroring how Kalshi builds the codes: a PREFIX of the
    squashed name (`HOU` -> `HOUSTON`, `SEA` -> `SEATTLE`) or its INITIALS
    (`LAA` -> `Los Angeles A`, `CWS` -> `Chicago WS` … via its word initials).
    """
    code = code.upper()
    squashed = re.sub(r"[^A-Za-z0-9]", "", shipped).upper()
    if squashed.startswith(code):
        return True
    return _initials(shipped) == code


def repair_truncated_names(
    external_id: Optional[str],
    outcome_names: Iterable[Optional[str]],
) -> dict[str, str]:
    """Map each truncated outcome name to its repaired full name.

    Returns ``{}`` when nothing can be repaired — an empty mapping is the normal,
    common case (tennis, esports and college tickers carry no mapped abbreviations
    at all) and the caller must treat it as "ship what Kalshi sent".

    Pure: no database, no network. The whole resolution is a ticker string and a
    constant map, so every claim it makes is provable in a unit test.
    """
    names = [n for n in outcome_names if n]
    if not external_id or not names:
        return {}

    pair = extract_team_codes_from_ticker(external_id)
    if not pair:
        return {}
    nicknames = [pair[0][1], pair[1][1]]

    repaired: dict[str, str] = {}
    for name in names:
        match = _TRUNCATED_TAIL_RE.match(str(name).strip())
        if not match:
            continue  # not truncated — correct data, left alone
        tail = match.group("tail")
        city = match.group("city").strip()

        # FIRST the ticker code, because it is the stronger signal and the one
        # gotcha #16 tells us to prefer. Only if the codes cannot separate the two
        # shipped names do we fall back to reading the truncated tail.
        by_code = [nick for code, nick in pair if _code_matches(code, str(name))]
        candidates = by_code if len(by_code) == 1 else [
            n for n in nicknames if _consistent(tail, n)
        ]
        # Exactly one, or we do not know which team this is. Two city siblings
        # sharing an initial that the codes also fail to separate land here and are
        # correctly left truncated: a short name is visibly short, a wrong one is not.
        if len(candidates) != 1:
            continue
        repaired[str(name)] = f"{city} {candidates[0]}"
    return repaired


def apply_name_repairs(text: Optional[str], repairs: dict[str, str]) -> Optional[str]:
    """Rewrite a card TITLE using the repairs derived from its outcomes.

    Longest-first so that a name which is a prefix of another cannot be rewritten
    out from under it. Substring replacement rather than a re-parse of the title,
    because the title's shape varies by series (`X vs Y`, `X vs Y: Spread`) and the
    outcome names are the part we have actually verified.
    """
    if not text or not repairs:
        return text
    out = str(text)
    for shipped in sorted(repairs, key=len, reverse=True):
        out = out.replace(shipped, repairs[shipped])
    return out
