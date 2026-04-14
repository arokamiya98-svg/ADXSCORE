"""
generate_html.py
data/scores.json → docs/index.html を生成（GitHub Pages用）
"""

import json
import os
from datetime import datetime, timezone, timedelta

DATA_PATH = "data/scores.json"
HTML_PATH = "docs/index.html"
JST = timezone(timedelta(hours=9))


def load_scores() -> list[dict]:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def score_to_color(score: float) -> str:
    """スコアに応じたカラー（設計書の感覚値ベース）"""
    if score >= 80:
        return "#00c853"   # 強緑
    elif score >= 60:
        return "#64dd17"   # 黄緑
    elif score >= 40:
        return "#ffd600"   # 黄
    elif score >= 24:
        return "#ff6d00"   # オレンジ
    else:
        return "#d50000"   # 赤（NG）


def score_to_label(score: float) -> str:
    if score >= 80:
        return "最強"
    elif score >= 60:
        return "強い"
    elif score >= 40:
        return "普通"
    elif score >= 24:
        return "様子見"
    else:
        return "NG"


def week_label(date_str: str) -> str:
    """YYYY-MM-DD → 月曜起算の週ラベル（W◯ YYYY）"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    monday = dt - timedelta(days=dt.weekday())
    return f"W{monday.strftime('%m/%d')}"


def group_by_week(records: list[dict]) -> dict[str, list[dict]]:
    weeks: dict[str, list[dict]] = {}
    for r in records:
        wk = week_label(r["date"])
        weeks.setdefault(wk, []).append(r)
    return weeks


def generate_html(records: list[dict]) -> str:
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    recent_5 = records[-5:] if len(records) >= 5 else records
    all_records = records  # 全件（グラフ用）

    # Chart.js用データ（全期間の週平均スコア）
    weeks_grouped = group_by_week(all_records)
    week_keys   = list(weeks_grouped.keys())
    week_avgs   = [
        round(sum(r["score"] for r in v) / len(v), 1)
        for v in weeks_grouped.values()
    ]

    # 直近5日のカード用データ
    cards_html = ""
    for r in recent_5:
        color = score_to_color(r["score"])
        label = score_to_label(r["score"])
        dow   = datetime.strptime(r["date"], "%Y-%m-%d").strftime("%a")
        cards_html += f"""
        <div class="card">
          <div class="date">{r['date']} <span class="dow">{dow}</span></div>
          <div class="score-circle" style="background:{color}">
            <span class="score-num">{r['score']}</span>
            <span class="score-label">{label}</span>
          </div>
          <div class="details">
            <div class="detail-row">
              <span class="detail-key">H1 avg ADX</span>
              <span class="detail-val">{r['h1_avg_adx']}</span>
            </div>
            <div class="detail-row">
              <span class="detail-key">H4 ADX≥20</span>
              <span class="detail-val">{r['h4_pct20']}%</span>
            </div>
            <div class="detail-row">
              <span class="detail-key">H4 ADX≥30</span>
              <span class="detail-val">{r['h4_pct30']}%</span>
            </div>
          </div>
        </div>"""

    # 週次テーブル（全週）
    week_rows = ""
    for wk, recs in weeks_grouped.items():
        avg = sum(r["score"] for r in recs) / len(recs)
        color = score_to_color(avg)
        label = score_to_label(avg)
        days_html = ""
        for r in recs:
            dc = score_to_color(r["score"])
            days_html += f'<span class="day-dot" style="background:{dc}" title="{r["date"]}: {r["score"]}">{r["score"]}</span>'
        week_rows += f"""
        <tr>
          <td class="wk-label">{wk}</td>
          <td><span class="badge" style="background:{color}">{round(avg,1)} {label}</span></td>
          <td class="day-dots">{days_html}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>XAUUSD ADXスコア | Gold Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  :root {{
    --bg: #0d1117;
    --card-bg: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --gold: #d4af37;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 20px;
    max-width: 900px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--gold);
    border-bottom: 1px solid var(--border);
    padding-bottom: 12px;
    margin-bottom: 6px;
  }}
  .updated {{
    font-size: 0.75rem;
    color: var(--muted);
    margin-bottom: 24px;
  }}
  h2 {{
    font-size: 1rem;
    color: var(--muted);
    margin: 28px 0 14px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}

  /* ── 直近5日カード ── */
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 12px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    text-align: center;
  }}
  .date {{ font-size: 0.78rem; color: var(--muted); margin-bottom: 10px; }}
  .dow  {{ font-weight: 700; color: var(--text); }}
  .score-circle {{
    width: 80px; height: 80px;
    border-radius: 50%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    margin: 0 auto 12px;
  }}
  .score-num   {{ font-size: 1.6rem; font-weight: 800; color: #000; line-height: 1; }}
  .score-label {{ font-size: 0.65rem; font-weight: 700; color: #000; margin-top: 2px; }}
  .details {{ text-align: left; }}
  .detail-row {{
    display: flex; justify-content: space-between;
    font-size: 0.72rem;
    border-top: 1px solid var(--border);
    padding: 4px 0;
  }}
  .detail-key {{ color: var(--muted); }}
  .detail-val {{ font-weight: 600; }}

  /* ── 週次グラフ ── */
  .chart-wrap {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }}

  /* ── 週次テーブル ── */
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    font-size: 0.82rem;
    text-align: left;
  }}
  th {{ color: var(--muted); font-weight: 600; background: var(--card-bg); }}
  .wk-label {{ font-weight: 700; color: var(--gold); width: 80px; }}
  .badge {{
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 700;
    color: #000;
    display: inline-block;
  }}
  .day-dots {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .day-dot {{
    width: 32px; height: 32px;
    border-radius: 50%;
    font-size: 0.62rem;
    font-weight: 700;
    color: #000;
    display: flex; align-items: center; justify-content: center;
    cursor: default;
  }}
  footer {{
    margin-top: 40px;
    font-size: 0.72rem;
    color: var(--muted);
    text-align: center;
    border-top: 1px solid var(--border);
    padding-top: 12px;
  }}
</style>
</head>
<body>

<h1>⚡ XAUUSD ADX Score Dashboard</h1>
<div class="updated">最終更新: {now_jst}</div>

<h2>📅 直近5営業日</h2>
<div class="cards">{cards_html}</div>

<h2>📈 週次スコア推移（月曜起算）</h2>
<div class="chart-wrap">
  <canvas id="weekChart" height="100"></canvas>
</div>

<h2>🗂 週次サマリー</h2>
<table>
  <thead><tr><th>週</th><th>平均スコア</th><th>日次ドット</th></tr></thead>
  <tbody>{week_rows}</tbody>
</table>

<footer>
  XAUUSD H1(ADX28) / H4(ADX30) | ADXスコア設計書準拠 | Auto-generated by GitHub Actions
</footer>

<script>
const ctx = document.getElementById('weekChart').getContext('2d');
const weekLabels = {json.dumps(week_keys, ensure_ascii=False)};
const weekAvgs   = {json.dumps(week_avgs)};

const gradient = ctx.createLinearGradient(0, 0, 0, 200);
gradient.addColorStop(0, 'rgba(212,175,55,0.4)');
gradient.addColorStop(1, 'rgba(212,175,55,0)');

new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: weekLabels,
    datasets: [{{
      label: '週平均ADXスコア',
      data: weekAvgs,
      borderColor: '#d4af37',
      backgroundColor: gradient,
      borderWidth: 2.5,
      pointBackgroundColor: weekAvgs.map(v =>
        v >= 80 ? '#00c853' : v >= 60 ? '#64dd17' : v >= 40 ? '#ffd600' : v >= 24 ? '#ff6d00' : '#d50000'
      ),
      pointRadius: 5,
      tension: 0.35,
      fill: true,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.parsed.y}} pt`
        }}
      }}
    }},
    scales: {{
      y: {{
        min: 0, max: 100,
        grid: {{ color: '#21262d' }},
        ticks: {{ color: '#8b949e', stepSize: 20 }}
      }},
      x: {{
        grid: {{ color: '#21262d' }},
        ticks: {{ color: '#8b949e' }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""
    return html


def main():
    print("=== generate_html.py 開始 ===")
    records = load_scores()
    print(f"  {len(records)} 件のスコアを読み込み")
    os.makedirs("docs", exist_ok=True)
    html = generate_html(records)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] {HTML_PATH} 生成完了")


if __name__ == "__main__":
    main()
