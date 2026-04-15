"""
generate_html.py v3
MT5出力CSV → 多銘柄ヒートマップHTML生成
機能:
  - 表示銘柄の選択（ON/OFF切替）
  - スコア順 / 銘柄名順 の並び替え
  - 期間スライダー
  - 直近5日パネル（scores.json から）
"""

import json, os, csv, io, math
from datetime import datetime, timezone, timedelta

CSV_PATH  = "data/adx_weekly.csv"
DATA_PATH = "data/scores.json"
HTML_PATH = "docs/index.html"
JST       = timezone(timedelta(hours=9))

SYM_COLORS = {
    "XAUUSD": "#ffd700", "XAGUSD": "#cccccc", "USDCAD": "#44ccff",
    "AUDUSD": "#88ffcc", "USDJPY": "#ff99cc", "EURUSD": "#bb88ff",
    "BTCUSD": "#ff8844",
}


# ── ADXスコア計算 ────────────────────────────────────
def calc_score(h1a, h4p20, h4p30):
    h1norm = max(0, min(100, (h1a - 10) / 30 * 100))
    a      = max(0.1, h1norm)
    b      = max(0.1, h4p20)
    base   = math.sqrt(a * b) * 0.85
    bonus  = 1.0 + (h4p30 / 100) * 0.5
    return round(min(100, base * bonus), 1)


def score_grade(s):
    if s >= 80: return ("🔥 爆発",    "#ff4400", "#fff")
    if s >= 65: return ("🔶 超強",    "#ff9900", "#000")
    if s >= 50: return ("⭐ 候補",    "#cccc00", "#000")
    if s >= 38: return ("✅ 良い",    "#00a85e", "#fff")
    if s >= 27: return ("🔹 OK",      "#007040", "#fff")
    if s >= 18: return ("⬜ 様子見",  "#1a3d25", "#88ccaa")
    if s >= 10: return ("⬛ 弱い",    "#252500", "#aaaa44")
    return             ("⬛ 見送り",  "#0c1018", "#2a3a48")


# ── CSV読み込み ──────────────────────────────────────
def load_csv(path):
    if not os.path.exists(path):
        print(f"[WARN] CSV未検出: {path}")
        return {}
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    except Exception:
        text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")

    raw_data = {}   # {sym: {week: {ws,h1a,h4p20,h4p30,score}}}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        sym  = row.get("Symbol","").strip()
        week = row.get("Week","").strip()
        ws   = row.get("WeekStart","").strip()
        if not sym or not week: continue
        try:
            h1a   = float(row.get("H1_AvgADX",     0))
            h4p20 = float(row.get("H4_Pct_Above20",0))
            h4p30 = float(row.get("H4_Pct_Above30",0))
        except (ValueError, TypeError):
            continue
        score = calc_score(h1a, h4p20, h4p30)
        raw_data.setdefault(sym, {})[week] = {
            "ws": ws, "h1a": round(h1a,2),
            "h4p20": round(h4p20,1), "h4p30": round(h4p30,1),
            "score": score,
        }
    for sym, wks in raw_data.items():
        print(f"  {sym}: {len(wks)}週")
    return raw_data


# ── 直近5日読み込み ──────────────────────────────────
def load_recent5(path):
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8") as f:
        recs = json.load(f)
    wd = [r for r in recs if datetime.strptime(r["date"],"%Y-%m-%d").weekday() < 5]
    return wd[-5:] if len(wd) >= 5 else wd


# ── セル色計算 ──────────────────────────────────────
def cell_style(score):
    _, bg, tx = score_grade(score)
    return bg, tx


# ── HTML生成 ─────────────────────────────────────────
def generate_html(raw_data, recent5):
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    # 全週リスト
    all_weeks = sorted({w for sym_d in raw_data.values() for w in sym_d})
    all_syms  = sorted(raw_data.keys(),
                       key=lambda s: list(SYM_COLORS.keys()).index(s)
                       if s in SYM_COLORS else 99)
    n_weeks   = len(all_weeks)

    # 最新週スコアバナー
    last_wk = all_weeks[-1] if all_weeks else ""
    last_ws = ""
    banner_cards = ""
    if last_wk:
        latest = []
        for sym in all_syms:
            r = raw_data.get(sym, {}).get(last_wk)
            if r:
                if not last_ws: last_ws = r["ws"]
                latest.append((sym, r["score"], r))
        # スコア降順
        latest.sort(key=lambda x: -x[1])
        for sym, score, r in latest:
            lbl, bg, tx = score_grade(score)
            sc = SYM_COLORS.get(sym, "#aaa")
            h4p30_str = f"H4_30:{r['h4p30']:.0f}%"
            banner_cards += f"""
    <div style="background:{bg};border-radius:8px;padding:10px 14px;text-align:center;min-width:100px;border:1px solid {sc}44;">
      <div style="font-size:10px;font-weight:700;color:{sc};">{sym}</div>
      <div style="font-size:26px;font-weight:700;color:{tx};line-height:1;">{int(round(score))}</div>
      <div style="font-size:9px;color:{tx};margin-top:2px;">{lbl}</div>
      <div style="font-size:8px;color:{tx};opacity:0.7;margin-top:2px;">{h4p30_str}</div>
    </div>"""

    # 直近5日パネル
    recent_html = ""
    if recent5:
        for r in recent5:
            s = calc_score(r["h1_avg_adx"], r["h4_pct20"], r["h4_pct30"])
            lbl, bg, tx = score_grade(s)
            dt  = datetime.strptime(r["date"], "%Y-%m-%d")
            dow = ["月","火","水","木","金","土","日"][dt.weekday()]
            d   = r["date"][5:].replace("-","/")
            recent_html += f"""
    <div style="background:{bg};border:1px solid #1a3050;border-radius:8px;padding:8px 10px;text-align:center;min-width:82px;">
      <div style="font-size:9px;color:#5a8aaa;margin-bottom:3px;">{d}({dow})</div>
      <div style="font-size:20px;font-weight:800;color:{tx};line-height:1;">{int(round(s))}</div>
      <div style="font-size:8px;font-weight:700;color:{tx};margin-top:2px;">{lbl}</div>
      <div style="margin-top:5px;border-top:1px solid rgba(255,255,255,0.1);padding-top:3px;font-size:7px;color:#6a9ab0;">
        H1avg <b style="color:#aaccff;">{r['h1_avg_adx']}</b><br>
        H4≥20 <b style="color:#ffcc44;">{r['h4_pct20']}%</b><br>
        H4≥30 <b style="color:#ff88cc;">{r['h4_pct30']}%</b>
      </div>
    </div>"""

    # 週ヘッダー（年ラベル・月ラベル）
    def week_header_cells():
        cells = []
        for i, wk in enumerate(all_weeks):
            is_yr = wk.endswith("W01")
            ws = raw_data.get(all_syms[0] if all_syms else "", {}).get(wk, {}).get("ws","")
            mon = int(ws[5:7])-1 if ws else 0
            ml  = ["J","F","M","A","M","J","J","A","S","O","N","D"]
            if is_yr:
                lbl = f"'{wk[2:4]}"
                style = "font-size:7px;color:#8a9a60;font-weight:700;"
                bl = "border-left:1px solid #2a3010;"
            elif i % 4 == 0:
                lbl = ml[mon]
                style = "font-size:7px;color:#3a4020;"
                bl = ""
            else:
                lbl = ""
                style = ""
                bl = ""
            cells.append(f'<td style="width:24px;text-align:center;{style}{bl}padding-bottom:4px;">{lbl}</td>')
        return "\n".join(cells)

    # 銘柄グリッド生成
    def sym_grid(sym):
        sym_data = raw_data.get(sym, {})
        sc = SYM_COLORS.get(sym, "#aaa")

        # スコア行
        score_cells = []
        h1_cells, h4p20_cells, h4p30_cells = [], [], []
        for wk in all_weeks:
            r = sym_data.get(wk)
            is_yr = wk.endswith("W01")
            bl = "border-left:1px solid #2a3010;" if is_yr else ""
            latest_outline = "outline:2px solid #ffd700;outline-offset:-1px;" if wk == last_wk else ""

            if r:
                s = r["score"]
                bg, tx = cell_style(s)
                score_cells.append(
                    f'<td class="cell" data-sym="{sym}" data-wk="{wk}" '
                    f'style="background:{bg};width:24px;height:28px;text-align:center;'
                    f'font-size:8px;color:{tx};font-weight:700;border-radius:2px;{bl}{latest_outline}">'
                    f'{int(round(s))}</td>')

                # H1avg
                v = r["h1a"]
                if v>=35: hbg,htx="#ff9900","#000"
                elif v>=30: hbg,htx="#00ffb3","#001a0e"
                elif v>=24: hbg,htx="#00a85e","#fff"
                elif v>=20: hbg,htx="#007040","#fff"
                elif v>=17: hbg,htx="#2a2a00","#aaaa44"
                else: hbg,htx="#0c1018","#2a3a48"
                h1_cells.append(
                    f'<td class="cell" data-sym="{sym}" data-wk="{wk}" '
                    f'style="background:{hbg};width:24px;height:20px;text-align:center;'
                    f'font-size:7px;color:{htx};font-weight:600;border-radius:2px;{bl}">'
                    f'{v:.1f}</td>')

                # H4≥20%
                for val, cells_list in [(r["h4p20"], h4p20_cells),(r["h4p30"], h4p30_cells)]:
                    if val>=75: pbg,ptx="#00ffb3","#001a0e"
                    elif val>=60: pbg,ptx="#00d97e","#001a0e"
                    elif val>=45: pbg,ptx="#00a85e","#fff"
                    elif val>=30: pbg,ptx="#007040","#fff"
                    elif val>=15: pbg,ptx="#1a3d25","#88ccaa"
                    elif val>=5:  pbg,ptx="#252500","#aaaa44"
                    else: pbg,ptx="#0c1018","#2a3a48"
                    cells_list.append(
                        f'<td class="cell" data-sym="{sym}" data-wk="{wk}" '
                        f'style="background:{pbg};width:24px;height:20px;text-align:center;'
                        f'font-size:7px;color:{ptx};font-weight:600;border-radius:2px;{bl}">'
                        f'{int(round(val))}</td>')
            else:
                empty = (f'<td style="width:24px;height:{{h}}px;background:#060b10;{bl}"></td>')
                score_cells.append(empty.format(h=28))
                h1_cells.append(empty.format(h=20))
                h4p20_cells.append(empty.format(h=20))
                h4p30_cells.append(empty.format(h=20))

        # AVG列
        vals = [sym_data[w]["score"] for w in all_weeks if w in sym_data]
        avg  = sum(vals)/len(vals) if vals else 0
        abg, atx = cell_style(avg)
        avg_score_cell = (
            f'<td style="text-align:center;font-size:11px;font-weight:700;padding-left:8px;'
            f'border-left:1px solid #1a2000;background:{abg};color:{atx};'
            f'position:sticky;right:0;z-index:1;border-radius:2px;height:28px;">'
            f'{int(round(avg))}</td>')

        def avg_cell(cells_list, h=20):
            return (f'<td style="text-align:center;font-size:9px;font-weight:700;padding-left:8px;'
                    f'border-left:1px solid #1a2000;background:#0a1520;color:#3a5a70;'
                    f'position:sticky;right:0;z-index:1;height:{h}px;"></td>')

        score_row  = "\n".join(score_cells)
        h1_row     = "\n".join(h1_cells)
        h4p20_row  = "\n".join(h4p20_cells)
        h4p30_row  = "\n".join(h4p30_cells)

        return f"""
<div class="sym-block" data-sym="{sym}" data-lastscore="{sym_data.get(last_wk,{}).get('score',0):.1f}" style="margin-bottom:22px;">
  <div style="font-size:13px;font-weight:700;color:{sc};margin-bottom:3px;padding-left:106px;letter-spacing:1px;">{sym}</div>
  <table style="border-collapse:separate;border-spacing:2px;min-width:max-content;">
  <thead><tr>
    <th style="min-width:102px;width:102px;background:#060b10;position:sticky;left:0;z-index:3;"></th>
    {week_header_cells()}
    <th style="width:46px;font-size:9px;color:#3a4020;text-align:center;padding-left:8px;border-left:1px solid #1a2000;position:sticky;right:0;background:#060b10;z-index:3;">AVG</th>
  </tr></thead>
  <tbody>
    <tr>
      <td style="font-size:10px;font-weight:700;color:#7ab8d8;padding-right:6px;padding-left:4px;white-space:nowrap;position:sticky;left:0;background:#060b10;z-index:2;">📊 相場点数</td>
      {score_row}
      {avg_score_cell}
    </tr>
    <tr><td style="height:3px;" colspan="{n_weeks+2}"></td></tr>
    <tr>
      <td style="font-size:9px;color:#4a7a90;padding-right:6px;padding-left:4px;white-space:nowrap;position:sticky;left:0;background:#060b10;z-index:2;">H1 avgADX</td>
      {h1_row}
      {avg_cell(h1_cells)}
    </tr>
    <tr>
      <td style="font-size:9px;color:#4a7a90;padding-right:6px;padding-left:4px;white-space:nowrap;position:sticky;left:0;background:#060b10;z-index:2;">H4 ≥20%</td>
      {h4p20_row}
      {avg_cell(h4p20_cells)}
    </tr>
    <tr>
      <td style="font-size:9px;color:#4a7a90;padding-right:6px;padding-left:4px;white-space:nowrap;position:sticky;left:0;background:#060b10;z-index:2;">H4 ≥30%</td>
      {h4p30_row}
      {avg_cell(h4p30_cells)}
    </tr>
  </tbody>
  </table>
</div>"""

    # 全銘柄グリッド
    all_grids = "\n".join(sym_grid(sym) for sym in all_syms)

    # TOOLTIP JSON
    tooltip = {}
    for sym in all_syms:
        for wk, r in raw_data.get(sym, {}).items():
            tooltip.setdefault(wk, {})[sym] = {
                "ws": r["ws"], "h1a": r["h1a"],
                "h4p20": r["h4p20"], "h4p30": r["h4p30"],
                "s": r["score"],
            }
    tooltip_json = json.dumps(tooltip, ensure_ascii=False)
    weeks_json   = json.dumps(all_weeks, ensure_ascii=False)
    syms_json    = json.dumps(all_syms, ensure_ascii=False)
    sym_c_json   = json.dumps(SYM_COLORS, ensure_ascii=False)
    recent_json  = json.dumps(recent5, ensure_ascii=False)

    # 銘柄フィルターボタン
    sym_filter_btns = ""
    for sym in all_syms:
        sc = SYM_COLORS.get(sym, "#aaa")
        sym_filter_btns += f"""
    <button class="sym-btn active" data-sym="{sym}"
      onclick="toggleSym('{sym}',this)"
      style="background:#0d1e30;border:1px solid {sc}66;border-radius:4px;
             color:{sc};font-size:11px;padding:4px 10px;cursor:pointer;
             font-family:inherit;font-weight:700;">{sym}</button>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ADX Score Dashboard — 多銘柄</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#060b10;font-family:'IBM Plex Mono','Courier New',monospace;color:#b0c8e0;}}
::-webkit-scrollbar{{width:5px;height:5px;}}
::-webkit-scrollbar-track{{background:#0a1520;}}
::-webkit-scrollbar-thumb{{background:#1a3050;border-radius:3px;}}
.cell{{cursor:default;transition:filter 0.08s;}}
.cell:hover{{filter:brightness(1.55);}}
input[type=range]{{-webkit-appearance:none;height:4px;border-radius:2px;background:#1a3050;outline:none;width:100%;}}
input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:#ffd700;cursor:pointer;}}
.sym-btn{{transition:opacity 0.15s;}}
.sym-btn.inactive{{opacity:0.3;}}
.ctrl-btn{{background:transparent;border:1px solid #1a3050;border-radius:4px;
           color:#3a5a70;font-size:10px;padding:4px 10px;cursor:pointer;
           font-family:inherit;white-space:nowrap;transition:all 0.1s;}}
.ctrl-btn:hover{{border-color:#3a5a70;color:#7ab8d8;}}
.ctrl-btn.active{{background:#0a2030;border-color:#2266aa;color:#44aaff;font-weight:700;}}
</style>
</head>
<body>

<!-- ヘッダー -->
<div style="background:linear-gradient(135deg,#0a1828,#060b10);border-bottom:1px solid #122030;padding:12px 18px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">
  <div>
    <div style="font-size:9px;color:#2a4a60;letter-spacing:2px;margin-bottom:2px;">
      ADX Score = sqrt(H1norm x H4_20) x 0.85 x (1 + H4_30x0.5) | MT5 iADX準拠
    </div>
    <div style="font-size:18px;font-weight:700;color:#d8f0ff;">⚡ ADX Score Dashboard</div>
    <div style="font-size:9px;color:#2a4a60;margin-top:2px;">最終更新: {now_jst} | {n_weeks}週 | {len(all_syms)}銘柄</div>
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
    <span style="font-size:10px;color:#3a5a70;">並び替え:</span>
    <button class="ctrl-btn active" id="btn-score" onclick="sortBy('score')">スコア順↓</button>
    <button class="ctrl-btn" id="btn-alpha" onclick="sortBy('alpha')">銘柄名順</button>
    <button class="ctrl-btn" id="btn-default" onclick="sortBy('default')">デフォルト</button>
  </div>
</div>

<!-- 最新週バナー -->
<div style="background:#0a1520;border-bottom:1px solid #122030;padding:10px 18px;">
  <div style="font-size:10px;color:#3a5a70;margin-bottom:8px;">📊 最新週スコア ({last_wk} / {last_ws}) — スコア降順</div>
  <div id="latest-banner" style="display:flex;gap:8px;flex-wrap:wrap;">{banner_cards}</div>
</div>

<!-- 直近5日パネル（XAUUSD日次）-->
{'<div style="background:#07101a;border-bottom:1px solid #122030;padding:10px 16px;"><div style="font-size:10px;color:#3a5a70;margin-bottom:8px;">📅 XAUUSD 直近5営業日</div><div style="display:flex;gap:8px;flex-wrap:wrap;">' + recent_html + '</div></div>' if recent_html else ''}

<!-- 銘柄フィルター -->
<div style="background:#0a1520;border-bottom:1px solid #122030;padding:8px 16px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
  <span style="font-size:10px;color:#3a5a70;">表示銘柄:</span>
  {sym_filter_btns}
  <button class="ctrl-btn" onclick="selectAll()" style="margin-left:4px;">全選択</button>
  <button class="ctrl-btn" onclick="selectNone()">全解除</button>
  <div style="margin-left:auto;display:flex;gap:5px;align-items:center;flex-wrap:wrap;">
    <span style="font-size:9px;color:#2a4a60;">スコア:</span>
    {''.join(f'<div style="display:flex;align-items:center;gap:2px;"><div style="width:16px;height:11px;background:{bg};border-radius:2px;border:1px solid #1a3050;"></div><span style="font-size:8px;color:#4a6a80;">{lbl}</span></div>'
             for lbl,bg in [("≥80🔥","#ff4400"),("≥65","#ff9900"),("≥50★","#cccc00"),("≥38","#00a85e"),("≥27","#007040"),("低","#0c1018")])}
  </div>
</div>

<!-- 期間スライダー -->
<div style="background:#07101a;border-bottom:1px solid #0d1e2e;padding:8px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
  <span style="font-size:10px;color:#3a5a70;white-space:nowrap;">開始:</span>
  <div style="display:flex;flex-direction:column;gap:2px;flex:1;min-width:150px;max-width:300px;">
    <input type="range" id="rStart" min="0" max="{n_weeks-1}" value="0" oninput="updateRange()">
    <div id="lStart" style="font-size:9px;color:#5a8aaa;"></div>
  </div>
  <span style="font-size:10px;color:#3a5a70;white-space:nowrap;">終了:</span>
  <div style="display:flex;flex-direction:column;gap:2px;flex:1;min-width:150px;max-width:300px;">
    <input type="range" id="rEnd" min="0" max="{n_weeks-1}" value="{n_weeks-1}" oninput="updateRange()">
    <div id="lEnd" style="font-size:9px;color:#5a8aaa;"></div>
  </div>
  <button class="ctrl-btn" onclick="setRange(0,{n_weeks-1})">全期間</button>
  <button class="ctrl-btn" onclick="setRange(Math.max(0,{n_weeks-1}-52),{n_weeks-1})">直近1年</button>
  <button class="ctrl-btn" onclick="setRange(Math.max(0,{n_weeks-1}-26),{n_weeks-1})">直近6ヶ月</button>
  <button class="ctrl-btn" onclick="setRange(Math.max(0,{n_weeks-1}-13),{n_weeks-1})">直近3ヶ月</button>
</div>

<!-- ツールチップ -->
<div id="tip" style="min-height:34px;padding:5px 16px;font-size:10px;color:#1a2e40;">
  セルにカーソル/タップで詳細表示
</div>

<!-- グリッド -->
<div id="grid-wrap" style="overflow-x:auto;padding:0 16px 28px;-webkit-overflow-scrolling:touch;">
  {all_grids}
</div>

<script>
const WEEKS   = {weeks_json};
const ALL_SYMS = {syms_json};
const SYM_C   = {sym_c_json};
const TOOLTIP = {tooltip_json};
const RECENT5 = {recent_json};

let visibleSyms = new Set(ALL_SYMS);
let sortMode    = 'score';  // 'score' | 'alpha' | 'default'

// ── 週ラベル ──
function fmtWk(wk) {{
  const blocks = document.querySelectorAll('.sym-block');
  for(const b of blocks) {{
    const td = b.querySelector(`[data-wk="${{wk}}"]`);
    if(td) {{
      const tds = Array.from(b.querySelector('thead tr').children);
      const idx = tds.indexOf(td);
      if(idx > 0) {{
        return WEEKS[idx-1] || wk;
      }}
    }}
  }}
  return wk;
}}
function fmtWkLabel(wk) {{
  const parts = wk.split('-');
  return parts[0].slice(2) + '/' + parts[1];
}}

// ── 銘柄表示切替 ──
function toggleSym(sym, btn) {{
  if(visibleSyms.has(sym)) {{
    if(visibleSyms.size <= 1) return; // 最低1銘柄は表示
    visibleSyms.delete(sym);
    btn.classList.remove('active');
    btn.classList.add('inactive');
  }} else {{
    visibleSyms.add(sym);
    btn.classList.add('active');
    btn.classList.remove('inactive');
  }}
  applyVisibility();
}}
function selectAll() {{
  visibleSyms = new Set(ALL_SYMS);
  document.querySelectorAll('.sym-btn').forEach(b => {{
    b.classList.add('active'); b.classList.remove('inactive');
  }});
  applyVisibility();
}}
function selectNone() {{
  // 最初の1銘柄だけ残す
  visibleSyms = new Set([ALL_SYMS[0]]);
  document.querySelectorAll('.sym-btn').forEach(b => {{
    const sym = b.getAttribute('data-sym');
    if(sym === ALL_SYMS[0]) {{ b.classList.add('active'); b.classList.remove('inactive'); }}
    else {{ b.classList.remove('active'); b.classList.add('inactive'); }}
  }});
  applyVisibility();
}}
function applyVisibility() {{
  document.querySelectorAll('.sym-block').forEach(el => {{
    el.style.display = visibleSyms.has(el.getAttribute('data-sym')) ? '' : 'none';
  }});
}}

// ── 並び替え ──
function sortBy(mode) {{
  sortMode = mode;
  ['score','alpha','default'].forEach(m => {{
    document.getElementById('btn-'+m).classList.toggle('active', m===mode);
  }});
  const wrap  = document.getElementById('grid-wrap');
  const blocks = Array.from(wrap.querySelectorAll('.sym-block'));
  if(mode === 'score') {{
    blocks.sort((a,b) => parseFloat(b.dataset.lastscore||0) - parseFloat(a.dataset.lastscore||0));
  }} else if(mode === 'alpha') {{
    blocks.sort((a,b) => a.dataset.sym.localeCompare(b.dataset.sym));
  }} else {{
    // デフォルト順（ALL_SYMSの順）
    blocks.sort((a,b) => ALL_SYMS.indexOf(a.dataset.sym) - ALL_SYMS.indexOf(b.dataset.sym));
  }}
  blocks.forEach(b => wrap.appendChild(b));
}}

// ── 期間スライダー ──
function updateRange() {{
  var s = parseInt(document.getElementById('rStart').value);
  var e = parseInt(document.getElementById('rEnd').value);
  if(s > e) {{ var tmp=s; s=e; e=tmp; }}
  document.getElementById('lStart').textContent = fmtWkLabel(WEEKS[s]) + ' (' + WEEKS[s] + ')';
  document.getElementById('lEnd').textContent   = fmtWkLabel(WEEKS[e]) + ' (' + WEEKS[e] + ')';
  document.querySelectorAll('.sym-block table tbody tr').forEach(function(row) {{
    var tds = row.querySelectorAll('td');
    tds.forEach(function(td, idx) {{
      if(idx===0 || idx===tds.length-1) return;
      td.style.display = (idx-1>=s && idx-1<=e) ? '' : 'none';
    }});
  }});
  document.querySelectorAll('.sym-block table thead tr').forEach(function(row) {{
    var ths = row.querySelectorAll('td,th');
    ths.forEach(function(th, idx) {{
      if(idx===0 || idx===ths.length-1) return;
      th.style.display = (idx-1>=s && idx-1<=e) ? '' : 'none';
    }});
  }});
}}
function setRange(s,e) {{
  document.getElementById('rStart').value = s;
  document.getElementById('rEnd').value   = e;
  updateRange();
}}

// ── ツールチップ ──
document.addEventListener('mouseover', function(e) {{
  var cell = e.target.closest('.cell');
  if(!cell) {{
    document.getElementById('tip').innerHTML =
      '<span style="color:#1a2e40">セルにカーソル/タップで詳細表示</span>';
    return;
  }}
  var wk  = cell.getAttribute('data-wk');
  var sym = cell.getAttribute('data-sym');
  if(!wk||!sym||!TOOLTIP[wk]||!TOOLTIP[wk][sym]) return;
  var t   = TOOLTIP[wk][sym];
  var sc  = SYM_C[sym] || '#aaa';
  var bonus = (1+(t.h4p30/100)*0.5).toFixed(2);
  var lbl_map = [
    [80,"🔥 爆発"],[65,"🔶 超強"],[50,"⭐ 候補"],
    [38,"✅ 良い"],[27,"🔹 OK"],[18,"⬜ 様子見"],[10,"⬛ 弱い"],[0,"⬛ 見送り"]
  ];
  var grade = lbl_map.find(([th])=>t.s>=th)[1];
  document.getElementById('tip').innerHTML =
    '<div style="display:flex;gap:10px;background:#0a1520;border:1px solid #122030;' +
    'border-radius:6px;padding:5px 14px;flex-wrap:wrap;align-items:center;">' +
    '<span style="color:'+sc+';font-weight:700;font-size:12px;">'+sym+'</span>' +
    '<span style="color:#2a4a60;">'+wk+' ('+t.ws+')</span>' +
    '<span style="color:#3a5a70;">│</span>' +
    '<span style="font-size:15px;font-weight:700;color:#ffd700;">📊 '+Math.round(t.s)+'点</span>' +
    '<span style="color:#88aa44;">'+grade+'</span>' +
    '<span style="color:#3a5a70;">│</span>' +
    '<span>H1avg: <b style="color:#aaccff;">'+(t.h1a).toFixed(2)+'</b></span>' +
    '<span>H4≥20: <b style="color:#ffcc44;">'+(t.h4p20).toFixed(1)+'%</b></span>' +
    '<span>H4≥30: <b style="color:#ff88cc;">'+(t.h4p30).toFixed(1)+'%</b>' +
    ' <span style="font-size:9px;color:#3a5070;">(x'+bonus+')</span></span>' +
    '</div>';
}});

// ── 初期化 ──
window.onload = function() {{
  document.getElementById('lStart').textContent = fmtWkLabel(WEEKS[0]) + ' (' + WEEKS[0] + ')';
  document.getElementById('lEnd').textContent   = fmtWkLabel(WEEKS[WEEKS.length-1]) + ' (' + WEEKS[WEEKS.length-1] + ')';
  // デフォルト: 直近26週表示
  setRange(Math.max(0, WEEKS.length-26), WEEKS.length-1);
  // デフォルト: スコア順
  sortBy('score');
  var wrap = document.getElementById('grid-wrap');
  setTimeout(()=>{{ wrap.scrollLeft = wrap.scrollWidth; }}, 100);
}};
</script>
</body>
</html>"""
    return html


def main():
    print("=== generate_html.py v3 開始 ===")
    raw_data = load_csv(CSV_PATH)
    recent5  = load_recent5(DATA_PATH)
    print(f"日次スコア: {len(recent5)}件")
    os.makedirs("docs", exist_ok=True)
    html = generate_html(raw_data, recent5)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] {HTML_PATH} 生成完了 ({len(html)//1024}KB)")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
