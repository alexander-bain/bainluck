"""The VENUE's own name for a fight card, joined on bout evidence (#4485).

A card built from the schedule (events) source alone cannot name itself. Kalshi
stamps a card's identity into its ticker and Polymarket's titles carry the
promotion, so those two branches of :func:`event_combat.list_card_concepts`
produce "UFC 332: Silva vs Cong" and "Fight Night: Rosas Jr vs Barcelos". The
events rows carry two fighter names and nothing else, so that branch falls
through to its own main event and the card is named after one of its fights —
"Alex Volkanovski vs Movsar Evloev", where a reader expects "UFC 333".

discover/027 read both of our stores and found the name in neither: there is no
Kalshi row of any kind for those cards and `events` has no card-name column. It
explicitly did NOT read the venue, and recorded that as the next step. It is
done, and it resolves the other way (standing notice 26 — measure the venue, not
our mirror):

    GET site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates=…

models **a card as one event** — `name` is the card name and `competitions[]`
are its bouts. Every one of the 14 cards in the forward window is named. So the
name is absent from our stores and present at the venue, which under notice 27
makes it ours.

THE JOIN IS BOUT EVIDENCE, AND THAT IS THIS ENGINE'S OWN STANDARD, NOT A NEW ONE.
`fold_venue_scoped_tokens` already specifies what a cross-source card identity
claim needs, and says in as many words that an adjacent date is not it:

    the evidence is a SHARED BOUT — both fighters of one fight. One is
    sufficient and is the whole test: a bout cannot be on two different cards
    the same night.

So a venue card names one of ours only when :func:`bouts_are_one_fight` joins a
fight on each side. Measured against the live rows on 2026-09-22, that admits
exactly the two cards it should and refuses every card it should:

    ours 26oct25 (Yan/Dvalishvili, Volkanovski/Evloev)
        -> "UFC 333: Volkanovski vs. Evloev"   2 shared bouts
    ours 26nov15 (Harrison/Nunes, Gane/Hokit)
        -> "UFC 334: Gane vs. Hokit"           2 shared bouts

    ours 26dec27, 27jan01, 27jul11  -> NO MATCH  (the Odds API rumour fixtures
        of #4560; ESPN lists no card on any of those nights)
    the 26sep25 OKTAGON card        -> NO MATCH  (not on ESPN's UFC board —
        and it carries a "Max Holloway", so a one-sided name test would have
        joined it and called a Czech regional card a UFC one)

That last row is why the test is both sides of one bout and never a name in
common. The refusals are the point: this names a card or it says nothing, and
saying nothing is exactly today's behaviour.

WHAT THIS DELIBERATELY DOES NOT DO. It does not set `is_major`, so no card moves
in the feed — `is_major` is the marquee key `list_card_concepts` sorts on, and
re-ranking a card is a different claim from naming it. It does not invent a name
for a card the venue does not list, which this issue's own acceptance forbids.
And it does not touch the date half — every concept card already prints a date
from the instant the client localises (discover/123), and the remaining date
defect is withholding one where the rows refute themselves, which is #4560.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from app.utils.event_combat import bout_roster_key, bouts_are_one_fight

#: Redis key for the venue's card listing. Versioned, because the stored shape
#: is this module's own and a reader of an older shape must miss rather than
#: mis-parse — a miss is today's behaviour and is always safe here.
REDIS_KEY = "combat:venue_card_names:v1"

#: The listing outlives one refresh by a wide margin on purpose. The consumer is
#: a NAME, not a price: a card name does not change, and serving yesterday's
#: listing is strictly better than serving none. Long enough that a few missed
#: refreshes cost nothing, short enough that a retired shape drains itself.
REDIS_TTL_SECONDS = 7 * 24 * 60 * 60

#: Our sport keys whose ESPN board lists CARDS rather than games. The producer
#: reads this; the serve path gates on the config's own `venue_card_names`, so
#: adding a sport here cannot start naming cards until that sport opts in.
ESPN_CARD_SPORT_KEYS: tuple[str, ...] = ("mma_mixed_martial_arts",)

#: How far either way a venue card's date may sit from our card's bout span.
#: Not the join — bout evidence is the join — but a sanity fence, because a UFC
#: card's US Saturday evening is Sunday UTC and our token is UTC-derived, so the
#: two legitimately disagree by a day. Two days absorbs that without letting a
#: repeat booking a year out borrow a name from this season (the 27jul02
#: "Makhachev vs Usman" rumour row is a live instance of exactly that shape).
DATE_WINDOW_DAYS = 2


def parse_espn_cards(payload: Any) -> list[dict]:
    """ESPN's MMA scoreboard JSON -> ``[{name, date, bouts:[title, …]}, …]``.

    Tolerant by construction: a card whose competitors do not come in pairs
    contributes no bout and simply cannot be joined, which is the safe
    direction. A card with no usable bout at all is dropped — it could only ever
    match by date, and date is not evidence here.
    """
    cards: list[dict] = []
    if not isinstance(payload, dict):
        return cards
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        name = (event.get("name") or "").strip()
        date = event.get("date")
        if not name or not date:
            continue
        bouts: list[str] = []
        for comp in event.get("competitions") or []:
            if not isinstance(comp, dict):
                continue
            names = []
            for competitor in comp.get("competitors") or []:
                if not isinstance(competitor, dict):
                    continue
                athlete = competitor.get("athlete")
                display = (athlete or {}).get("displayName") if athlete else None
                if display:
                    names.append(str(display).strip())
            if len(names) == 2:
                bouts.append(f"{names[0]} vs {names[1]}")
        if bouts:
            cards.append({"name": name, "date": str(date), "bouts": bouts})
    return cards


def _as_utc(value: Any) -> Optional[datetime]:
    """A UTC-aware datetime out of an ISO string or a datetime, or None."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def match_card_name(
    bout_titles: Iterable[str],
    cards: Iterable[dict],
    *,
    span: tuple[Any, Any] | None = None,
) -> Optional[str]:
    """The venue's name for the card these bouts belong to, or None.

    ``bout_titles`` are OUR card's fights ("Alex Volkanovski vs Movsar Evloev");
    ``cards`` is :func:`parse_espn_cards`' output; ``span`` is our card's
    (earliest, latest) bout instant and applies :data:`DATE_WINDOW_DAYS`.

    Returns None — today's behaviour, a card named after its main event — on
    every uncertain reading, and there are three of them:

    * no venue card shares a bout with ours;
    * the only candidates sit outside the date fence;
    * **two or more venue cards match.** A bout cannot be on two cards, so a
      double match means one of the two joins is wrong and there is no way to
      tell which. Naming the card from either would be a coin flip, and this
      module's whole warrant is that a name it emits is the venue's.
    """
    mine = [k for k in (bout_roster_key(t) for t in bout_titles) if k]
    if not mine:
        return None

    lo = hi = None
    if span:
        lo, hi = _as_utc(span[0]), _as_utc(span[1])

    hits: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        name = card.get("name")
        if not name:
            continue
        when = _as_utc(card.get("date"))
        if lo is not None and hi is not None:
            if when is None:
                continue
            fence = timedelta(days=DATE_WINDOW_DAYS)
            if when < lo - fence or when > hi + fence:
                continue
        theirs = [k for k in (bout_roster_key(b) for b in card.get("bouts") or []) if k]
        if any(bouts_are_one_fight(a, b) for a in mine for b in theirs):
            hits.append(str(name))

    return hits[0] if len(hits) == 1 else None


def _client():
    """The bounded shared Redis client, or None. Never raises (gotcha #39)."""
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def store_card_names(cards: list[dict], rc=None) -> bool:
    """Publish the venue listing. False when nothing was stored."""
    import json

    rc = rc or _client()
    if rc is None or not cards:
        return False
    try:
        rc.setex(REDIS_KEY, REDIS_TTL_SECONDS, json.dumps(cards))
        return True
    except Exception:
        return False


def load_card_names(rc=None) -> list[dict]:
    """The published venue listing, or ``[]``.

    Fail-open in the only direction that exists: an empty list makes
    :func:`match_card_name` return None for every card, which is exactly the
    naming this engine did before #4485. No reader can be worse off for Redis
    being cold, down, or holding a shape this version does not know.
    """
    import json

    rc = rc or _client()
    if rc is None:
        return []
    try:
        raw = rc.get(REDIS_KEY)
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        cards = json.loads(raw)
        return cards if isinstance(cards, list) else []
    except Exception:
        return []
