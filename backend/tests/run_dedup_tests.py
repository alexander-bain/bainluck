"""Standalone cross-source golfer dedup tests.

Runs without importing the full app (avoids Python 3.9 incompatibility
with float|None syntax in espn_api.py). Copy-paste of the pure functions
from golf.py for validation.
"""

import re
import unicodedata


_EXTRA_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "æ": "ae", "Æ": "AE",
})


def _strip_diacritics(s):
    s = s.translate(_EXTRA_TRANSLITERATIONS)
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_golfer_name(name):
    name = name.strip()
    name = re.sub(r"^(Yes|No)\s*[-:]\s*", "", name, flags=re.I)
    name = re.sub(r'^"(.*)"$', r"\1", name)
    comma_match = re.match(r"^(\w[\w'-]+),\s+(\w[\w'-]+.*)$", name, flags=re.UNICODE)
    if comma_match:
        name = f"{comma_match.group(2)} {comma_match.group(1)}"
    return name


def _match_key(name):
    clean = _normalize_golfer_name(name)
    clean = re.split(r"\s+[-\u2013]\s+|\s+for\s+", clean, maxsplit=1)[0]
    clean = _strip_diacritics(clean)
    clean = clean.lower()
    clean = re.sub(r"^the\s+", "", clean)
    clean = clean.split(":")[0].strip()
    clean = re.sub(r"\b(?:jr|sr|iii|ii|iv)\.?\b", "", clean)
    clean = re.sub(r"[^a-z0-9\s]", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean


# Tests
tests_passed = 0
tests_failed = 0


def check(desc, got, expected):
    global tests_passed, tests_failed
    if got == expected:
        tests_passed += 1
        print(f"  PASS: {desc}")
    else:
        tests_failed += 1
        print(f"  FAIL: {desc}: got {got!r}, expected {expected!r}")


print("=== _normalize_golfer_name ===")
check("plain name", _normalize_golfer_name("Scottie Scheffler"), "Scottie Scheffler")
check("yes prefix", _normalize_golfer_name("Yes: Scottie Scheffler"), "Scottie Scheffler")
check("no prefix", _normalize_golfer_name("No - Tiger Woods"), "Tiger Woods")
check("quoted", _normalize_golfer_name('"Scottie Scheffler"'), "Scottie Scheffler")
check("last,first", _normalize_golfer_name("Scheffler, Scottie"), "Scottie Scheffler")
check("homa", _normalize_golfer_name("Homa, Max"), "Max Homa")
check("fleetwood", _normalize_golfer_name("Fleetwood, Tommy"), "Tommy Fleetwood")

print("\n=== Cross-source _match_key ===")
check("DG vs PM", _match_key("Scheffler, Scottie"), _match_key("Scottie Scheffler"))
check("Kalshi yes", _match_key("Yes: Scottie Scheffler"), _match_key("Scottie Scheffler"))
check("PM quoted", _match_key('"Rory McIlroy"'), _match_key("Rory McIlroy"))
check("diacritics", _match_key("Skarsgård, Gustav"), _match_key("Gustav Skarsgard"))
check("hovland", _match_key("Hovland, Viktor"), _match_key("Viktor Hovland"))
check("umlaut", _match_key("Müller, Thomas"), _match_key("Thomas Muller"))
check("hojgaard", _match_key("Højgaard, Nicolai"), _match_key("Nicolai Hojgaard"))
check("jr suffix", _match_key("Cam Davis Jr."), _match_key("Cam Davis"))
check("III suffix", _match_key("Davis Love III"), _match_key("Davis Love"))

print("\n=== 4-source roundtrip ===")
dg = _match_key("McIlroy, Rory")
pm = _match_key('"Rory McIlroy"')
ka = _match_key("Yes: Rory McIlroy")
oa = _match_key("Rory McIlroy")
check("4-source McIlroy", dg == pm == ka == oa == "rory mcilroy", True)

dg = _match_key("Hovland, Viktor")
pm = _match_key("Viktor Hovland")
ka = _match_key("Yes: Viktor Hovland")
oa = _match_key("Viktor Hovland")
check("4-source Hovland", dg == pm == ka == oa == "viktor hovland", True)

print("\n=== Edge cases ===")
check("dash suffix", _match_key("Scottie Scheffler - Masters"), _match_key("Scottie Scheffler"))
check("for suffix", _match_key("Tiger Woods for Masters"), _match_key("Tiger Woods"))
check("empty", _match_key(""), "")
check("whitespace", _match_key("  Scottie   Scheffler  "), "scottie scheffler")
check("the prefix", _match_key("The Field"), "field")

print(f"\n{'='*40}")
print(f"Results: {tests_passed} passed, {tests_failed} failed")
if tests_failed > 0:
    exit(1)
