"""
Prediction Market Calibration Analysis

Answers: "Do prediction markets really predict anything?"

Pulls all resolved markets with opening probabilities, buckets them by decile,
and checks whether N% of outcomes that opened at N% actually happened.
Generates a static HTML report with overall + per-category calibration curves.
"""

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

import psycopg2


def get_db_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        result = subprocess.run(
            ["heroku", "config:get", "DATABASE_URL", "-a", "bainluck"],
            capture_output=True, text=True
        )
        url = result.stdout.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


QUERY = """
SELECT
    fo.opening_probability,
    fo.is_winner,
    fm.source,
    fm.llm_sport_category,
    fm.category,
    fm.market_type,
    fm.name AS market_name,
    fo.name AS outcome_name,
    fm.status,
    fm.resolution_date
FROM futures_outcomes fo
JOIN futures_markets fm ON fo.market_id = fm.id
WHERE fm.status = 'resolved'
  AND fo.opening_probability IS NOT NULL
  AND fo.opening_probability > 0
  AND fo.opening_probability < 1
ORDER BY fo.opening_probability
"""


def bucket_label(prob):
    low = int(prob * 10) * 10
    high = low + 10
    if low == 100:
        low, high = 90, 100
    return f"{low}-{high}%"


def bucket_midpoint(prob):
    low = int(prob * 10) * 10
    if low == 100:
        low = 90
    return low + 5


def compute_calibration(rows):
    buckets = defaultdict(lambda: {"total": 0, "winners": 0, "sum_prob": 0.0})
    for row in rows:
        prob = float(row["opening_probability"])
        label = bucket_label(prob)
        buckets[label]["total"] += 1
        buckets[label]["sum_prob"] += prob
        if row["is_winner"]:
            buckets[label]["winners"] += 1

    result = []
    for label in sorted(buckets.keys(), key=lambda x: int(x.split("-")[0])):
        b = buckets[label]
        avg_prob = b["sum_prob"] / b["total"]
        actual_rate = b["winners"] / b["total"]
        result.append({
            "bucket": label,
            "midpoint": int(label.split("-")[0]) + 5,
            "n": b["total"],
            "winners": b["winners"],
            "avg_opening_prob": round(avg_prob * 100, 1),
            "actual_win_rate": round(actual_rate * 100, 1),
            "calibration_error": round((actual_rate - avg_prob) * 100, 1),
        })
    return result


def categorize(row):
    cat = (row["llm_sport_category"] or "").lower().strip()
    name = (row["market_name"] or "").lower()

    sport_cats = {
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "tennis", "mma", "boxing", "cricket", "rugby",
        "motorsport", "cycling", "esports"
    }
    politics_cats = {"politics", "geopolitics", "government"}
    entertainment_cats = {"entertainment", "movies", "music", "tv", "awards", "culture"}
    weather_cats = {"weather", "climate", "temperature"}
    economics_cats = {"economics", "finance", "fed", "crypto", "stocks", "business"}
    science_cats = {"science", "technology", "tech", "ai", "space"}

    if cat in sport_cats:
        return "Sports"
    if cat in politics_cats:
        return "Politics"
    if cat in entertainment_cats:
        return "Entertainment"
    if cat in weather_cats:
        return "Weather"
    if cat in economics_cats:
        return "Economics & Finance"
    if cat in science_cats:
        return "Science & Tech"

    # Fallback: check market name
    for kw in ["election", "president", "congress", "senate", "trump", "biden"]:
        if kw in name:
            return "Politics"
    for kw in ["movie", "oscar", "grammy", "box office", "rotten", "spotify"]:
        if kw in name:
            return "Entertainment"
    for kw in ["temperature", "weather", "rain", "hurricane", "snow"]:
        if kw in name:
            return "Weather"
    for kw in ["fed", "gdp", "inflation", "interest rate", "stock", "bitcoin", "crypto"]:
        if kw in name:
            return "Economics & Finance"

    if cat:
        return cat.title()
    return "Uncategorized"


def compute_brier_score(rows):
    """Brier score: mean squared error of probabilistic forecasts. 0 = perfect, 0.25 = coin flip."""
    if not rows:
        return None
    total = 0.0
    for row in rows:
        prob = float(row["opening_probability"])
        outcome = 1.0 if row["is_winner"] else 0.0
        total += (prob - outcome) ** 2
    return round(total / len(rows), 4)


def compute_log_loss(rows):
    """Log loss (cross-entropy). Lower = better. 0.693 = coin flip."""
    import math
    if not rows:
        return None
    total = 0.0
    eps = 1e-10
    for row in rows:
        prob = max(min(float(row["opening_probability"]), 1 - eps), eps)
        outcome = 1.0 if row["is_winner"] else 0.0
        total += -(outcome * math.log(prob) + (1 - outcome) * math.log(1 - prob))
    return round(total / len(rows), 4)


def generate_html(overall_cal, category_cals, source_cals, stats, rows):
    categories_json = json.dumps(category_cals)
    sources_json = json.dumps(source_cals)
    overall_json = json.dumps(overall_cal)

    # Top movers: biggest calibration errors
    biggest_errors = sorted(overall_cal, key=lambda x: abs(x["calibration_error"]), reverse=True)[:3]

    # Category stats
    cat_stats = {}
    for cat, cal in category_cals.items():
        cat_rows = [r for r in rows if categorize(r) == cat]
        cat_stats[cat] = {
            "n": sum(b["n"] for b in cal),
            "brier": compute_brier_score(cat_rows),
        }
    cat_stats_json = json.dumps(cat_stats)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Prediction Market Calibration — Bain Luck</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #fafaf9;
    --surface: #ffffff;
    --text: #1c1917;
    --text-secondary: #57534e;
    --text-muted: #a8a29e;
    --border: #e7e5e4;
    --accent: #2563eb;
    --accent-light: #dbeafe;
    --green: #16a34a;
    --red: #dc2626;
    --orange: #ea580c;
    --perfect-line: #94a3b8;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
  }}
  .subtitle {{
    color: var(--text-secondary);
    font-size: 1.1rem;
    margin-bottom: 2rem;
  }}
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
  }}
  .stat-card .label {{
    font-size: 0.8rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
  }}
  .stat-card .value {{
    font-size: 1.8rem;
    font-weight: 700;
  }}
  .stat-card .detail {{
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
  }}
  .grade-A {{ color: var(--green); }}
  .grade-B {{ color: var(--accent); }}
  .grade-C {{ color: var(--orange); }}
  .grade-F {{ color: var(--red); }}

  .section {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .section h2 {{
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 1rem;
  }}
  .section h3 {{
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 0.75rem;
    color: var(--text-secondary);
  }}
  .chart-container {{
    position: relative;
    height: 400px;
    margin-bottom: 1rem;
  }}
  .chart-container.small {{
    height: 300px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }}
  th, td {{
    text-align: left;
    padding: 0.6rem 0.8rem;
    border-bottom: 1px solid var(--border);
  }}
  th {{
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .error-pos {{ color: var(--green); }}
  .error-neg {{ color: var(--red); }}
  .error-ok {{ color: var(--text-muted); }}

  .category-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 1.5rem;
  }}
  .category-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
  }}
  .category-card h3 {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .category-card .n-label {{
    font-size: 0.8rem;
    font-weight: 400;
    color: var(--text-muted);
  }}

  .commentary {{
    background: #fefce8;
    border: 1px solid #fde68a;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .commentary h2 {{
    font-size: 1.15rem;
    margin-bottom: 0.75rem;
  }}
  .commentary p, .commentary li {{
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
  }}
  .commentary ul {{
    padding-left: 1.5rem;
  }}
  .commentary strong {{
    color: var(--text);
  }}

  .next-steps {{
    background: var(--accent-light);
    border: 1px solid #93c5fd;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .next-steps h2 {{ font-size: 1.15rem; margin-bottom: 0.75rem; }}
  .next-steps li {{
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
  }}
  .next-steps ul {{ padding-left: 1.5rem; }}

  .footer {{
    text-align: center;
    color: var(--text-muted);
    font-size: 0.8rem;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
  }}

  .tab-bar {{
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
  }}
  .tab-bar button {{
    padding: 0.4rem 0.9rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    cursor: pointer;
    font-size: 0.85rem;
    color: var(--text-secondary);
    transition: all 0.15s;
  }}
  .tab-bar button.active {{
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }}
  .tab-bar button:hover:not(.active) {{
    border-color: var(--accent);
    color: var(--accent);
  }}
</style>
</head>
<body>

<h1>Do Prediction Markets Predict Anything?</h1>
<p class="subtitle">Calibration analysis of {stats['total_outcomes']:,} resolved outcomes across {stats['total_markets']:,} markets &mdash; generated {stats['generated_at']}</p>

<div class="stats-grid">
  <div class="stat-card">
    <div class="label">Resolved Outcomes</div>
    <div class="value">{stats['total_outcomes']:,}</div>
    <div class="detail">{stats['total_markets']:,} markets, {stats['total_winners']:,} winners</div>
  </div>
  <div class="stat-card">
    <div class="label">Mean Calibration Error</div>
    <div class="value {_grade_class(stats['mean_cal_error'])}">{stats['mean_cal_error']:.1f}pp</div>
    <div class="detail">{_grade_label(stats['mean_cal_error'])}</div>
  </div>
  <div class="stat-card">
    <div class="label">Brier Score</div>
    <div class="value">{stats['brier']}</div>
    <div class="detail">0 = perfect, 0.25 = coin flip</div>
  </div>
  <div class="stat-card">
    <div class="label">Sources</div>
    <div class="value">{stats['n_sources']}</div>
    <div class="detail">{', '.join(stats['sources'])}</div>
  </div>
  <div class="stat-card">
    <div class="label">Categories</div>
    <div class="value">{stats['n_categories']}</div>
    <div class="detail">{stats['top_categories']}</div>
  </div>
</div>

<div class="section">
  <h2>Overall Calibration Curve</h2>
  <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 1rem;">
    The diagonal line represents perfect calibration. Points above the line mean outcomes happened more often than predicted; below means less often.
  </p>
  <div class="chart-container">
    <canvas id="overallChart"></canvas>
  </div>
</div>

<div class="section">
  <h2>Calibration Table</h2>
  <table>
    <thead>
      <tr>
        <th>Bucket</th>
        <th style="text-align:right">N</th>
        <th style="text-align:right">Winners</th>
        <th style="text-align:right">Avg Opening Prob</th>
        <th style="text-align:right">Actual Win Rate</th>
        <th style="text-align:right">Error</th>
      </tr>
    </thead>
    <tbody>
      {"".join(_table_row(b) for b in overall_cal)}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>By Source</h2>
  <div class="tab-bar" id="sourceTabBar"></div>
  <div class="chart-container" id="sourceChartContainer">
    <canvas id="sourceChart"></canvas>
  </div>
</div>

<div class="section">
  <h2>By Category</h2>
  <div class="tab-bar" id="categoryTabBar"></div>
  <div class="chart-container" id="categoryChartContainer">
    <canvas id="categoryChart"></canvas>
  </div>
</div>

<div class="category-grid" id="categoryCards"></div>

<div class="commentary">
  <h2>Analysis & Commentary</h2>
  <div id="commentary"></div>
</div>

<div class="next-steps">
  <h2>Suggested Next Steps</h2>
  <ul>
    <li><strong>Live calibration page:</strong> Add a <code>/calibration</code> route that re-runs this query on demand. Update nightly via Celery task. Show users "our markets are X% calibrated" as a trust signal.</li>
    <li><strong>Time-series calibration:</strong> Track how calibration changes as markets approach resolution. Are markets more accurate 1 week out vs. 1 month out? Use <code>futures_odds_snapshots</code> for this.</li>
    <li><strong>Closing vs. opening:</strong> Compare opening odds calibration to closing odds. If closing odds are significantly better, that tells you markets are learning over time (price discovery is real).</li>
    <li><strong>Cross-source comparison:</strong> Who's better calibrated — Kalshi, Polymarket, or traditional sportsbooks? This could be a compelling differentiator for the platform ("Polymarket is 3pp better calibrated than Kalshi on politics").</li>
    <li><strong>Overconfidence analysis:</strong> Dig into the tails. Are markets systematically overconfident on favorites (90%+ bucket) or underconfident on longshots (0-10%)? The "favorite-longshot bias" is one of the most studied phenomena in prediction markets.</li>
    <li><strong>Resolution volume weighting:</strong> Weight calibration by market volume/liquidity. A well-traded market with $1M volume should count more than a thin one with $100.</li>
    <li><strong>Sharpe-like metric:</strong> Create a "prediction quality score" that accounts for calibration, resolution, and discrimination (ability to distinguish outcomes). Could become a Bain Luck signature metric.</li>
    <li><strong>User prediction calibration:</strong> Compare market calibration against your users' Higher/Lower predictions. Are your users better or worse than the markets?</li>
  </ul>
</div>

<div class="footer">
  Generated by Bain Luck calibration analysis &mdash; {stats['generated_at']}
</div>

<script>
const overallData = {overall_json};
const categoryData = {categories_json};
const sourceData = {sources_json};
const catStats = {cat_stats_json};

const COLORS = {{
  accent: '#2563eb',
  perfect: '#94a3b8',
  green: '#16a34a',
  red: '#dc2626',
  orange: '#ea580c',
  purple: '#7c3aed',
  pink: '#db2777',
  teal: '#0d9488',
  amber: '#d97706',
  indigo: '#4f46e5',
  lime: '#65a30d',
}};

const CATEGORY_COLORS = [
  COLORS.accent, COLORS.green, COLORS.red, COLORS.orange,
  COLORS.purple, COLORS.pink, COLORS.teal, COLORS.amber,
  COLORS.indigo, COLORS.lime
];

function makeCalibrationChart(ctx, datasets, title) {{
  return new Chart(ctx, {{
    type: 'scatter',
    data: {{
      datasets: [
        {{
          label: 'Perfect calibration',
          data: [{{x:0,y:0}}, {{x:5,y:5}}, {{x:15,y:15}}, {{x:25,y:25}}, {{x:35,y:35}}, {{x:45,y:45}}, {{x:55,y:55}}, {{x:65,y:65}}, {{x:75,y:75}}, {{x:85,y:85}}, {{x:95,y:95}}, {{x:100,y:100}}],
          borderColor: COLORS.perfect,
          borderDash: [6, 4],
          borderWidth: 2,
          pointRadius: 0,
          showLine: true,
          fill: false,
          order: 10,
        }},
        ...datasets
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{
        mode: 'nearest',
        intersect: false,
      }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              if (ctx.dataset.label === 'Perfect calibration') return null;
              const pt = ctx.raw;
              return `${{ctx.dataset.label}}: ${{pt.y.toFixed(1)}}% actual at ${{pt.x}}% predicted (n=${{pt.n || '?'}})`;
            }}
          }}
        }},
        legend: {{
          position: 'bottom',
          labels: {{
            usePointStyle: true,
            padding: 16,
            filter: item => item.text !== 'Perfect calibration'
          }}
        }},
      }},
      scales: {{
        x: {{
          title: {{ display: true, text: 'Predicted Probability (%)', font: {{ weight: '600' }} }},
          min: 0,
          max: 100,
          ticks: {{ stepSize: 10 }},
          grid: {{ color: '#f5f5f4' }},
        }},
        y: {{
          title: {{ display: true, text: 'Actual Win Rate (%)', font: {{ weight: '600' }} }},
          min: 0,
          max: 100,
          ticks: {{ stepSize: 10 }},
          grid: {{ color: '#f5f5f4' }},
        }}
      }}
    }}
  }});
}}

function calDataToPoints(calData) {{
  return calData.map(b => ({{ x: b.midpoint, y: b.actual_win_rate, n: b.n }}));
}}

// Overall chart
makeCalibrationChart(
  document.getElementById('overallChart'),
  [{{
    label: 'All markets',
    data: calDataToPoints(overallData),
    borderColor: COLORS.accent,
    backgroundColor: COLORS.accent + '33',
    borderWidth: 3,
    pointRadius: 6,
    pointHoverRadius: 8,
    showLine: true,
    tension: 0.1,
    fill: false,
  }}]
);

// Source chart
let sourceChart = null;
const sourceNames = Object.keys(sourceData).sort((a,b) => {{
  const na = sourceData[a].reduce((s,b) => s+b.n, 0);
  const nb = sourceData[b].reduce((s,b) => s+b.n, 0);
  return nb - na;
}});

function renderSourceChart(selectedSources) {{
  const ctx = document.getElementById('sourceChart');
  if (sourceChart) sourceChart.destroy();
  const datasets = selectedSources.map((src, i) => ({{
    label: src + ' (n=' + sourceData[src].reduce((s,b) => s+b.n, 0).toLocaleString() + ')',
    data: calDataToPoints(sourceData[src]),
    borderColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
    backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] + '33',
    borderWidth: 2.5,
    pointRadius: 5,
    showLine: true,
    tension: 0.1,
    fill: false,
  }}));
  sourceChart = makeCalibrationChart(ctx, datasets);
}}

// Source tabs
const sourceTabBar = document.getElementById('sourceTabBar');
const allSourceBtn = document.createElement('button');
allSourceBtn.textContent = 'All Sources';
allSourceBtn.className = 'active';
allSourceBtn.onclick = () => {{
  document.querySelectorAll('#sourceTabBar button').forEach(b => b.className = '');
  allSourceBtn.className = 'active';
  renderSourceChart(sourceNames);
}};
sourceTabBar.appendChild(allSourceBtn);
sourceNames.forEach(src => {{
  const btn = document.createElement('button');
  const n = sourceData[src].reduce((s,b) => s+b.n, 0);
  btn.textContent = src + ' (' + n.toLocaleString() + ')';
  btn.onclick = () => {{
    document.querySelectorAll('#sourceTabBar button').forEach(b => b.className = '');
    btn.className = 'active';
    renderSourceChart([src]);
  }};
  sourceTabBar.appendChild(btn);
}});
renderSourceChart(sourceNames);

// Category chart
let categoryChart = null;
const catNames = Object.keys(categoryData).sort((a,b) => {{
  const na = categoryData[a].reduce((s,b) => s+b.n, 0);
  const nb = categoryData[b].reduce((s,b) => s+b.n, 0);
  return nb - na;
}});

function renderCategoryChart(selectedCats) {{
  const ctx = document.getElementById('categoryChart');
  if (categoryChart) categoryChart.destroy();
  const datasets = selectedCats.map((cat, i) => ({{
    label: cat + ' (n=' + categoryData[cat].reduce((s,b) => s+b.n, 0).toLocaleString() + ')',
    data: calDataToPoints(categoryData[cat]),
    borderColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
    backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] + '33',
    borderWidth: 2.5,
    pointRadius: 5,
    showLine: true,
    tension: 0.1,
    fill: false,
  }}));
  categoryChart = makeCalibrationChart(ctx, datasets);
}}

// Category tabs
const catTabBar = document.getElementById('categoryTabBar');
const allCatBtn = document.createElement('button');
allCatBtn.textContent = 'All Categories';
allCatBtn.className = 'active';
allCatBtn.onclick = () => {{
  document.querySelectorAll('#categoryTabBar button').forEach(b => b.className = '');
  allCatBtn.className = 'active';
  renderCategoryChart(catNames.slice(0, 6));
}};
catTabBar.appendChild(allCatBtn);
catNames.forEach(cat => {{
  const btn = document.createElement('button');
  const n = categoryData[cat].reduce((s,b) => s+b.n, 0);
  btn.textContent = cat + ' (' + n.toLocaleString() + ')';
  btn.onclick = () => {{
    document.querySelectorAll('#categoryTabBar button').forEach(b => b.className = '');
    btn.className = 'active';
    renderCategoryChart([cat]);
  }};
  catTabBar.appendChild(btn);
}});
renderCategoryChart(catNames.slice(0, 6));

// Category cards
const cardsContainer = document.getElementById('categoryCards');
catNames.forEach((cat, i) => {{
  const cal = categoryData[cat];
  const n = cal.reduce((s,b) => s+b.n, 0);
  const brier = catStats[cat]?.brier;
  const card = document.createElement('div');
  card.className = 'category-card';
  card.innerHTML = `
    <h3>${{cat}} <span class="n-label">${{n.toLocaleString()}} outcomes${{brier != null ? ' · Brier: ' + brier : ''}}</span></h3>
    <div class="chart-container small"><canvas id="catChart${{i}}"></canvas></div>
  `;
  cardsContainer.appendChild(card);
  const ctx = card.querySelector('canvas');
  makeCalibrationChart(ctx, [{{
    label: cat,
    data: calDataToPoints(cal),
    borderColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
    backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] + '33',
    borderWidth: 2.5,
    pointRadius: 5,
    showLine: true,
    tension: 0.1,
    fill: false,
  }}]);
}});

// Commentary
const commentary = document.getElementById('commentary');
const meanErr = {stats['mean_cal_error']:.1f};
const brier = {stats['brier']};
const nOutcomes = {stats['total_outcomes']};

let html = '<p>';
if (meanErr < 3) {{
  html += '<strong>Verdict: Markets are well-calibrated.</strong> With a mean calibration error of ' + meanErr.toFixed(1) + 'pp, these prediction markets are doing what they claim — events predicted at X% really do happen about X% of the time.';
}} else if (meanErr < 6) {{
  html += '<strong>Verdict: Markets are reasonably calibrated, with room for improvement.</strong> Mean error of ' + meanErr.toFixed(1) + 'pp suggests the broad strokes are right, but there are systematic biases worth investigating.';
}} else {{
  html += '<strong>Verdict: Markets show notable calibration issues.</strong> A mean error of ' + meanErr.toFixed(1) + 'pp indicates systematic over- or under-confidence in certain probability ranges.';
}}
html += '</p>';

html += '<p>The Brier score of ' + brier + ' ';
if (brier < 0.10) {{
  html += 'is excellent — well below the 0.25 coin-flip baseline and competitive with the best forecasting systems studied in the academic literature.';
}} else if (brier < 0.15) {{
  html += 'is good — meaningfully better than random guessing (0.25), indicating genuine predictive signal.';
}} else if (brier < 0.20) {{
  html += 'is moderate — better than chance but with meaningful room for improvement. This is typical for markets with thin liquidity or long time horizons.';
}} else {{
  html += 'suggests limited predictive value above random guessing. This could indicate thin markets, poor opening prices, or fundamental unpredictability in the domains covered.';
}}
html += '</p>';

// Per-category commentary
html += '<h3 style="margin-top: 1rem;">Category Insights</h3><ul>';
catNames.forEach(cat => {{
  const cal = categoryData[cat];
  const n = cal.reduce((s,b) => s+b.n, 0);
  if (n < 20) return;
  const errors = cal.map(b => Math.abs(b.calibration_error));
  const avgErr = errors.reduce((a,b) => a+b, 0) / errors.length;
  const b = catStats[cat]?.brier;
  let note = '';
  if (avgErr < 3) note = 'very well-calibrated';
  else if (avgErr < 6) note = 'reasonably calibrated';
  else if (avgErr < 10) note = 'has notable calibration gaps';
  else note = 'shows significant calibration issues';
  html += `<li><strong>${{cat}}</strong> (n=${{n.toLocaleString()}}): ${{note}} (avg |error| = ${{avgErr.toFixed(1)}}pp${{b != null ? ', Brier = ' + b : ''}})</li>`;
}});
html += '</ul>';

// Favorite-longshot bias
const lowBuckets = overallData.filter(b => b.midpoint <= 15);
const highBuckets = overallData.filter(b => b.midpoint >= 85);
if (lowBuckets.length > 0 && highBuckets.length > 0) {{
  const lowErr = lowBuckets.reduce((s,b) => s + b.calibration_error, 0) / lowBuckets.length;
  const highErr = highBuckets.reduce((s,b) => s + b.calibration_error, 0) / highBuckets.length;
  html += '<h3 style="margin-top: 1rem;">Favorite-Longshot Bias</h3><p>';
  if (lowErr > 2) {{
    html += 'Longshots (0-15%) win more often than predicted (+' + lowErr.toFixed(1) + 'pp), consistent with the classic favorite-longshot bias. ';
  }} else if (lowErr < -2) {{
    html += 'Longshots (0-15%) win less often than predicted (' + lowErr.toFixed(1) + 'pp) — an unusual reverse favorite-longshot bias. ';
  }} else {{
    html += 'Longshots (0-15%) are well-calibrated (error: ' + lowErr.toFixed(1) + 'pp). ';
  }}
  if (highErr < -2) {{
    html += 'Favorites (85%+) also show overconfidence (' + highErr.toFixed(1) + 'pp) — they win less often than their prices suggest.';
  }} else if (highErr > 2) {{
    html += 'Favorites (85%+) are underconfident (+' + highErr.toFixed(1) + 'pp) — they win even more often than predicted.';
  }} else {{
    html += 'Favorites (85%+) are well-calibrated (error: ' + highErr.toFixed(1) + 'pp).';
  }}
  html += '</p>';
}}

commentary.innerHTML = html;
</script>
</body>
</html>"""
    return html


def _grade_class(err):
    err = abs(err)
    if err < 3:
        return "grade-A"
    if err < 6:
        return "grade-B"
    if err < 10:
        return "grade-C"
    return "grade-F"


def _grade_label(err):
    err = abs(err)
    if err < 3:
        return "Excellent calibration"
    if err < 6:
        return "Good calibration"
    if err < 10:
        return "Fair calibration"
    return "Needs improvement"


def _table_row(b):
    err = b["calibration_error"]
    if abs(err) < 2:
        cls = "error-ok"
    elif err > 0:
        cls = "error-pos"
    else:
        cls = "error-neg"
    sign = "+" if err > 0 else ""
    return f"""<tr>
      <td>{b['bucket']}</td>
      <td class="num">{b['n']:,}</td>
      <td class="num">{b['winners']:,}</td>
      <td class="num">{b['avg_opening_prob']}%</td>
      <td class="num">{b['actual_win_rate']}%</td>
      <td class="num {cls}">{sign}{err}pp</td>
    </tr>"""


def main():
    print("Connecting to database...")
    db_url = get_db_url()
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    print("Querying resolved outcomes with opening probabilities...")
    cur.execute(QUERY)
    columns = [desc[0] for desc in cur.description]
    raw_rows = cur.fetchall()
    rows = [dict(zip(columns, row)) for row in raw_rows]

    print(f"  Found {len(rows):,} resolved outcomes")

    # Count distinct markets
    cur.execute("SELECT COUNT(*) FROM futures_markets WHERE status = 'resolved'")
    total_markets = cur.fetchone()[0]

    cur.close()
    conn.close()

    if not rows:
        print("No resolved outcomes with opening probabilities found.")
        sys.exit(1)

    # Overall calibration
    overall_cal = compute_calibration(rows)
    print("\nOverall Calibration:")
    for b in overall_cal:
        sign = "+" if b["calibration_error"] > 0 else ""
        print(f"  {b['bucket']:>8s}  n={b['n']:>6,}  winners={b['winners']:>5,}  "
              f"avg_open={b['avg_opening_prob']:>5.1f}%  actual={b['actual_win_rate']:>5.1f}%  "
              f"error={sign}{b['calibration_error']}pp")

    # By category
    cat_groups = defaultdict(list)
    for row in rows:
        cat = categorize(row)
        cat_groups[cat].append(row)

    category_cals = {}
    for cat in sorted(cat_groups.keys(), key=lambda c: -len(cat_groups[c])):
        cal = compute_calibration(cat_groups[cat])
        if len(cat_groups[cat]) >= 10:
            category_cals[cat] = cal
            print(f"\n{cat} ({len(cat_groups[cat]):,} outcomes):")
            for b in cal:
                sign = "+" if b["calibration_error"] > 0 else ""
                print(f"  {b['bucket']:>8s}  n={b['n']:>5,}  actual={b['actual_win_rate']:>5.1f}%  error={sign}{b['calibration_error']}pp")

    # By source
    source_groups = defaultdict(list)
    for row in rows:
        source_groups[row["source"]].append(row)

    source_cals = {}
    for src in sorted(source_groups.keys(), key=lambda s: -len(source_groups[s])):
        cal = compute_calibration(source_groups[src])
        if len(source_groups[src]) >= 10:
            source_cals[src] = cal

    # Compute stats
    brier = compute_brier_score(rows)
    mean_cal_error = sum(abs(b["calibration_error"]) for b in overall_cal) / len(overall_cal)
    sources = sorted(source_groups.keys())
    top_cats = ", ".join(
        f"{c} ({len(cat_groups[c]):,})"
        for c in sorted(cat_groups.keys(), key=lambda c: -len(cat_groups[c]))[:3]
    )

    stats = {
        "total_outcomes": len(rows),
        "total_markets": total_markets,
        "total_winners": sum(1 for r in rows if r["is_winner"]),
        "brier": brier,
        "mean_cal_error": mean_cal_error,
        "n_sources": len(sources),
        "sources": sources,
        "n_categories": len(category_cals),
        "top_categories": top_cats,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    print(f"\nBrier Score: {brier}")
    print(f"Mean Calibration Error: {mean_cal_error:.1f}pp")

    # Generate HTML
    html = generate_html(overall_cal, category_cals, source_cals, stats, rows)

    output_path = os.path.join(os.path.dirname(__file__), "..", "..", "calibration_report.html")
    output_path = os.path.abspath(output_path)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"\nReport written to: {output_path}")
    print(f"Open with: open {output_path}")


if __name__ == "__main__":
    main()
