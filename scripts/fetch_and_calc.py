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
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol":     SYMBOL,
        "interval":   interval,
        "outputsize": outputsize,
        "apikey":     API_KEY,
        "order":      "ASC",   # 古い順
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "values" not in data:
        raise ValueError(f"API error: {data}")
    return data["values"]   # list of {datetime, open, high, low, close}


# ── Wilder's ADX 計算 ─────────────────────────────────
def calc_adx(bars: list[dict], period: int) -> list[dict]:
    """
    bars: [{"datetime":..., "high":..., "low":..., "close":...}, ...]
    return: [{"datetime":..., "adx":..., "plus_di":..., "minus_di":...}, ...]
    """
    n = len(bars)
    highs  = [float(b["high"])  for b in bars]
    lows   = [float(b["low"])   for b in bars]
    closes = [float(b["close"]) for b in bars]

    tr_list, pdm_list, mdm_list = [], [], []
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i-1]
        tr  = max(h - l, abs(h - pc), abs(l - pc))
        pdm = max(highs[i] - highs[i-1], 0) if (highs[i] - highs[i-1]) > (lows[i-1] - lows[i]) else 0
        mdm = max(lows[i-1] - lows[i], 0)   if (lows[i-1] - lows[i]) > (highs[i] - highs[i-1]) else 0
        tr_list.append(tr)
        pdm_list.append(pdm)
        mdm_list.append(mdm)

    # Wilder smoothing（最初のperiod本は単純平均）
    def wilder(lst, p):
        out = [None] * p
        out.append(sum(lst[:p]))  # 初期値
        for v in lst[p:]:
            out.append(out[-1] - out[-1] / p + v)
        return out

    atr_w  = wilder(tr_list,  period)
    pdm_w  = wilder(pdm_list, period)
    mdm_w  = wilder(mdm_list, period)

    result = []
    for i in range(len(atr_w)):
        if atr_w[i] is None or atr_w[i] == 0:
            continue
        pdi = 100 * pdm_w[i] / atr_w[i]
        mdi = 100 * mdm_w[i] / atr_w[i]
        dx  = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0
        result.append({
            "datetime":  bars[i + 1]["datetime"],   # +1: tr_listはi=1から
            "adx":       dx,
            "plus_di":   pdi,
            "minus_di":  mdi,
        })

    # ADX = Wilderスムージングの DX
    # 簡易実装: DXをそのまま返す（本来はDXをさらにWilderする）
    # ※より正確にするならDXリストをさらにwilder()に通す
    dx_list = [r["adx"] for r in result]
    adx_w   = wilder(dx_list, period)

    out = []
    for i, r in enumerate(result):
        if adx_w[i] is None:
            continue
        out.append({
            "datetime":  r["datetime"],
            "adx":       adx_w[i],
            "plus_di":   r["plus_di"],
            "minus_di":  r["minus_di"],
        })
    return out


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
    """
    H1 ADX: 1時間足の直近5営業日ごとに週平均ADXを算出
    H4 ADX: H4足の各日でADX≥20/≥30の割合を算出
    ※ "1日" = UTC 00:00〜23:59 の区切り
    """

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


# ── scores.json 読み書き ──────────────────────────────
def load_scores() -> list[dict]:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_scores(records: list[dict]):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    # date をキーに重複排除（新しいものを優先）
    seen = {}
    for r in records:
        seen[r["date"]] = r
    merged = sorted(seen.values(), key=lambda x: x["date"])
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[OK] scores.json に {len(merged)} 件保存")


# ── メイン ────────────────────────────────────────────
def main():
    print("=== fetch_and_calc.py 開始 ===")
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    print(f"実行時刻: {now_jst}")

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


if __name__ == "__main__":
    main()

