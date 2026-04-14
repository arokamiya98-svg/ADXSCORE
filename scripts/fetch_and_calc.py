"""
fetch_and_calc.py
XAUUSD H1/H4 ADXスコア計算 → data/scores.json に追記
"""

import os
import json
import math
import requests
from datetime import datetime, timezone, timedelta

# ── 設定 ──────────────────────────────────────────────
API_KEY   = os.environ["TWELVE_DATA_API_KEY"]
SYMBOL    = "XAU/USD"
DATA_PATH = "data/scores.json"

ADX_PERIOD_H1 = 28
ADX_PERIOD_H4 = 30

H1_BARS = 200
H4_BARS = 60

JST = timezone(timedelta(hours=9))


# ── Twelve Data から時系列取得 ────────────────────────
def fetch_ohlcv(interval: str, outputsize: int) -> list[dict]:
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol":     SYMBOL,
        "interval":   interval,
        "outputsize": outputsize,
        "apikey":     API_KEY,
        "order":      "ASC",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "values" not in data:
        raise ValueError(f"API error: {data}")
    return data["values"]


# ── Wilder's ADX 計算（修正版） ───────────────────────
def calc_adx(bars: list[dict], period: int) -> list[dict]:
    n = len(bars)
    highs  = [float(b["high"])  for b in bars]
    lows   = [float(b["low"])   for b in bars]
    closes = [float(b["close"]) for b in bars]

    # i=1始まりで TR / +DM / -DM を計算
    tr_list, pdm_list, mdm_list, dt_list = [], [], [], []
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr   = max(h - l, abs(h - pc), abs(l - pc))
        up   = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        pdm  = up   if (up > down and up > 0)   else 0.0
        mdm  = down if (down > up and down > 0) else 0.0
        tr_list.append(tr)
        pdm_list.append(pdm)
        mdm_list.append(mdm)
        dt_list.append(bars[i]["datetime"])  # bars[i] のみ使用（i+1ではない）

    # Wilder平滑化
    def wilder(lst, p):
        if len(lst) < p:
            return [None] * len(lst)
        out = [None] * (p - 1)
        out.append(sum(lst[:p]))
        for v in lst[p:]:
            out.append(out[-1] - out[-1] / p + v)
        return out

    atr_w = wilder(tr_list,  period)
    pdm_w = wilder(pdm_list, period)
    mdm_w = wilder(mdm_list, period)

    # DX リスト作成
    dx_list, dx_dt, dx_pdi, dx_mdi = [], [], [], []
    for i in range(len(atr_w)):
        if atr_w[i] is None or atr_w[i] == 0:
            continue
        pdi = 100 * pdm_w[i] / atr_w[i]
        mdi = 100 * mdm_w[i] / atr_w[i]
        dx  = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
        dx_list.append(dx)
        dx_dt.append(dt_list[i])
        dx_pdi.append(pdi)
        dx_mdi.append(mdi)

    # DX を Wilder平滑化 → ADX
    adx_w = wilder(dx_list, period)

    out = []
    for i, adx_val in enumerate(adx_w):
        if adx_val is None:
            continue
        out.append({
            "datetime":  dx_dt[i],
            "adx":       adx_val,
            "plus_di":   dx_pdi[i],
            "minus_di":  dx_mdi[i],
        })

    return out


# ── ADXスコア計算 ────────────────────────────────────
def adx_score(h1_avg_adx: float, h4_pct_above20: float, h4_pct_above30: float) -> float:
    h1_norm = max(0.0, min(100.0, (h1_avg_adx - 10) / 30 * 100))
    a     = max(0.1, h1_norm)
    b     = max(0.1, h4_pct_above20)
    base  = math.sqrt(a * b) * 0.85
    bonus = 1.0 + (h4_pct_above30 / 100) * 0.5
    return round(min(100.0, base * bonus), 1)


# ── 直近5営業日スコア計算 ────────────────────────────
def calc_scores_5days(h1_adx_series: list[dict], h4_adx_series: list[dict]) -> list[dict]:
    h4_by_date: dict[str, list[float]] = {}
    for row in h4_adx_series:
        date_str = row["datetime"][:10]
        h4_by_date.setdefault(date_str, []).append(row["adx"])

    h1_by_date: dict[str, list[float]] = {}
    for row in h1_adx_series:
        date_str = row["datetime"][:10]
        h1_by_date.setdefault(date_str, []).append(row["adx"])

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
            "date":       date_str,
            "symbol":     "XAUUSD",   # 将来の複数銘柄対応用
            "h1_avg_adx": round(h1_avg, 2),
            "h4_pct20":   round(h4_pct20, 1),
            "h4_pct30":   round(h4_pct30, 1),
            "score":      score,
        })

    return scores


# ── scores.json 読み書き ─────────────────────────────
def load_scores() -> list[dict]:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_scores(records: list[dict]):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    seen = {}
    for r in records:
        seen[r["date"]] = r
    merged = sorted(seen.values(), key=lambda x: x["date"])
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[OK] scores.json に {len(merged)} 件保存")


# ── メイン ───────────────────────────────────────────
def main():
    print("=== fetch_and_calc.py 開始 ===")
    print(f"実行時刻: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")

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

    if not h1_adx or not h4_adx:
        raise RuntimeError("ADX計算結果が空です。バー数が不足しています。")

    print("スコア計算中（直近5営業日）...")
    new_scores = calc_scores_5days(h1_adx, h4_adx)
    for s in new_scores:
        print(f"  {s['date']}: score={s['score']}  H1avg={s['h1_avg_adx']}  "
              f"H4_20={s['h4_pct20']}%  H4_30={s['h4_pct30']}%")

    existing = load_scores()
    save_scores(existing + new_scores)
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
