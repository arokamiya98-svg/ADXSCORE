"""
fetch_and_calc_v2.py
XAUUSD H1/H4 ADXスコア計算 → data/scores.json に追記

【計算スコア】
  v1スコア: 既存設計（H1avg × H4_pct20/30 幾何平均方式）
  v3スコア: 適正状態評価（vel山型 + ATRフェーズ + ADX強度）

【v3日次近似】
  軸A: H4 vel_pos_pct（当日の H4バー中でvel>0の割合）
  軸B: ATRフェーズ  （当日のATR ratio × 前日比delta）
  軸C: ADX強度      （H4 avg + H1 above20 avg）
"""

import os
import json
import math
import requests
from datetime import datetime, timezone, timedelta
from collections import deque

# ── 設定 ──────────────────────────────────────────────
API_KEY   = os.environ["TWELVE_DATA_API_KEY"]
SYMBOL    = "XAU/USD"
DATA_PATH = "data/scores.json"

ADX_PERIOD_H1  = 28
ADX_PERIOD_H4  = 30
ATR_PERIOD     = 14
H4_VEL_PERIOD  = 5    # H4 vel計算バー数（5本前比較 = 20時間前）
ATR_MED_WEEKS  = 8    # ATR中央値の基準週数（週末ATRを8週分）

# ウォームアップを十分確保
H1_BARS = 400
H4_BARS = 200

JST = timezone(timedelta(hours=9))


# ── Twelve Data 取得 ──────────────────────────────────
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


# ── Wilder ADX ───────────────────────────────────────
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
        TR.append(tr)
        PDM.append(up if (up > dn and up > 0) else 0.0)
        MDM.append(dn if (dn > up and dn > 0) else 0.0)

    def wilder_sum(lst, p):
        if len(lst) < p: return [None] * len(lst)
        result = [None] * (p - 1)
        s = sum(lst[:p]); result.append(s)
        for v in lst[p:]:
            s = s - s / p + v; result.append(s)
        return result

    def wilder_ema(lst, p):
        if len(lst) < p: return [None] * len(lst)
        result = [None] * (p - 1)
        s = sum(lst[:p]) / p; result.append(s)
        for v in lst[p:]:
            s = (s * (p - 1) + v) / p; result.append(s)
        return result

    sTR  = wilder_sum(TR,  period)
    sPDM = wilder_sum(PDM, period)
    sMDM = wilder_sum(MDM, period)

    dx_list, dx_dt, dx_pdi, dx_mdi = [], [], [], []
    for i in range(len(sTR)):
        if sTR[i] is None or sTR[i] <= 0: continue
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
        if adx_val is None: continue
        out.append({
            "datetime": dx_dt[i],
            "adx":      round(adx_val, 4),
            "plus_di":  round(dx_pdi[i], 4),
            "minus_di": round(dx_mdi[i], 4),
        })
    return out


# ── ATR計算（H4）────────────────────────────────────
def calc_atr(bars: list[dict], period: int) -> list[dict]:
    n = len(bars)
    H = [float(b["high"])  for b in bars]
    L = [float(b["low"])   for b in bars]
    C = [float(b["close"]) for b in bars]
    D = [b["datetime"]     for b in bars]

    tr_list = []
    for i in range(1, n):
        tr = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
        tr_list.append((D[i], tr))

    # Wilder EMA
    if len(tr_list) < period:
        return []
    atr_val = sum(t for _, t in tr_list[:period]) / period
    out = []
    for i in range(period, len(tr_list)):
        dt, tr = tr_list[i]
        atr_val = (atr_val * (period - 1) + tr) / period
        out.append({"datetime": dt, "atr": round(atr_val, 4)})
    return out


# ── v1 スコア計算 ────────────────────────────────────
def calc_score_v1(h1_avg: float, h4_pct20: float, h4_pct30: float) -> float:
    h1_norm = max(0.0, min(100.0, (h1_avg - 10) / 30 * 100))
    a     = max(5.0, h1_norm)
    b     = max(5.0, h4_pct20)
    base  = math.sqrt(a * b) * 0.85
    bonus = 1.0 + (h4_pct30 / 100) * 0.5
    return round(min(100.0, base * bonus), 1)


# ── v3 軸スコア計算 ──────────────────────────────────
def axis_a_vel(pos_pct: float) -> float:
    """vel山型スコア（最大40点）"""
    if 60 <= pos_pct <= 80: return 40.0
    if 50 <= pos_pct < 60:  return 33.0
    if 80 < pos_pct <= 90:  return 28.0
    if 40 <= pos_pct < 50:  return 25.0
    if 20 <= pos_pct < 40:  return 22.0
    if pos_pct > 90:        return 15.0
    return 10.0  # <20%


def atr_phase(ratio: float, delta_pct: float) -> str:
    """ATRフェーズ判定"""
    if ratio <= 0: return "N/A"
    if ratio < 0.75:   return "BOTTOM"
    elif ratio < 0.90: return "BOTTOM_TURN" if delta_pct > 5 else "BOTTOM_CONT"
    elif ratio < 1.10:
        if delta_pct > 8:    return "NORMAL_RISE"
        elif delta_pct < -8: return "NORMAL_FALL"
        return "NORMAL_FLAT"
    elif ratio < 1.30: return "HIGH_FALL" if delta_pct < -5 else "HIGH_CONT"
    else:              return "PEAK_FALL" if delta_pct < -8 else "PEAK_CONT"


PHASE_SCORE = {
    "BOTTOM_CONT": 35, "NORMAL_FLAT": 32, "BOTTOM_TURN": 28, "BOTTOM": 25,
    "PEAK_CONT":   18, "NORMAL_FALL": 15, "HIGH_FALL":   13, "PEAK_FALL": 12,
    "HIGH_CONT":    8, "NORMAL_RISE":  5, "N/A":         15,
}


def axis_b_atr(phase: str) -> float:
    """ATRフェーズスコア（最大35点）"""
    return float(PHASE_SCORE.get(phase, 15))


def axis_c_adx(h4_avg: float, h1_s20_avg: float) -> float:
    """ADX強度スコア（最大25点）"""
    h4n = max(0.0, min(1.0, (h4_avg - 15.0) / 25.0)) * 12.0
    h1n = max(0.0, min(1.0, (h1_s20_avg - 20.0) / 20.0)) * 13.0 if h1_s20_avg > 0 else 0.0
    return h4n + h1n


def calc_score_v3(vel_pos_pct: float, phase: str, h4_avg: float, h1_s20_avg: float) -> float:
    """v3総合スコア（最大100点）"""
    a = axis_a_vel(vel_pos_pct)
    b = axis_b_atr(phase)
    c = axis_c_adx(h4_avg, h1_s20_avg)
    return round(min(100.0, a + b + c), 1)


def band_v3(score: float) -> str:
    if score >= 75: return "OPTIMAL"
    elif score >= 60: return "GOOD"
    elif score >= 45: return "WATCH"
    return "CAUTION"


def comment_v3(score: float, prev_score: float, phase: str, vel_neg_pct: float) -> str:
    if score >= 75:                                          return "OPTIMAL"
    if phase in ("HIGH_CONT", "NORMAL_RISE") and score < 45: return "OVERHEAT"
    if vel_neg_pct >= 80 and score < 45:                     return "ADX_DROP"
    if prev_score >= 0 and (prev_score - score) >= 15:       return "SCORE_FALL"
    if prev_score >= 0 and (score - prev_score) >= 15:       return "RISING"
    if phase in ("BOTTOM_CONT", "BOTTOM"):                   return "BOTTOM_WAIT"
    return "NORMAL"


# ── 日次スコア計算（直近5営業日）────────────────────
def calc_scores_5days(
    h1_adx: list[dict],
    h4_adx: list[dict],
    h4_atr: list[dict],
    h4_bars: list[dict],      # raw H4バー（velの元データ）
) -> list[dict]:

    # H1: 日付ごとにグループ
    h1_by_date: dict[str, list[float]] = {}
    for row in h1_adx:
        d = row["datetime"][:10]
        h1_by_date.setdefault(d, []).append(row["adx"])

    # H4 ADX: 日付ごと
    h4_adx_by_date: dict[str, list[float]] = {}
    for row in h4_adx:
        d = row["datetime"][:10]
        h4_adx_by_date.setdefault(d, []).append(row["adx"])

    # H4 ATR: 日付ごと（最後のバーを当日ATRとして使う）
    h4_atr_by_date: dict[str, list[float]] = {}
    for row in h4_atr:
        d = row["datetime"][:10]
        h4_atr_by_date.setdefault(d, []).append(row["atr"])

    # H4 vel計算（H4 ADX系列全体で一括計算）
    # h4_adx は時系列順（古い→新しい）
    h4_adx_vals  = [r["adx"]      for r in h4_adx]
    h4_adx_dts   = [r["datetime"] for r in h4_adx]
    h4_vel_by_date: dict[str, list[float]] = {}
    for i in range(H4_VEL_PERIOD, len(h4_adx_vals)):
        prev = h4_adx_vals[i - H4_VEL_PERIOD]
        curr = h4_adx_vals[i]
        if prev > 0:
            vel = (curr - prev) / prev * 100.0
            d   = h4_adx_dts[i][:10]
            h4_vel_by_date.setdefault(d, []).append(vel)

    # ATR中央値（直近8週の週末ATR）
    # 週末 = 金曜日のATR末尾値を蓄積
    atr_week_buf: deque[float] = deque(maxlen=ATR_MED_WEEKS)
    atr_end_by_date: dict[str, float] = {}  # 各日のATR末尾値（当日最終バー）
    for d in sorted(h4_atr_by_date.keys()):
        vals = h4_atr_by_date[d]
        if vals:
            atr_end = vals[-1]
            atr_end_by_date[d] = atr_end
            # 金曜の場合は週末バッファに追加
            if datetime.strptime(d, "%Y-%m-%d").weekday() == 4:
                atr_week_buf.append(atr_end)

    # 有効日付
    def is_weekday(d: str) -> bool:
        return datetime.strptime(d, "%Y-%m-%d").weekday() < 5

    all_dates = sorted(
        d for d in set(h1_by_date) & set(h4_adx_by_date)
        if is_weekday(d)
    )
    recent_5 = all_dates[-5:]

    # 前日ATR（delta計算用）
    sorted_atr_dates = sorted(atr_end_by_date.keys())
    prev_atr_end: dict[str, float] = {}
    for i, d in enumerate(sorted_atr_dates):
        if i > 0:
            prev_atr_end[d] = atr_end_by_date[sorted_atr_dates[i - 1]]

    # 前スコア（コメント計算用）
    prev_v3_score: dict[str, float] = {}

    scores = []
    for date_str in recent_5:
        h1_vals  = h1_by_date.get(date_str, [])
        h4_vals  = h4_adx_by_date.get(date_str, [])
        vel_vals = h4_vel_by_date.get(date_str, [])
        atr_end  = atr_end_by_date.get(date_str, 0.0)

        if not h1_vals or not h4_vals: continue
        if len(h4_vals) < 3:
            print(f"  [SKIP] H4バー不足: {date_str} ({len(h4_vals)}本)")
            continue
        if len(h1_vals) < 10:
            print(f"  [SKIP] H1バー不足: {date_str} ({len(h1_vals)}本)")
            continue

        # v1用
        h1_avg   = sum(h1_vals) / len(h1_vals)
        h4_pct20 = 100 * sum(1 for v in h4_vals if v >= 20) / len(h4_vals)
        h4_pct30 = 100 * sum(1 for v in h4_vals if v >= 30) / len(h4_vals)
        score_v1 = calc_score_v1(h1_avg, h4_pct20, h4_pct30)

        # v3用
        h1_s20_avg   = (sum(v for v in h1_vals if v >= 20) / sum(1 for v in h1_vals if v >= 20)
                        if any(v >= 20 for v in h1_vals) else 0.0)
        h4_avg       = sum(h4_vals) / len(h4_vals)
        vel_pos_pct  = (100 * sum(1 for v in vel_vals if v > 0) / len(vel_vals)
                        if vel_vals else 50.0)  # データなし時は中立
        vel_neg_pct  = 100 - vel_pos_pct

        # ATR ratio
        atr_med = (sorted(atr_week_buf)[len(atr_week_buf)//2]
                   if len(atr_week_buf) >= 4 else atr_end)
        atr_ratio    = atr_end / atr_med if atr_med > 0 else 1.0
        prev_atr     = prev_atr_end.get(date_str, atr_end)
        atr_delta    = (atr_end - prev_atr) / prev_atr * 100 if prev_atr > 0 else 0.0
        phase        = atr_phase(atr_ratio, atr_delta)

        score_v3_val = calc_score_v3(vel_pos_pct, phase, h4_avg, h1_s20_avg)
        band         = band_v3(score_v3_val)

        # 前日スコア取得
        prev_idx  = all_dates.index(date_str) - 1
        prev_date = all_dates[prev_idx] if prev_idx >= 0 else None
        prev_s    = prev_v3_score.get(prev_date, -1.0) if prev_date else -1.0

        cmt = comment_v3(score_v3_val, prev_s, phase, vel_neg_pct)
        prev_v3_score[date_str] = score_v3_val

        scores.append({
            "date":          date_str,
            "symbol":        "XAUUSD",
            # v1
            "h1_avg_adx":   round(h1_avg, 2),
            "h4_pct20":     round(h4_pct20, 1),
            "h4_pct30":     round(h4_pct30, 1),
            "score":        score_v1,          # v1スコア（既存キー維持）
            "h1_bars":      len(h1_vals),
            "h4_bars":      len(h4_vals),
            # v3
            "h1_s20_avg":   round(h1_s20_avg, 2),
            "h4_avg_adx":   round(h4_avg, 2),
            "vel_pos_pct":  round(vel_pos_pct, 1),
            "vel_neg_pct":  round(vel_neg_pct, 1),
            "atr_ratio":    round(atr_ratio, 3),
            "atr_delta":    round(atr_delta, 1),
            "atr_phase":    phase,
            "score_v3":     score_v3_val,
            "band_v3":      band,
            "comment_v3":   cmt,
        })
    return scores


# ── scores.json 読み書き ─────────────────────────────
def load_scores() -> list[dict]:
    if not os.path.exists(DATA_PATH): return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_scores(records: list[dict]):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    seen = {}
    for r in records:
        if "symbol" not in r: r["symbol"] = "XAUUSD"
        if r.get("h1_avg_adx", 0) > 100:
            print(f"  [SKIP] 異常値: {r['date']} h1={r['h1_avg_adx']}")
            continue
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        if dt.weekday() >= 5:
            continue
        key = f"{r['date']}_{r['symbol']}"
        seen[key] = r
    merged = sorted(seen.values(), key=lambda x: x["date"])
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[OK] scores.json に {len(merged)} 件保存")


def validate_adx(series: list[dict], label: str):
    vals = [r["adx"] for r in series[-20:]]
    avg  = sum(vals) / len(vals)
    print(f"  {label}: 直近20本 avg={avg:.2f} min={min(vals):.2f} max={max(vals):.2f}")
    if avg > 100:
        raise ValueError(f"[ERROR] {label} ADX値異常 avg={avg:.2f}")


# ── メイン ───────────────────────────────────────────
def main():
    print("=== fetch_and_calc_v2.py 開始 ===")
    print(f"実行時刻: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")

    print(f"\n[1/4] H1データ取得 ({H1_BARS}本)...")
    h1_bars = fetch_ohlcv("1h", H1_BARS)
    print(f"  → {len(h1_bars)}本")

    print(f"\n[2/4] H4データ取得 ({H4_BARS}本)...")
    h4_bars_raw = fetch_ohlcv("4h", H4_BARS)
    print(f"  → {len(h4_bars_raw)}本")

    print("\n[3/4] ADX / ATR計算中...")
    h1_adx = calc_adx(h1_bars,     ADX_PERIOD_H1)
    h4_adx = calc_adx(h4_bars_raw, ADX_PERIOD_H4)
    h4_atr = calc_atr(h4_bars_raw, ATR_PERIOD)
    print(f"  H1 ADX: {len(h1_adx)}本 / H4 ADX: {len(h4_adx)}本 / H4 ATR: {len(h4_atr)}本")
    validate_adx(h1_adx, "H1(28)")
    validate_adx(h4_adx, "H4(30)")

    print("\n[4/4] スコア計算中（直近5営業日）...")
    new_scores = calc_scores_5days(h1_adx, h4_adx, h4_atr, h4_bars_raw)

    if not new_scores:
        print("[WARN] スコアが空です")
        return

    print("\n  --- スコアサマリー ---")
    for s in new_scores:
        print(f"  {s['date']}:"
              f"  v1={s['score']:5.1f}"
              f"  v3={s['score_v3']:5.1f} [{s['band_v3']:7s}] {s['comment_v3']}"
              f"  phase={s['atr_phase']}"
              f"  vel_pos={s['vel_pos_pct']:.0f}%")

    existing = load_scores()
    save_scores(existing + new_scores)
    print("\n=== 完了 ===")


if __name__ == "__main__":
    main()
