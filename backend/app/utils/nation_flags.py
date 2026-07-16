"""National-team flag resolution — #208 (WC V2 CLIMB, Item 1c).

The World Cup winner field and the bracket duels are NATIONS, not clubs, and the
``teams`` rows for national sides ship with ``logo_url = NULL`` (verified live
2026-07-15: every ``soccer_fifa_world_cup`` nation had no crest). A national team's
canonical crest IS its flag, so we resolve one from a curated NATION-NAME -> ISO
map against a free flag CDN (flagcdn.com, ISO 3166-1 alpha-2, lowercase; the UK
home nations use flagcdn's ``gb-eng`` / ``gb-sct`` / ``gb-wls`` / ``gb-nir``
subdivision codes).

This is deliberately a CURATED map, not a heuristic: only known national-team
names resolve, so a club ("Real Madrid", "Boca Juniors") NEVER gets a flag — the
"clubs untouched" guarantee the ruling requires. Diacritic-insensitive lookup
("Côte d'Ivoire" == "cote d'ivoire") mirrors ``event_soccer._norm``.

Pure module (imports only the stdlib) so it is safe to unit-test, safe to reuse
read-side in the concept adapter, and safe to drive a one-off ``teams.logo_url``
backfill (``scripts/backfill_nation_flags.py``)."""

from __future__ import annotations

import re
import unicodedata

# Curated national-team name -> flagcdn code. Covers every nation the 2026 FIFA
# World Cup winner field + bracket surfaced live (2026-07-15) plus the common
# alternate spellings the sources use. Keys are stored raw; lookup is normalized.
_NATION_TO_ISO: dict[str, str] = {
    # --- 2026 WC field + qualifier nations ---
    "Spain": "es",
    "England": "gb-eng",
    "Argentina": "ar",
    "France": "fr",
    "Portugal": "pt",
    "Brazil": "br",
    "Germany": "de",
    "Netherlands": "nl",
    "Belgium": "be",
    "Italy": "it",
    "Croatia": "hr",
    "Morocco": "ma",
    "USA": "us",
    "United States": "us",
    "Mexico": "mx",
    "Canada": "ca",
    "Uruguay": "uy",
    "Colombia": "co",
    "Ecuador": "ec",
    "Paraguay": "py",
    "Bolivia": "bo",
    "Switzerland": "ch",
    "Austria": "at",
    "Denmark": "dk",
    "Sweden": "se",
    "Norway": "no",
    "Iceland": "is",
    "Poland": "pl",
    "Ukraine": "ua",
    "Romania": "ro",
    "Czech Republic": "cz",
    "Czechia": "cz",
    "Slovakia": "sk",
    "Albania": "al",
    "North Macedonia": "mk",
    "Kosovo": "xk",
    "Bosnia & Herzegovina": "ba",
    "Bosnia and Herzegovina": "ba",
    "Turkey": "tr",
    "Turkiye": "tr",
    "Türkiye": "tr",
    "Wales": "gb-wls",
    "Scotland": "gb-sct",
    "Northern Ireland": "gb-nir",
    "Republic of Ireland": "ie",
    "Ireland": "ie",
    "Japan": "jp",
    "South Korea": "kr",
    "Korea Republic": "kr",
    "Iran": "ir",
    "Iraq": "iq",
    "Saudi Arabia": "sa",
    "Qatar": "qa",
    "Jordan": "jo",
    "Uzbekistan": "uz",
    "Australia": "au",
    "New Zealand": "nz",
    "New Caledonia": "nc",
    "Senegal": "sn",
    "Ghana": "gh",
    "Ivory Coast": "ci",
    "Côte d'Ivoire": "ci",
    "Cote d'Ivoire": "ci",
    "South Africa": "za",
    "Algeria": "dz",
    "Tunisia": "tn",
    "Egypt": "eg",
    "Cape Verde": "cv",
    "DR Congo": "cd",
    "Congo DR": "cd",
    "Nigeria": "ng",
    "Cameroon": "cm",
    "Panama": "pa",
    "Jamaica": "jm",
    "Haiti": "ht",
    "Suriname": "sr",
    "Curaçao": "cw",
    "Curacao": "cw",
}


def _norm(s: str | None) -> str:
    """Diacritic-stripped, lowercased, whitespace-collapsed key — matches
    ``event_soccer._norm`` so linkage and flag lookup agree."""
    n = re.sub(r"\s+", " ", (s or "").strip().lower())
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", n) if not unicodedata.combining(ch)
    )


# Normalized-name -> ISO, built once.
_ISO_BY_NORM: dict[str, str] = {_norm(k): v for k, v in _NATION_TO_ISO.items()}


def nation_iso(name: str | None) -> str | None:
    """ISO flagcdn code for a national-team name, or None if it is not a known
    nation (clubs, awards, placeholders all return None)."""
    return _ISO_BY_NORM.get(_norm(name))


def is_nation(name: str | None) -> bool:
    """True when ``name`` is a known national team (the "nation-type entity" mark)."""
    return _norm(name) in _ISO_BY_NORM


def flag_url(name: str | None, size: str = "w160") -> str | None:
    """Full flag-CDN URL for a national-team name, or None for non-nations.

    ``size`` is a flagcdn width token (``w80`` / ``w160`` / ``w320`` ...)."""
    iso = nation_iso(name)
    if iso is None:
        return None
    return f"https://flagcdn.com/{size}/{iso}.png"
