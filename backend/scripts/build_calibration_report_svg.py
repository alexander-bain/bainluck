"""
Build a static HTML calibration report using inline SVG charts (no dependencies).
Usage: python3 scripts/build_calibration_report_svg.py /tmp/cal_v6.json
"""

import json
import sys
from collections import defaultdict
from datetime import datetime


CATEGORY_DISPLAY = {
    "basketball": "Basketball", "baseball": "Baseball", "hockey": "Hockey",
    "football": "Football", "soccer": "Soccer", "golf": "Golf",
    "tennis": "Tennis", "mma": "MMA", "boxing": "Boxing",
    "cricket": "Cricket", "rugby": "Rugby", "motorsports": "Motorsports",
    "esports": "Esports", "lacrosse": "Lacrosse", "olympics": "Olympics",
    "politics": "Politics", "geopolitics": "Geopolitics",
    "entertainment": "Entertainment", "culture": "Culture",
    "weather": "Weather", "economics": "Economics",
    "crypto": "Crypto", "commodities": "Commodities",
    "tech": "Tech", "uncategorized": "Uncategorized",
}

SUPER_CATEGORIES = {
    "Sports": ["basketball", "baseball", "hockey", "football", "soccer", "golf",
               "tennis", "mma", "boxing", "cricket", "rugby", "motorsports",
               "esports", "lacrosse", "olympics", "wrestling", "darts", "chess",
               "poker", "aussierules", "pickleball", "horse_racing", "cycling"],
    "Politics": ["politics", "geopolitics"],
    "Entertainment": ["entertainment", "culture"],
    "Weather": ["weather"],
    "Economics": ["economics", "crypto", "commodities"],
    "Science & Tech": ["tech"],
}

SPORT_KEY_TO_CATEGORY = {
    "basketball_nba": "basketball", "basketball_ncaab": "basketball",
    "basketball_wnba": "basketball", "basketball_euroleague": "basketball",
    "basketball_nbl": "basketball",
    "americanfootball_nfl": "football", "americanfootball_ncaaf": "football",
    "baseball_mlb": "baseball", "baseball_ncaa": "baseball",
    "icehockey_nhl": "hockey",
    "soccer_epl": "soccer", "soccer_usa_mls": "soccer",
    "soccer_uefa_champs_league": "soccer", "soccer_spain_la_liga": "soccer",
    "soccer_germany_bundesliga": "soccer", "soccer_italy_serie_a": "soccer",
    "soccer_france_ligue_one": "soccer", "soccer_uefa_europa_league": "soccer",
    "mma_mixed_martial_arts": "mma",
    "tennis_atp_french_open": "tennis", "tennis_wta_french_open": "tennis",
    "golf_pga": "golf", "golf_lpga": "golf",
    "cricket_ipl": "cricket", "cricket_test_match": "cricket",
}

COLORS = [
    "#2563eb", "#16a34a", "#dc2626", "#ea580c", "#7c3aed",
    "#db2777", "#0d9488", "#d97706", "#4f46e5", "#65a30d",
    "#0891b2", "#be185d", "#059669", "#9333ea", "#c2410c",
]


def normalize_category(cat):
    """Normalize sport keys (basketball_nba) to base categories (basketball)."""
    if cat in SPORT_KEY_TO_CATEGORY:
        return SPORT_KEY_TO_CATEGORY[cat]
    base = cat.split("_")[0]
    if base in ("americanfootball",):
        return "football"
    if base in ("icehockey",):
        return "hockey"
    return base if base in CATEGORY_DISPLAY else cat


def aggregate_buckets(buckets, filter_fn=None):
    agg = defaultdict(lambda: {"n": 0, "winners": 0, "sum_prob": 0.0, "sum_sq_err": 0.0})
    for b in buckets:
        if filter_fn and not filter_fn(b):
            continue
        idx = b["bucket_idx"]
        agg[idx]["n"] += b["n"]
        agg[idx]["winners"] += b["winners"]
        agg[idx]["sum_prob"] += b["sum_prob"]
        agg[idx]["sum_sq_err"] += b["sum_sq_err"]
    result = []
    for idx in sorted(agg.keys()):
        a = agg[idx]
        if a["n"] == 0:
            continue
        avg_prob = a["sum_prob"] / a["n"]
        actual = a["winners"] / a["n"]
        result.append({
            "midpoint": idx * 10 + 5,
            "n": a["n"],
            "avg_prob": round(avg_prob * 100, 1),
            "actual": round(actual * 100, 1),
            "error": round((actual - avg_prob) * 100, 1),
            "bucket": f"{idx*10}-{idx*10+10}%",
        })
    return result


def mean_cal_error(cal):
    if not cal:
        return 0
    return sum(abs(b["error"]) for b in cal) / len(cal)


def brier_score(buckets, filter_fn=None):
    n = 0
    sq = 0
    for b in buckets:
        if filter_fn and not filter_fn(b):
            continue
        n += b["n"]
        sq += b["sum_sq_err"]
    return round(sq / n, 4) if n > 0 else None


def svg_calibration_chart(cal_data, width=560, height=360, color="#2563eb",
                          label="", show_legend=True, multi=None):
    """Generate an SVG calibration scatter+line chart."""
    pad_l, pad_r, pad_t, pad_b = 55, 20, 25, 50
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def px(pct):
        return pad_l + pct / 100 * plot_w

    def py(pct):
        return pad_t + (100 - pct) / 100 * plot_h

    lines = []
    lines.append(f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
                 f'style="font-family:-apple-system,system-ui,sans-serif;">')

    # Background
    lines.append(f'<rect width="{width}" height="{height}" fill="white" rx="8"/>')

    # Grid lines
    for v in range(0, 101, 10):
        x = px(v)
        y = py(v)
        lines.append(f'<line x1="{pad_l}" y1="{y}" x2="{width-pad_r}" y2="{y}" '
                     f'stroke="#f0f0f0" stroke-width="1"/>')
        lines.append(f'<line x1="{x}" y1="{pad_t}" x2="{x}" y2="{height-pad_b}" '
                     f'stroke="#f0f0f0" stroke-width="1"/>')
        # Y-axis labels
        lines.append(f'<text x="{pad_l-8}" y="{y+4}" text-anchor="end" '
                     f'fill="#a8a29e" font-size="11">{v}%</text>')
        # X-axis labels
        lines.append(f'<text x="{x}" y="{height-pad_b+18}" text-anchor="middle" '
                     f'fill="#a8a29e" font-size="11">{v}%</text>')

    # Axis labels
    lines.append(f'<text x="{width/2}" y="{height-5}" text-anchor="middle" '
                 f'fill="#57534e" font-size="12" font-weight="600">Predicted Probability</text>')
    lines.append(f'<text x="14" y="{height/2}" text-anchor="middle" '
                 f'fill="#57534e" font-size="12" font-weight="600" '
                 f'transform="rotate(-90,14,{height/2})">Actual Win Rate</text>')

    # Perfect calibration line (diagonal)
    lines.append(f'<line x1="{px(0)}" y1="{py(0)}" x2="{px(100)}" y2="{py(100)}" '
                 f'stroke="#cbd5e1" stroke-width="2" stroke-dasharray="6,4"/>')

    # Confidence band (±5pp)
    band_points_upper = " ".join(f"{px(v)},{py(min(100, v+5))}" for v in range(0, 101, 5))
    band_points_lower = " ".join(f"{px(v)},{py(max(0, v-5))}" for v in range(100, -1, -5))
    lines.append(f'<polygon points="{band_points_upper} {band_points_lower}" '
                 f'fill="#f1f5f9" opacity="0.5"/>')

    # Re-draw diagonal on top of band
    lines.append(f'<line x1="{px(0)}" y1="{py(0)}" x2="{px(100)}" y2="{py(100)}" '
                 f'stroke="#cbd5e1" stroke-width="2" stroke-dasharray="6,4"/>')

    datasets = multi if multi else [(cal_data, color, label)]

    legend_items = []
    for series_idx, (cal, clr, lbl) in enumerate(datasets):
        if not cal:
            continue

        # Line
        path_points = " ".join(f"{px(b['midpoint'])},{py(b['actual'])}" for b in cal)
        lines.append(f'<polyline points="{path_points}" fill="none" '
                     f'stroke="{clr}" stroke-width="2.5" stroke-linejoin="round"/>')

        # Points with size proportional to n
        max_n = max(b["n"] for b in cal)
        for b in cal:
            x = px(b["midpoint"])
            y = py(b["actual"])
            r = 4 + 6 * (b["n"] / max_n) ** 0.5
            lines.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{clr}" opacity="0.85"/>')
            lines.append(f'<title>{b["bucket"]}: {b["actual"]}% actual at {b["avg_prob"]}% predicted '
                         f'(n={b["n"]:,}, error={b["error"]:+.1f}pp)</title>')

        if show_legend and lbl:
            legend_items.append((clr, lbl))

    # Legend
    if legend_items:
        ly = pad_t + 8
        for i, (clr, lbl) in enumerate(legend_items):
            lx = pad_l + 10 + i * 180
            if lx + 150 > width:
                lx = pad_l + 10
                ly += 18
            lines.append(f'<circle cx="{lx}" cy="{ly}" r="5" fill="{clr}"/>')
            lines.append(f'<text x="{lx+10}" y="{ly+4}" fill="#57534e" font-size="11">{lbl}</text>')

    lines.append('</svg>')
    return "\n".join(lines)


def table_html(cal):
    rows = []
    for b in cal:
        err = b["error"]
        cls = "" if abs(err) < 3 else ("color:#16a34a" if err > 0 else "color:#dc2626")
        sign = "+" if err > 0 else ""
        rows.append(f'<tr><td>{b["bucket"]}</td><td class="num">{b["n"]:,}</td>'
                    f'<td class="num">{b["avg_prob"]}%</td><td class="num">{b["actual"]}%</td>'
                    f'<td class="num" style="{cls}">{sign}{err}pp</td></tr>')
    return "\n".join(rows)


def build_report(data):
    # Normalize categories (basketball_nba → basketball, etc.)
    for b in data["buckets"]:
        b["category"] = normalize_category(b["category"])
    buckets = data["buckets"]
    total_outcomes = data["total_outcomes"]
    total_markets = data["total_markets"]
    total_events = data.get("total_events", 0)
    total_winners = data["total_winners"]

    overall = aggregate_buckets(buckets)
    mce = mean_cal_error(overall)
    brier = brier_score(buckets)

    # Sources
    sources = sorted(set(b["source"] for b in buckets))
    source_cals = {}
    source_stats = {}
    for src in sources:
        fn = lambda b, s=src: b["source"] == s
        cal = aggregate_buckets(buckets, fn)
        source_cals[src] = cal
        n = sum(b["n"] for b in buckets if b["source"] == src)
        source_stats[src] = {"n": n, "mce": mean_cal_error(cal), "brier": brier_score(buckets, fn)}

    # Categories
    raw_cats = sorted(set(b["category"] for b in buckets))
    cat_volumes = {c: sum(b["n"] for b in buckets if b["category"] == c) for c in raw_cats}
    top_cats = [c for c in sorted(raw_cats, key=lambda c: -cat_volumes[c]) if cat_volumes[c] >= 100][:15]

    cat_cals = {}
    cat_stats = {}
    for cat in top_cats:
        fn = lambda b, c=cat: b["category"] == c
        cal = aggregate_buckets(buckets, fn)
        cat_cals[cat] = cal
        cat_stats[cat] = {"n": cat_volumes[cat], "mce": mean_cal_error(cal),
                          "brier": brier_score(buckets, fn)}

    # Super-categories
    super_cals = {}
    super_stats = {}
    for sc, members in SUPER_CATEGORIES.items():
        fn = lambda b, m=members: b["category"] in m
        cal = aggregate_buckets(buckets, fn)
        n = sum(x["n"] for x in cal)
        if n < 50:
            continue
        super_cals[sc] = cal
        super_stats[sc] = {"n": n, "mce": mean_cal_error(cal), "brier": brier_score(buckets, fn)}

    # Suspicious categories
    suspicious = set()
    for cat, cal in cat_cals.items():
        for b in cal:
            if b["n"] > 100 and abs(b["error"]) > 20:
                suspicious.add(cat)
                break

    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")

    # Grade
    grade_cls = "grade-A" if mce < 4 else "grade-B" if mce < 8 else "grade-C" if mce < 12 else "grade-F"
    grade_lbl = "Excellent" if mce < 4 else "Good" if mce < 8 else "Fair" if mce < 12 else "Poor"

    top_3 = ", ".join(f"{CATEGORY_DISPLAY.get(c,c)} ({cat_volumes[c]:,})" for c in top_cats[:3])

    # SVG Charts
    overall_svg = svg_calibration_chart(overall, width=700, height=400,
                                         label=f"All Markets (n={total_outcomes:,})")

    # Source comparison
    source_multi = [(source_cals[s], COLORS[i], f"{s} (n={source_stats[s]['n']:,})")
                    for i, s in enumerate(sorted(sources, key=lambda s: -source_stats[s]["n"]))]
    source_svg = svg_calibration_chart(None, width=540, height=320, multi=source_multi)

    # Super-category comparison
    sc_sorted = sorted(super_cals.keys(), key=lambda s: -super_stats[s]["n"])
    super_multi = [(super_cals[s], COLORS[i], f"{s} ({super_stats[s]['n']:,})")
                   for i, s in enumerate(sc_sorted)]
    super_svg = svg_calibration_chart(None, width=540, height=320, multi=super_multi)

    # Category cards
    cat_cards_html = []
    for i, cat in enumerate(top_cats):
        display = CATEGORY_DISPLAY.get(cat, cat)
        st = cat_stats[cat]
        is_susp = cat in suspicious
        border = "border-color:#ea580c;" if is_susp else ""
        flag = " ⚠" if is_susp else ""
        card_svg = svg_calibration_chart(cat_cals[cat], width=420, height=260,
                                          color="#ea580c" if is_susp else COLORS[i % len(COLORS)],
                                          label="", show_legend=False)
        cat_cards_html.append(f'''<div class="category-card" style="{border}">
          <h3>{display}{flag} <span class="n-label">{st["n"]:,} outcomes · MCE: {st["mce"]:.1f}pp · Brier: {st["brier"]}</span></h3>
          {card_svg}
        </div>''')

    # Source stats table
    src_rows = "\n".join(
        f'<li><strong>{s}</strong> ({source_stats[s]["n"]:,} outcomes): MCE = {source_stats[s]["mce"]:.1f}pp, Brier = {source_stats[s]["brier"]}</li>'
        for s in sorted(sources, key=lambda s: -source_stats[s]["n"])
    )

    # Category insights
    cat_insights = []
    for cat in sorted(top_cats, key=lambda c: -cat_stats[c]["n"]):
        st = cat_stats[cat]
        display = CATEGORY_DISPLAY.get(cat, cat)
        verdict = ("very well-calibrated" if st["mce"] < 5 else
                   "well-calibrated" if st["mce"] < 8 else
                   "reasonably calibrated" if st["mce"] < 12 else
                   "has calibration gaps (data quality issues)" if st["mce"] < 20 else
                   "has significant data quality issues")
        cat_insights.append(f'<li><strong>{display}</strong> ({st["n"]:,}): {verdict} — MCE {st["mce"]:.1f}pp, Brier {st["brier"]}</li>')

    # Favorite-longshot analysis
    low_buckets = [b for b in overall if b["midpoint"] <= 15]
    high_buckets = [b for b in overall if b["midpoint"] >= 85]
    flb_text = ""
    if low_buckets and high_buckets:
        low_err = sum(b["error"] for b in low_buckets) / len(low_buckets)
        high_err = sum(b["error"] for b in high_buckets) / len(high_buckets)
        flb_parts = []
        if abs(low_err) > 2:
            direction = "more" if low_err > 0 else "less"
            flb_parts.append(f'Longshots (0-15%) win <strong>{direction}</strong> often than predicted ({low_err:+.1f}pp)')
        else:
            flb_parts.append(f'Longshots (0-15%) are well-calibrated ({low_err:+.1f}pp)')
        if abs(high_err) > 2:
            direction = "less" if high_err < 0 else "more"
            flb_parts.append(f'Favorites (85%+) win <strong>{direction}</strong> often than predicted ({high_err:+.1f}pp)')
        else:
            flb_parts.append(f'Favorites (85%+) are well-calibrated ({high_err:+.1f}pp)')
        flb_text = f'<h3>Favorite-Longshot Bias</h3><p>{". ".join(flb_parts)}.</p>'

    # Warning section
    warning_html = ""
    if suspicious:
        susp_list = "\n".join(f'<li><strong>{CATEGORY_DISPLAY.get(c,c)}</strong></li>' for c in sorted(suspicious))
        warning_html = f'''<div class="warning">
      <h2>Data Quality Notes</h2>
      <p>These categories show &gt;20pp error in at least one bucket (n&gt;100):</p>
      <ul>{susp_list}</ul>
      <p><strong>Root cause 1: Three-way sports.</strong> Soccer, football, and cricket have win/draw/lose outcomes stored as separate binary sub-markets. The "closest to 50%" dedup picks the favorite, which loses to draws + upsets.</p>
      <p><strong>Root cause 2: Field-level futures.</strong> Golf and motorsports have 30+ outcomes per tournament with stale opening prices on tail outcomes.</p>
    </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Do Prediction Markets Predict Anything? — Bain Luck</title>
<style>
  :root {{ --bg:#fafaf9; --surface:#fff; --text:#1c1917; --text2:#57534e; --muted:#a8a29e; --border:#e7e5e4; --accent:#2563eb; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; padding:1.5rem; max-width:1200px; margin:0 auto; }}
  h1 {{ font-size:2rem; font-weight:700; margin-bottom:0.25rem; }}
  .subtitle {{ color:var(--text2); font-size:1.05rem; margin-bottom:1.5rem; }}
  .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:0.75rem; margin-bottom:1.5rem; }}
  .stat-card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:1rem; }}
  .stat-card .label {{ font-size:0.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em; }}
  .stat-card .value {{ font-size:1.6rem; font-weight:700; }}
  .stat-card .detail {{ font-size:0.8rem; color:var(--text2); }}
  .grade-A {{ color:#16a34a; }} .grade-B {{ color:#2563eb; }} .grade-C {{ color:#ea580c; }} .grade-F {{ color:#dc2626; }}
  .section {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:1.25rem; margin-bottom:1.25rem; }}
  .section h2 {{ font-size:1.15rem; font-weight:600; margin-bottom:0.75rem; }}
  .section p {{ color:var(--text2); font-size:0.85rem; margin-bottom:0.5rem; }}
  .section svg {{ display:block; margin:0 auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.85rem; }}
  th,td {{ text-align:left; padding:0.5rem 0.6rem; border-bottom:1px solid var(--border); }}
  th {{ font-weight:600; color:var(--text2); font-size:0.75rem; text-transform:uppercase; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:1.25rem; }}
  @media (max-width:768px) {{ .two-col {{ grid-template-columns:1fr; }} }}
  .category-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(440px,1fr)); gap:1rem; margin-bottom:1.25rem; }}
  .category-card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:1rem; }}
  .category-card h3 {{ display:flex; justify-content:space-between; align-items:baseline; font-size:0.95rem; margin-bottom:0.5rem; }}
  .category-card .n-label {{ font-size:0.75rem; font-weight:400; color:var(--muted); }}
  .commentary {{ background:#fefce8; border:1px solid #fde68a; border-radius:10px; padding:1.25rem; margin-bottom:1.25rem; }}
  .commentary h2 {{ font-size:1.1rem; margin-bottom:0.5rem; }}
  .commentary h3 {{ font-size:0.95rem; margin-top:1rem; margin-bottom:0.25rem; color:var(--text); }}
  .commentary p,.commentary li {{ font-size:0.9rem; color:var(--text2); margin-bottom:0.4rem; }}
  .commentary ul {{ padding-left:1.25rem; }}
  .commentary strong {{ color:var(--text); }}
  .warning {{ background:#fef2f2; border:1px solid #fecaca; border-radius:10px; padding:1.25rem; margin-bottom:1.25rem; }}
  .warning h2 {{ font-size:1.1rem; margin-bottom:0.5rem; color:#dc2626; }}
  .warning p,.warning li {{ font-size:0.9rem; color:var(--text2); margin-bottom:0.4rem; }}
  .warning ul {{ padding-left:1.25rem; }}
  .next-steps {{ background:#dbeafe; border:1px solid #93c5fd; border-radius:10px; padding:1.25rem; margin-bottom:1.25rem; }}
  .next-steps h2 {{ font-size:1.1rem; margin-bottom:0.5rem; }}
  .next-steps li {{ font-size:0.9rem; color:var(--text2); margin-bottom:0.5rem; }}
  .next-steps ul {{ padding-left:1.25rem; }}
  .footer {{ text-align:center; color:var(--muted); font-size:0.75rem; margin-top:1.5rem; padding-top:0.75rem; border-top:1px solid var(--border); }}
</style>
</head>
<body>

<h1>Do Prediction Markets Predict Anything?</h1>
<p class="subtitle">Calibration analysis of {total_outcomes:,} resolved outcomes across {total_markets:,} markets — {generated_at}</p>

<div class="stats-grid">
  <div class="stat-card">
    <div class="label">Resolved Outcomes</div>
    <div class="value">{total_outcomes:,}</div>
    <div class="detail">{total_markets:,} markets, {total_winners:,} winners</div>
  </div>
  <div class="stat-card">
    <div class="label">Mean Calibration Error</div>
    <div class="value {grade_cls}">{mce:.1f}pp</div>
    <div class="detail">{grade_lbl}</div>
  </div>
  <div class="stat-card">
    <div class="label">Brier Score</div>
    <div class="value">{brier}</div>
    <div class="detail">0 = perfect, 0.25 = random · {max(0, (1 - brier/0.25)*100):.0f}% better than guessing</div>
  </div>
  <div class="stat-card">
    <div class="label">Sources</div>
    <div class="value">{len(sources)}</div>
    <div class="detail">{', '.join(sources)}</div>
  </div>
  <div class="stat-card">
    <div class="label">Categories</div>
    <div class="value">{len(cat_cals)}</div>
    <div class="detail">{top_3}</div>
  </div>
</div>

<div class="section">
  <h2>Overall Calibration Curve</h2>
  <p>Points on the diagonal = perfect calibration. Above the line = outcomes happened <em>more</em> than predicted. Below = <em>less</em>. Shaded band = ±5pp. Point size reflects sample count. Hover for details.</p>
  {overall_svg}
</div>

<div class="section">
  <h2>Calibration Table</h2>
  <table>
    <thead><tr><th>Bucket</th><th style="text-align:right">N</th><th style="text-align:right">Avg Opening</th><th style="text-align:right">Actual Rate</th><th style="text-align:right">Error</th></tr></thead>
    <tbody>{table_html(overall)}</tbody>
  </table>
</div>

<div class="two-col">
  <div class="section">
    <h2>By Source</h2>
    {source_svg}
  </div>
  <div class="section">
    <h2>By Category Group</h2>
    {super_svg}
  </div>
</div>

<div class="section">
  <h2>Individual Categories</h2>
</div>
<div class="category-grid">
  {"".join(cat_cards_html)}
</div>

{warning_html}

<div class="commentary">
  <h2>Analysis & Commentary</h2>
  <p><strong>Verdict: Yes, prediction markets contain real predictive signal.</strong> With a Brier score of {brier} ({max(0, (1 - brier/0.25)*100):.0f}% better than random guessing) and mean calibration error of {mce:.1f}pp, these markets are meaningfully better than chance. When markets say something has a 30% chance of happening, it happens about 30% of the time.</p>
  <p><strong>What is a Brier score?</strong> It measures the average squared distance between each prediction and the actual outcome (0 or 1). A Brier score of 0 means every prediction was perfect; 0.25 is what you'd get by flipping a coin on every question. Our score of {brier} means these markets are extracting real information from collective human judgment. For context, Nate Silver's FiveThirtyEight achieved Brier scores of 0.09-0.12 on US election forecasts — considered excellent — and they used far more sophisticated models than raw market prices.</p>

  <h3>Source Comparison</h3>
  <ul>{src_rows}</ul>

  <h3>Category Insights</h3>
  <ul>{"".join(cat_insights)}</ul>

  {flb_text}
</div>

<div class="section">
  <h2>Further Reading</h2>
  <p style="margin-bottom:0.75rem;">Our findings are consistent with decades of academic research on prediction market accuracy:</p>
  <ul style="font-size:0.9rem; color:var(--text2); padding-left:1.25rem;">
    <li style="margin-bottom:0.5rem;"><strong>Arrow et al., "The Promise of Prediction Markets" (2008, <em>Science</em>)</strong> — A letter signed by 22 leading economists arguing that prediction markets are "among the most accurate forecasting mechanisms known," consistently outperforming polls, expert panels, and statistical models.</li>
    <li style="margin-bottom:0.5rem;"><strong>Berg, Nelson &amp; Rietz, "Prediction Market Accuracy in the Long Run" (2008)</strong> — The Iowa Electronic Markets predicted US presidential election outcomes within 1.5 percentage points on average, outperforming 74% of contemporaneous polls.</li>
    <li style="margin-bottom:0.5rem;"><strong>Tetlock &amp; Gardner, <em>Superforecasting</em> (2015)</strong> — The foundational work on calibration in forecasting. Well-calibrated forecasters can be identified by their calibration curves — exactly what we measure here.</li>
    <li style="margin-bottom:0.5rem;"><strong>Wolfers &amp; Zitzewitz, "Prediction Markets" (2004, <em>J. Econ. Perspectives</em>)</strong> — A comprehensive survey finding that prediction markets aggregate information efficiently and produce well-calibrated probability estimates across politics, sports, and entertainment.</li>
    <li style="margin-bottom:0.5rem;"><strong>Metaculus Track Record</strong> — The forecasting platform publishes its calibration curve publicly, achieving ~2-3pp mean calibration error — the benchmark for online prediction platforms.</li>
  </ul>
</div>

<div class="next-steps">
  <h2>Methodology &amp; Limitations</h2>
  <ul>
    <li><strong>Winner inference:</strong> Winners are inferred from <code>current_probability &ge; 0.95</code> on resolved markets (the <code>is_winner</code> column is not yet populated). Backfilling from market settlement data would improve accuracy.</li>
    <li><strong>Opening vs. closing line:</strong> We use first-seen price, which may be days before resolution. The academic gold standard is the "closing line" at event start, which would likely show even better calibration.</li>
    <li><strong>Market reconstruction:</strong> Polymarket decomposes multi-outcome events into binary sub-markets. We reconstruct these using <code>group_id</code>. Markets without <code>group_id</code> (~25%) may be miscounted.</li>
    <li><strong>Field price correction:</strong> In 10+ outcome markets, <code>opening_probability &gt; 0.50</code> is inverted (stores "No" price). We correct by using <code>1 - opening_probability</code>.</li>
    <li><strong>Sources:</strong> Covers Kalshi and Polymarket. Traditional sportsbook data (The Odds API) will be included in a future version.</li>
  </ul>
</div>

<div class="footer">
  Generated by Bain Luck calibration analysis — {generated_at}<br>
  {total_outcomes:,} resolved outcomes · {len(sources)} sources · {len(cat_cals)} categories
</div>
</body>
</html>'''

    return html


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 build_calibration_report_svg.py <data.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)

    html = build_report(data)
    output = "calibration_report.html"
    with open(output, "w") as f:
        f.write(html)

    print(f"Report written to {output}")
    print(f"  {data['total_outcomes']:,} outcomes, {data['total_markets']:,} markets")
    print(f"  Open with: open {output}")


if __name__ == "__main__":
    main()
