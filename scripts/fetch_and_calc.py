"""
fetch_and_calc.py v4
XAUUSD H1/H4 ADXスコア計算 → data/scores.json に追記

【ADX実装】MT5 / TradingView と一致する正確なWilder ADX
  - TR/+DM/-DM はWilder合計型平滑（初期値=period本の単純合計）
  - ADX はDXをEMA型Wilder平滑（初期値=period本のDXの平均）
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

# period×4以上を確保（ウォームアップ分）
H1_BARS = 300
H4_BARS = 150

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


# ── Wilder's ADX（MT5 / TradingView 準拠）────────────
def calc_adx(bars: list[dict], period: int) -> list[dict]:
    """
    正確なWilder ADX計算。

    TR/+DM/-DM の平滑化:
      初期値 = sum(lst[0:period])  ← Wilderオリジナル（合計型）
      以降   = S - S/period + val

    ADX（DXの平滑化）:
      初期値 = mean(DX[0:period])  ← EMA型
      以降   = (S*(period-1) + val) / period
    """
    n = len(bars)
    H = [float(b["high"])  for b in bars]
    L = [float(b["low"])   for b in bars]
    C = [float(b["close"]) for b in bars]
    D = [b["datetime"]     for b in bars]

    if n < period * 3:
        raise ValueError(f"バー数不足: {n}本（{period*3}本以上必要）")

    # Step1: 生のTR / +DM / -DM（長さ n-1）
    TR, PDM, MDM = [], [], []
    for i in range(1, n):
        tr  = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
        up  = H[i] - H[i-1]
        dn  = L[i-1] - L[i]
        pdm = up if (up > dn and up > 0) else 0.0
        mdm = dn if (dn > up and dn > 0) else 0.0
        TR.append(tr); PDM.append(pdm); MDM.append(mdm)

    # Step2: Wilder合計型平滑（TR / +DM / -DM 用）
    def wilder_sum(lst, p):
        """初期値=合計、以降= S - S/p + val（MT5標準）"""
        if len(lst) < p:
            return [None] * len(lst)
        result = [None] * (p - 1)
        s = sum(lst[:p])
        result.append(s)
        for v in lst[p:]:
            s = s - s / p + v
            result.append(s)
        return result

    sTR  = wilder_sum(TR,  period)
    sPDM = wilder_sum(PDM, period)
    sMDM = wilder_sum(MDM, period)

    # Step3: +DI / -DI → DX
    dx_list, dx_dt, dx_pdi, dx_mdi = [], [], [], []
    for i in range(len(sTR)):
        if sTR[i] is None or sTR[i] <= 0:
            continue
        pdi   = 100.0 * sPDM[i] / sTR[i]
        mdi   = 100.0 * sMDM[i] / sTR[i]
        denom = pdi + mdi
        dx    = 100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0
        dx_list.append(dx)
        dx_dt.append(D[i + 1])   # TR[i] は bars[i+1] に対応
        dx_pdi.append(pdi)
        dx_mdi.append(mdi)

    if len(dx_list) < period:
        raise ValueError(f"DX数不足: {len(dx_list)}本")

    # Step4: ADX = DXをEMA型Wilder平滑（初期値=平均）
    def wilder_ema(lst, p):
        """初期値=平均、以降= (S*(p-1) + val) / p（ADX標準）"""
        if len(lst) < p:
            return [None] * len(lst)
        result = [None] * (p - 1)
        s = sum(lst[:p]) / p
        result.append(s)
        for v in lst[p:]:
            s = (s * (p - 1) + v) / p
            result.append(s)
        return result

    adx_list = wilder_ema(dx_list, period)

    # Step5: 結果まとめ
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


# ── ADXスコア計算（設計書準拠）──────────────────────
def adx_score(h1_avg_adx: float, h4_pct_above20: float, h4_pct_above30: float) -> float:
    h1_norm = max(0.0, min(100.0, (h1_avg_adx - 10) / 30 * 100))
    # フロア5.0: H4_20=0%でもスコアが極端に潰れないようにする
    # （設計書の期待値には影響なし。H4_20が低い弱相場を適切に表現）
    a     = max(5.0, h1_norm)
    b     = max(5.0, h4_pct_above20)
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

    def is_weekday(date_str: str) -> bool:
        """土日を除外（月=0 〜 金=4）"""
        return datetime.strptime(date_str, "%Y-%m-%d").weekday() < 5

    all_dates = sorted(
        d for d in set(h4_by_date.keys()) & set(h1_by_date.keys())
        if is_weekday(d)
    )
    recent_5  = all_dates[-5:]

    scores = []
    for date_str in recent_5:
        h1_vals = h1_by_date.get(date_str, [])
        h4_vals = h4_by_date.get(date_str, [])
        if not h1_vals or not h4_vals:
            continue

        # H4バー本数チェック
        # 通常: 23h稼働 → 5〜6本。3本未満はクローズ日・祝日短縮のデータ不完全
        if len(h4_vals) < 3:
            print(f"  [SKIP] H4バー不足: {date_str} ({len(h4_vals)}本)")
            continue

        # H1バー本数チェック
        # 通常: 23本。10本未満はデータ不完全
        if len(h1_vals) < 10:
            print(f"  [SKIP] H1バー不足: {date_str} ({len(h1_vals)}本)")
            continue

        h1_avg   = sum(h1_vals) / len(h1_vals)
        h4_pct20 = 100 * sum(1 for v in h4_vals if v >= 20) / len(h4_vals)
        h4_pct30 = 100 * sum(1 for v in h4_vals if v >= 30) / len(h4_vals)
        score    = adx_score(h1_avg, h4_pct20, h4_pct30)

        scores.append({
            "date":        date_str,
            "symbol":      "XAUUSD",
            "h1_avg_adx":  round(h1_avg, 2),
            "h4_pct20":    round(h4_pct20, 1),
            "h4_pct30":    round(h4_pct30, 1),
            "score":       score,
            "h1_bars":     len(h1_vals),   # デバッグ用
            "h4_bars":     len(h4_vals),   # デバッグ用
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
        # symbolフィールドがない古いデータを補完
        if "symbol" not in r:
            r["symbol"] = "XAUUSD"
        # 異常値除去（h1_avg_adx > 100 は明らかにバグデータ）
        if r.get("h1_avg_adx", 0) > 100:
            print(f"  [SKIP] 異常データ除去: {r['date']} h1_avg_adx={r['h1_avg_adx']}")
            continue
        # 土日データを除去
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        if dt.weekday() >= 5:
            print(f"  [SKIP] 土日データ除去: {r['date']} ({['月','火','水','木','金','土','日'][dt.weekday()]})")
            continue
        key = f"{r['date']}_{r['symbol']}"
        seen[key] = r
    merged = sorted(seen.values(), key=lambda x: x["date"])
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[OK] scores.json に {len(merged)} 件保存")


# ── 妥当性チェック ────────────────────────────────────
def validate_adx(series: list[dict], label: str):
    vals = [r["adx"] for r in series[-20:]]
    avg  = sum(vals) / len(vals)
    mn, mx = min(vals), max(vals)
    print(f"  {label}: 直近20本 avg={avg:.2f} min={mn:.2f} max={mx:.2f}")
    if avg > 100:
        raise ValueError(
            f"[ERROR] {label} ADX平均値={avg:.2f} が異常です（100超）。"
            "バー数不足かAPIデータ異常の可能性があります。"
        )


# ── メイン ───────────────────────────────────────────
def main():
    print("=== fetch_and_calc.py v4 開始 ===")
    print(f"実行時刻: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")

    print(f"H1データ取得中... ({H1_BARS}本)")
    h1_bars = fetch_ohlcv("1h", H1_BARS)
    print(f"  → {len(h1_bars)} 本取得")

    print(f"H4データ取得中... ({H4_BARS}本)")
    h4_bars = fetch_ohlcv("4h", H4_BARS)
    print(f"  → {len(h4_bars)} 本取得")

    print("ADX計算中...")
    h1_adx = calc_adx(h1_bars, ADX_PERIOD_H1)
    h4_adx = calc_adx(h4_bars, ADX_PERIOD_H4)
    print(f"  H1 ADX: {len(h1_adx)}本 / H4 ADX: {len(h4_adx)}本")

    validate_adx(h1_adx, "H1(28)")
    validate_adx(h4_adx, "H4(30)")

    print("スコア計算中（直近5営業日）...")
    new_scores = calc_scores_5days(h1_adx, h4_adx)

    if not new_scores:
        print("[WARN] スコアが空です")
        return

    for s in new_scores:
        print(f"  {s['date']}: score={s['score']:5.1f}  "
              f"H1avg={s['h1_avg_adx']:5.2f}  "
              f"H4_20={s['h4_pct20']:5.1f}%  "
              f"H4_30={s['h4_pct30']:5.1f}%")

    existing = load_scores()
    save_scores(existing + new_scores)
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
