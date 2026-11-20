"""Literal requests for a game's title market or an upcoming team set."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitSearch:
    subject: str
    next_games: int | None = None


_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_COUNTS.update({str(value): value for value in range(1, 6)})


def explicit_search(query: str) -> ExplicitSearch | None:
    words = query.split()
    lowered = [word.casefold() for word in words]
    # A fixed suffix keeps this linear even for a long, untrusted query.
    if (len(words) >= 4 and lowered[-3] == "next"
            and lowered[-2] in _COUNTS and lowered[-1] in {"game", "games"}):
        return ExplicitSearch(" ".join(words[:-3]), _COUNTS[lowered[-2]])
    if lowered and lowered[-1].endswith("?"):
        lowered[-1] = lowered[-1][:-1]
    if lowered in (["who", "will", "win", "the", "super", "bowl"],
                   ["who", "will", "win", "super", "bowl"]):
        return ExplicitSearch("super bowl")
    return None
