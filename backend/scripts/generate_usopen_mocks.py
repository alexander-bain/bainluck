#!/usr/bin/env python3
"""Render the /tournaments/us-open layout directions as static HTML (UX-P130 Item 3).

Three directions for Alex to open and react to.  Every number below is REAL:
blends come from the committed register's pinned identities, trend lines are
actual daily snapshot averages (unsmoothed, plotted on a fixed 0-100 axis), and
the slate rows are live Polymarket US Open qualification markets ordered by
volume.  Nothing is invented, because a mock with pretty fake data hides exactly
the problems a mock is for: the real men's board is one 52% row and a long tail
under 3%, and no amount of lorem would have shown that.

Output: docs/mocks/us-open/{a-two-boards,b-today-first,c-split-story}.html
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import normalize_player_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "docs" / "mocks" / "us-open"

# --- Design tokens, mirrored from frontend/app/globals.css (light mode only) ---
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --surface-page:#f7f8fa; --surface-card:#ffffff; --surface-border:#e6e8ec;
  --text-primary:#0f1115; --text-secondary:#5b6472; --text-muted:#98a1af;
  --accent-brand:#1a56db; --accent-live:#0f9d58; --accent-danger:#d93025;
  --stale:#b26a00; --stale-bg:#fff6e5;
}
html{-webkit-text-size-adjust:100%}
body{background:var(--surface-page);color:var(--text-primary);
  font:400 15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.phone{width:390px;margin:0 auto;background:var(--surface-page);min-height:100vh;
  border-left:1px solid var(--surface-border);border-right:1px solid var(--surface-border)}
.pad{padding:0 16px}
header.hero{padding:18px 16px 14px;background:var(--surface-card);
  border-bottom:1px solid var(--surface-border)}
h1{font-size:24px;line-height:1.15;letter-spacing:-.02em;font-weight:700}
.sub{color:var(--text-secondary);font-size:13px;margin-top:3px}
.section-title{font-size:12px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--text-muted);margin:22px 0 8px}
.card{background:var(--surface-card);border:1px solid var(--surface-border);border-radius:14px;
  overflow:hidden}

/* Draw toggle */
.toggle{display:flex;gap:6px;background:#eef0f4;padding:4px;border-radius:11px;margin-top:14px}
.toggle button{flex:1;border:0;background:transparent;padding:8px 0;border-radius:8px;
  font:600 14px inherit;color:var(--text-secondary);cursor:pointer}
.toggle button[aria-selected=true]{background:var(--surface-card);color:var(--text-primary);
  box-shadow:0 1px 2px rgba(15,17,21,.10)}

/* Board rows */
.row{display:grid;grid-template-columns:22px 1fr 62px 52px;align-items:center;gap:10px;
  padding:11px 14px;border-top:1px solid var(--surface-border)}
.row:first-child{border-top:0}
.rank{font-size:12px;color:var(--text-muted);font-variant-numeric:tabular-nums;text-align:right}
.who{min-width:0}
.nm{font-weight:600;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{font-size:11px;color:var(--text-muted);margin-top:1px}
/* THE BLEND: the one number. Everything else is quieter by construction. */
.blend{font-size:19px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums;
  letter-spacing:-.02em}
.lead .blend{font-size:26px}
.spark{width:52px;height:26px;display:block}
.delta{font-size:11px;font-variant-numeric:tabular-nums;text-align:right}
.up{color:var(--accent-live)} .dn{color:var(--accent-danger)} .flat{color:var(--text-muted)}
/* Sources: present, deliberately faint, never a comparison surface. */
.srcs{font-size:10.5px;color:var(--text-muted);margin-top:2px;letter-spacing:.01em}

/* Honest states */
.stale{background:var(--stale-bg);color:var(--stale);font-size:11.5px;padding:9px 14px;
  display:flex;gap:7px;align-items:flex-start;border-top:1px solid #f2e2c2}
.stale b{font-weight:700}
.empty{padding:22px 16px;text-align:center;color:var(--text-secondary);font-size:13.5px}
.empty .big{font-weight:650;color:var(--text-primary);font-size:15px;margin-bottom:4px}

/* Slate */
.match{padding:12px 14px;border-top:1px solid var(--surface-border)}
.match:first-child{border-top:0}
.mhead{display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);
  margin-bottom:7px}
.side{display:flex;align-items:center;gap:9px;padding:3px 0}
.side .nm{flex:1;font-weight:600}
.side .p{font-weight:700;font-variant-numeric:tabular-nums;width:46px;text-align:right}
.side.fav .p{color:var(--accent-brand)}
.bar{height:4px;border-radius:2px;background:#eceef2;overflow:hidden;margin-top:7px}
.bar i{display:block;height:100%;background:var(--accent-brand)}

/* Bracket slot */
.bracket-slot{border:1.5px dashed #cdd3dc;border-radius:14px;padding:18px 16px;text-align:center;
  background:#fbfcfd}
.bracket-slot .big{font-weight:650;margin-bottom:3px}
.bracket-slot .sm{font-size:12.5px;color:var(--text-secondary)}
.railwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:4px}
.rail{display:flex;gap:10px;min-width:min-content}
.rail .card{width:150px;flex:0 0 auto;padding:12px}

.footer{padding:26px 16px 40px;color:var(--text-muted);font-size:11.5px;line-height:1.5}
.tabs{display:flex;border-bottom:1px solid var(--surface-border);background:var(--surface-card)}
.tabs button{flex:1;border:0;background:transparent;padding:13px 0;font:600 13.5px inherit;
  color:var(--text-muted);border-bottom:2px solid transparent;cursor:pointer}
.tabs button[aria-selected=true]{color:var(--text-primary);border-bottom-color:var(--text-primary)}
.note{max-width:390px;margin:0 auto;padding:14px 16px;font-size:12px;color:var(--text-secondary);
  background:#eef1f6;border-bottom:1px solid var(--surface-border)}
.note b{color:var(--text-primary)}
"""


def sparkline(points: list[float], w: int = 52, h: int = 26) -> str:
    """Straight segments between real observations on a FIXED 0-100 axis.

    No smoothing, no curve fitting, no auto-scaled y-axis — a 2pp wiggle must
    not look like a collapse, which is exactly what an auto-scaled axis does.
    """
    if len(points) < 2:
        return f'<svg class="spark" viewBox="0 0 {w} {h}"></svg>'
    n = len(points)
    coords = [
        (i * w / (n - 1), h - (max(0.0, min(100.0, p)) / 100.0) * h)
        for i, p in enumerate(points)
    ]
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    rising = points[-1] >= points[0]
    colour = "#0f9d58" if rising else "#d93025"
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline points="{d}" fill="none" stroke="{colour}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def delta_html(series: list[float]) -> str:
    if len(series) < 2:
        return '<div class="delta flat">—</div>'
    d = series[-1] - series[0]
    cls = "up" if d > 0.3 else "dn" if d < -0.3 else "flat"
    sign = "+" if d > 0 else ""
    return f'<div class="delta {cls}">{sign}{d:.1f}</div>'


def parse_series(path: Path) -> dict[str, list[float]]:
    """Daily means per player across sources — the blend's own history."""
    daily: dict[str, dict[str, list[float]]] = {}
    for line in path.read_text().splitlines():
        parts = [c.strip() for c in line.split("|")]
        if len(parts) != 4 or parts[0] in ("name",) or parts[0].startswith("--"):
            continue
        name, _source, day, prob = parts
        try:
            daily.setdefault(normalize_player_name(name), {}).setdefault(day, []).append(float(prob))
        except ValueError:
            continue
    return {
        name: [sum(v) / len(v) for _, v in sorted(days.items())]
        for name, days in daily.items()
    }


def board_rows(players: list[dict], series: dict[str, list[float]], limit: int) -> str:
    out = []
    for i, p in enumerate(players[:limit], start=1):
        s = series.get(normalize_player_name(p["name"]), [])
        srcs = " · ".join(f"{k} {v:g}%" for k, v in sorted(p["sources"].items()))
        one_source = ' <span style="color:#b26a00">1 source</span>' if p["n"] == 1 else ""
        out.append(
            f'<div class="row{" lead" if i == 1 else ""}">'
            f'<div class="rank">{i}</div>'
            f'<div class="who"><div class="nm">{p["name"]}</div>'
            f'<div class="srcs">{srcs}{one_source}</div></div>'
            f'<div><div class="blend">{p["blend"]:.1f}%</div>{delta_html(s)}</div>'
            f'{sparkline(s)}'
            f"</div>"
        )
    return "".join(out)


STALE_BANNER = (
    '<div class="stale"><span>&#9888;</span><span><b>Prices paused.</b> '
    "The championship boards last updated 8 days ago — we&rsquo;re showing the last "
    "confirmed reading, not a live price. Match markets below are live.</span></div>"
)


def slate_rows(matches: list[dict]) -> str:
    out = []
    for m in matches:
        a, b = m["players"]
        pa = m["p"]
        pb = 100 - pa
        fav_a = pa >= pb
        out.append(
            f'<div class="match">'
            f'<div class="mhead"><span>{m["draw"]} &middot; Qualifying</span>'
            f'<span>{m["time"]}</span></div>'
            f'<div class="side{" fav" if fav_a else ""}"><span class="nm">{a}</span>'
            f'<span class="p">{pa:g}%</span></div>'
            f'<div class="side{"" if fav_a else " fav"}"><span class="nm">{b}</span>'
            f'<span class="p">{pb:g}%</span></div>'
            f'<div class="bar"><i style="width:{pa:g}%"></i></div>'
            f"</div>"
        )
    return "".join(out)


def page(title: str, note: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — /tournaments/us-open mock</title>
<style>{CSS}</style></head>
<body>
<div class="note"><b>{title}</b> — {note}</div>
<div class="phone">{body}
<div class="footer">Mock rendered from the committed US Open register
(<code>backend/data/tournament_registers/us-open-2026.json</code>). Blends, trend lines and
slate prices are real production readings from 2026-08-25. Probabilities only; trend lines are
unsmoothed on a fixed 0&ndash;100 axis.</div>
</div></body></html>"""


def main() -> int:
    data = json.loads(Path("/tmp/uso/mockdata.json").read_text())
    men, women = data["mens-singles"], data["womens-singles"]
    series = parse_series(Path("/tmp/uso/series_men.txt"))
    series.update(parse_series(Path("/tmp/uso/series_women.txt")))

    # Real Polymarket US Open qualification markets, highest volume first.
    slate = [
        {"players": ("Dominika Salkova", "Akasha Urhobo"), "p": 66.5, "draw": "Women", "time": "3:30 PM"},
        {"players": ("Elena Pridankina", "Aliona Falei"), "p": 50.5, "draw": "Women", "time": "11:00 AM"},
        {"players": ("Lukas Neumayer", "Oliver Crawford"), "p": 47.5, "draw": "Men", "time": "3:30 PM"},
        {"players": ("Joel Schwaerzler", "Gustavo Heide"), "p": 52.5, "draw": "Men", "time": "2:00 PM"},
        {"players": ("Qinwen Zheng", "Xiaodi You"), "p": 91.5, "draw": "Women", "time": "11:00 AM"},
        {"players": ("Marco Cecchinato", "Liam Broady"), "p": 51.5, "draw": "Men", "time": "12:30 PM"},
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []

    # ---------------- A — Two Boards -------------------------------------
    # The championship IS the page. One draw at a time, full depth, slate as a
    # secondary band. Bets the user came to ask "who wins the US Open?"
    body_a = f"""
<header class="hero">
  <h1>US Open 2026</h1>
  <div class="sub">Main draws begin Sunday &middot; Flushing Meadows</div>
  <div class="toggle" role="tablist">
    <button role="tab" aria-selected="true">Men</button>
    <button role="tab" aria-selected="false">Women</button>
  </div>
</header>
<div class="pad">
  <div class="section-title">Who wins the title</div>
  <div class="card">{STALE_BANNER}{board_rows(men, series, 12)}</div>
  <div class="section-title">Today&rsquo;s matches</div>
  <div class="card">{slate_rows(slate[:4])}</div>
  <div class="section-title">Bracket</div>
  <div class="bracket-slot">
    <div class="big">Draw not released</div>
    <div class="sm">The bracket appears here Thursday, when the draw is made.</div>
  </div>
</div>"""

    # ---------------- B — Today First ------------------------------------
    # Inverts A: the slate leads because it is the half that is actually live,
    # and the boards are a compact top-5 with depth one tap away.
    body_b = f"""
<header class="hero">
  <h1>US Open 2026</h1>
  <div class="sub">Qualifying &middot; 24 matches today</div>
</header>
<div class="pad">
  <div class="section-title">Today</div>
  <div class="card">{slate_rows(slate)}</div>
  <div class="section-title">Title race</div>
  <div class="card">{STALE_BANNER}{board_rows(men, series, 5)}
    <div class="row" style="justify-content:center">
      <div style="grid-column:1/-1;text-align:center;color:var(--accent-brand);font-weight:600;
        font-size:13.5px">All 36 men &rarr;</div></div>
  </div>
  <div class="card" style="margin-top:10px">{board_rows(women, series, 5)}
    <div class="row"><div style="grid-column:1/-1;text-align:center;color:var(--accent-brand);
      font-weight:600;font-size:13.5px">All 44 women &rarr;</div></div>
  </div>
  <div class="section-title">Bracket</div>
  <div class="railwrap"><div class="rail">
    <div class="card"><div style="font-size:12px;color:var(--text-muted)">Round of 128</div>
      <div style="font-weight:650;margin-top:4px">Opens Thursday</div></div>
    <div class="card"><div style="font-size:12px;color:var(--text-muted)">Quarter-finals</div>
      <div style="font-weight:650;margin-top:4px">Sep 8</div></div>
    <div class="card"><div style="font-size:12px;color:var(--text-muted)">Final</div>
      <div style="font-weight:650;margin-top:4px">Sep 13</div></div>
  </div></div>
</div>"""

    # ---------------- C — Split Story ------------------------------------
    # Tabs instead of a toggle, and each row leads with movement rather than
    # standing: "the script vs the divergence" applied to the title race.
    body_c = f"""
<header class="hero" style="padding-bottom:12px">
  <h1>US Open 2026</h1>
  <div class="sub">Main draws begin Sunday</div>
</header>
<div class="tabs" role="tablist">
  <button role="tab" aria-selected="true">Title</button>
  <button role="tab" aria-selected="false">Today</button>
  <button role="tab" aria-selected="false">Bracket</button>
</div>
<div class="pad">
  <div class="section-title">Men &middot; 36 contenders</div>
  <div class="card">{STALE_BANNER}{board_rows(men, series, 8)}</div>
  <div class="section-title">Women &middot; 44 contenders</div>
  <div class="card">{board_rows(women, series, 8)}</div>
  <div class="section-title">Where the bracket lives</div>
  <div class="card"><div class="empty">
    <div class="big">Its own tab</div>
    Full 128-slot draw, horizontally scrollable, from Thursday.
    The title boards never move to make room for it.
  </div></div>
</div>"""

    for slug, title, note, body in [
        ("a-two-boards", "A — Two Boards",
         "the championship is the page; one draw at a time, full depth, slate second.", body_a),
        ("b-today-first", "B — Today First",
         "the live half leads; boards are a top-5 with depth one tap away.", body_b),
        ("c-split-story", "C — Split Story",
         "both draws on one scroll, tabs for slate and bracket.", body_c),
    ]:
        path = OUT_DIR / f"{slug}.html"
        path.write_text(page(title, note, body))
        written.append(path)

    for p in written:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
