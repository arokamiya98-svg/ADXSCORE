"""
send_line_v2.py
LINE Messaging API（Flex Message）2ページ構成配信

Page 1 (Carousel 1枚目): v3スコア
  - OPTIMAL / GOOD / WATCH / CAUTION バンド
  - スコアコメント（OPTIMAL / RISING / SCORE_FALL / BOTTOM_WAIT / NORMAL / OVERHEAT / ADX_DROP）
  - ATRフェーズ / vel_pos_pct
  - 直近5日のv3スコア一覧

Page 2 (Carousel 2枚目): v1スコア（従来デザイン）
  - 従来のH1avg / H4≥20 / H4≥30
  - 直近5日のv1スコア一覧
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta

DATA_PATH    = "data/scores.json"
LINE_TOKEN   = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
PAGES_URL    = os.environ.get("PAGES_URL", "https://your-user.github.io/your-repo/")

JST = timezone(timedelta(hours=9))


# ── データ読み込み ────────────────────────────────────
def load_scores() -> list[dict]:
    if not os.path.exists(DATA_PATH): return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_recent5(records: list[dict]) -> list[dict]:
    wd = [r for r in records if datetime.strptime(r["date"], "%Y-%m-%d").weekday() < 5]
    return wd[-5:] if len(wd) >= 5 else wd


# ── カラー関数（v3）──────────────────────────────────
def v3_band_color(band: str) -> tuple[str, str]:
    """(bg, text_color)"""
    return {
        "OPTIMAL": ("#00c853", "#001a0a"),
        "GOOD":    ("#69f0ae", "#001a0a"),
        "WATCH":   ("#ffd740", "#1a1000"),
        "CAUTION": ("#ff5252", "#1a0000"),
    }.get(band, ("#444444", "#ffffff"))


def v3_comment_emoji(cmt: str) -> str:
    return {
        "OPTIMAL":     "🎯",
        "RISING":      "📈",
        "SCORE_FALL":  "📉",
        "BOTTOM_WAIT": "⏳",
        "NORMAL":      "→",
        "OVERHEAT":    "🔥",
        "ADX_DROP":    "❄️",
    }.get(cmt, "→")


def v3_comment_label(cmt: str) -> str:
    return {
        "OPTIMAL":     "最適環境",
        "RISING":      "スコア急上昇",
        "SCORE_FALL":  "急落後 反発監視",
        "BOTTOM_WAIT": "収束底 蓄積中",
        "NORMAL":      "通常状態",
        "OVERHEAT":    "過熱域 注意",
        "ADX_DROP":    "ADX剥落 スキップ",
    }.get(cmt, "通常状態")


def v3_phase_label(phase: str) -> str:
    return {
        "BOTTOM_CONT":  "🟢 収束底継続",
        "NORMAL_FLAT":  "🟢 ATR安定",
        "BOTTOM_TURN":  "🟡 底から立上",
        "BOTTOM":       "🟡 底圏待機",
        "PEAK_CONT":    "🟡 高ボラ継続",
        "NORMAL_FALL":  "🟠 収縮中",
        "HIGH_FALL":    "🟠 高ボラ収縮",
        "PEAK_FALL":    "🔴 過熱後急落",
        "HIGH_CONT":    "🔴 危険 過熱",
        "NORMAL_RISE":  "🔴 危険 ATR急拡",
        "N/A":          "⬜ 不明",
    }.get(phase, phase)


# ── カラー関数（v1）──────────────────────────────────
def v1_score_color(score: float) -> str:
    if score >= 80:   return "#00c853"
    elif score >= 60: return "#69f0ae"
    elif score >= 40: return "#ffd740"
    elif score >= 24: return "#ff9100"
    else:             return "#ff5252"


def v1_score_label(score: float) -> str:
    if score >= 80:   return "最強 🔥"
    elif score >= 60: return "強い ✅"
    elif score >= 40: return "普通 🔶"
    elif score >= 24: return "様子見 ⚠️"
    else:             return "NG ❌"


# ── Page1: v3スコア Bubble ────────────────────────────
def build_bubble_v3(records: list[dict]) -> dict:
    recent = get_recent5(records)
    if not recent:
        return {"type": "bubble", "body": {"type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "データなし"}]}}

    today     = recent[-1]
    score_v3  = today.get("score_v3", 0)
    band      = today.get("band_v3", "CAUTION")
    cmt       = today.get("comment_v3", "NORMAL")
    phase     = today.get("atr_phase", "N/A")
    vel_pos   = today.get("vel_pos_pct", 0)
    today_dt  = datetime.strptime(today["date"], "%Y-%m-%d")
    today_str = today_dt.strftime("%-m/%-d(%a)")

    bg_color, tx_color = v3_band_color(band)
    cmt_emoji  = v3_comment_emoji(cmt)
    cmt_label  = v3_comment_label(cmt)
    phase_lbl  = v3_phase_label(phase)

    # 5日間履歴行
    history_rows = []
    for r in recent:
        s3   = r.get("score_v3", 0)
        bd   = r.get("band_v3", "CAUTION")
        b_c, t_c = v3_band_color(bd)
        dt   = datetime.strptime(r["date"], "%Y-%m-%d")
        is_t = r["date"] == today["date"]
        dow  = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][dt.weekday()]
        lbl  = dt.strftime(f"%-m/%-d({dow})")
        row = {
            "type": "box",
            "layout": "horizontal",
            "paddingAll": "4px",
            "cornerRadius": "4px",
            "margin": "xs",
            "contents": [
                {"type": "text", "text": lbl, "size": "xs",
                 "color": "#e0e0e0" if is_t else "#888888",
                 "flex": 3, "weight": "bold" if is_t else "regular"},
                {"type": "text", "text": f"{s3}pt", "size": "xs",
                 "color": b_c if b_c != "#444444" else "#aaaaaa",
                 "flex": 2, "weight": "bold", "align": "end"},
                {"type": "text", "text": bd.split("(")[0],
                 "size": "xs", "color": b_c if b_c != "#444444" else "#aaaaaa",
                 "flex": 3, "align": "end"},
            ],
        }
        if is_t:
            row["backgroundColor"] = "#1a2a1a"
        history_rows.append(row)

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0d1117",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "⚡ XAUUSD ADX Score  v3",
                 "size": "sm", "color": "#d4af37", "weight": "bold"},
                {"type": "text", "text": today_str + "  適正状態評価",
                 "size": "xs", "color": "#666666", "margin": "xs"},
            ],
        },
        "hero": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0d1117",
            "paddingAll": "16px",
            "paddingBottom": "8px",
            "contents": [
                # スコア大表示
                {"type": "text", "text": str(score_v3),
                 "size": "5xl", "weight": "bold",
                 "color": bg_color, "align": "center"},
                # バンド
                {"type": "text", "text": f"■ {band}",
                 "size": "md", "weight": "bold",
                 "color": bg_color, "align": "center", "margin": "sm"},
                # コメント
                {"type": "box", "layout": "horizontal",
                 "margin": "md", "backgroundColor": "#161b22",
                 "cornerRadius": "6px", "paddingAll": "8px",
                 "contents": [
                     {"type": "text", "text": cmt_emoji,
                      "size": "md", "flex": 0},
                     {"type": "text",
                      "text": f" {cmt_label}",
                      "size": "sm", "color": "#e0e0e0",
                      "weight": "bold", "flex": 1},
                 ]},
                {"type": "separator", "margin": "md", "color": "#30363d"},
                # ATRフェーズ / vel
                {"type": "box", "layout": "horizontal", "margin": "md",
                 "contents": [
                     {"type": "box", "layout": "vertical", "flex": 1,
                      "contents": [
                          {"type": "text", "text": "ATRフェーズ",
                           "size": "xxs", "color": "#666666"},
                          {"type": "text", "text": phase_lbl,
                           "size": "xs", "weight": "bold", "color": "#e6edf3",
                           "wrap": True},
                      ]},
                     {"type": "box", "layout": "vertical", "flex": 1,
                      "contents": [
                          {"type": "text", "text": "H4 vel上昇",
                           "size": "xxs", "color": "#666666"},
                          {"type": "text", "text": f"{vel_pos:.0f}%",
                           "size": "sm", "weight": "bold",
                           "color": "#69f0ae" if 60<=vel_pos<=80 else
                                    ("#ffd740" if 40<=vel_pos<60 else "#ff5252")},
                      ]},
                 ]},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#161b22",
            "paddingAll": "12px",
            "contents": [
                {"type": "text", "text": "直近5営業日 (v3)",
                 "size": "xs", "color": "#666666", "weight": "bold"},
                *history_rows,
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0d1117",
            "paddingAll": "10px",
            "contents": [
                {"type": "button",
                 "action": {"type": "uri", "label": "📊 週次レポートを見る",
                            "uri": PAGES_URL},
                 "style": "primary", "color": "#d4af37", "height": "sm"},
            ],
        },
    }
    return bubble


# ── Page2: v1スコア Bubble（既存デザイン維持）────────
def build_bubble_v1(records: list[dict]) -> dict:
    recent = get_recent5(records)
    if not recent:
        return {"type": "bubble", "body": {"type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "データなし"}]}}

    today     = recent[-1]
    score_v1  = today.get("score", 0)
    h1_avg    = today.get("h1_avg_adx", 0)
    h4_pct20  = today.get("h4_pct20", 0)
    h4_pct30  = today.get("h4_pct30", 0)
    today_dt  = datetime.strptime(today["date"], "%Y-%m-%d")
    today_str = today_dt.strftime("%-m/%-d(%a)")

    score_color = v1_score_color(score_v1)
    score_label = v1_score_label(score_v1)

    history_rows = []
    for r in recent:
        s1   = r.get("score", 0)
        s_c  = v1_score_color(s1)
        dt   = datetime.strptime(r["date"], "%Y-%m-%d")
        is_t = r["date"] == today["date"]
        dow  = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][dt.weekday()]
        lbl  = dt.strftime(f"%-m/%-d({dow})")
        row  = {
            "type": "box",
            "layout": "horizontal",
            "paddingAll": "4px",
            "cornerRadius": "4px",
            "margin": "xs",
            "contents": [
                {"type": "text", "text": lbl, "size": "xs",
                 "color": "#e0e0e0" if is_t else "#888888",
                 "flex": 3, "weight": "bold" if is_t else "regular"},
                {"type": "text", "text": f"{s1}pt", "size": "xs",
                 "color": s_c, "flex": 2, "weight": "bold", "align": "end"},
                {"type": "text",
                 "text": v1_score_label(s1).split(" ")[0],
                 "size": "xs", "color": s_c, "flex": 3, "align": "end"},
            ],
        }
        if is_t:
            row["backgroundColor"] = "#1e2a1e"
        history_rows.append(row)

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0d1117",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "⚡ XAUUSD ADX Score  v1",
                 "size": "sm", "color": "#d4af37", "weight": "bold"},
                {"type": "text", "text": today_str + "  相場環境評価",
                 "size": "xs", "color": "#666666", "margin": "xs"},
            ],
        },
        "hero": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0d1117",
            "paddingAll": "20px",
            "paddingBottom": "10px",
            "contents": [
                {"type": "text", "text": str(score_v1),
                 "size": "5xl", "weight": "bold",
                 "color": score_color, "align": "center"},
                {"type": "text", "text": score_label,
                 "size": "md", "weight": "bold",
                 "color": score_color, "align": "center", "margin": "xs"},
                {"type": "separator", "margin": "lg", "color": "#30363d"},
                {"type": "box", "layout": "horizontal", "margin": "md",
                 "contents": [
                     {"type": "box", "layout": "vertical", "flex": 1,
                      "contents": [
                          {"type": "text", "text": "H1 avg ADX",
                           "size": "xxs", "color": "#666666"},
                          {"type": "text", "text": str(h1_avg),
                           "size": "sm", "weight": "bold", "color": "#e6edf3"},
                      ]},
                     {"type": "box", "layout": "vertical", "flex": 1,
                      "contents": [
                          {"type": "text", "text": "H4 ADX≥20",
                           "size": "xxs", "color": "#666666"},
                          {"type": "text", "text": f"{h4_pct20}%",
                           "size": "sm", "weight": "bold", "color": "#e6edf3"},
                      ]},
                     {"type": "box", "layout": "vertical", "flex": 1,
                      "contents": [
                          {"type": "text", "text": "H4 ADX≥30",
                           "size": "xxs", "color": "#666666"},
                          {"type": "text", "text": f"{h4_pct30}%",
                           "size": "sm", "weight": "bold", "color": "#e6edf3"},
                      ]},
                 ]},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#161b22",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "直近5営業日 (v1)",
                 "size": "xs", "color": "#666666", "weight": "bold"},
                *history_rows,
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0d1117",
            "paddingAll": "10px",
            "contents": [
                {"type": "button",
                 "action": {"type": "uri", "label": "📊 週次レポートを見る",
                            "uri": PAGES_URL},
                 "style": "primary", "color": "#d4af37", "height": "sm"},
            ],
        },
    }
    return bubble


# ── Carousel メッセージ組み立て ──────────────────────
def build_carousel(records: list[dict]) -> dict:
    bubble_v3 = build_bubble_v3(records)
    bubble_v1 = build_bubble_v1(records)

    recent = get_recent5(records)
    today  = recent[-1] if recent else {}
    score_v3 = today.get("score_v3", 0)
    band     = today.get("band_v3", "CAUTION")
    score_v1 = today.get("score", 0)
    today_str = datetime.strptime(today.get("date", "2000-01-01"), "%Y-%m-%d").strftime("%-m/%-d(%a)") if today else "??"

    return {
        "type": "flex",
        "altText": f"[ADX] {today_str}  v3:{score_v3}pt {band} / v1:{score_v1}pt",
        "contents": {
            "type": "carousel",
            "contents": [bubble_v3, bubble_v1],
        },
    }


# ── LINE 送信 ────────────────────────────────────────
def send_line(message: dict):
    url     = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }
    payload = {"to": LINE_USER_ID, "messages": [message]}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if resp.status_code == 200:
        print("[OK] LINE送信成功")
    else:
        print(f"[ERROR] LINE送信失敗: {resp.status_code} {resp.text}")
        resp.raise_for_status()


# ── メイン ───────────────────────────────────────────
def main():
    print("=== send_line_v2.py 開始 ===")
    records = load_scores()
    if not records:
        print("[WARN] データなし → スキップ")
        return

    recent = get_recent5(records)
    today  = recent[-1] if recent else {}
    print(f"今日: {today.get('date','')}  "
          f"v3={today.get('score_v3','?')} [{today.get('band_v3','?')}] {today.get('comment_v3','?')}  "
          f"v1={today.get('score','?')}")

    msg = build_carousel(records)
    send_line(msg)
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
