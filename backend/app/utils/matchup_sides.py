"""Name the two sides of a bare matchup market, so a card stops rendering "Yes".

WHY THIS EXISTS (#3089, second surface)
---------------------------------------
A Polymarket game market is ingested as a decomposed sub-market (gotcha #18) and
``tasks/polymarket.py`` writes its two outcomes with hardcoded literal names::

    over_name  = "Over"  if "o/u" in sub_name.lower() else "Yes"   # :1340
    under_name = "Under" if "o/u" in sub_name.lower() else "No"    # :1451

The venue's own label is *also* the string ``"Yes"`` — ``_leg_label`` already
refuses it (``if _label_key(token) in _YES_NO_LABELS: return derived``) — so the
side is nowhere in the outcome text and nowhere in the metadata. The only place
it survives is the market's own NAME, which is Polymarket's question title:

    US Open WTA: Iga Swiatek vs Qinwen Zheng     Yes 0.795 / No 0.205

Rendered as-is that card is unreadable: 79.5% for WHOM? On ``/api/hub/tennis``
eleven of nineteen match cards read this way, and because the payload sorts most
probable first, the order flips between cards ("No 0.555 / Yes 0.445" on
Osaka vs Rybakina) — so a reader who learns the convention is wrong half the time.

``Yes`` IS THE FIRST-NAMED SIDE — MEASURED, NOT ASSUMED
-------------------------------------------------------
Verified on production 2026-09-06 by comparing each bare-matchup market's ``Yes``
price against an INDEPENDENT named-side outcome on the same event (a sibling
market that spells the player out), over open tennis/table_tennis markets:

    79 agreements, 0 reversals, remainder a stale 0.5/0.005 placeholder.

e.g. "US Open ATP: Botic van de Zandschulp vs Alex de Minaur" Yes = 1.000 against
the independently named "Botic van de Zandschulp" = 0.9865.

WHY THE PARSE IS STRICT, AND NOT ``extract_matchup``
-----------------------------------------------------
``utils.prediction_market_matching.extract_matchup`` is deliberately PERMISSIVE —
it is built to recover participants from "A vs. B: O/U 11.5" so the matcher can
link a prop row to its game. Reusing it here would be precisely backwards: a prop
row is the one case we must refuse. Two shapes share the "% vs %" name, and only
the first may be named (census, production 2026-09-06, open markets with an exact
Yes/No pair and " vs " in the name — tennis 1,944, table_tennis 882, esports 179,
cricket 139):

    SHAPE 1  the match itself       "US Open WTA: Iga Swiatek vs Qinwen Zheng"
             -> Yes = Swiatek wins. Nameable.

    SHAPE 2  a PROP about the match "Set Handicap: Vallejo (-1.5) vs Monfils (+1.5)"
                                    "Counter-Strike: fnatic vs NIP - Map 1 Winner"
                                    "ECS Portugal: Odivelas vs Amadora - Who wins the toss?"
             -> Yes = "covers -1.5" / "wins map 1" / "wins the toss", NOT "wins".
                Naming these re-commits the exact defect 43cc8658 repaired on the
                event page one commit ago. Refused.

So this module answers one question only — *is this name nothing but a matchup?*
— and returns None the moment anything else is in the string. An unnameable row
keeps its "Yes" and renders exactly as it does today; the failure mode is the
status quo, never a wrong name.
"""

from __future__ import annotations

import re

# A qualifier anywhere in the name means the market asks something NARROWER than
# "who wins", so its Yes/No cannot be a side.
#
# Group 1 is the measured Shape-2 vocabulary ("Set 1 Winner", "Set Handicap",
# "Game Spread", "Total Sets: O/U 2.5"). Group 2 is the scope nouns those
# qualifiers attach to, so a bare "Set 1: A vs B" is refused even though it names
# no qualifier at all.
#
# Word-anchored, and this matters: "Sunderland" must not trip `under`,
# "Winegar" must not trip `wins`, "Roland" must not trip `round`, and
# "(Doubles)" must stay legal — it is a draw type, not a prop.
_PROP_QUALIFIER = re.compile(
    r"\b(?:winner|wins|handicap|spread|totals?|over|under|o/u|moneyline"
    r"|map|set|sets|game|games|round|period|quarter|half|innings)\b",
    re.IGNORECASE,
)

# " vs " / " vs. ", the only split we accept.
_VS = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)

# One leading "Tournament: " prefix ("US Open ATP (Doubles): ..."). Parens are
# allowed HERE — the noise is the tournament's, not the matchup's.
_PREFIX_SPLIT = ": "

_MIN_SIDE_LEN = 2
_MAX_SIDE_LEN = 60


def _side_is_nameable(side: str) -> bool:
    """A side must look like a person, pair or team — nothing else."""
    if not (_MIN_SIDE_LEN <= len(side) <= _MAX_SIDE_LEN):
        return False
    if not re.search(r"[A-Za-z]", side):
        return False
    # "(‑1.5)", "(BO3)", any residual bracketing: the body of a bare matchup has
    # none. Prefix parens were already discarded above.
    if "(" in side or ")" in side or "[" in side:
        return False
    return True


def bare_matchup_sides(market_name: str | None) -> tuple[str, str] | None:
    """The two sides of ``name``, but ONLY when the name is nothing but a matchup.

    Returns ``(first_named, second_named)`` for a Shape-1 name, else ``None``.

    >>> bare_matchup_sides("US Open WTA: Iga Swiatek vs Qinwen Zheng")
    ('Iga Swiatek', 'Qinwen Zheng')
    >>> bare_matchup_sides("Set Handicap: Vallejo (-1.5) vs Monfils (+1.5)") is None
    True
    >>> bare_matchup_sides("Counter-Strike: fnatic vs NIP - Map 1 Winner") is None
    True
    """
    name = (market_name or "").strip()
    if not name:
        return None

    # Exactly one matchup in the whole string. Two means we cannot tell which one
    # the Yes belongs to.
    if len(_VS.findall(name)) != 1:
        return None

    # " - " introduces a suffix qualifier on every Shape-2 row measured
    # ("- Map 1 Winner", "- Who wins the toss?"). A question mark likewise.
    # Note this is the SPACED hyphen only, so "Counter-Strike" is untouched.
    if " - " in name or "?" in name:
        return None

    body = name.split(_PREFIX_SPLIT, 1)[1] if _PREFIX_SPLIT in name else name

    # A second colon means the prefix was not the only qualifier
    # ("...: Total Sets: O/U 2.5").
    if ":" in body:
        return None

    # The matchup must survive into the body — "A vs B: something" splits to a
    # body with no " vs " at all, and that something is a prop.
    parts = _VS.split(body)
    if len(parts) != 2:
        return None

    # Checked against the FULL name: the qualifier may sit in the prefix
    # ("Set 1 Winner: Vallejo vs Monfils") or the body.
    if _PROP_QUALIFIER.search(name):
        return None

    first, second = parts[0].strip(), parts[1].strip()
    if not _side_is_nameable(first) or not _side_is_nameable(second):
        return None
    if first.lower() == second.lower():
        return None
    return first, second


# The convention above is MEASURED on racket-sport markets and nowhere else.
#
# The same ingest line writes "Yes" for every sport, so the ordering is very
# likely universal — but "likely" is not the bar for a name rendered next to a
# price. Cricket is the concrete refusal: its bare-matchup rows are real
# (139 open), yet its only independent named-side source is a parent whose
# outcomes are truncated child titles, and the Yes/No pair on
# "German Super League NRW T10: Dusseldorf Blackcaps vs Cricket Club Koln"
# sums to 1.235 — unverifiable AND junk. Esports self-refuses on the parse (every
# bare-matchup esports row carries a " - <tournament>" suffix).
#
# Widening this set is an evidence question, not a judgement call: re-run the
# named-side agreement measurement for the sport and require 0 reversals.
VERIFIED_SIDE_ORDER_SPORTS = frozenset({"tennis", "table_tennis"})

_YES_NO = ("Yes", "No")


def sided_yes_no_labels(
    market_name: str | None,
    sport_category: str | None,
    outcome_names: list[str],
) -> dict[str, str] | None:
    """``{"Yes": first_named, "No": second_named}``, or None to leave the card alone.

    Every precondition must hold: a verified sport, an exact two-row Yes/No pair,
    and a name that is nothing but a matchup.
    """
    if (sport_category or "") not in VERIFIED_SIDE_ORDER_SPORTS:
        return None
    if sorted(outcome_names) != sorted(_YES_NO):
        return None
    sides = bare_matchup_sides(market_name)
    if sides is None:
        return None
    return {"Yes": sides[0], "No": sides[1]}
