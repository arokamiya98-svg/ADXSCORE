"""
initialize_history.py
2025-01-01 から今日まで の日次ADXスコアを一括取得・計算して
data/scores.json に書き込む（初期化用・1回実行）

実行方法:
  python scripts/initialize_history.py

Twelve Data 無料枠消費目安:
  H1: 約300本/月 × 15ヶ月 = 4500本 → 1リクエスト（outputsize=5000で十分）
  H4: 約90本/月  × 15ヶ月 = 1350本 → 1リクエスト
  合計2リクエスト（無料枠800/日に対して余裕）
"""

import os
import json
import math
import time
import requests
from datetime import datetime, timezone, timedelta

# ── 設定 ──────────────────────────────────────────────
API_KEY    = os.environ["TWELVE_DATA_API_KEY"]
SYMBOL     = "XAU/USD"
DATA_PATH  = "data/scores.json"
START_DATE = "2025-01-01"   # 取得開始日

ADX_PERIOD_H1 = 28
ADX_PERIOD_H4 = 30

# 5000本でH1約7ヶ月、H4約2.3年 → 2025年〜は余裕でカバー
H1_OUTPUTSIZE = 5000
H4_OUTPUTSIZE = 5000

JST = timezone(timedelta(hours=9))


# ── Twelve Data 取得（start_date指定版）─────────────
def fetch_ohlcv_full(interval: str, outputsize: int) -> list[dict]:
    """
    outputsize=5000 で最新から遡って取得。
    Twelve Dataは古い順（ASC）で返すよう指定。
    """
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol":     SYMBOL,
        "interval":   interval,
        "outputsize": outputsize,
        "apikey":     API_KEY,
        "order":      "ASC",
    }
    print(f"  APIリクエスト: {interval} {outputsize}本...")
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if "values" not in data:
        raise ValueError(f"API error: {data}")
    bars = data["values"]
    print(f"  → {len(bars)} 本取得 ({bars[0]['datetime'][:10]} 〜 {bars[-1]['datetime'][:10]})")
    return bars


# ── Wilder ADX（fetch_and_calc.py と同一実装）────────
def calc_adx(bars: list[dict], period: int) -> list[dict]:
    n = len(bars)
    H = [float(b["high"])  for b in bars]
    L = [float(b["low"])   for b in bars]
    C = [float(b["close"]) for b in bars]
    D = [b["datetime"]     for b in bars]

    TR, PDM, MDM = [], [], []
    for i in range(1, n):
        tr  = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
        up  = H[i] - H[i-1]
        dn  = L[i-1] - L[i]
        pdm = up if (up > dn and up > 0) else 0.0
        mdm = dn if (dn > up and dn > 0) else 0.0
        TR.append(tr); PDM.append(pdm); MDM.append(mdm)

    def wilder_sum(lst, p):
        if len(lst) < p:
            return [None] * len(lst)
        result = [None] * (p - 1)
        s = sum(lst[:p])
        result.append(s)
        for v in lst[p:]:
            s = s - s / p + v
            result.append(s)
        return result

    def wilder_ema(lst, p):
        if len(lst) < p:
            return [None] * len(lst)
        result = [None] * (p - 1)
        s = sum(lst[:p]) / p
        result.append(s)
        for v in lst[p:]:
            s = (s * (p - 1) + v) / p
            result.append(s)
        return result

    sTR  = wilder_sum(TR,  period)
    sPDM = wilder_sum(PDM, period)
    sMDM = wilder_sum(MDM, period)

    dx_list, dx_dt, dx_pdi, dx_mdi = [], [], [], []
    for i in range(len(sTR)):
        if sTR[i] is None or sTR[i] <= 0:
            continue
        pdi   = 100.0 * sPDM[i] / sTR[i]
        mdi   = 100.0 * sMDM[i] / sTR[i]
        denom = pdi + mdi
        dx    = 100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0
        dx_list.append(dx)
        dx_dt.append(D[i + 1])
        dx_pdi.append(pdi)
        dx_mdi.append(mdi)

    adx_list = wilder_ema(dx_list, period)

    out = []
    for i, adx_val in enumerate(adx_list):
        if adx_val is None:
            continue
        out.append({
            "datetime":  dx_dt[i],
            "adx":       round(adx_val, 4),
            "plus_di":   round(dx_pdi[i], 4),
            "minus_di":  round(dx_mdi[i], 4),
        })
    return out


# ── ADXスコア計算 ────────────────────────────────────
def adx_score(h1_avg: float, h4_pct20: float, h4_pct30: float) -> float:
    h1_norm = max(0.0, min(100.0, (h1_avg - 10) / 30 * 100))
    a     = max(0.1, h1_norm)
    b     = max(0.1, h4_pct20)
    base  = math.sqrt(a * b) * 0.85
    bonus = 1.0 + (h4_pct30 / 100) * 0.5
    return round(min(100.0, base * bonus), 1)


# ── 全日程のスコアを計算（平日のみ・START_DATE以降）──
def calc_all_scores(h1_adx: list[dict], h4_adx: list[dict]) -> list[dict]:
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")

    # 日付でグループ化
    h1_by_date: dict[str, list[float]] = {}
    for row in h1_adx:
        d = row["datetime"][:10]
        h1_by_date.setdefault(d, []).append(row["adx"])

    h4_by_date: dict[str, list[float]] = {}
    for row in h4_adx:
        d = row["datetime"][:10]
        h4_by_date.setdefault(d, []).append(row["adx"])

    # START_DATE以降の平日のみ
    all_dates = sorted(
        d for d in set(h1_by_date.keys()) & set(h4_by_date.keys())
        if datetime.strptime(d, "%Y-%m-%d") >= start_dt
        and datetime.strptime(d, "%Y-%m-%d").weekday() < 5  # 月〜金
    )

    print(f"  対象日数: {len(all_dates)} 日（{all_dates[0]} 〜 {all_dates[-1]}）")

    scores = []
    for date_str in all_dates:
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
            "symbol":     "XAUUSD",
            "h1_avg_adx": round(h1_avg, 2),
            "h4_pct20":   round(h4_pct20, 1),
            "h4_pct30":   round(h4_pct30, 1),
            "score":      score,
        })

    return scores


# ── scores.json 上書き保存 ────────────────────────────
def save_scores(records: list[dict]):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

    # 異常値・土日を除去してから保存
    clean = []
    for r in records:
        if r.get("h1_avg_adx", 0) > 100:
            continue
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        if dt.weekday() >= 5:
            continue
        clean.append(r)

    # dateでソート・重複排除
    seen = {}
    for r in clean:
        seen[f"{r['date']}_{r.get('symbol','XAUUSD')}"] = r
    merged = sorted(seen.values(), key=lambda x: x["date"])

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[OK] {len(merged)} 件を {DATA_PATH} に保存")


# ── メイン ───────────────────────────────────────────
def main():
    print("=" * 50)
    print(f"  XAUUSD ADX Score 初期化スクリプト")
    print(f"  取得期間: {START_DATE} 〜 今日")
    print("=" * 50)

    # H1取得
    print("\n[1/4] H1 データ取得...")
    h1_bars = fetch_ohlcv_full("1h", H1_OUTPUTSIZE)

    # レート制限対策（無料枠は8req/分）
    print("  → 8秒待機（APIレート制限対策）")
    time.sleep(8)

    # H4取得
    print("\n[2/4] H4 データ取得...")
    h4_bars = fetch_ohlcv_full("4h", H4_OUTPUTSIZE)

    # ADX計算
    print("\n[3/4] ADX計算中...")
    h1_adx = calc_adx(h1_bars, ADX_PERIOD_H1)
    h4_adx = calc_adx(h4_bars, ADX_PERIOD_H4)
    print(f"  H1 ADX: {len(h1_adx)} 本")
    print(f"  H4 ADX: {len(h4_adx)} 本")

    # ADX値の妥当性チェック
    h1_vals = [r["adx"] for r in h1_adx[-20:]]
    h4_vals = [r["adx"] for r in h4_adx[-20:]]
    print(f"  H1 直近20本 avg={sum(h1_vals)/len(h1_vals):.2f} "
          f"min={min(h1_vals):.2f} max={max(h1_vals):.2f}")
    print(f"  H4 直近20本 avg={sum(h4_vals)/len(h4_vals):.2f} "
          f"min={min(h4_vals):.2f} max={max(h4_vals):.2f}")
    if sum(h1_vals)/len(h1_vals) > 100:
        raise ValueError("H1 ADX値が異常です。計算を中止します。")

    # スコア計算
    print("\n[4/4] スコア計算中...")
    all_scores = calc_all_scores(h1_adx, h4_adx)

    # 結果サマリー表示
    print("\n  --- スコアサンプル（最初・最後の5件）---")
    for r in all_scores[:5] + all_scores[-5:]:
        print(f"  {r['date']}: score={r['score']:5.1f}  "
              f"H1avg={r['h1_avg_adx']:5.2f}  "
              f"H4_20={r['h4_pct20']:5.1f}%  "
              f"H4_30={r['h4_pct30']:5.1f}%")

    # 保存（既存データは完全上書き）
    print(f"\n  scores.json を上書き保存します...")
    save_scores(all_scores)

    print("\n" + "=" * 50)
    print(f"  完了！ {len(all_scores)} 日分のデータを保存しました")
    print(f"  次回からは daily.yml が毎日追記します")
    print("=" * 50)


if __name__ == "__main__":
    main()
