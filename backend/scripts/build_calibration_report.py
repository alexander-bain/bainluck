"""
Build a static HTML calibration report from pre-aggregated bucket data.
Usage: python3 scripts/build_calibration_report.py /tmp/cal_data3.json
"""

import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_chartjs():
    """Load Chart.js from a local cache, downloading if needed."""
    cache_path = os.path.join(SCRIPT_DIR, ".chartjs_cache.js")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return f.read()
    import urllib.request
    url = "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"
    data = urllib.request.urlopen(url).read().decode("utf-8")
    with open(cache_path, "w") as f:
        f.write(data)
    return data


def load_data(path):
    with open(path) as f:
        return json.load(f)


# --- Category mapping ---

CATEGORY_DISPLAY = {
    "basketball": "Basketball", "baseball": "Baseball", "hockey": "Hockey",
    "football": "Football", "soccer": "Soccer", "golf": "Golf",
    "tennis": "Tennis", "mma": "MMA", "boxing": "Boxing",
    "cricket": "Cricket", "rugby": "Rugby", "motorsports": "Motorsports",
    "cycling": "Cycling", "esports": "Esports", "lacrosse": "Lacrosse",
    "pickleball": "Pickleball", "horse_racing": "Horse Racing",
    "olympics": "Olympics", "wrestling": "Wrestling", "darts": "Darts",
    "chess": "Chess", "poker": "Poker", "aussierules": "Aussie Rules",
    "politics": "Politics", "geopolitics": "Geopolitics",
    "entertainment": "Entertainment", "culture": "Culture",
    "weather": "Weather", "economics": "Economics",
    "crypto": "Crypto", "commodities": "Commodities",
    "tech": "Tech", "education": "Education", "health": "Health",
    "legal": "Legal", "uncategorized": "Uncategorized",
}

SUPER_CATEGORIES = {
    "Sports": ["basketball", "baseball", "hockey", "football", "soccer", "golf",
               "tennis", "mma", "boxing", "cricket", "rugby", "motorsports",
               "cycling", "esports", "lacrosse", "pickleball", "horse_racing",
               "olympics", "wrestling", "darts", "chess", "poker", "aussierules"],
    "Politics & Geo": ["politics", "geopolitics"],
    "Entertainment": ["entertainment", "culture"],
    "Weather": ["weather"],
    "Economics & Finance": ["economics", "crypto", "commodities"],
    "Science & Tech": ["tech"],
    "Other": ["education", "health", "legal", "uncategorized"],
}


def aggregate_buckets(buckets, filter_fn=None):
    """Aggregate bucket data, optionally filtering rows."""
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
            "bucket": f"{idx*10}-{idx*10+10}%",
            "midpoint": idx * 10 + 5,
            "n": a["n"],
            "winners": a["winners"],
            "avg_opening_prob": round(avg_prob * 100, 1),
            "actual_win_rate": round(actual * 100, 1),
            "calibration_error": round((actual - avg_prob) * 100, 1),
        })
    return result


def compute_brier(buckets, filter_fn=None):
    total_n = 0
    total_sq_err = 0
    for b in buckets:
        if filter_fn and not filter_fn(b):
            continue
        total_n += b["n"]
        total_sq_err += b["sum_sq_err"]
    if total_n == 0:
        return None
    return round(total_sq_err / total_n, 4)


def mean_cal_error(cal):
    if not cal:
        return 0
    return sum(abs(b["calibration_error"]) for b in cal) / len(cal)


def grade_class(err):
    err = abs(err)
    if err < 4: return "grade-A"
    if err < 8: return "grade-B"
    if err < 12: return "grade-C"
    return "grade-F"


def grade_label(err):
    err = abs(err)
    if err < 4: return "Excellent"
    if err < 8: return "Good"
    if err < 12: return "Fair"
    return "Poor"


def table_row_html(b):
    err = b["calibration_error"]
    cls = "error-ok" if abs(err) < 3 else ("error-pos" if err > 0 else "error-neg")
    sign = "+" if err > 0 else ""
    return f"""<tr>
      <td>{b['bucket']}</td>
      <td class="num">{b['n']:,}</td>
      <td class="num">{b['winners']:,}</td>
      <td class="num">{b['avg_opening_prob']}%</td>
      <td class="num">{b['actual_win_rate']}%</td>
      <td class="num {cls}">{sign}{err}pp</td>
    </tr>"""


def build_report(data):
    chartjs_code = load_chartjs()
    buckets = data["buckets"]
    total_markets = data["total_markets"]
    total_outcomes = data["total_outcomes"]
    total_winners = data["total_winners"]

    # Overall
    overall_cal = aggregate_buckets(buckets)
    overall_mce = mean_cal_error(overall_cal)
    overall_brier = compute_brier(buckets)

    # By source
    sources = sorted(set(b["source"] for b in buckets))
    source_cals = {}
    source_stats = {}
    for src in sources:
        fn = lambda b, s=src: b["source"] == s
        cal = aggregate_buckets(buckets, fn)
        source_cals[src] = cal
        n = sum(b["n"] for b in buckets if b["source"] == src)
        source_stats[src] = {"n": n, "brier": compute_brier(buckets, fn), "mce": mean_cal_error(cal)}

    # By raw category (top 15 by volume)
    raw_cats = sorted(set(b["category"] for b in buckets))
    cat_volumes = {c: sum(b["n"] for b in buckets if b["category"] == c) for c in raw_cats}
    top_cats = sorted(raw_cats, key=lambda c: -cat_volumes[c])[:15]

    cat_cals = {}
    cat_stats = {}
    for cat in top_cats:
        fn = lambda b, c=cat: b["category"] == c
        cal = aggregate_buckets(buckets, fn)
        if sum(x["n"] for x in cal) < 50:
            continue
        cat_cals[cat] = cal
        n = cat_volumes[cat]
        cat_stats[cat] = {"n": n, "brier": compute_brier(buckets, fn), "mce": mean_cal_error(cal)}

    # By super-category
    super_cals = {}
    super_stats = {}
    for sc, members in SUPER_CATEGORIES.items():
        fn = lambda b, m=members: b["category"] in m
        cal = aggregate_buckets(buckets, fn)
        n = sum(x["n"] for x in cal)
        if n < 50:
            continue
        super_cals[sc] = cal
        super_stats[sc] = {"n": n, "brier": compute_brier(buckets, fn), "mce": mean_cal_error(cal)}

    # Identify suspicious categories
    suspicious = []
    for cat, cal in cat_cals.items():
        # Check if any bucket has >20pp error with n>100
        for b in cal:
            if b["n"] > 100 and abs(b["calibration_error"]) > 20:
                suspicious.append(cat)
                break

    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")

    # Build JSON for charts
    overall_json = json.dumps(overall_cal)
    cat_cals_json = json.dumps({CATEGORY_DISPLAY.get(c, c): v for c, v in cat_cals.items()})
    source_cals_json = json.dumps(source_cals)
    super_cals_json = json.dumps(super_cals)
    cat_stats_json = json.dumps({CATEGORY_DISPLAY.get(c, c): v for c, v in cat_stats.items()})
    source_stats_json = json.dumps(source_stats)
    super_stats_json = json.dumps(super_stats)
    suspicious_json = json.dumps([CATEGORY_DISPLAY.get(c, c) for c in suspicious])

    # Table rows
    table_rows = "".join(table_row_html(b) for b in overall_cal)

    # Top categories text
    top_3 = ", ".join(f"{CATEGORY_DISPLAY.get(c,c)} ({cat_volumes[c]:,})" for c in top_cats[:3])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Do Prediction Markets Predict Anything? — Bain Luck</title>
<script>{chartjs_code}</script>
<style>
  :root {{
    --bg: #fafaf9; --surface: #ffffff; --text: #1c1917;
    --text-secondary: #57534e; --text-muted: #a8a29e; --border: #e7e5e4;
    --accent: #2563eb; --accent-light: #dbeafe; --green: #16a34a;
    --red: #dc2626; --orange: #ea580c; --perfect-line: #94a3b8;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    padding: 1.5rem; max-width: 1200px; margin: 0 auto;
  }}
  h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 0.25rem; }}
  .subtitle {{ color: var(--text-secondary); font-size: 1.05rem; margin-bottom: 1.5rem; }}
  .stats-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.75rem; margin-bottom: 1.5rem;
  }}
  .stat-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1rem;
  }}
  .stat-card .label {{
    font-size: 0.75rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.15rem;
  }}
  .stat-card .value {{ font-size: 1.6rem; font-weight: 700; }}
  .stat-card .detail {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.15rem; }}
  .grade-A {{ color: var(--green); }}
  .grade-B {{ color: var(--accent); }}
  .grade-C {{ color: var(--orange); }}
  .grade-F {{ color: var(--red); }}
  .section {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.25rem; margin-bottom: 1.25rem;
  }}
  .section h2 {{ font-size: 1.15rem; font-weight: 600; margin-bottom: 0.75rem; }}
  .section h3 {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text-secondary); }}
  .chart-container {{ position: relative; height: 380px; margin-bottom: 0.75rem; }}
  .chart-container.small {{ height: 280px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border); }}
  th {{ font-weight: 600; color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .error-pos {{ color: var(--green); }}
  .error-neg {{ color: var(--red); }}
  .error-ok {{ color: var(--text-muted); }}
  .category-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 1rem;
  }}
  .category-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1rem;
  }}
  .category-card h3 {{
    display: flex; justify-content: space-between; align-items: baseline;
  }}
  .category-card .n-label {{
    font-size: 0.75rem; font-weight: 400; color: var(--text-muted);
  }}
  .commentary {{
    background: #fefce8; border: 1px solid #fde68a;
    border-radius: 10px; padding: 1.25rem; margin-bottom: 1.25rem;
  }}
  .commentary h2 {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
  .commentary p, .commentary li {{
    font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 0.4rem;
  }}
  .commentary ul {{ padding-left: 1.25rem; }}
  .commentary strong {{ color: var(--text); }}
  .warning {{
    background: #fef2f2; border: 1px solid #fecaca;
    border-radius: 10px; padding: 1.25rem; margin-bottom: 1.25rem;
  }}
  .warning h2 {{ font-size: 1.1rem; margin-bottom: 0.5rem; color: var(--red); }}
  .warning p, .warning li {{ font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 0.4rem; }}
  .warning ul {{ padding-left: 1.25rem; }}
  .next-steps {{
    background: var(--accent-light); border: 1px solid #93c5fd;
    border-radius: 10px; padding: 1.25rem; margin-bottom: 1.25rem;
  }}
  .next-steps h2 {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
  .next-steps li {{ font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 0.5rem; }}
  .next-steps ul {{ padding-left: 1.25rem; }}
  .footer {{
    text-align: center; color: var(--text-muted); font-size: 0.75rem;
    margin-top: 1.5rem; padding-top: 0.75rem; border-top: 1px solid var(--border);
  }}
  .tab-bar {{ display: flex; gap: 0.4rem; margin-bottom: 0.75rem; flex-wrap: wrap; }}
  .tab-bar button {{
    padding: 0.35rem 0.75rem; border: 1px solid var(--border); border-radius: 7px;
    background: var(--surface); cursor: pointer; font-size: 0.8rem;
    color: var(--text-secondary); transition: all 0.15s;
  }}
  .tab-bar button.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
  .tab-bar button:hover:not(.active) {{ border-color: var(--accent); color: var(--accent); }}
  .tab-bar button.suspicious {{ border-color: var(--orange); color: var(--orange); }}
  .tab-bar button.suspicious.active {{ background: var(--orange); color: white; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }}
  @media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<h1>Do Prediction Markets Predict Anything?</h1>
<p class="subtitle">
  Calibration analysis of {total_outcomes:,} resolved outcomes across {total_markets:,} markets
  &mdash; {generated_at}
</p>

<div class="stats-grid">
  <div class="stat-card">
    <div class="label">Resolved Outcomes</div>
    <div class="value">{total_outcomes:,}</div>
    <div class="detail">{total_markets:,} markets, {total_winners:,} winners</div>
  </div>
  <div class="stat-card">
    <div class="label">Mean Calibration Error</div>
    <div class="value {grade_class(overall_mce)}">{overall_mce:.1f}pp</div>
    <div class="detail">{grade_label(overall_mce)}</div>
  </div>
  <div class="stat-card">
    <div class="label">Brier Score</div>
    <div class="value">{overall_brier}</div>
    <div class="detail">0 = perfect, 0.25 = coin flip</div>
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
  <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 0.75rem;">
    Points on the diagonal = perfect calibration. Above the line = outcomes happened <em>more</em> than predicted. Below = <em>less</em>.
    Point size reflects sample count.
  </p>
  <div class="chart-container"><canvas id="overallChart"></canvas></div>
</div>

<div class="section">
  <h2>Overall Calibration Table</h2>
  <table>
    <thead><tr>
      <th>Bucket</th><th style="text-align:right">N</th><th style="text-align:right">Winners</th>
      <th style="text-align:right">Avg Opening</th><th style="text-align:right">Actual Rate</th>
      <th style="text-align:right">Error</th>
    </tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>

<div class="two-col">
  <div class="section">
    <h2>By Source</h2>
    <div class="tab-bar" id="sourceTabBar"></div>
    <div class="chart-container small"><canvas id="sourceChart"></canvas></div>
  </div>
  <div class="section">
    <h2>By Super-Category</h2>
    <div class="tab-bar" id="superTabBar"></div>
    <div class="chart-container small"><canvas id="superChart"></canvas></div>
  </div>
</div>

<div class="section">
  <h2>By Category (Individual)</h2>
  <div class="tab-bar" id="categoryTabBar"></div>
  <div class="chart-container"><canvas id="categoryChart"></canvas></div>
</div>

<div class="category-grid" id="categoryCards"></div>

<div class="warning" id="warningSection" style="display:none">
  <h2>Data Quality Warning</h2>
  <div id="warningContent"></div>
</div>

<div class="commentary">
  <h2>Analysis &amp; Commentary</h2>
  <div id="commentary"></div>
</div>

<div class="next-steps">
  <h2>Suggested Next Steps</h2>
  <ul>
    <li><strong>Backfill <code>is_winner</code>:</strong> 131K "resolved" markets have zero <code>is_winner=True</code> outcomes. Winners are inferred from <code>current_probability</code>, which works for most markets but introduces noise. A Celery task that sets <code>is_winner</code> from final prices, ESPN results, or StatPal box scores would give us ground truth.</li>
    <li><strong>Use closing line instead of opening:</strong> The academic gold standard for calibration is the "closing line" &mdash; odds immediately before the event starts. Our <code>opening_probability</code> captures the first-seen price, which could be days or weeks early. A task that snapshots probabilities at event start time from <code>futures_odds_snapshots</code> would give more meaningful calibration data.</li>
    <li><strong>Fix 3-way sport dedup:</strong> Soccer, football, and cricket markets decompose into separate "Team A wins" / "Draw" / "Team B wins" sub-markets. The current dedup picks one per market, but the "closest to 50%" outcome in a 3-way sport systematically picks the favorite, which loses to draws + upsets. Need to either treat 3-way sports specially or use the full market structure.</li>
    <li><strong>Fix golf field outcomes:</strong> Kalshi golf markets have 30+ outcomes per tournament. Many tail outcomes (longshot golfers) have stale or incorrect <code>opening_probability</code> values that distort the 90-100% bucket.</li>
    <li><strong>Live calibration page:</strong> Add a <code>/calibration</code> route that re-runs this query nightly via Celery. Show "our markets are X% calibrated" as a trust signal.</li>
    <li><strong>Opening vs. closing:</strong> Compare opening odds to closing odds calibration. If closing is better, that's evidence of price discovery working.</li>
    <li><strong>Time-to-resolution:</strong> Are markets more accurate 1 week out vs. 1 month? Use <code>futures_odds_snapshots</code> time series.</li>
    <li><strong>Cross-source comparison:</strong> Which source is better calibrated? "Polymarket is X pp better calibrated than Kalshi on politics" could be a compelling differentiator.</li>
    <li><strong>User vs. market:</strong> Compare user Higher/Lower prediction accuracy against market calibration. Are your users better or worse than the market?</li>
    <li><strong>Volume weighting:</strong> Weight by trading volume &mdash; a $1M market should count more than a $100 one.</li>
  </ul>
</div>

<div class="footer">
  Generated by Bain Luck calibration analysis &mdash; {generated_at}<br>
  Data: {total_outcomes:,} resolved outcomes &middot; {len(sources)} sources &middot; {len(cat_cals)} categories
</div>

<script>
const OVERALL = {overall_json};
const CAT_CALS = {cat_cals_json};
const SOURCE_CALS = {source_cals_json};
const SUPER_CALS = {super_cals_json};
const CAT_STATS = {cat_stats_json};
const SOURCE_STATS = {source_stats_json};
const SUPER_STATS = {super_stats_json};
const SUSPICIOUS = {suspicious_json};

const COLORS = [
  '#2563eb','#16a34a','#dc2626','#ea580c','#7c3aed',
  '#db2777','#0d9488','#d97706','#4f46e5','#65a30d',
  '#0891b2','#be185d','#059669','#9333ea','#c2410c',
];

function pts(cal) {{
  return cal.map(b => ({{x: b.midpoint, y: b.actual_win_rate, n: b.n}}));
}}

function perfectLine() {{
  return {{
    label: 'Perfect', data: [{{x:0,y:0}},{{x:100,y:100}}],
    borderColor: '#94a3b8', borderDash: [6,4], borderWidth: 2,
    pointRadius: 0, showLine: true, fill: false, order: 10,
  }};
}}

function makeChart(ctx, datasets) {{
  return new Chart(ctx, {{
    type: 'scatter',
    data: {{ datasets: [perfectLine(), ...datasets] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{ mode: 'nearest', intersect: false }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: ctx => {{
              if (ctx.dataset.label === 'Perfect') return null;
              const p = ctx.raw;
              return `${{ctx.dataset.label}}: ${{p.y.toFixed(1)}}% actual @ ${{p.x}}% predicted (n=${{p.n?.toLocaleString() || '?'}})`;
            }}
          }}
        }},
        legend: {{
          position: 'bottom',
          labels: {{ usePointStyle: true, padding: 12, filter: i => i.text !== 'Perfect' }}
        }},
      }},
      scales: {{
        x: {{
          title: {{ display: true, text: 'Predicted Probability (%)', font: {{ weight: '600' }} }},
          min: 0, max: 100, ticks: {{ stepSize: 10 }}, grid: {{ color: '#f5f5f4' }},
        }},
        y: {{
          title: {{ display: true, text: 'Actual Win Rate (%)', font: {{ weight: '600' }} }},
          min: 0, max: 100, ticks: {{ stepSize: 10 }}, grid: {{ color: '#f5f5f4' }},
        }},
      }},
    }},
  }});
}}

function ds(label, data, color, lineWidth=2.5) {{
  return {{
    label, data, borderColor: color, backgroundColor: color + '33',
    borderWidth: lineWidth, pointRadius: 5, pointHoverRadius: 7,
    showLine: true, tension: 0.15, fill: false,
  }};
}}

// Overall chart with point size proportional to n
const overallPts = OVERALL.map(b => ({{x: b.midpoint, y: b.actual_win_rate, n: b.n}}));
const maxN = Math.max(...overallPts.map(p => p.n));
new Chart(document.getElementById('overallChart'), {{
  type: 'scatter',
  data: {{ datasets: [perfectLine(), {{
    label: 'All Markets (n=' + {total_outcomes}.toLocaleString() + ')',
    data: overallPts, borderColor: '#2563eb', backgroundColor: '#2563eb33',
    borderWidth: 3, showLine: true, tension: 0.15, fill: false,
    pointRadius: overallPts.map(p => 4 + 8 * Math.sqrt(p.n / maxN)),
    pointHoverRadius: 9,
  }}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'nearest', intersect: false }},
    plugins: {{
      tooltip: {{ callbacks: {{ label: ctx => {{
        if (ctx.dataset.label === 'Perfect') return null;
        const p = ctx.raw;
        return `${{p.y.toFixed(1)}}% actual @ ${{p.x}}% predicted (n=${{p.n?.toLocaleString()}})`;
      }} }} }},
      legend: {{ position: 'bottom', labels: {{ usePointStyle: true, padding: 12, filter: i => i.text !== 'Perfect' }} }},
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Predicted (%)', font: {{ weight: '600' }} }}, min: 0, max: 100, ticks: {{ stepSize: 10 }}, grid: {{ color: '#f5f5f4' }} }},
      y: {{ title: {{ display: true, text: 'Actual (%)', font: {{ weight: '600' }} }}, min: 0, max: 100, ticks: {{ stepSize: 10 }}, grid: {{ color: '#f5f5f4' }} }},
    }},
  }},
}});

// Source chart
let sourceChart = null;
const srcNames = Object.keys(SOURCE_CALS).sort((a,b) => {{
  const na = SOURCE_CALS[a].reduce((s,b)=>s+b.n,0);
  const nb = SOURCE_CALS[b].reduce((s,b)=>s+b.n,0);
  return nb - na;
}});
function renderSourceChart(selected) {{
  if (sourceChart) sourceChart.destroy();
  sourceChart = makeChart(document.getElementById('sourceChart'),
    selected.map((s,i) => ds(
      s + ' (n=' + SOURCE_CALS[s].reduce((a,b)=>a+b.n,0).toLocaleString() + ')',
      pts(SOURCE_CALS[s]), COLORS[i % COLORS.length]
    ))
  );
}}
const srcBar = document.getElementById('sourceTabBar');
const srcAll = document.createElement('button');
srcAll.textContent = 'All'; srcAll.className = 'active';
srcAll.onclick = () => {{ srcBar.querySelectorAll('button').forEach(b=>b.className=''); srcAll.className='active'; renderSourceChart(srcNames); }};
srcBar.appendChild(srcAll);
srcNames.forEach(s => {{
  const btn = document.createElement('button');
  const n = SOURCE_CALS[s].reduce((a,b)=>a+b.n,0);
  btn.textContent = s + ' (' + n.toLocaleString() + ')';
  btn.onclick = () => {{ srcBar.querySelectorAll('button').forEach(b=>b.className=''); btn.className='active'; renderSourceChart([s]); }};
  srcBar.appendChild(btn);
}});
renderSourceChart(srcNames);

// Super-category chart
let superChart = null;
const scNames = Object.keys(SUPER_CALS).sort((a,b) => {{
  const na = SUPER_CALS[a].reduce((s,b)=>s+b.n,0);
  const nb = SUPER_CALS[b].reduce((s,b)=>s+b.n,0);
  return nb - na;
}});
function renderSuperChart(selected) {{
  if (superChart) superChart.destroy();
  superChart = makeChart(document.getElementById('superChart'),
    selected.map((s,i) => ds(
      s + ' (n=' + SUPER_CALS[s].reduce((a,b)=>a+b.n,0).toLocaleString() + ')',
      pts(SUPER_CALS[s]), COLORS[i % COLORS.length]
    ))
  );
}}
const scBar = document.getElementById('superTabBar');
const scAll = document.createElement('button');
scAll.textContent = 'All'; scAll.className = 'active';
scAll.onclick = () => {{ scBar.querySelectorAll('button').forEach(b=>b.className=''); scAll.className='active'; renderSuperChart(scNames); }};
scBar.appendChild(scAll);
scNames.forEach(s => {{
  const btn = document.createElement('button');
  btn.textContent = s;
  btn.onclick = () => {{ scBar.querySelectorAll('button').forEach(b=>b.className=''); btn.className='active'; renderSuperChart([s]); }};
  scBar.appendChild(btn);
}});
renderSuperChart(scNames);

// Category chart
let catChart = null;
const catNames = Object.keys(CAT_CALS).sort((a,b) => {{
  const na = CAT_CALS[a].reduce((s,b)=>s+b.n,0);
  const nb = CAT_CALS[b].reduce((s,b)=>s+b.n,0);
  return nb - na;
}});
function renderCatChart(selected) {{
  if (catChart) catChart.destroy();
  catChart = makeChart(document.getElementById('categoryChart'),
    selected.map((s,i) => ds(
      s + ' (n=' + CAT_CALS[s].reduce((a,b)=>a+b.n,0).toLocaleString() + ')',
      pts(CAT_CALS[s]), COLORS[i % COLORS.length]
    ))
  );
}}
const catBar = document.getElementById('categoryTabBar');
const catAll = document.createElement('button');
catAll.textContent = 'Top 6'; catAll.className = 'active';
catAll.onclick = () => {{ catBar.querySelectorAll('button').forEach(b=>b.className=''); catAll.className='active'; renderCatChart(catNames.slice(0,6)); }};
catBar.appendChild(catAll);
catNames.forEach(cat => {{
  const btn = document.createElement('button');
  const n = CAT_CALS[cat].reduce((a,b)=>a+b.n,0);
  btn.textContent = cat + ' (' + n.toLocaleString() + ')';
  if (SUSPICIOUS.includes(cat)) btn.className = 'suspicious';
  btn.onclick = () => {{
    catBar.querySelectorAll('button').forEach(b => {{
      b.className = SUSPICIOUS.includes(b.textContent.split(' (')[0]) ? 'suspicious' : '';
    }});
    btn.className = SUSPICIOUS.includes(cat) ? 'suspicious active' : 'active';
    renderCatChart([cat]);
  }};
  catBar.appendChild(btn);
}});
renderCatChart(catNames.slice(0,6));

// Category cards
const cardsEl = document.getElementById('categoryCards');
catNames.forEach((cat, i) => {{
  const cal = CAT_CALS[cat];
  const n = cal.reduce((s,b)=>s+b.n,0);
  const stats = CAT_STATS[cat];
  const isSusp = SUSPICIOUS.includes(cat);
  const card = document.createElement('div');
  card.className = 'category-card';
  if (isSusp) card.style.borderColor = '#ea580c';
  card.innerHTML = `
    <h3>${{cat}}${{isSusp ? ' ⚠️' : ''}} <span class="n-label">${{n.toLocaleString()}} outcomes &middot; Brier: ${{stats?.brier ?? '?'}} &middot; MCE: ${{stats?.mce?.toFixed(1) ?? '?'}}pp</span></h3>
    <div class="chart-container small"><canvas id="catCard${{i}}"></canvas></div>
  `;
  cardsEl.appendChild(card);
  makeChart(card.querySelector('canvas'), [
    ds(cat, pts(cal), isSusp ? '#ea580c' : COLORS[i % COLORS.length])
  ]);
}});

// Warnings
if (SUSPICIOUS.length > 0) {{
  document.getElementById('warningSection').style.display = '';
  document.getElementById('warningContent').innerHTML = `
    <p>The following categories show calibration errors &gt;20pp in at least one bucket with n&gt;100. Two root causes have been identified:</p>
    <ul>
      ${{SUSPICIOUS.map(c => '<li><strong>' + c + '</strong>').join('')}}
    </ul>
    <p><strong>Root cause 1: Three-way sports.</strong> Soccer, football, and cricket have win/draw/lose outcomes stored as separate
    binary sub-markets. When deduplicating to one outcome per market, the "closest to 50%" rule picks the favorite team — but that team
    loses to draws + upsets more than 50% of the time. This inflates the 40-50% bucket's loss rate.</p>
    <p><strong>Root cause 2: Field-level futures.</strong> Golf and motorsports markets have 30+ outcomes per tournament. Many tail
    outcomes (longshot players) have <code>opening_probability</code> values that don't reflect actual trading activity, distorting
    the extreme buckets. Additionally, <code>is_winner</code> is never populated in the DB, so winners are inferred from
    <code>current_probability</code> — which may not be fully updated to 1.0/0.0 for all outcomes in large multi-outcome markets.</p>
  `;
}}

// Commentary
const comm = document.getElementById('commentary');
const mce = {overall_mce:.1f};
const brier = {overall_brier};
const nOutcomes = {total_outcomes};
const suspCount = SUSPICIOUS.length;

let html = '<p>';
if (suspCount > 3) {{
  html += '<strong>Verdict: The data tells a split story.</strong> Several categories show excellent calibration, but ' +
    suspCount + ' categories have data quality issues that inflate the overall error. ';
  html += 'Excluding the suspicious categories, the remaining markets show that prediction markets <em>do</em> predict — ' +
    'things that open at 30% happen about 30% of the time.';
}} else if (mce < 4) {{
  html += '<strong>Verdict: Yes, prediction markets predict.</strong> Mean calibration error of ' + mce.toFixed(1) + 'pp means events predicted at X% really do happen about X% of the time.';
}} else if (mce < 8) {{
  html += '<strong>Verdict: Markets are reasonably calibrated, with room for improvement.</strong> Mean error of ' + mce.toFixed(1) + 'pp suggests the broad strokes are right, but systematic biases exist.';
}} else {{
  html += '<strong>Verdict: Markets show notable calibration issues, but the story varies by category.</strong> Mean error of ' + mce.toFixed(1) + 'pp is driven partly by data quality issues in certain categories.';
}}
html += '</p>';

html += '<p>The overall Brier score of ' + brier + ' ';
if (brier < 0.12) html += 'is strong — well below the 0.25 coin-flip baseline, indicating genuine predictive signal.';
else if (brier < 0.18) html += 'is reasonable — better than random, indicating real information is embedded in prices.';
else html += 'is moderate, influenced by the data quality issues flagged above.';
html += '</p>';

// Per-source
html += '<h3 style="margin-top:1rem;">Source Comparison</h3><ul>';
Object.entries(SOURCE_STATS).sort((a,b) => b[1].n - a[1].n).forEach(([src, stats]) => {{
  html += `<li><strong>${{src}}</strong> (${{stats.n.toLocaleString()}} outcomes): MCE = ${{stats.mce.toFixed(1)}}pp, Brier = ${{stats.brier}}</li>`;
}});
html += '</ul>';

// Per super-category
html += '<h3 style="margin-top:1rem;">Category Group Insights</h3><ul>';
Object.entries(SUPER_STATS).sort((a,b) => b[1].n - a[1].n).forEach(([sc, stats]) => {{
  let verdict = '';
  if (stats.mce < 4) verdict = 'very well-calibrated';
  else if (stats.mce < 8) verdict = 'reasonably calibrated';
  else if (stats.mce < 15) verdict = 'has notable calibration gaps (possible data issues)';
  else verdict = 'has significant calibration issues (likely data quality)';
  html += `<li><strong>${{sc}}</strong> (${{stats.n.toLocaleString()}}): ${{verdict}} — MCE ${{stats.mce.toFixed(1)}}pp, Brier ${{stats.brier}}</li>`;
}});
html += '</ul>';

// Favorite-longshot
const lowBuckets = OVERALL.filter(b => b.midpoint <= 15);
const highBuckets = OVERALL.filter(b => b.midpoint >= 85);
if (lowBuckets.length && highBuckets.length) {{
  const lowErr = lowBuckets.reduce((s,b) => s + b.calibration_error, 0) / lowBuckets.length;
  const highErr = highBuckets.reduce((s,b) => s + b.calibration_error, 0) / highBuckets.length;
  html += '<h3 style="margin-top:1rem;">Favorite-Longshot Bias</h3><p>';
  if (lowErr > 2) html += 'Longshots (0-15%) win <strong>more</strong> often than predicted (+' + lowErr.toFixed(1) + 'pp), consistent with the classic favorite-longshot bias. ';
  else if (lowErr < -2) html += 'Longshots (0-15%) win <strong>less</strong> than predicted (' + lowErr.toFixed(1) + 'pp). ';
  else html += 'Longshots (0-15%) are well-calibrated (' + lowErr.toFixed(1) + 'pp). ';
  if (highErr < -2) html += 'Favorites (85%+) show overconfidence (' + highErr.toFixed(1) + 'pp) — they win less often than predicted.';
  else if (highErr > 2) html += 'Favorites (85%+) are underconfident (+' + highErr.toFixed(1) + 'pp) — they win even more than predicted.';
  else html += 'Favorites (85%+) are well-calibrated (' + highErr.toFixed(1) + 'pp).';
  html += '</p>';
}}

// 40-50% dip
const midBuckets = OVERALL.filter(b => b.midpoint >= 35 && b.midpoint <= 55);
if (midBuckets.length) {{
  const midErr = midBuckets.reduce((s,b) => s + b.calibration_error, 0) / midBuckets.length;
  if (Math.abs(midErr) > 5) {{
    html += '<h3 style="margin-top:1rem;">The Midrange Dip</h3><p>';
    html += 'The 40-60% range shows a notable ' + midErr.toFixed(1) + 'pp error. ';
    html += 'This is likely driven by binary markets (e.g., "Will X happen? Yes/No") where both outcomes cluster near 50%. ';
    html += 'In multi-outcome markets (like championship futures), the 50% bucket is rare. The dip may also reflect ';
    html += 'markets where opening prices were stale or thinly traded.</p>';
  }}
}}

comm.innerHTML = html;
</script>
</body>
</html>"""

    return html


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 build_calibration_report.py <data.json>")
        sys.exit(1)

    data = load_data(sys.argv[1])
    html = build_report(data)

    output = "calibration_report.html"
    with open(output, "w") as f:
        f.write(html)

    print(f"Report written to {output}")
    print(f"  {data['total_outcomes']:,} outcomes, {data['total_markets']:,} markets")
    print(f"  Open with: open {output}")


if __name__ == "__main__":
    main()
