"""Shared editorial wording helpers for grouped-card candidate producers (#12288).

Enforces Fable's 8-rule editorial wording standard across dynamic grouped-card
templates:
1. Title: finding or plain label, <= 45 chars.
2. Reason: 1–2 sentences, <= 120 chars, person/team + number + comparison/record/change.
3. Zero build-jargon ("actively trading", "excluded", "omitted", "boards", "$0-volume",
   "settles on", "within ±", "priced at", "holdovers", "recent trading verified").
4. Zero brackets in title, reason, row labels, or footer; no repeating title/rows.
5. Plain 1-line row labels (never raw market titles, never full work title before artist).
6. Footer: one plain fact or empty.
7. External records loaded from stored, dated JSON.
8. Only facts held in our data ("was X% before the game", never "opened at X%").
"""

from __future__ import annotations

import re
from typing import Optional

NUMBER_WORDS: dict[int, str] = {
    1: "One",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
}

EDITORIAL_JARGON_RE = re.compile(
    r"\b(?:"
    r"actively\s+trading|excluded|omitted|boards?|0-volume|settles?\s+on|"
    r"priced\s+at|holdovers?|recent\s+trading|verified|independent\s+markets|"
    r"mutually\s+exclusive|single-winner\s+market|frontrunner\s+chance|"
    r"matched\s+within|questions?|stale|settled|venues?|kalshi|polymarket|"
    r"opened|big\s+game|domains?"
    r")\b"
    r"|within\s*±",
    re.IGNORECASE,
)

BRACKET_RE = re.compile(r"[\(\)\[\]]")

_MULTI_WORD_CLUBS: tuple[str, ...] = (
    "Trail Blazers",
    "Maple Leafs",
    "Red Wings",
    "Blue Jackets",
    "Golden Knights",
    "Red Sox",
    "White Sox",
    "Blue Jays",
    "Utah HC",
    "Inter Miami",
    "LA Galaxy",
    "Real Madrid",
    "Aston Villa",
    "West Ham",
    "Crystal Palace",
    "Nottingham Forest",
    "Manchester City",
    "Manchester United",
)

_EXACT_SHORT_TEAMS: dict[str, str] = {
    "san antonio spurs": "Spurs",
    "utah jazz": "Jazz",
    "los angeles lakers": "Lakers",
    "la lakers": "Lakers",
    "los angeles clippers": "Clippers",
    "la clippers": "Clippers",
    "phoenix suns": "Suns",
    "minnesota timberwolves": "Timberwolves",
    "chicago bulls": "Bulls",
    "dallas mavericks": "Mavericks",
    "cleveland cavaliers": "Cavaliers",
    "boston celtics": "Celtics",
    "miami heat": "Heat",
    "atlanta hawks": "Hawks",
    "oklahoma city thunder": "Thunder",
    "denver nuggets": "Nuggets",
    "golden state warriors": "Warriors",
    "new york knicks": "Knicks",
    "philadelphia 76ers": "76ers",
    "houston rockets": "Rockets",
    "detroit pistons": "Pistons",
    "detroit lions": "Lions",
    "new england patriots": "Patriots",
    "denver broncos": "Broncos",
    "las vegas raiders": "Raiders",
    "kansas city chiefs": "Chiefs",
    "buffalo bills": "Bills",
    "philadelphia eagles": "Eagles",
    "san francisco 49ers": "49ers",
    "green bay packers": "Packers",
    "baltimore ravens": "Ravens",
    "nashville predators": "Predators",
    "san jose sharks": "Sharks",
    "colorado avalanche": "Avalanche",
    "winnipeg jets": "Jets",
    "carolina hurricanes": "Hurricanes",
    "edmonton oilers": "Oilers",
    "florida panthers": "Panthers",
    "dallas stars": "Stars",
    "minnesota wild": "Wild",
    "tampa bay lightning": "Lightning",
    "timrå ik": "Timrå",
    "brynäs if": "Brynäs",
    "växjö lakers": "Växjö",
    "malmö redhawks": "Malmö",
    "newport county": "Newport",
    "crewe alexandra": "Crewe",
    "córdoba cf": "Córdoba",
    "ud almería": "Almería",
}

_MONTH_SHORT: dict[str, str] = {
    "january": "Jan",
    "february": "Feb",
    "march": "Mar",
    "april": "Apr",
    "may": "May",
    "june": "Jun",
    "july": "Jul",
    "august": "Aug",
    "september": "Sep",
    "october": "Oct",
    "november": "Nov",
    "december": "Dec",
}


def number_word(n: int, *, capitalize: bool = True) -> str:
    word = NUMBER_WORDS.get(int(n), str(int(n)))
    return word if capitalize else word.lower()


def short_team_name(team: str, sport: Optional[str] = None) -> str:
    cleaned = " ".join(str(team or "").split()).strip()
    if not cleaned:
        return ""
    low = cleaned.lower()
    if low in _EXACT_SHORT_TEAMS:
        return _EXACT_SHORT_TEAMS[low]
    for mw in _MULTI_WORD_CLUBS:
        if low.endswith(mw.lower()):
            return mw
    # Strip soccer/hockey club suffixes like IK, IF, FC, AFC, CF
    stripped = re.sub(r"^(?:UD|CD|FC|AC|AS|SC)\s+|\s+(?:FC|AFC|CF|IK|IF|BK|SK)$", "", cleaned)
    if stripped != cleaned and stripped:
        return stripped
    # College sports (194-A): print the school, never the mascot
    sp_low = str(sport or "").lower()
    if any(tok in sp_low for tok in ("ncaab", "ncaaf", "ncaaw", "college")):
        school = re.sub(
            r"\s+(?:Blue\s+Devils|Crimson\s+Tide|Tar\s+Heels|Fighting\s+Irish|"
            r"Golden\s+Eagles|Red\s+Raiders|Nittany\s+Lions|Horned\s+Frogs|"
            r"Yellow\s+Jackets|Sun\s+Devils|Demon\s+Deacons|Scarlet\s+Knights|"
            r"Bulldogs|Rebels|Wildcats|Tigers|Eagles|Bears|Cougars|Huskies|"
            r"Spartans|Wolverines|Buckeyes|Hoosiers|Boilermakers|Illini|Hawkeyes|"
            r"Badgers|Gators|Volunteers|Commodores|Razorbacks|Aggies|Longhorns|"
            r"Sooners|Jayhawks|Cyclones|Mountaineers|Bruins|Trojans|Ducks|"
            r"Beavers|Cardinals|Cavaliers|Hokies|Seminoles|Hurricanes|Orangemen|Orange)$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        if school:
            return school
    # Standard US pro leagues (NBA/NFL/NHL/MLB): use mascot word when 2+ words
    if sp_low in {
        "basketball_nba",
        "americanfootball_nfl",
        "icehockey_nhl",
        "baseball_mlb",
    }:
        parts = cleaned.split()
        if len(parts) >= 2:
            return parts[-1]
    return stripped or cleaned


def short_matchup_phrase(opp_phrase: str, sport: Optional[str] = None) -> str:
    cleaned = " ".join(str(opp_phrase or "").split()).strip()
    m = re.match(r"^(at|vs)\s+(.+)$", cleaned, flags=re.IGNORECASE)
    if not m:
        return short_team_name(cleaned, sport)
    prep, raw_team = m.group(1).lower(), m.group(2)
    return f"{prep} {short_team_name(raw_team, sport)}"


def display_award_leader(raw_leader: str) -> str:
    """Strip full song/album work title before ' - ' so award rows show 'Category · leader'."""
    cleaned = " ".join(str(raw_leader or "").split()).strip()
    if " - " in cleaned:
        artist_part = cleaned.split(" - ", 1)[1].strip()
        if "," in artist_part:
            artist_part = artist_part.split(",", 1)[0].strip()
        if artist_part:
            return artist_part
    return cleaned


def _strip_brackets_and_corp(text: str) -> str:
    out = re.sub(r"\s*\([^)]*\)", "", text)
    out = re.sub(r"\s*\[[^\]]*\]", "", out)
    out = re.sub(r"\b(?:Inc\.|Corp\.|Corporation|Ltd\.|PLC)\b", "", out, flags=re.IGNORECASE)
    return " ".join(out.split()).strip(" ,.-?!")


def plain_market_subject(market_name: str, outcome_name: str = "Yes") -> Optional[str]:
    """Convert raw upstream market + outcome strings into a plain 1-line subject."""
    m_raw = re.sub(
        r"\b(?:\d{4}\s+)?Big\s+Game\b",
        "Super Bowl",
        " ".join(str(market_name or "").split()).strip().rstrip("?"),
        flags=re.IGNORECASE,
    )
    o_raw = re.sub(
        r"\b(?:\d{4}\s+)?Big\s+Game\b",
        "Super Bowl",
        " ".join(str(outcome_name or "").split()).strip(),
        flags=re.IGNORECASE,
    )
    if not m_raw or not o_raw:
        return None
    low_out = o_raw.lower()
    if low_out in {"no", "other", "none", "field"} or low_out.startswith("not "):
        return None
    if "___" in m_raw or "___" in o_raw:
        return None

    # 1. Stock touch low/high: "Will Alphabet Inc. (GOOGL) hit (LOW) $270 in November"
    m_hit = re.match(
        r"^Will\s+(.+?)\s+hit\s+\(\s*(LOW|HIGH)\s*\)\s*(\$\d+(?:\.\d+)?)\s+in\s+([A-Za-z]+|\d{4})$",
        m_raw,
        flags=re.IGNORECASE,
    )
    if m_hit:
        company = _strip_brackets_and_corp(m_hit.group(1))
        direction = "below" if m_hit.group(2).upper() == "LOW" else "above"
        price_tok = m_hit.group(3)
        period_raw = m_hit.group(4)
        period = _MONTH_SHORT.get(period_raw.lower(), period_raw)
        return f"{company} {direction} {price_tok} in {period}"

    # 2. Arena / benchmark rank debut: "Gemini Krypton: Text Arena Rank Debut" + "Top 3"
    m_debut = re.match(
        r"^(.+?):\s*(?:Text\s+|Coding\s+)?Arena\s+Rank\s+Debut$",
        m_raw,
        flags=re.IGNORECASE,
    )
    if m_debut and re.match(r"^top\s+\d+$", low_out):
        model_name = _strip_brackets_and_corp(m_debut.group(1))
        rank_hyphen = re.sub(r"\s+", "-", low_out)
        return f"{model_name} {rank_hyphen} debut"

    # 3. Golf / tournament top-N finish: "Austin Championship Top 5 Finish" + "Brendon Todd"
    m_top_finish = re.match(
        r"^(.+?)\s+Top\s+(\d+)\s+Finish$",
        m_raw,
        flags=re.IGNORECASE,
    )
    if m_top_finish and low_out != "yes":
        event_raw = _strip_brackets_and_corp(m_top_finish.group(1))
        top_n = m_top_finish.group(2)
        loc = re.sub(
            r"\s+(?:Championship|Tournament|Classic|Invitational|Open|Masters)$",
            "",
            event_raw,
            flags=re.IGNORECASE,
        ).strip()
        person = _strip_brackets_and_corp(o_raw)
        prep = "in" if loc and loc != event_raw else "at"
        target = loc or event_raw
        return f"{person} top {top_n} {prep} {target}"

    # 4. Ceremony award winner: "Grammys 2027: Record of the Year Winner" + "Manchild - Sabrina Carpenter"
    m_ceremony = re.match(
        r"^(?:Grammys?|Oscars?|Academy\s+Awards?|Emmys?|Golden\s+Globes?)(?:\s+\d{4})?\s*(?:winner)?\s*:\s*(.+?)(?:\s+Winner)?$",
        m_raw,
        flags=re.IGNORECASE,
    )
    if not m_ceremony:
        m_ceremony = re.match(
            r"^(?:Oscar|Grammy|Emmy|Golden\s+Globe)\s+winner\s*:\s*(.+)$",
            m_raw,
            flags=re.IGNORECASE,
        )
    if m_ceremony and low_out != "yes":
        cat = _strip_brackets_and_corp(m_ceremony.group(1))
        leader = _strip_brackets_and_corp(display_award_leader(o_raw))
        return f"{cat} · {leader}"

    # 5. League division winner: "NBA Northwest Division Winner" + "Trail Blazers"
    m_div = re.match(
        r"^(NBA|NFL|NHL|MLB)\s+(.+?)\s+Division\s+(?:Winner|Champion)$",
        m_raw,
        flags=re.IGNORECASE,
    )
    if m_div and low_out != "yes":
        lg = m_div.group(1).upper()
        div_name = _strip_brackets_and_corp(m_div.group(2))
        club = short_team_name(_strip_brackets_and_corp(o_raw))
        return f"{club} · {lg} {div_name}"

    # 6. Next <Role>: "Next James Bond actor" / "Next CEO of NVIDIA"
    m_next_ceo = re.match(r"^Next\s+CEO\s+of\s+(.+)$", m_raw, flags=re.IGNORECASE)
    if m_next_ceo and low_out != "yes":
        co = _strip_brackets_and_corp(m_next_ceo.group(1))
        person = _strip_brackets_and_corp(o_raw)
        return f"Next {co} CEO · {person}"

    m_next = re.match(r"^Next\s+(.+?)(?:\s+actor)?$", m_raw, flags=re.IGNORECASE)
    if m_next and low_out != "yes":
        role = _strip_brackets_and_corp(m_next.group(1))
        person = _strip_brackets_and_corp(o_raw)
        return f"Next {role} · {person}"

    # 7. IPO market cap: "Anthropic IPO Closing Market Cap" + "$1.25–$1.5T"
    m_ipo = re.match(r"^(.+?)\s+IPO\s+(?:Closing\s+)?Market\s+Cap$", m_raw, flags=re.IGNORECASE)
    if m_ipo and low_out != "yes":
        co = _strip_brackets_and_corp(m_ipo.group(1))
        cap = _strip_brackets_and_corp(o_raw)
        return f"{co} IPO at {cap}"

    # 8. Date deadline outcome ("December 31, 2027")
    m_year_out = re.match(
        r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s*(202\d)$",
        o_raw,
        flags=re.IGNORECASE,
    )
    if m_year_out:
        yr = m_year_out.group(1)
        subj = _strip_brackets_and_corp(re.sub(r"^Will\s+", "", m_raw, flags=re.IGNORECASE))
        subj = re.sub(r"\s+announces?\s+another\s+", " ", subj, flags=re.IGNORECASE)
        subj = re.sub(r"\s+solution$", "", subj, flags=re.IGNORECASE)
        return f"{subj} by {yr}"

    # 9. Generic clean fallback
    base = re.sub(r"^Will\s+", "", m_raw, flags=re.IGNORECASE)
    base = re.sub(r"\s+Winner$", "", base, flags=re.IGNORECASE)
    base = _strip_brackets_and_corp(base)
    out_clean = _strip_brackets_and_corp(o_raw)
    if not base:
        return None
    if low_out == "yes" or out_clean.lower() == base.lower():
        result = base
    else:
        result = f"{base} · {out_clean}"
    if BRACKET_RE.search(result) or EDITORIAL_JARGON_RE.search(result):
        return None
    return result
