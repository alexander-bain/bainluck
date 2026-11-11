"""Typed NFL prop rows and held-pair selection for #12581.

The existing typed predicate reader owns player/stat/line parsing. Standard
NFL and protected contracts stay distinct. A cross-venue participation-rule
hold selects one book; it never averages the incompatible contracts.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.utils.event_props_matrix import STAT_TABLE, _team_forms, type_prop_row
from app.utils.source_mark import _probability

# Verified against the actual KXNFL parents and Polymarket event 1356913.
# Kept local to this slice: the DURING matrix's closed stat table is unchanged.
NFL_STATS = {
    "passing yards": "passing_yards",
    "passing touchdowns": "passing_touchdowns",
    "receiving yards": "receiving_yards",
    "rushing yards": "rushing_yards",
    "touchdowns": "touchdowns",
}
NFL_LABELS = {
    "passing_yards": "Passing yards",
    "passing_touchdowns": "Passing touchdowns",
    "receiving_yards": "Receiving yards",
    "rushing_yards": "Rushing yards",
    "touchdowns": "Touchdowns",
}
_LABELS = {r[0]: r[1] for r in STAT_TABLE} | NFL_LABELS
_VERIFIED_PARTICIPATION_HOLDS = frozenset(
    {
        "passing_touchdowns",
        "receiving_yards",
        "rushing_yards",
        "touchdowns",
    }
)
_PROTECTED_SERIES = {
    "KXNFLPASSTDSPROT": "passing_touchdowns",
    "KXNFLRECYDSPROT": "receiving_yards",
    "KXNFLRSHYDSPROT": "rushing_yards",
    "KXNFLTDPROT": "touchdowns",
}


def _typed(
    row: dict, market: Any, player_and_stat: Callable, team_forms: set
) -> tuple[dict, str | None]:
    ticker = getattr(market, "external_id", "") or ""
    protected = (
        _PROTECTED_SERIES.get(ticker.split("-", 1)[0])
        if getattr(market, "source", None) == "kalshi"
        else None
    )
    name = row.get("market_name") or ""
    # Only a verified protected series may shed the suffix for parsing.
    if protected and name.endswith(" (protected)"):
        name = name[: -len(" (protected)")]
    typed = type_prop_row(
        name,
        row.get("outcome_name"),
        player_and_stat,
        team_forms,
        additional_stats=NFL_STATS,
    )
    if protected and typed.get("stat_key") != protected:
        typed = {"refused": "protected_stat_mismatch"}
    return typed, protected


def annotate_prop_fields(
    rows: list[dict],
    *,
    markets: Mapping[int, Any],
    player_and_stat: Callable,
    home_team: str | None,
    away_team: str | None,
) -> None:
    """Name the predicate on the served over axis, or retain an explicit refusal.

    This reuses the closed typed-stat vocabulary. An ambiguous predicate is
    retained unchanged, with null typed parts; it is never guessed or dropped.
    Protected labels precede all grouping so they cannot be averaged with a
    standard contract, including on finished games.
    """
    forms = _team_forms(home_team, away_team)
    for row in rows:
        typed, protected = _typed(
            row, markets.get(row.get("_market_id")), player_and_stat, forms
        )
        if "refused" in typed:
            row.update(
                player=None,
                stat=None,
                line=None,
                side=None,
                period=None,
                typing_refusal=typed["refused"],
            )
            continue
        stat = typed["stat_key"]
        label = _LABELS[stat] + (" (protected)" if protected else "")
        count = typed["count"] + (typed["kind"] == "count_at_most")
        row.update(
            player={"key": typed["subject_key"], "name": typed["subject_label"]},
            stat={"key": stat + ("_protected" if protected else ""), "label": label},
            line={"kind": "count_at_least", "value": count, "label": f"{count}+"},
            side="over",
            period="full_game",
        )
        if protected:
            row["market_name"] = f"{away_team} vs {home_team}: {label}"


def _book_width(row: dict, legs: Mapping[int, Any]) -> float:
    widths = []
    for oid in row.get("contributor_outcome_ids", []):
        leg = legs.get(oid)
        bid = _probability(getattr(leg, "current_yes_bid", None))
        ask = _probability(getattr(leg, "current_yes_ask", None))
        if bid is None or ask is None or ask == 0 or bid > ask:
            return float("inf")
        widths.append(ask - bid)
    return round(max(widths), 10) if widths else float("inf")


def shape_nfl_prop_rows(
    rows: list[dict],
    *,
    markets: Mapping[int, Any],
    legs: Mapping[int, Any],
    player_and_stat: Callable,
    home_team: str | None,
    away_team: str | None,
    sport_key: str | None,
) -> tuple[list[dict], list[dict]]:
    """One standard row per typed prop; protected remains a separate family.

    The hold records name every discarded contributor. A source-only prop
    remains present, including Polymarket rows older apps couldn't parse.
    Untyped/graded rows are left intact rather than guessed or re-adjudicated.
    """
    if sport_key != "americanfootball_nfl":
        return rows, []
    team_forms = _team_forms(home_team, away_team)
    groups: dict[tuple, list[tuple[dict, dict, bool]]] = {}
    untouched = []
    for row in rows:
        market = markets.get(row.get("_market_id"))
        typed, protected_stat = _typed(row, market, player_and_stat, team_forms)
        if (
            "refused" in typed
            or typed["stat_key"] not in _LABELS
            or row.get("resolution_source") is not None
            or row.get("hit") is not None
        ):
            untouched.append(row)
            continue
        if protected_stat is not None and protected_stat != typed["stat_key"]:
            untouched.append(row)
            continue
        count = typed["count"] + (typed["kind"] == "count_at_most")
        key = (typed["subject_key"], typed["stat_key"], count, bool(protected_stat))
        groups.setdefault(key, []).append((row, typed, bool(protected_stat)))

    selected = []
    held = []
    for (player, stat, count, protected), entries in groups.items():
        # First choose one own-side leg per venue/market. A genuine over/yes
        # leg outranks the complemented under leg of that SAME book.
        books: dict[tuple, tuple[dict, dict, bool]] = {}
        for entry in entries:
            row, typed, _ = entry
            key = (row.get("source"), row.get("_market_id"))
            previous = books.get(key)
            if previous is None or (
                typed["side"] == "over" and previous[1]["side"] != "over"
            ):
                books[key] = entry
        # Known book beats unknown, then narrower book, then the existing
        # Kalshi preference. Unknown widths are reported, never called tight.
        chosen = min(
            books.values(),
            key=lambda e: (
                _book_width(e[0], legs),
                e[0].get("source") != "kalshi",
                e[0].get("_market_id") or 0,
            ),
        )
        row, typed, _ = chosen
        result = dict(row)
        result["player"] = {"key": player, "name": typed["subject_label"]}
        label = _LABELS[stat] + (" (protected)" if protected else "")
        result["stat"] = {
            "key": stat + ("_protected" if protected else ""),
            "label": label,
        }
        result["line"] = {
            "kind": "count_at_least",
            "value": count,
            "label": f"{count}+",
        }
        result["side"] = "over"
        result["period"] = "full_game"
        result["contract_key"] = (
            "kalshi_protected" if protected else str(row.get("source"))
        )
        result["market_name"] = f"{away_team} vs {home_team}: {label}"
        result["outcome_name"] = f"{typed['subject_label']}: {count}+"
        result["threshold"] = count
        result["represented_outcome_ids"] = sorted(
            {
                oid
                for entry in entries
                for oid in entry[0].get("contributor_outcome_ids", [])
            }
        )
        if typed["side"] == "under" and isinstance(
            result.get("movement"), (int, float)
        ):
            result["movement"] = -result["movement"]
        result["_inverted"] = False
        result["all_sources"] = [row["source"]]
        result["source_count"] = 1
        # SourceLabels on installed iOS builds renders this key as no pill.
        # Actual venue provenance remains solely the chosen source mark.
        if row.get("source") == "polymarket":
            result["source"] = "bainluck"
        selected.append(result)

        venues = {entry[0].get("source") for entry in entries}
        if len(venues) > 1:
            width = _book_width(row, legs)
            known_widths = [
                _book_width(entry[0], legs)
                for entry in books.values()
                if _book_width(entry[0], legs) != float("inf")
            ]
            selection = "book_width_unknown"
            if len(known_widths) == 1:
                selection = "only_known_book"
            elif known_widths:
                selection = (
                    "book_width_tie"
                    if known_widths.count(width) > 1
                    else "tighter_book"
                )
            held.append(
                {
                    "player": player,
                    "stat": stat,
                    "at_least": count,
                    "reason": (
                        "participation_rule_differs"
                        if stat in _VERIFIED_PARTICIPATION_HOLDS
                        else "contract_equivalence_unverified"
                    ),
                    "selected_source": row.get("source"),
                    "selection": selection,
                    "selected_outcome_ids": list(
                        row.get("contributor_outcome_ids", [])
                    ),
                    "candidate_outcome_ids": sorted(
                        {
                            oid
                            for e in entries
                            for oid in e[0].get("contributor_outcome_ids", [])
                        }
                    ),
                    "candidate_market_ids": sorted(
                        {e[0]["_market_id"] for e in entries}
                    ),
                }
            )
    return untouched + selected, held
