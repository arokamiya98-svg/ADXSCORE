"""
send_line.py
LINE Messaging API（Flex Message）でADXスコアを配信
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta

DATA_PATH    = "data/scores.json"
LINE_TOKEN   = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]   # 配信先ユーザーID
PAGES_URL    = os.environ.get("GITHUB_PAGES_URL", "https://your-user.github.io/your-repo/")

JST = timezone(timedelta(hours=9))


def load_scores() -> list[dict]:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def score_to_color(score: float) -> str:
    if score >= 80: return "#00c853"
    elif score >= 60: return "#64dd17"
    elif score >= 40: return "#FFD600"
    elif score >= 24: return "#FF6D00"
    else: return "#D50000"


def score_to_label(score: float) -> str:
    if score >= 80: return "最強 🔥"
    elif score >= 60: return "強い ✅"
    elif score >= 40: return "普通 🔶"
    elif score >= 24: return "様子見 ⚠️"
    else: return "NG ❌"


def build_flex(records: list[dict]) -> dict:
    """
    Flex Message（バブル形式）の構築
    ヘッダー: 今日のスコア（大きく）
    ボディ:   直近5日のミニ表
    フッター: HTMLページへのリンク
    """
    recent_5 = records[-5:] if len(records) >= 5 else records
    today    = recent_5[-1] if recent_5 else None

    if today is None:
        return {"type": "text", "text": "[ADXスコア] データなし"}

    today_score = today["score"]
    today_color = score_to_color(today_score)
    today_label = score_to_label(today_score)
    today_dt    = datetime.strptime(today["date"], "%Y-%m-%d")
    today_str   = today_dt.strftime("%-m/%-d(%a)")   # 例: 4/14(Mon)

    # 5日分のミニ行
    rows = []
    for r in recent_5:
        dt    = datetime.strptime(r["date"], "%Y-%m-%d")
        label = dt.strftime("%-m/%-d(%a)")
        color = score_to_color(r["score"])
        is_today = r["date"] == today["date"]
        rows.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": label,
                    "size": "xs",
                    "color": "#FFFFFF" if is_today else "#8b949e",
                    "flex": 3,
                    "weight": "bold" if is_today else "regular",
                },
                {
                    "type": "text",
                    "text": f"{r['score']}pt",
                    "size": "xs",
                    "color": color,
                    "flex": 2,
                    "weight": "bold",
                    "align": "end",
                },
                {
                    "type": "text",
                    "text": score_to_label(r["score"]).split(" ")[0],
                    "size": "xs",
                    "color": color,
                    "flex": 3,
                    "align": "end",
                },
            ],
            "paddingAll": "4px",
            "backgroundColor": "#1e2a1e" if is_today else None,
            "cornerRadius": "4px",
            "margin": "xs",
        })

    flex_message = {
        "type": "flex",
        "altText": f"[ADXスコア] {today_str} → {today_score}pt {today_label}",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0d1117",
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "text",
                        "text": "⚡ XAUUSD ADX Score",
                        "size": "sm",
                        "color": "#d4af37",
                        "weight": "bold",
                    },
                    {
                        "type": "text",
                        "text": today_str,
                        "size": "xs",
                        "color": "#8b949e",
                        "margin": "xs",
                    },
                ],
            },
            "hero": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0d1117",
                "paddingAll": "20px",
                "paddingBottom": "10px",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{today_score}",
                        "size": "5xl",
                        "weight": "bold",
                        "color": today_color,
                        "align": "center",
                    },
                    {
                        "type": "text",
                        "text": today_label,
                        "size": "md",
                        "weight": "bold",
                        "color": today_color,
                        "align": "center",
                        "margin": "xs",
                    },
                    {
                        "type": "separator",
                        "margin": "lg",
                        "color": "#30363d",
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "vertical",
                                "flex": 1,
                                "contents": [
                                    {"type": "text", "text": "H1 avg ADX", "size": "xxs", "color": "#8b949e"},
                                    {"type": "text", "text": str(today["h1_avg_adx"]), "size": "sm", "weight": "bold", "color": "#e6edf3"},
                                ],
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "flex": 1,
                                "contents": [
                                    {"type": "text", "text": "H4 ADX≥20", "size": "xxs", "color": "#8b949e"},
                                    {"type": "text", "text": f"{today['h4_pct20']}%", "size": "sm", "weight": "bold", "color": "#e6edf3"},
                                ],
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "flex": 1,
                                "contents": [
                                    {"type": "text", "text": "H4 ADX≥30", "size": "xxs", "color": "#8b949e"},
                                    {"type": "text", "text": f"{today['h4_pct30']}%", "size": "sm", "weight": "bold", "color": "#e6edf3"},
                                ],
                            },
                        ],
                    },
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#161b22",
                "paddingAll": "14px",
                "contents": [
                    {
                        "type": "text",
                        "text": "直近5営業日",
                        "size": "xs",
                        "color": "#8b949e",
                        "margin": "none",
                        "weight": "bold",
                    },
                    *rows,
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0d1117",
                "paddingAll": "12px",
                "contents": [
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "label": "📊 週次レポートを見る",
                            "uri": PAGES_URL,
                        },
                        "style": "primary",
                        "color": "#d4af37",
                        "height": "sm",
                    },
                ],
            },
        },
    }
    return flex_message


def send_line(message: dict):
    url     = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }
    payload = {
        "to":       LINE_USER_ID,
        "messages": [message],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if resp.status_code == 200:
        print("[OK] LINE送信成功")
    else:
        print(f"[ERROR] LINE送信失敗: {resp.status_code} {resp.text}")
        resp.raise_for_status()


def main():
    print("=== send_line.py 開始 ===")
    records = load_scores()
    if not records:
        print("[WARN] スコアデータなし → スキップ")
        return
    flex = build_flex(records)
    send_line(flex)
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
