“””
fetch_and_calc.py
XAUUSD H1/H4 ADXスコア計算 → data/scores.json に追記
“””

import os
import json
import math
import requests
from datetime import datetime, timezone, timedelta

# ── 設定 ──────────────────────────────────────────────

API_KEY   = os.environ[“TWELVE_DATA_API_KEY”]
SYMBOL    = “XAU/USD”
DATA_PATH = “data/scores.json”

# ADX期間

ADX_PERIOD_H1 = 28
ADX_PERIOD_H4 = 30

# スコア計算に必要なH1本数（週平均=5日×24本 + バッファ）

H1_BARS   = 200

# H4本数（5日×6本 + バッファ）

H4_BARS   = 60

JST = timezone(timedelta(hours=9))

# ── Twelve Data から時系列取得 ────────────────────────

def fetch_ohlcv(interval: str, outputsize: int) -> list[dict]:
url = “https://api.twelvedata.com/time_series”
params = {
“symbol”:     SYMBOL,
“interval”:   interval,
“outputsize”: outputsize,
“apikey”:     API_KEY,
“order”:      “ASC”,   # 古い順
}
resp = requests.get(url, params=params, timeout=30)
resp.raise_for_status()
data = resp.json()
if “values” not in data:
raise ValueError(f”API error: {data}”)
return data[“values”]   # list of {datetime, open, high, low, close}

# ── Wilder’s ADX 計算 ─────────────────────────────────

def calc_adx(bars: list[dict], period: int) -> list[dict]:
“””
bars: [{“datetime”:…, “high”:…, “low”:…, “close”:…}, …]
return: [{“datetime”:…, “adx”:…, “plus_di”:…, “minus_di”:…}, …]

```
※ Wilder smoothing を正しくインデックス管理するため全面修正。
　 bars[i] (i=1..n-1) に対してTR/DM を計算し、
　 datetimeは bars[i]["datetime"] を直接使う。
"""
n = len(bars)
if n < period * 2 + 2:
    raise ValueError(f"bars数({n})が少なすぎます。period*2+2={period*2+2}本以上必要です")

highs  = [float(b["high"])  for b in bars]
lows   = [float(b["low"])   for b in bars]
closes = [float(b["close"]) for b in bars]
dts    = [b["datetime"]     for b in bars]

# Step1: TR / +DM / -DM を i=1..n-1 で計算
# → インデックスiはbars[i]に対応
tr_arr, pdm_arr, mdm_arr = [], [], []
for i in range(1, n):
    h, l, pc = highs[i], lows[i], closes[i-1]
    up   = highs[i]  - highs[i-1]
    down = lows[i-1] - lows[i]
    tr_arr.append(max(h - l, abs(h - pc), abs(l - pc)))
    pdm_arr.append(max(up,   0) if up   > down else 0)
    mdm_arr.append(max(down, 0) if down > up   else 0)
# tr_arr[k] は bars[k+1] に対応（k=0..n-2）

# Step2: Wilder平滑化（戻り値はNoneなしのリスト、長さ = len(lst)-period+1）
def wilder_smooth(lst: list[float], p: int) -> list[float]:
    """インデックス0がperiod本目の単純平均、以降はWilder更新"""
    result = [sum(lst[:p])]          # 最初のperiod本の合計（Wilderは合計で管理）
    for v in lst[p:]:
        result.append(result[-1] - result[-1] / p + v)
    return result
# wilder_smooth の result[k] は tr_arr[k + period - 1] に対応
# → bars インデックスで言うと bars[k + period]

atr_s  = wilder_smooth(tr_arr,  period)   # len = n - period
pdm_s  = wilder_smooth(pdm_arr, period)
mdm_s  = wilder_smooth(mdm_arr, period)

# Step3: +DI / -DI / DX を計算
dx_arr  = []
dt_arr  = []
pdi_arr = []
mdi_arr = []
for k in range(len(atr_s)):
    bar_idx = k + period   # 対応するbarsのインデックス
    atr = atr_s[k]
    if atr == 0:
        continue
    pdi = 100 * pdm_s[k] / atr
    mdi = 100 * mdm_s[k] / atr
    dx  = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0
    dx_arr.append(dx)
    dt_arr.append(dts[bar_idx])
    pdi_arr.append(pdi)
    mdi_arr.append(mdi)

# Step4: DXをさらにWilder平滑化 → ADX
if len(dx_arr) < period:
    raise ValueError(f"DX配列({len(dx_arr)})がperiod({period})より短い。barsを増やしてください")

adx_s = wilder_smooth(dx_arr, period)
# adx_s[k] は dx_arr[k + period - 1] に対応

out = []
for k, adx_val in enumerate(adx_s):
    src_k = k + period - 1   # dx_arr のインデックス
    out.append({
        "datetime":  dt_arr[src_k],
        "adx":       adx_val,
        "plus_di":   pdi_arr[src_k],
        "minus_di":  mdi_arr[src_k],
    })
return out
```

# ── ADXスコア計算（設計書準拠） ───────────────────────

def adx_score(h1_avg_adx: float, h4_pct_above20: float, h4_pct_above30: float) -> float:
h1_norm = max(0.0, min(100.0, (h1_avg_adx - 10) / 30 * 100))
a    = max(0.1, h1_norm)
b    = max(0.1, h4_pct_above20)
base = math.sqrt(a * b) * 0.85
bonus = 1.0 + (h4_pct_above30 / 100) * 0.5
return round(min(100.0, base * bonus), 1)

# ── 直近5営業日分のスコアを計算 ──────────────────────

def calc_scores_5days(h1_adx_series: list[dict], h4_adx_series: list[dict]) -> list[dict]:
“””
H1 ADX: 1時間足の直近5営業日ごとに週平均ADXを算出
H4 ADX: H4足の各日でADX≥20/≥30の割合を算出
※ “1日” = UTC 00:00〜23:59 の区切り
“””

```
# H4を日付でグループ化
h4_by_date: dict[str, list[float]] = {}
for row in h4_adx_series:
    date_str = row["datetime"][:10]
    h4_by_date.setdefault(date_str, []).append(row["adx"])

# H1を日付でグループ化
h1_by_date: dict[str, list[float]] = {}
for row in h1_adx_series:
    date_str = row["datetime"][:10]
    h1_by_date.setdefault(date_str, []).append(row["adx"])

# 直近5日（H4に含まれる日付で絞る）
all_dates = sorted(set(h4_by_date.keys()) & set(h1_by_date.keys()))
recent_5  = all_dates[-5:]

scores = []
for date_str in recent_5:
    h1_vals = h1_by_date.get(date_str, [])
    h4_vals = h4_by_date.get(date_str, [])
    if not h1_vals or not h4_vals:
        continue

    h1_avg   = sum(h1_vals) / len(h1_vals)
    h4_pct20 = 100 * sum(1 for v in h4_vals if v >= 20) / len(h4_vals)
    h4_pct30 = 100 * sum(1 for v in h4_vals if v >= 30) / len(h4_vals)
    score    = adx_score(h1_avg, h4_pct20, h4_pct30)

    scores.append({
        "date":        date_str,
        "h1_avg_adx":  round(h1_avg, 2),
        "h4_pct20":    round(h4_pct20, 1),
        "h4_pct30":    round(h4_pct30, 1),
        "score":       score,
    })

return scores
```

# ── scores.json 読み書き ──────────────────────────────

def load_scores() -> list[dict]:
if not os.path.exists(DATA_PATH):
return []
with open(DATA_PATH, encoding=“utf-8”) as f:
return json.load(f)

def save_scores(records: list[dict]):
os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
# date をキーに重複排除（新しいものを優先）
seen = {}
for r in records:
seen[r[“date”]] = r
merged = sorted(seen.values(), key=lambda x: x[“date”])
with open(DATA_PATH, “w”, encoding=“utf-8”) as f:
json.dump(merged, f, ensure_ascii=False, indent=2)
print(f”[OK] scores.json に {len(merged)} 件保存”)

# ── メイン ────────────────────────────────────────────

def main():
print(”=== fetch_and_calc.py 開始 ===”)
now_jst = datetime.now(JST).strftime(”%Y-%m-%d %H:%M JST”)
print(f”実行時刻: {now_jst}”)

```
print("H1データ取得中...")
h1_bars = fetch_ohlcv("1h", H1_BARS)
print(f"  → {len(h1_bars)} 本取得")

print("H4データ取得中...")
h4_bars = fetch_ohlcv("4h", H4_BARS)
print(f"  → {len(h4_bars)} 本取得")

print("ADX計算中...")
h1_adx = calc_adx(h1_bars, ADX_PERIOD_H1)
h4_adx = calc_adx(h4_bars, ADX_PERIOD_H4)
print(f"  H1 ADX: {len(h1_adx)} 本 / H4 ADX: {len(h4_adx)} 本")

print("スコア計算中（直近5営業日）...")
new_scores = calc_scores_5days(h1_adx, h4_adx)
for s in new_scores:
    print(f"  {s['date']}: score={s['score']}  H1avg={s['h1_avg_adx']}  H4_20={s['h4_pct20']}%  H4_30={s['h4_pct30']}%")

existing = load_scores()
save_scores(existing + new_scores)
print("=== 完了 ===")
```

if **name** == “**main**”:
main()
