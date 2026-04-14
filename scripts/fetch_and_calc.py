"""
fetch_and_calc.py
XAUUSD H1/H4 ADXスコア計算 -> data/scores.json に追記
"""

import os
import json
import math
import requests
from datetime import datetime, timezone, timedelta

# -- 設定 --
API_KEY   = os.environ["TWELVE_DATA_API_KEY"]
SYMBOL    = "XAU/USD"
DATA_PATH = "data/scores.json"

ADX_PERIOD_H1 = 28
ADX_PERIOD_H4 = 30

# barsは多めに取る（ADX計算でperiod*3本消費するため）
H1_BARS = 300
H4_BARS = 120

JST = timezone(timedelta(hours=9))


# -- Twelve Data から時系列取得 --
def fetch_ohlcv(interval, outputsize):
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


# -- Wilder's ADX 計算 --
def calc_adx(bars, period):
    """
    Wilder's True ADX 実装（MT5準拠）

    Wilder平滑化の初期値はperiod本の単純平均（合計ではなく平均）。
    TR/PDM/MDMは全て平均ベースで統一するため、DI計算も正規化される。

    bars: [{"datetime":..., "high":..., "low":..., "close":...}, ...]
    return: [{"datetime":..., "adx":..., "plus_di":..., "minus_di":...}, ...]
    """
    n = len(bars)

    # Step1: TR / +DM / -DM（bars[1]..bars[n-1]）
    tr_arr  = []
    pdm_arr = []
    mdm_arr = []
    dts     = [b["datetime"] for b in bars]

    for i in range(1, n):
        h  = float(bars[i]["high"])
        l  = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        ph = float(bars[i - 1]["high"])
        pl = float(bars[i - 1]["low"])

        tr   = max(h - l, abs(h - pc), abs(l - pc))
        up   = h  - ph
        down = pl - l

        pdm = max(up,   0.0) if up   > down else 0.0
        mdm = max(down, 0.0) if down > up   else 0.0

        tr_arr.append(tr)
        pdm_arr.append(pdm)
        mdm_arr.append(mdm)

    # tr_arr[i] は bars[i+1] に対応（i=0..n-2）

    # Step2: Wilder平滑化（初期値 = period本の単純平均）
    def wilder_smooth(lst, p):
        """
        戻り値 out[k] はインデックス k+p-1 までを使った Wilder 平均値。
        bars インデックスで: out[k] の対応 bars = k + p
        """
        if len(lst) < p:
            raise ValueError(
                f"データ不足: 配列長 {len(lst)} < period {p}。"
                f"H1_BARS/H4_BARS を増やしてください。"
            )
        # 初期値は単純平均（合計ではない）
        init = sum(lst[:p]) / p
        out  = [init]
        for v in lst[p:]:
            # Wilder: out[k] = out[k-1] * (p-1)/p + v/p
            out.append(out[-1] * (p - 1) / p + v / p)
        return out

    atr_s = wilder_smooth(tr_arr,  period)
    pdm_s = wilder_smooth(pdm_arr, period)
    mdm_s = wilder_smooth(mdm_arr, period)

    # atr_s の長さ = len(tr_arr) - period + 1 = n - period

    # Step3: +DI / -DI / DX
    dx_arr  = []
    dt_arr  = []
    pdi_arr = []
    mdi_arr = []

    for k in range(len(atr_s)):
        bar_idx = k + period   # 対応する bars のインデックス（最大 n-1 で安全）
        atr = atr_s[k]
        if atr == 0:
            continue

        pdi = 100.0 * pdm_s[k] / atr
        mdi = 100.0 * mdm_s[k] / atr
        dx  = 100.0 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0

        dx_arr.append(dx)
        dt_arr.append(dts[bar_idx])
        pdi_arr.append(pdi)
        mdi_arr.append(mdi)

    # Step4: DX を再度 Wilder 平滑化 -> ADX（0〜100 に収まる）
    if len(dx_arr) < period:
        raise ValueError(
            f"DX配列({len(dx_arr)}) < period({period})。"
            f"bars を増やしてください（現在 {n} 本）。"
        )

    adx_s = wilder_smooth(dx_arr, period)

    out = []
    for m, adx_val in enumerate(adx_s):
        src = m + period - 1   # dt_arr のインデックス
        out.append({
            "datetime":  dt_arr[src],
            "adx":       adx_val,
            "plus_di":   pdi_arr[src],
            "minus_di":  mdi_arr[src],
        })

    return out


# -- ADXスコア計算（設計書準拠） --
def adx_score(h1_avg_adx, h4_pct_above20, h4_pct_above30):
    h1_norm = max(0.0, min(100.0, (h1_avg_adx - 10) / 30 * 100))
    a     = max(0.1, h1_norm)
    b     = max(0.1, h4_pct_above20)
    base  = math.sqrt(a * b) * 0.85
    bonus = 1.0 + (h4_pct_above30 / 100) * 0.5
    return round(min(100.0, base * bonus), 1)


# -- 直近5営業日分のスコアを計算 --
def calc_scores_5days(h1_adx_series, h4_adx_series):
    # H4を日付でグループ化
    h4_by_date = {}
    for row in h4_adx_series:
        date_str = row["datetime"][:10]
        h4_by_date.setdefault(date_str, []).append(row["adx"])

    # H1を日付でグループ化
    h1_by_date = {}
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
            "date":        date_str,
            "h1_avg_adx":  round(h1_avg, 2),
            "h4_pct20":    round(h4_pct20, 1),
            "h4_pct30":    round(h4_pct30, 1),
            "score":       score,
        })

    return scores


# -- scores.json 読み書き --
def load_scores():
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_scores(records):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    seen = {}
    for r in records:
        seen[r["date"]] = r
    merged = sorted(seen.values(), key=lambda x: x["date"])
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[OK] scores.json に {len(merged)} 件保存")


# -- メイン --
def main():
    print("=== fetch_and_calc.py 開始 ===")
    print(f"実行時刻: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")

    print("H1データ取得中...")
    h1_bars = fetch_ohlcv("1h", H1_BARS)
    print(f"  -> {len(h1_bars)} 本取得")

    print("H4データ取得中...")
    h4_bars = fetch_ohlcv("4h", H4_BARS)
    print(f"  -> {len(h4_bars)} 本取得")

    print("ADX計算中...")
    h1_adx = calc_adx(h1_bars, ADX_PERIOD_H1)
    h4_adx = calc_adx(h4_bars, ADX_PERIOD_H4)
    print(f"  H1 ADX: {len(h1_adx)} 本 / H4 ADX: {len(h4_adx)} 本")

    print("スコア計算中（直近5営業日）...")
    new_scores = calc_scores_5days(h1_adx, h4_adx)
    for s in new_scores:
        print(
            f"  {s['date']}: score={s['score']}"
            f"  H1avg={s['h1_avg_adx']}"
            f"  H4_20={s['h4_pct20']}%"
            f"  H4_30={s['h4_pct30']}%"
        )

    existing = load_scores()
    save_scores(existing + new_scores)
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
