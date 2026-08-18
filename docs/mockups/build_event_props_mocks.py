#!/usr/bin/env python3
"""Build the UX-AMBITION-1 event-page props mocks from REAL production payloads.

Every number rendered by this script is read out of the four JSON files captured
from production on 2026-08-18; nothing is invented and nothing is rounded into a
prettier shape. That is the point: Alex rules by looking, and a mock that shows
numbers the product cannot actually produce is a promise we would then owe.

Inputs (captured 2026-08-18 ~20:19 UTC against api.bainluck.com @ 9e0f0f37):
  mets.json         GET /api/events/15199882/game-markets   (scheduled — THE SCRIPT)
  mets-detail.json  GET /api/events/15199882
  reds.json         GET /api/events/14788546/game-markets   (completed — DIVERGENCE / WHAT HIT)
  reds-detail.json  GET /api/events/14788546

The payloads are committed alongside this script under `data/`, so the mock is
reproducible byte-for-byte long after those markets settle and the endpoints stop
returning them.

Usage:  python3 docs/mockups/build_event_props_mocks.py [payload_dir] [out.html]
        (both default to this file's own directory)
"""

import json
import re
import sys
import collections
from pathlib import Path

PLAYER_LINE = re.compile(r"^(?P<player>[^:]+):\s*(?P<threshold>\d+)\+$")
# Kalshi game tickers encode the game as KX<SERIES>-YYMMMDDHHMM<TEAMS>.
TICKER_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{4})")
MONTHS = dict(JAN=1, FEB=2, MAR=3, APR=4, MAY=5, JUN=6,
              JUL=7, AUG=8, SEP=9, OCT=10, NOV=11, DEC=12)


def ticker_date_audit(payload, game_date):
    """How many linked kalshi rows claim a date that is not this game's date?

    The ticker is the provider's own statement of which game a market belongs to.
    If it disagrees with the event we hung it on, the prop set on screen may be a
    different game's prop set — and a page that narrates the wrong game with total
    confidence is worse than a page with no props at all.
    """
    seen = collections.Counter()
    total = 0
    for section in ("totals", "team_totals", "period_markets", "player_props"):
        for row in payload.get(section) or []:
            m = TICKER_DATE.search(row.get("_external_id") or "")
            if not m:
                continue
            total += 1
            yy, mon, dd, _ = m.groups()
            iso = f"20{yy}-{MONTHS[mon]:02d}-{dd}"
            if iso != game_date:
                seen[iso] += 1
    return sum(seen.values()), total, dict(sorted(seen.items()))


# ---------------------------------------------------------------- data shaping

def stat_of(market_name):
    """'New York M vs San Diego: Hits' -> 'Hits'."""
    return (market_name or "").split(":")[-1].strip()


def ladders(payload):
    """Collapse player_props into one unit per (player, stat).

    This is the 'one question = one unit' primitive. The API hands back one row
    per threshold, which is exactly the pile the current page renders as sibling
    cards. Contradictions (the same rung answered twice with different numbers)
    are recorded rather than silently de-duplicated — a page that quietly picks
    one of two disagreeing answers is the thing we are trying to stop doing.
    """
    rungs = collections.defaultdict(dict)
    conflicts = collections.defaultdict(set)
    meta = {}
    for row in payload.get("player_props") or []:
        m = PLAYER_LINE.match(row.get("outcome_name") or "")
        if not m:
            continue
        player = m.group("player").strip()
        threshold = int(m.group("threshold"))
        stat = stat_of(row.get("market_name"))
        prob = row.get("over_probability")
        if prob is None:
            continue
        key = (player, stat)
        meta.setdefault(key, {"headshot": row.get("player_headshot"),
                              "team": row.get("player_team"),
                              "sources": row.get("source_count") or 1})
        prior = rungs[key].get(threshold)
        if prior is not None and abs(prior["p"] - prob) > 1e-9:
            conflicts[key].add(threshold)
        rungs[key].setdefault(threshold, {
            "p": prob,
            "mark": row.get("pregame_mark"),
            "is_winner": row.get("is_winner"),
            "actual": row.get("actual"),
        })

    out = []
    for key, by_threshold in rungs.items():
        player, stat = key
        steps = [dict(threshold=t, **v) for t, v in sorted(by_threshold.items())]
        out.append({
            "player": player,
            "stat": stat,
            "steps": steps,
            "conflicted": sorted(conflicts.get(key, ())),
            **meta[key],
        })
    return out


def movers(units, floor=0.10):
    """Every rung whose current probability has left its pregame mark."""
    rows = []
    for u in units:
        for s in u["steps"]:
            if s["mark"] is None:
                continue
            delta = s["p"] - s["mark"]
            if abs(delta) >= floor:
                rows.append({"player": u["player"], "stat": u["stat"],
                             "threshold": s["threshold"], "mark": s["mark"],
                             "now": s["p"], "delta": delta})
    return sorted(rows, key=lambda r: -abs(r["delta"]))


def vouch_game_lines(payload):
    """Split the three game-level sections into 'can show' and 'withheld, why'.

    A game total whose every row is a PLAYER outcome is not a game total; a
    ladder that answers 0.5+ at 99% and 2.5+ at 1% is not a distribution. The
    page has to make that call somewhere, and making it here — visibly, with a
    reason — is the design proposal.
    """
    verdicts = []
    for section, label in (("totals", "Game total"),
                           ("spreads", "Spread"),
                           ("period_markets", "First 5 innings")):
        rows = payload.get(section) or []
        if not rows:
            verdicts.append((label, None, "no market linked to this game"))
            continue
        player_rows = [r for r in rows
                       if PLAYER_LINE.match(r.get("outcome_name") or "")]
        if player_rows and len(player_rows) == len(rows):
            verdicts.append((label, None,
                             f"all {len(rows)} rows are player lines, not {label.lower()}s"))
            continue
        probs = [r.get("over_probability") if r.get("over_probability") is not None
                 else r.get("probability") for r in rows]
        probs = [p for p in probs if p is not None]
        if probs and min(probs) <= 0.01 and max(probs) >= 0.99:
            verdicts.append((label, None,
                             f"rungs span {min(probs):.0%}–{max(probs):.0%}; not a distribution"))
            continue
        # A harder line must never be likelier than an easier one. Two spreads at
        # the same probability is the same failure with the inequality flattened:
        # -2.5 cannot be as likely as -1.5, so a tie is evidence the ladder is not
        # really priced. Without this the section renders a 99%/99% spread pair and
        # the words "we vouch for these" become false.
        rungs = sorted((r.get("threshold"), p) for r, p in zip(rows, probs)
                       if r.get("threshold") is not None)
        for (t1, p1), (t2, p2) in zip(rungs, rungs[1:]):
            if t2 > t1 and p2 >= p1 - 1e-9:
                verdicts.append((label, None,
                                 f"{t1:g} and {t2:g} both priced {p2:.0%}; the ladder is flat"))
                break
        else:
            verdicts.append((label, rows, None))
    return verdicts


# ------------------------------------------------------------------ rendering

def pct(x):
    return f"{round(x * 100)}%"


def ladder_html(unit, mode="script"):
    """The one-question unit: a player's whole threshold ladder as one strip."""
    cells = []
    for s in unit["steps"]:
        p = s["p"]
        shade = min(0.92, max(0.06, p))
        graded = ""
        if mode == "whathit":
            if s["is_winner"] is True:
                graded = " rung--hit"
            elif s["actual"] is None:
                graded = " rung--ungraded"
            else:
                graded = " rung--miss"
        delta_tick = ""
        if mode == "divergence" and s["mark"] is not None:
            d = p - s["mark"]
            if abs(d) >= 0.10:
                delta_tick = (f'<span class="tick {"tick--up" if d > 0 else "tick--dn"}">'
                              f'{"+" if d > 0 else "−"}{abs(round(d * 100))}</span>')
        cells.append(
            f'<div class="rung{graded}">'
            f'<div class="rung__bar" style="--fill:{shade:.3f}"></div>'
            f'<div class="rung__n">{s["threshold"]}+</div>'
            f'<div class="rung__p">{pct(p)}</div>{delta_tick}</div>'
        )
    warn = ""
    if unit["conflicted"]:
        rung_list = ", ".join(f"{t}+" for t in unit["conflicted"])
        warn = (f'<div class="conflict">two different answers for {rung_list} — '
                f'withheld until they agree</div>')
    src = ""
    if (unit.get("sources") or 1) > 1:
        src = f'<span class="srcs">{unit["sources"]} sources</span>'
    return (f'<div class="unit">'
            f'<div class="unit__hd"><span class="unit__who">{unit["player"]}</span>'
            f'<span class="unit__stat">{unit["stat"]}</span>{src}</div>'
            f'<div class="rungs">{"".join(cells)}</div>{warn}</div>')


def diverge_html(row):
    """A prop against its own pregame mark — the bar IS the comparison."""
    lo, hi = sorted((row["mark"], row["now"]))
    up = row["delta"] > 0
    return (
        f'<div class="dv">'
        f'<div class="dv__hd"><span class="dv__who">{row["player"]}</span>'
        f'<span class="dv__q">{row["threshold"]}+ {row["stat"]}</span>'
        f'<span class="dv__d {"dv__d--up" if up else "dv__d--dn"}">'
        f'{"+" if up else "−"}{abs(round(row["delta"] * 100))}</span></div>'
        f'<div class="dv__track">'
        f'<div class="dv__span {"dv__span--up" if up else "dv__span--dn"}" '
        f'style="left:{lo*100:.1f}%;width:{(hi-lo)*100:.1f}%"></div>'
        f'<div class="dv__mark" style="left:{row["mark"]*100:.1f}%"></div>'
        f'<div class="dv__now {"dv__now--up" if up else "dv__now--dn"}" '
        f'style="left:{row["now"]*100:.1f}%"></div>'
        f'</div>'
        f'<div class="dv__ft"><span>script said {pct(row["mark"])}</span>'
        f'<span class="dv__ftnow">now {pct(row["now"])}</span></div>'
        f'</div>'
    )


CSS = """
:root{
  --surface-deep:#F5F5F7; --surface-card:#FFFFFF; --surface-elevated:#F0F0F2;
  --surface-border:#E5E7EB; --text-primary:#111827; --text-secondary:#6B7280;
  --text-muted:#9CA3AF; --accent-live:#22C55E; --accent-brand:#10B981;
  --accent-futures:#8B5CF6; --accent-warning:#F59E0B; --accent-danger:#EF4444;
  --font-sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,Inter,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-sans);background:var(--surface-deep);color:var(--text-primary);
     -webkit-font-smoothing:antialiased;padding:28px 18px 60px}
.page-hd{max-width:1320px;margin:0 auto 26px}
.page-hd h1{font-size:21px;letter-spacing:-.02em}
.page-hd p{color:var(--text-secondary);font-size:13.5px;margin-top:7px;max-width:78ch;line-height:1.55}
.rail{display:flex;gap:22px;align-items:flex-start;max-width:1320px;margin:0 auto;
      flex-wrap:wrap;justify-content:center}
.col{width:392px;flex:0 0 392px}
.ask{background:#111827;color:#F8FAFC;border-radius:12px;padding:13px 15px;margin-bottom:12px}
.ask__k{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:#9CA3AF}
.ask__q{font-size:14px;line-height:1.45;margin-top:5px;font-weight:600}
.ask__n{font-size:11.5px;line-height:1.5;margin-top:8px;color:#D1D5DB;font-weight:400}

/* ---- the phone ---- */
.phone{background:var(--surface-card);border:1px solid var(--surface-border);
       border-radius:26px;overflow:hidden;box-shadow:0 8px 28px rgba(17,24,39,.10)}
.status{height:26px;background:var(--surface-card);display:flex;align-items:center;
        justify-content:space-between;padding:0 17px;font-size:10.5px;color:var(--text-muted)}
.scroll{max-height:1180px;overflow-y:auto}

/* ---- hero (unchanged component — do not redesign) ---- */
.hero{padding:14px 16px 16px;border-bottom:1px solid var(--surface-border)}
.hero__meta{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--text-secondary)}
.pill{font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;padding:3px 7px;
      border-radius:999px;font-weight:700}
.pill--pre{background:#EEF2FF;color:#4338CA}
.pill--live{background:#DCFCE7;color:#166534}
.pill--final{background:var(--surface-elevated);color:var(--text-secondary)}
.hero__teams{display:flex;justify-content:space-between;align-items:flex-end;margin-top:11px}
.tm{display:flex;flex-direction:column;gap:2px}
.tm__n{font-size:15px;font-weight:650;letter-spacing:-.01em}
.tm__p{font-size:31px;font-weight:730;letter-spacing:-.035em;line-height:1}
.tm--away{text-align:right}
.tm__s{font-size:26px;font-weight:730;letter-spacing:-.03em}
.split{height:6px;border-radius:3px;background:var(--surface-elevated);margin-top:11px;
       overflow:hidden;display:flex}
.split__h{background:var(--text-primary)}
.split__a{background:var(--surface-border)}
.hero__src{font-size:10.5px;color:var(--text-muted);margin-top:7px}

/* ---- section chrome ---- */
.sec{padding:15px 16px 6px}
.sec__hd{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:3px}
.sec__t{font-size:12px;letter-spacing:.13em;text-transform:uppercase;font-weight:730}
.sec__c{font-size:11px;color:var(--text-muted)}
.sec__lede{font-size:13px;color:var(--text-secondary);line-height:1.5;margin:5px 0 13px}
.sec__lede b{color:var(--text-primary);font-weight:650}

/* ---- the one-question ladder unit ---- */
.unit{border:1px solid var(--surface-border);border-radius:11px;padding:10px 11px;margin-bottom:9px}
.unit__hd{display:flex;align-items:baseline;gap:7px;margin-bottom:8px}
.unit__who{font-size:13.5px;font-weight:650;letter-spacing:-.01em}
.unit__stat{font-size:11.5px;color:var(--text-secondary)}
.srcs{margin-left:auto;font-size:10px;color:var(--text-muted)}
.rungs{display:flex;gap:5px}
.rung{flex:1;position:relative;border-radius:7px;background:var(--surface-elevated);
      padding:7px 4px 6px;text-align:center;overflow:hidden}
.rung__bar{position:absolute;inset:auto 0 0 0;height:calc(var(--fill)*100%);
           background:rgba(17,24,39,.10)}
.rung__n{position:relative;font-size:10.5px;color:var(--text-secondary);font-weight:600}
.rung__p{position:relative;font-size:14px;font-weight:700;letter-spacing:-.02em;margin-top:1px}
.rung--hit{outline:2px solid var(--accent-brand);outline-offset:-2px;background:#ECFDF5}
.rung--miss{opacity:.42}
.rung--ungraded{background:repeating-linear-gradient(135deg,#F0F0F2 0 5px,#E9E9ED 5px 10px)}
.tick{position:relative;display:block;font-size:9.5px;font-weight:700;margin-top:2px}
.tick--up{color:var(--accent-brand)} .tick--dn{color:var(--accent-danger)}
.conflict{margin-top:7px;font-size:10.5px;color:var(--accent-warning);
          background:#FFFBEB;border-radius:6px;padding:5px 7px;line-height:1.4}

/* ---- divergence ---- */
.dv{border:1px solid var(--surface-border);border-radius:11px;padding:10px 11px;margin-bottom:9px}
.dv__hd{display:flex;align-items:baseline;gap:7px}
.dv__who{font-size:13.5px;font-weight:650;letter-spacing:-.01em}
.dv__q{font-size:11.5px;color:var(--text-secondary)}
.dv__d{margin-left:auto;font-size:15px;font-weight:750;letter-spacing:-.02em}
.dv__d--up{color:var(--accent-brand)} .dv__d--dn{color:var(--accent-danger)}
.dv__track{position:relative;height:9px;border-radius:5px;background:var(--surface-elevated);
           margin:10px 0 6px}
.dv__span{position:absolute;top:0;height:9px;border-radius:5px;opacity:.24}
.dv__span--up{background:var(--accent-brand)} .dv__span--dn{background:var(--accent-danger)}
.dv__mark{position:absolute;top:-3px;width:2px;height:15px;background:var(--text-muted);
          transform:translateX(-1px)}
.dv__now{position:absolute;top:-3.5px;width:11px;height:16px;border-radius:4px;
         transform:translateX(-5.5px);border:2px solid var(--surface-card)}
.dv__now--up{background:var(--accent-brand)} .dv__now--dn{background:var(--accent-danger)}
.dv__ft{display:flex;justify-content:space-between;font-size:10.5px;color:var(--text-muted)}
.dv__ftnow{color:var(--text-primary);font-weight:650}

/* ---- honest-empty ---- */
.empty{border:1px dashed var(--surface-border);border-radius:11px;padding:11px;
       margin-bottom:9px;background:#FCFCFD}
.empty__t{font-size:12.5px;font-weight:650}
.empty__w{font-size:11px;color:var(--text-secondary);margin-top:3px;line-height:1.45}
.rowline{display:flex;justify-content:space-between;align-items:center;padding:9px 0;
         border-bottom:1px solid var(--surface-border);font-size:13px}
.rowline:last-child{border-bottom:0}
.rowline__p{font-weight:700;letter-spacing:-.02em}
.note{margin:4px 16px 16px;font-size:11px;color:var(--text-muted);line-height:1.5}
.gap{height:9px}
.flag{max-width:1320px;margin:0 auto 26px;background:#FFFBEB;border:1px solid #FDE68A;
      border-left:4px solid var(--accent-warning);border-radius:10px;padding:13px 16px}
.flag__t{font-size:13px;font-weight:730;color:#92400E}
.flag__b{font-size:12.5px;color:#78350F;line-height:1.6;margin-top:5px;max-width:96ch}
.flag__b code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
              background:#FEF3C7;padding:1px 4px;border-radius:3px}
"""


def phone(state_pill, pill_class, hero, body):
    return f"""<div class="phone"><div class="status"><span>9:41</span><span>Bain&nbsp;Luck</span></div>
<div class="scroll">{hero}{body}</div></div>"""


def hero_html(detail, pill_text, pill_class, final=False):
    home, away = detail["home_team"], detail["away_team"]
    hp = detail.get("hero_probability") or 0
    ap = detail.get("hero_probability_away") or (1 - hp)
    if final:
        right = (f'<div class="tm tm--away"><div class="tm__n">{away}</div>'
                 f'<div class="tm__s">{detail.get("away_score")}</div></div>')
        left = (f'<div class="tm"><div class="tm__n">{home}</div>'
                f'<div class="tm__s">{detail.get("home_score")}</div></div>')
        srcline = "Final · blended win probability closed at " + pct(hp) + " " + home
    else:
        left = (f'<div class="tm"><div class="tm__n">{home}</div>'
                f'<div class="tm__p">{pct(hp)}</div></div>')
        right = (f'<div class="tm tm--away"><div class="tm__n">{away}</div>'
                 f'<div class="tm__p">{pct(ap)}</div></div>')
        srcline = "Blended across every source we read"
    return f"""<div class="hero">
<div class="hero__meta"><span class="pill {pill_class}">{pill_text}</span><span>MLB</span></div>
<div class="hero__teams">{left}{right}</div>
<div class="split"><div class="split__h" style="width:{hp*100:.1f}%"></div>
<div class="split__a" style="width:{ap*100:.1f}%"></div></div>
<div class="hero__src">{srcline}</div></div>"""


# ----------------------------------------------------------------------- build

def main():
    here = Path(__file__).resolve().parent
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "data"
    out = (Path(sys.argv[2]) if len(sys.argv) > 2
           else here / "event-props-script-divergence-mock.html")
    mets = json.loads((src / "mets.json").read_text())
    reds = json.loads((src / "reds.json").read_text())
    mets_d = json.loads((src / "mets-detail.json").read_text())
    reds_d = json.loads((src / "reds-detail.json").read_text())

    # ---------------- MOCK 1 — THE SCRIPT (pregame, real scheduled game)
    units = ladders(mets)
    # The script leads with the expectations that are actually saying something:
    # a rung at 99% or 1% is noise, a rung near the middle is a question.
    def interest(u):
        return max((0.5 - abs(0.5 - s["p"])) for s in u["steps"])
    lead = sorted(units, key=interest, reverse=True)[:5]
    rest = len(units) - len(lead)
    script_units = "".join(ladder_html(u, "script") for u in lead)

    verdicts = vouch_game_lines(mets)
    shown, withheld = [], []
    for label, rows, why in verdicts:
        if rows is None:
            withheld.append(f'<div class="empty"><div class="empty__t">{label} — not shown</div>'
                            f'<div class="empty__w">{why}</div></div>')
        else:
            shown.append(f'<div class="rowline"><span>{label}</span>'
                         f'<span class="rowline__p">{len(rows)} lines</span></div>')
    game_lines = ("".join(shown) or "") + ("".join(withheld) or "")
    n_ok, n_no = len(shown), len(withheld)

    m1_body = f"""
<div class="sec"><div class="sec__hd"><div class="sec__t">The script</div>
<div class="sec__c">{len(units)} questions</div></div>
<div class="sec__lede">Tonight the market expects <b>{lead[0]['player']}</b> to be the
game's live question — {pct(lead[0]['steps'][0]['p'])} for {lead[0]['steps'][0]['threshold']}+
{lead[0]['stat']}. Everything below is what the world thinks happens before a pitch
is thrown.</div>
{script_units}
<div class="note">+{rest} more questions — near-certainties collapsed by default.</div>
<div class="sec__hd"><div class="sec__t">Game lines</div>
<div class="sec__c">{n_ok} shown · {n_no} withheld</div></div>
<div class="sec__lede">A line we cannot stand behind is worse than no line.</div>
{game_lines}
</div>"""

    # ---------------- MOCK 2 — THE DIVERGENCE (real recorded movement)
    runits = ladders(reds)
    mv = movers(runits, 0.10)
    top = mv[:6]
    m2_body = f"""
<div class="sec"><div class="sec__hd"><div class="sec__t">The divergence</div>
<div class="sec__c">{len(mv)} off script</div></div>
<div class="sec__lede">Tonight is <b>not</b> going to script for the pitchers.
{top[0]['player']}'s strikeout number has fallen {abs(round(top[0]['delta']*100))} points
since first pitch.</div>
{''.join(diverge_html(r) for r in top)}
<div class="note">Ordered by distance from the pregame mark — the grey tick is what the
script said, the dot is where it is now. Props still on script are below the fold.</div>
</div>"""

    # ---------------- MOCK 3 — WHAT HIT (settled; the honest-empty question)
    graded = [u for u in runits if any(s["is_winner"] is True for s in u["steps"])]
    show = (graded + [u for u in runits if u not in graded])[:4]
    n_tot = sum(len(u["steps"]) for u in runits)
    n_no_actual = sum(1 for u in runits for s in u["steps"] if s["actual"] is None)
    n_flag_win = sum(1 for u in runits for s in u["steps"] if s["is_winner"] is True)
    m3_body = f"""
<div class="sec"><div class="sec__hd"><div class="sec__t">What hit</div>
<div class="sec__c">{n_flag_win} of {n_tot} settled</div></div>
<div class="sec__lede">The script, graded — except it cannot be. The two fields that say
what happened <b>disagree</b>: {n_flag_win} of {n_tot} rungs carry a winner flag, while
<b>all {n_no_actual}</b> carry no actual result at all.</div>
{''.join(ladder_html(u, 'whathit') for u in show)}
<div class="empty"><div class="empty__t">{n_no_actual} rungs have no result</div>
<div class="empty__w">The settlement feed returned <code>actual: null</code> for every rung
on this game, so <code>is_winner: false</code> cannot be read as "missed" — it is doing double
duty for "missed" and "never graded". Drawing the other {n_tot - n_flag_win} rungs as red
misses would be inventing results we were never given.</div></div>
<div class="note">Hatched = no result returned. Solid green = winner flag set. This state is
blocked on the backend telling the two fields apart.</div>
</div>"""

    m1 = phone("Tonight 4:10 PT", "pill--pre",
               hero_html(mets_d, "Pregame", "pill--pre"), m1_body)
    m2 = phone("Live", "pill--live",
               hero_html(reds_d, "Live · replay", "pill--live"), m2_body)
    m3 = phone("Final", "pill--final",
               hero_html(reds_d, "Final", "pill--final", final=True), m3_body)

    asks = [
        ("Mock 1 · THE SCRIPT",
         "Does the pregame page lead with the five questions that are actually live, "
         "or with the whole prop set?",
         f"Real data: {mets_d['away_team']} @ {mets_d['home_team']}, tonight. "
         f"{len(units)} player questions linked. This mock ranks by how close a rung sits to "
         "50% — a 99% rung tells you nothing, so it collapses. The alternative is a full "
         "A-to-Z list and no editorial call at all."),
        ("Mock 2 · THE DIVERGENCE",
         "Should a prop that left its pregame mark be shown as a travelled bar, "
         "or as a sentence?",
         f"Real data: {reds_d['away_team']} @ {reds_d['home_team']}, replayed at its recorded "
         f"state. {len(mv)} of {sum(len(u['steps']) for u in runits)} rungs moved 10+ points "
         "from their own pregame mark. The bar shows the journey; a sentence would read "
         "\"Mautz's strikeout number collapsed\" and fit more per screen."),
        ("Mock 3 · WHAT HIT",
         "When the source returns no result, does the row disappear — or does it say so?",
         f"Real data, and the reason this mock matters: all {n_no_actual} of {n_tot} settled "
         f"rungs on this game came back with no result, while {n_flag_win} carries a winner "
         "flag — the two fields disagree. Drawing the rest as misses would be a lie; hiding "
         "them makes the page look thinner than the game was. This mock says so out loud."),
    ]

    cols = "".join(
        f'<div class="col"><div class="ask"><div class="ask__k">{k}</div>'
        f'<div class="ask__q">{q}</div><div class="ask__n">{n}</div></div>{m}</div>'
        for (k, q, n), m in zip(asks, (m1, m2, m3)))

    m_bad, m_tot, m_dates = ticker_date_audit(mets, "2026-08-18")
    r_bad, r_tot, r_dates = ticker_date_audit(reds, "2026-08-17")
    date_list = ", ".join(sorted(set(list(m_dates) + list(r_dates))))

    out.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-AMBITION-1 — Event page, props as the story</title><style>{CSS}</style></head>
<body>
<div class="page-hd">
<h1>Event page — props as the story</h1>
<p>Three states of one idea: pregame the prop set is <b>the script</b>, in-game the movement
against those marks is <b>the divergence</b>, settled it is <b>what hit</b>. Every number below
is read from production payloads captured 2026-08-18 against api.bainluck.com @ 9e0f0f37 —
no invented data. Rendered at iPhone width, because that is where this has to work.
The win-probability hero is shown unchanged; it is not what this is proposing to alter.</p>
</div>
<div class="flag">
<div class="flag__t">Read the numbers, but do not trust the roster — a linkage check failed
while these were being built</div>
<div class="flag__b">Every kalshi row on both games carries a ticker whose own date is not the
game's date: <b>{m_bad} of {m_tot}</b> rows on the Mets game and <b>{r_bad} of {r_tot}</b> on the
Reds game, dated {date_list} against games played 2026-08-17 and 2026-08-18. The ticker is the
provider's statement of which game a market belongs to, so the prop set drawn above may be
<i>a different game's</i> prop set — which is also the likeliest reason unexpected names appear
in these line-ups. The layout is what is being ruled on here; the linkage is a separate defect
that has to be fixed before any of this can ship, because a page that narrates the wrong game
confidently is worse than a page with no props at all.</div>
</div>
<div class="rail">{cols}</div>
</body></html>""")
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")
    print(f"  mock 1: {len(units)} ladder units from {len(mets.get('player_props') or [])} rows")
    print(f"  mock 2: {len(mv)} movers >=10pts")
    print(f"  mock 3: {n_no_actual}/{n_tot} rungs with actual=None, "
          f"{n_flag_win} with is_winner=True")
    print(f"  linkage: mets {m_bad}/{m_tot}, reds {r_bad}/{r_tot} rows off-date")


if __name__ == "__main__":
    main()
