"""Literal requests for a game's title market or an upcoming team set."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ExplicitSearch:
    subject: str
    next_games: int | None = None


_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_NEXT = re.compile(r"(?P<team>.+?)\s+next\s+(?P<count>[1-5]|one|two|three|four|five)\s+games?", re.I)
_TITLE = re.compile(r"who\s+will\s+win\s+(?:the\s+)?(super\s+bowl)\??", re.I)


def explicit_search(query: str) -> ExplicitSearch | None:
    query = " ".join(query.split())
    if match := _NEXT.fullmatch(query):
        value = match["count"].lower()
        return ExplicitSearch(match["team"], _COUNTS[value] if value in _COUNTS else int(value))
    if match := _TITLE.fullmatch(query):
        return ExplicitSearch("super bowl")
    return None
