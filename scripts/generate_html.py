"""
generate_html.py v5
MT5出力CSV → 軽量ヒートマップHTML（JSでDOM動的生成）
- Pythonのf-stringとJSテンプレートリテラルの衝突を完全解消
- 週ラベルをWeekStart日付（03/30形式）で表示
- 期間スライダー連動のAVGリアルタイム更新
- 表示銘柄選択・並び替え対応
"""

import json, os, csv, io, math
from datetime import datetime, timezone, timedelta


def _find_csv():
    for p in ["data/adx_weekly.csv", "data/adx_Weekly.csv",
              "data/ADX_Weekly.csv", "data/ADX_Weekly_Above_v2.csv"]:
        if os.path.exists(p):
            print(f"  CSV検出: {p}")
            return p
    return "data/adx_weekly.csv"


CSV_PATH  = _find_csv()
DATA_PATH = "data/scores.json"
HTML_PATH = "docs/index.html"
JST       = timezone(timedelta(hours=9))

SYM_COLORS = {
    "XAUUSD": "#ffd700", "XAGUSD": "#cccccc", "USDCAD": "#44ccff",
    "AUDUSD": "#88ffcc", "USDJPY": "#ff99cc", "EURUSD": "#bb88ff",
    "BTCUSD": "#ff8844",
}
SYM_ORDER = list(SYM_COLORS.keys())


# ── スコア計算 ───────────────────────────────────────
def calc_score(h1a, h4p20, h4p30):
    h1n  = max(0, min(100, (h1a - 10) / 30 * 100))
    base = math.sqrt(max(0.1, h1n) * max(0.1, h4p20)) * 0.85
    return round(min(100, base * (1 + h4p30 / 100 * 0.5)), 1)


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

    data = {}
    for row in csv.DictReader(io.StringIO(text)):
        sym  = row.get("Symbol", "").strip()
        week = row.get("Week", "").strip()
        ws   = row.get("WeekStart", "").strip()
        if not sym or not week:
            continue
        try:
            h1a   = float(row.get("H1_AvgADX",      0))
            h4p20 = float(row.get("H4_Pct_Above20", 0))
            h4p30 = float(row.get("H4_Pct_Above30", 0))
        except Exception:
            continue
        data.setdefault(sym, {})[week] = {
            "ws":    ws,
            "h1a":   round(h1a, 2),
            "h4p20": round(h4p20, 1),
            "h4p30": round(h4p30, 1),
            "score": calc_score(h1a, h4p20, h4p30),
        }
    for sym, wks in data.items():
        print(f"  {sym}: {len(wks)}週")
    return data


# ── 日次スコア読み込み ───────────────────────────────
def load_recent5(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        recs = json.load(f)
    wd = [r for r in recs
          if datetime.strptime(r["date"], "%Y-%m-%d").weekday() < 5]
    return wd[-5:] if len(wd) >= 5 else wd


# ── 週ラベル生成（WeekStart日付から）───────────────
def make_week_labels(all_weeks, raw_data, all_syms):
    """
    "2026.03.30" → "03/30"
    年変わりの最初の週は "'26 01/06" 形式
    """
    labels = {}
    prev_yr = None
    ref_sym = all_syms[0] if all_syms else ""
    for wk in all_weeks:
        ws = raw_data.get(ref_sym, {}).get(wk, {}).get("ws", "")
        if ws and len(ws) >= 10:
            yr   = ws[:4]
            mmdd = ws[5:7] + "/" + ws[8:10]
            if yr != prev_yr:
                labels[wk] = f"'{yr[2:]} {mmdd}"
                prev_yr = yr
            else:
                labels[wk] = mmdd
        else:
            labels[wk] = wk[-3:]
    return labels


# ── 直近5日パネルHTML ────────────────────────────────
def make_recent_panel(recent5):
    if not recent5:
        return ""

    def score_style(s):
        if s >= 80: return "#ff4400", "#fff"
        if s >= 65: return "#ff9900", "#000"
        if s >= 50: return "#cccc00", "#000"
        if s >= 38: return "#00a85e", "#fff"
        if s >= 27: return "#007040", "#fff"
        if s >= 18: return "#1a3d25", "#88ccaa"
        if s >= 10: return "#252500", "#aaaa44"
        return "#0c1018", "#2a3a48"

    def score_lbl(s):
        for thr, lbl in [(80,"最強🔥"),(65,"超強✅"),(50,"★候補"),
                         (38,"良い"),(27,"OK"),(18,"様子見⚠️"),(10,"弱い"),(0,"NG❌")]:
            if s >= thr: return lbl
        return "NG❌"

    cards = ""
    for r in recent5:
        s   = calc_score(r["h1_avg_adx"], r["h4_pct20"], r["h4_pct30"])
        bg, tx = score_style(s)
        dt  = datetime.strptime(r["date"], "%Y-%m-%d")
        dow = ["月","火","水","木","金","土","日"][dt.weekday()]
        d   = r["date"][5:].replace("-", "/")
        lbl = score_lbl(s)
        cards += (
            f'<div style="background:{bg};border:1px solid #1a3050;border-radius:8px;'
            f'padding:8px 10px;text-align:center;min-width:82px;">'
            f'<div style="font-size:9px;color:#5a8aaa;margin-bottom:3px;">{d}({dow})</div>'
            f'<div style="font-size:20px;font-weight:800;color:{tx};line-height:1;">{int(round(s))}</div>'
            f'<div style="font-size:8px;font-weight:700;color:{tx};margin-top:2px;">{lbl}</div>'
            f'<div style="margin-top:5px;border-top:1px solid rgba(255,255,255,0.1);'
            f'padding-top:3px;font-size:7px;color:#6a9ab0;">'
            f'H1avg <b style="color:#aaccff;">{r["h1_avg_adx"]}</b><br>'
            f'H4≥20 <b style="color:#ffcc44;">{r["h4_pct20"]}%</b><br>'
            f'H4≥30 <b style="color:#ff88cc;">{r["h4_pct30"]}%</b>'
            f'</div></div>'
        )
    return (
        '<div style="background:#07101a;border-bottom:1px solid #122030;padding:10px 16px;">'
        '<div style="font-size:10px;color:#3a5a70;margin-bottom:8px;">📅 XAUUSD 直近5営業日</div>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;">{cards}</div>'
        '</div>'
    )


# ── JSコード（raw文字列 → プレースホルダー置換） ─────
# ※ JSのテンプレートリテラル ${...} をPythonのf-stringと混在させないために
#    JSコードをraw文字列として定義し、Python変数は <<<VAR>>> で差し込む
JS_CODE = r"""
const RAW    = <<<RAW_JSON>>>;
const WEEKS  = <<<WEEKS_JSON>>>;
const LABELS = <<<LABELS_JSON>>>;
const SYMS   = <<<SYMS_JSON>>>;
const SYM_C  = <<<SYMC_JSON>>>;

let curS = 0, curE = WEEKS.length - 1;
let visibleSyms = new Set(SYMS);
let sortMode = 'score';

// ── スコア→色 ──────────────────────────────────────
function scoreStyle(s) {
  if(s==null) return ['#0c1018','#2a3a48'];
  if(s>=80) return ['#ff4400','#fff'];
  if(s>=65) return ['#ff9900','#000'];
  if(s>=50) return ['#cccc00','#000'];
  if(s>=38) return ['#00a85e','#fff'];
  if(s>=27) return ['#007040','#fff'];
  if(s>=18) return ['#1a3d25','#88ccaa'];
  if(s>=10) return ['#252500','#aaaa44'];
  if(s>=4)  return ['#1a1400','#555533'];
  return ['#0c1018','#2a3a48'];
}
function h1Style(v) {
  if(v==null) return ['#0c1018','#2a3a48'];
  if(v>=35) return ['#ff9900','#000'];
  if(v>=30) return ['#00ffb3','#001a0e'];
  if(v>=24) return ['#00a85e','#fff'];
  if(v>=20) return ['#007040','#fff'];
  if(v>=17) return ['#2a2a00','#aaaa44'];
  return ['#0c1018','#2a3a48'];
}
function pctStyle(v) {
  if(v==null) return ['#0c1018','#2a3a48'];
  if(v>=75) return ['#00ffb3','#001a0e'];
  if(v>=60) return ['#00d97e','#001a0e'];
  if(v>=45) return ['#00a85e','#fff'];
  if(v>=30) return ['#007040','#fff'];
  if(v>=15) return ['#1a3d25','#88ccaa'];
  if(v>=5)  return ['#252500','#aaaa44'];
  return ['#0c1018','#2a3a48'];
}
function scoreLabel(s) {
  if(s>=80) return '🔥最強'; if(s>=65) return '✅超強';
  if(s>=50) return '⭐候補';  if(s>=38) return '良い';
  if(s>=27) return 'OK';     if(s>=18) return '⚠️様子見';
  if(s>=10) return '弱い';   return 'NG❌';
}

// ── AVG計算（表示期間のみ）────────────────────────
function calcAvg(sym, key, s, e) {
  const vals = [];
  for(let i = s; i <= e; i++) {
    const r = RAW[sym]?.[WEEKS[i]];
    if(!r) continue;
    const v = key === 'score' ? r.score : r[key];
    if(v != null) vals.push(v);
  }
  return vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null;
}

// ── セル要素生成 ───────────────────────────────────
function makeCell(sym, wk, val, styleFn, h, bold) {
  const td = document.createElement('td');
  td.className = 'cell';
  td.dataset.sym = sym;
  td.dataset.wk  = wk;
  const [bg, tx] = styleFn(val);
  const fs   = bold ? 8 : 7;
  const fw   = bold ? 700 : 600;
  td.style.cssText =
    'background:' + bg + ';width:24px;height:' + h + 'px;text-align:center;' +
    'font-size:' + fs + 'px;color:' + tx + ';font-weight:' + fw + ';border-radius:2px;';
  if(val != null) {
    td.textContent = bold
      ? Math.round(val)
      : (Number.isInteger(val) ? val : val.toFixed(1));
  }
  td.addEventListener('mouseenter', showTip);
  td.addEventListener('mouseleave', hideTip);
  return td;
}

// ── 1銘柄ブロック生成 ─────────────────────────────
function buildSymBlock(sym) {
  const sc      = SYM_C[sym] || '#aaa';
  const symData = RAW[sym] || {};
  const lastWk  = WEEKS[WEEKS.length - 1];

  const wrap = document.createElement('div');
  wrap.className = 'sym-block';
  wrap.dataset.sym = sym;
  wrap.dataset.lastscore = symData[lastWk]?.score ?? 0;
  wrap.style.marginBottom = '22px';

  // 銘柄ラベル
  const title = document.createElement('div');
  title.style.cssText =
    'font-size:13px;font-weight:700;color:' + sc +
    ';margin-bottom:3px;padding-left:106px;letter-spacing:1px;';
  title.textContent = sym;
  wrap.appendChild(title);

  const table = document.createElement('table');

  // ── thead ──
  const thead = document.createElement('thead');
  const hRow  = document.createElement('tr');

  const thLabel = document.createElement('th');
  thLabel.className = 'sticky-head';
  thLabel.style.cssText = 'min-width:102px;width:102px;';
  hRow.appendChild(thLabel);

  WEEKS.forEach((wk, i) => {
    const th  = document.createElement('td');
    th.dataset.col = i;
    const lbl = LABELS[wk] || wk.slice(-3);
    const isYr = lbl.startsWith("'");
    th.style.cssText =
      'width:24px;text-align:center;font-size:7px;padding-bottom:4px;' +
      'color:' + (isYr ? '#8a9a60' : '#3a4020') + ';' +
      'font-weight:' + (isYr ? '700' : '400') + ';' +
      (isYr ? 'border-left:1px solid #2a3010;' : '');
    th.textContent = lbl;
    hRow.appendChild(th);
  });

  // AVGヘッダー（期間表示中の平均であることを明示）
  const thAvg = document.createElement('th');
  thAvg.className = 'sticky-avg';
  thAvg.style.cssText =
    'width:52px;font-size:8px;color:#5a8aaa;text-align:center;' +
    'padding-left:6px;border-left:1px solid #1a2000;background:#060b10;';
  thAvg.textContent = '期間AVG';
  hRow.appendChild(thAvg);
  thead.appendChild(hRow);
  table.appendChild(thead);

  // ── tbody ──
  const tbody = document.createElement('tbody');
  const rowDefs = [
    {key:'score', label:'📊 相場点数', fn:scoreStyle, h:28, bold:true},
    {key:'h1a',   label:'H1 avgADX',  fn:h1Style,    h:20, bold:false},
    {key:'h4p20', label:'H4 ≥20%',   fn:pctStyle,   h:20, bold:false},
    {key:'h4p30', label:'H4 ≥30%',   fn:pctStyle,   h:20, bold:false},
  ];

  rowDefs.forEach((rd, ri) => {
    const tr = document.createElement('tr');

    // 行ラベル
    const tdL = document.createElement('td');
    tdL.className = 'sticky-label';
    tdL.style.cssText =
      'font-size:' + (rd.bold ? 10 : 9) + 'px;' +
      'font-weight:' + (rd.bold ? 700 : 500) + ';' +
      'color:' + (rd.bold ? '#7ab8d8' : '#4a7a90') + ';' +
      'padding-right:6px;padding-left:4px;white-space:nowrap;';
    tdL.textContent = rd.label;
    tr.appendChild(tdL);

    // 週セル
    WEEKS.forEach((wk, i) => {
      const r   = symData[wk];
      const val = r ? r[rd.key] : null;
      const td  = makeCell(sym, wk, val, rd.fn, rd.h, rd.bold);
      td.dataset.col = i;
      if(wk.endsWith('W01'))  td.style.borderLeft = '1px solid #2a3010';
      if(wk === lastWk)       td.style.outline    = '2px solid #ffd700';
      tr.appendChild(td);
    });

    // AVGセル
    const tdA = document.createElement('td');
    tdA.className  = 'avg-cell sticky-avg';
    tdA.dataset.sym = sym;
    tdA.dataset.key = rd.key;
    tdA.style.cssText =
      'text-align:center;font-size:' + (rd.bold ? 12 : 9) + 'px;' +
      'font-weight:700;padding-left:6px;border-left:1px solid #1a2000;' +
      'border-radius:2px;height:' + rd.h + 'px;';
    tr.appendChild(tdA);
    tbody.appendChild(tr);

    // スコア行の後に隙間
    if(ri === 0) {
      const sp  = document.createElement('tr');
      const std = document.createElement('td');
      std.colSpan = WEEKS.length + 2;
      std.style.height = '3px';
      sp.appendChild(std);
      tbody.appendChild(sp);
    }
  });

  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

// ── グリッド構築 ───────────────────────────────────
function buildGrid() {
  const wrap = document.getElementById('grid-wrap');
  wrap.innerHTML = '';
  getOrderedSyms().forEach(sym => {
    if(visibleSyms.has(sym)) wrap.appendChild(buildSymBlock(sym));
  });
  applyRange();
  updateAvg();
  updateBanner();
}

// ── 表示範囲適用 ──────────────────────────────────
function applyRange() {
  const s = curS, e = curE;
  document.querySelectorAll('[data-col]').forEach(el => {
    const i = parseInt(el.dataset.col);
    el.style.display = (i >= s && i <= e) ? '' : 'none';
  });
}

// ── AVG更新（期間連動）────────────────────────────
function updateAvg() {
  document.querySelectorAll('.avg-cell').forEach(td => {
    const sym = td.dataset.sym;
    const key = td.dataset.key;
    const avg = calcAvg(sym, key, curS, curE);
    if(key === 'score') {
      const [bg, tx] = scoreStyle(avg);
      td.style.background = bg;
      td.style.color      = tx;
      td.textContent = avg != null ? Math.round(avg) : '';
    } else {
      td.style.background = '#0a1520';
      td.style.color      = '#5a8aaa';
      td.textContent = avg != null
        ? (key === 'h1a' ? avg.toFixed(1) : Math.round(avg))
        : '';
    }
  });
}

// ── バナー更新 ────────────────────────────────────
function updateBanner() {
  const lastWk = WEEKS[WEEKS.length - 1];
  const lastWs = Object.values(RAW)[0]?.[lastWk]?.ws || '';
  const lbl    = document.getElementById('banner-label');
  if(lbl) lbl.textContent =
    '📊 最新週スコア (' + lastWk + ' / ' + lastWs + ') — スコア降順';

  const items = SYMS
    .map(sym => { const r = RAW[sym]?.[lastWk]; return r ? {sym,score:r.score,h4p30:r.h4p30} : null; })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score);

  const banner = document.getElementById('latest-banner');
  banner.innerHTML = '';
  items.forEach(({sym, score, h4p30}) => {
    const sc        = SYM_C[sym] || '#aaa';
    const [bg, tx]  = scoreStyle(score);
    const lbl_score = scoreLabel(score);
    const card      = document.createElement('div');
    card.style.cssText =
      'background:' + bg + ';border-radius:8px;padding:10px 14px;' +
      'text-align:center;min-width:100px;border:1px solid ' + sc + '44;';
    card.innerHTML =
      '<div style="font-size:10px;font-weight:700;color:' + sc + ';">' + sym + '</div>' +
      '<div style="font-size:26px;font-weight:700;color:' + tx + ';line-height:1;">' + Math.round(score) + '</div>' +
      '<div style="font-size:9px;color:' + tx + ';margin-top:2px;">' + lbl_score + '</div>' +
      '<div style="font-size:8px;color:' + tx + ';opacity:0.7;margin-top:2px;">H4_30:' + h4p30 + '%</div>';
    banner.appendChild(card);
  });
}

// ── 期間スライダー ────────────────────────────────
function updateRange() {
  let s = parseInt(document.getElementById('rStart').value);
  let e = parseInt(document.getElementById('rEnd').value);
  if(s > e) { let t = s; s = e; e = t; }
  curS = s; curE = e;
  document.getElementById('lStart').textContent =
    LABELS[WEEKS[s]] + ' (' + WEEKS[s] + ')';
  document.getElementById('lEnd').textContent =
    LABELS[WEEKS[e]] + ' (' + WEEKS[e] + ')';
  applyRange();
  updateAvg();
}
function setRange(s, e) {
  document.getElementById('rStart').value = s;
  document.getElementById('rEnd').value   = e;
  updateRange();
}

// ── 銘柄切替 ─────────────────────────────────────
function toggleSym(sym, btn) {
  if(visibleSyms.has(sym)) {
    if(visibleSyms.size <= 1) return;
    visibleSyms.delete(sym);
    btn.classList.remove('active'); btn.classList.add('inactive');
    document.querySelectorAll('.sym-block[data-sym="' + sym + '"]')
      .forEach(b => b.style.display = 'none');
  } else {
    visibleSyms.add(sym);
    btn.classList.add('active'); btn.classList.remove('inactive');
    document.querySelectorAll('.sym-block[data-sym="' + sym + '"]')
      .forEach(b => b.style.display = '');
  }
}
function selectAll() {
  visibleSyms = new Set(SYMS);
  document.querySelectorAll('.sym-btn').forEach(b => {
    b.classList.add('active'); b.classList.remove('inactive');
  });
  document.querySelectorAll('.sym-block').forEach(b => b.style.display = '');
}
function selectNone() {
  visibleSyms = new Set([SYMS[0]]);
  document.querySelectorAll('.sym-btn').forEach(b => {
    const s = b.dataset.sym;
    if(s === SYMS[0]) { b.classList.add('active'); b.classList.remove('inactive'); }
    else { b.classList.remove('active'); b.classList.add('inactive'); }
  });
  document.querySelectorAll('.sym-block').forEach(b => {
    b.style.display = b.dataset.sym === SYMS[0] ? '' : 'none';
  });
}

// ── 並び替え ─────────────────────────────────────
function getOrderedSyms() {
  const order  = [...SYMS];
  const lastWk = WEEKS[WEEKS.length - 1];
  if(sortMode === 'score') {
    order.sort((a, b) => (RAW[b]?.[lastWk]?.score || 0) - (RAW[a]?.[lastWk]?.score || 0));
  } else if(sortMode === 'alpha') {
    order.sort((a, b) => a.localeCompare(b));
  }
  return order;
}
function sortBy(mode) {
  sortMode = mode;
  ['score','alpha','default'].forEach(m =>
    document.getElementById('btn-' + m).classList.toggle('active', m === mode)
  );
  const wrap   = document.getElementById('grid-wrap');
  const order  = getOrderedSyms();
  const blocks = {};
  wrap.querySelectorAll('.sym-block').forEach(b => blocks[b.dataset.sym] = b);
  order.forEach(sym => { if(blocks[sym]) wrap.appendChild(blocks[sym]); });
}

// ── ツールチップ ─────────────────────────────────
function showTip(e) {
  const cell = e.currentTarget;
  const wk   = cell.dataset.wk;
  const sym  = cell.dataset.sym;
  const r    = RAW[sym]?.[wk];
  if(!r) return;
  const sc    = SYM_C[sym] || '#aaa';
  const bonus = (1 + (r.h4p30 / 100) * 0.5).toFixed(2);
  const lbl   = scoreLabel(r.score);
  const wsLbl = LABELS[wk] ? LABELS[wk] + ' (' + wk + ')' : wk;
  document.getElementById('tip').innerHTML =
    '<div style="display:flex;gap:10px;background:#0a1520;border:1px solid #122030;' +
    'border-radius:6px;padding:5px 14px;flex-wrap:wrap;align-items:center;">' +
    '<span style="color:' + sc + ';font-weight:700;font-size:12px;">' + sym + '</span>' +
    '<span style="color:#2a4a60;">' + wsLbl + '（' + r.ws + '週始）</span>' +
    '<span style="color:#3a5a70;">│</span>' +
    '<span style="font-size:15px;font-weight:700;color:#ffd700;">📊 ' + Math.round(r.score) + '点</span>' +
    '<span style="color:#88aa44;">' + lbl + '</span>' +
    '<span style="color:#3a5a70;">│</span>' +
    '<span>H1avg: <b style="color:#aaccff;">' + r.h1a.toFixed(2) + '</b></span>' +
    '<span>H4≥20: <b style="color:#ffcc44;">' + r.h4p20.toFixed(1) + '%</b></span>' +
    '<span>H4≥30: <b style="color:#ff88cc;">' + r.h4p30.toFixed(1) + '%</b>' +
    '<span style="font-size:9px;color:#3a5070;"> (x' + bonus + ')</span></span>' +
    '</div>';
}
function hideTip() {
  document.getElementById('tip').innerHTML =
    '<span style="color:#1a2e40">セルにカーソル/タップで詳細表示</span>';
}

// ── 初期化 ───────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  buildGrid();
  setRange(Math.max(0, WEEKS.length - 26), WEEKS.length - 1);
  sortBy('score');
  setTimeout(() => {
    document.getElementById('grid-wrap').scrollLeft = 99999;
  }, 150);
});
"""


# ── HTML生成 ─────────────────────────────────────────
def generate_html(raw_data, recent5):
    now_jst   = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    all_weeks = sorted({w for d in raw_data.values() for w in d})
    all_syms  = ([s for s in SYM_ORDER if s in raw_data] +
                 [s for s in sorted(raw_data) if s not in SYM_ORDER])
    n = len(all_weeks)

    week_labels  = make_week_labels(all_weeks, raw_data, all_syms)
    recent_panel = make_recent_panel(recent5)

    # 銘柄フィルターボタン
    sym_btns = ""
    for sym in all_syms:
        sc = SYM_COLORS.get(sym, "#aaa")
        sym_btns += (
            f'<button class="sym-btn active" data-sym="{sym}"'
            f' onclick="toggleSym(\'{sym}\',this)"'
            f' style="background:#0d1e30;border:1px solid {sc}66;border-radius:4px;'
            f'color:{sc};font-size:11px;padding:4px 10px;cursor:pointer;'
            f'font-family:inherit;font-weight:700;">{sym}</button>\n    '
        )

    # 凡例
    legend = "".join(
        f'<div style="display:flex;align-items:center;gap:2px;">'
        f'<div style="width:14px;height:10px;background:{bg};border-radius:2px;"></div>'
        f'<span style="font-size:8px;color:#4a6a80;">{lbl}</span></div>'
        for lbl, bg in [("≥80🔥","#ff4400"),("≥65","#ff9900"),("≥50★","#cccc00"),
                        ("≥38","#00a85e"),("≥27","#007040"),("低","#0c1018")]
    )

    # JSデータをプレースホルダーで差し込む
    js_rendered = (JS_CODE
        .replace("<<<RAW_JSON>>>",    json.dumps(raw_data,    ensure_ascii=False))
        .replace("<<<WEEKS_JSON>>>",  json.dumps(all_weeks,   ensure_ascii=False))
        .replace("<<<LABELS_JSON>>>", json.dumps(week_labels, ensure_ascii=False))
        .replace("<<<SYMS_JSON>>>",   json.dumps(all_syms,    ensure_ascii=False))
        .replace("<<<SYMC_JSON>>>",   json.dumps(SYM_COLORS,  ensure_ascii=False))
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ADX Score Dashboard</title>
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
.sym-btn.inactive{{opacity:0.28;}}
.cbtn{{background:transparent;border:1px solid #1a3050;border-radius:4px;color:#3a5a70;font-size:10px;padding:4px 10px;cursor:pointer;font-family:inherit;white-space:nowrap;}}
.cbtn:hover{{border-color:#3a5a70;color:#7ab8d8;}}
.cbtn.active{{background:#0a2030;border-color:#2266aa;color:#44aaff;font-weight:700;}}
#grid-wrap{{overflow-x:auto;padding:0 16px 28px;-webkit-overflow-scrolling:touch;}}
table{{border-collapse:separate;border-spacing:2px;min-width:max-content;}}
.sticky-label{{position:sticky;left:0;background:#060b10;z-index:2;}}
.sticky-avg{{position:sticky;right:0;z-index:2;}}
.sticky-head{{position:sticky;left:0;background:#060b10;z-index:3;}}
</style>
</head>
<body>

<div style="background:linear-gradient(135deg,#0a1828,#060b10);border-bottom:1px solid #122030;padding:12px 18px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">
  <div>
    <div style="font-size:9px;color:#2a4a60;letter-spacing:2px;margin-bottom:2px;">ADX Score = sqrt(H1norm x H4_20) x 0.85 x (1 + H4_30x0.5) | MT5 iADX準拠</div>
    <div style="font-size:18px;font-weight:700;color:#d8f0ff;">⚡ ADX Score Dashboard</div>
    <div style="font-size:9px;color:#2a4a60;margin-top:2px;">更新: {now_jst} | {n}週 | {len(all_syms)}銘柄</div>
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
    <span style="font-size:10px;color:#3a5a70;">並び替え:</span>
    <button class="cbtn active" id="btn-score" onclick="sortBy('score')">スコア順↓</button>
    <button class="cbtn" id="btn-alpha" onclick="sortBy('alpha')">銘柄名順</button>
    <button class="cbtn" id="btn-default" onclick="sortBy('default')">デフォルト</button>
  </div>
</div>

<div style="background:#0a1520;border-bottom:1px solid #122030;padding:10px 18px;">
  <div id="banner-label" style="font-size:10px;color:#3a5a70;margin-bottom:8px;">📊 最新週スコア</div>
  <div id="latest-banner" style="display:flex;gap:8px;flex-wrap:wrap;"></div>
</div>

{recent_panel}

<div style="background:#0a1520;border-bottom:1px solid #122030;padding:8px 16px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
  <span style="font-size:10px;color:#3a5a70;">表示銘柄:</span>
  {sym_btns}
  <button class="cbtn" onclick="selectAll()">全選択</button>
  <button class="cbtn" onclick="selectNone()">全解除</button>
  <div style="margin-left:auto;display:flex;gap:4px;align-items:center;flex-wrap:wrap;">
    <span style="font-size:9px;color:#2a4a60;">凡例:</span>
    {legend}
  </div>
</div>

<div style="background:#07101a;border-bottom:1px solid #0d1e2e;padding:8px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
  <span style="font-size:10px;color:#3a5a70;white-space:nowrap;">開始:</span>
  <div style="display:flex;flex-direction:column;gap:2px;flex:1;min-width:140px;max-width:280px;">
    <input type="range" id="rStart" min="0" max="{n-1}" value="0" oninput="updateRange()">
    <div id="lStart" style="font-size:9px;color:#5a8aaa;"></div>
  </div>
  <span style="font-size:10px;color:#3a5a70;white-space:nowrap;">終了:</span>
  <div style="display:flex;flex-direction:column;gap:2px;flex:1;min-width:140px;max-width:280px;">
    <input type="range" id="rEnd" min="0" max="{n-1}" value="{n-1}" oninput="updateRange()">
    <div id="lEnd" style="font-size:9px;color:#5a8aaa;"></div>
  </div>
  <button class="cbtn" onclick="setRange(0,{n-1})">全期間</button>
  <button class="cbtn" onclick="setRange(Math.max(0,{n-1}-52),{n-1})">直近1年</button>
  <button class="cbtn" onclick="setRange(Math.max(0,{n-1}-26),{n-1})">直近6ヶ月</button>
  <button class="cbtn" onclick="setRange(Math.max(0,{n-1}-13),{n-1})">直近3ヶ月</button>
</div>

<div id="tip" style="min-height:34px;padding:5px 16px;font-size:10px;color:#1a2e40;">
  セルにカーソル/タップで詳細表示
</div>

<div id="grid-wrap"></div>

<script>
{js_rendered}
</script>
</body>
</html>"""
    return html


# ── メイン ───────────────────────────────────────────
def main():
    print("=== generate_html.py v5 開始 ===")
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
