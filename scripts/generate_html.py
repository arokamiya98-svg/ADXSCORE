"""
generate_html.py
data/scores.json（日次）→ 週次集計 → docs/index.html（ヒートマップ）生成
f-string内のJSX三項演算子衝突を回避するため、
HTMLテンプレートを通常文字列で定義し、プレースホルダー置換方式を採用
"""

import json
import os
from datetime import datetime, timezone, timedelta

DATA_PATH = "data/scores.json"
HTML_PATH = "docs/index.html"
JST       = timezone(timedelta(hours=9))

SYMBOLS = ["XAUUSD"]
# SYMBOLS = ["XAUUSD", "USDCAD", "AUDUSD", "USDJPY"]  # 将来拡張用


# ── 日付 → ISO週ラベル（月曜起算）────────────────────
def to_week_key(date_str: str) -> str:
    dt  = datetime.strptime(date_str, "%Y-%m-%d")
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_start(week_key: str) -> str:
    year, w  = week_key.split("-W")
    monday   = datetime.fromisocalendar(int(year), int(w), 1)
    return monday.strftime("%Y.%m.%d")


# ── 日次 → 週次集計 ──────────────────────────────────
def aggregate_to_weekly(records: list[dict], symbol: str) -> dict:
    by_week: dict[str, list[dict]] = {}
    for r in records:
        if r.get("symbol", "XAUUSD") != symbol:
            continue
        wk = to_week_key(r["date"])
        by_week.setdefault(wk, []).append(r)

    result = {}
    for wk, recs in sorted(by_week.items()):
        h1_vals = [r["h1_avg_adx"] for r in recs]
        h4p20   = [r["h4_pct20"]   for r in recs]
        h4p30   = [r["h4_pct30"]   for r in recs]
        result[wk] = {
            "ws":    week_start(wk),
            "h1a":   round(sum(h1_vals) / len(h1_vals), 2),
            "h4p20": round(sum(h4p20)   / len(h4p20),   1),
            "h4p30": round(sum(h4p30)   / len(h4p30),   1),
        }
    return result


# ── HTMLテンプレート（プレースホルダー: <<<VAR>>>）─────
# JSX内の {} は全てそのまま書ける（f-stringを使わないため）
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XAUUSD ADX Score — 週次ヒートマップ</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#060b10;font-family:'IBM Plex Mono','Courier New',monospace;color:#b0c8e0;}
::-webkit-scrollbar{width:5px;height:5px;}
::-webkit-scrollbar-track{background:#0a1520;}
::-webkit-scrollbar-thumb{background:#1a3050;border-radius:3px;}
.cell{border-radius:2px;transition:filter 0.08s;cursor:default;}
.cell:hover{filter:brightness(1.6)!important;}
input[type=range]{-webkit-appearance:none;height:4px;border-radius:2px;background:#1a3050;outline:none;}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:#44aaff;cursor:pointer;}
</style>
</head>
<body>
<div id="root"></div>

<script>
// ── 自動生成データ（GitHub Actions が毎日更新）──
const RAW        = <<<RAW_JSON>>>;
const ALL_WEEKS  = <<<WEEKS_JSON>>>;
const ALL_SYMS   = <<<SYMS_JSON>>>;
const RECENT_5   = <<<RECENT_JSON>>>;
const UPDATED_AT = "<<<UPDATED_AT>>>";
</script>

<script type="text/babel">
const {useState, useMemo, useEffect, useRef} = React;

const SYM_C = {
  XAUUSD:"#ffd700", USDCAD:"#44ccff",
  AUDUSD:"#88ffcc", USDJPY:"#ff99cc"
};
const ML = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ── ADXスコア計算（設計書準拠）──
function calcScore(h1a, h4p20, h4p30) {
  if(h1a==null||h4p20==null||h4p30==null) return null;
  const h1norm = Math.max(0, Math.min(100, (h1a - 10) / 30 * 100));
  const a      = Math.max(0.1, h1norm);
  const b      = Math.max(0.1, h4p20);
  const base   = Math.sqrt(a * b) * 0.85;
  const bonus  = 1.0 + (h4p30 / 100) * 0.5;
  return Math.min(100, base * bonus);
}

// ── カラー関数 ──
function scoreColor(s) {
  if(s==null) return {bg:"#0c1018",tx:"#1e2e3e"};
  if(s>=80)   return {bg:"#ff4400",tx:"#fff"};
  if(s>=65)   return {bg:"#ff9900",tx:"#000"};
  if(s>=50)   return {bg:"#cccc00",tx:"#000"};
  if(s>=38)   return {bg:"#00a85e",tx:"#fff"};
  if(s>=27)   return {bg:"#007040",tx:"#fff"};
  if(s>=18)   return {bg:"#1a3d25",tx:"#88ccaa"};
  if(s>=10)   return {bg:"#252500",tx:"#aaaa44"};
  if(s>=4)    return {bg:"#1a1400",tx:"#555533"};
  return             {bg:"#0c1018",tx:"#2a3a48"};
}
function h1AvgColor(v) {
  if(v==null) return {bg:"#0c1018",tx:"#1e2e3e"};
  if(v>=40)   return {bg:"#ff4400",tx:"#fff"};
  if(v>=35)   return {bg:"#ff9900",tx:"#000"};
  if(v>=30)   return {bg:"#00ffb3",tx:"#001a0e"};
  if(v>=27)   return {bg:"#00d97e",tx:"#001a0e"};
  if(v>=24)   return {bg:"#00a85e",tx:"#fff"};
  if(v>=21)   return {bg:"#007040",tx:"#fff"};
  if(v>=20)   return {bg:"#1a3d25",tx:"#88ccaa"};
  if(v>=17)   return {bg:"#2a2a00",tx:"#aaaa44"};
  return             {bg:"#0c1018",tx:"#2a3a48"};
}
function pctColor(v) {
  if(v==null) return {bg:"#0c1018",tx:"#1e2e3e"};
  if(v>=75)   return {bg:"#00ffb3",tx:"#001a0e"};
  if(v>=60)   return {bg:"#00d97e",tx:"#001a0e"};
  if(v>=45)   return {bg:"#00a85e",tx:"#fff"};
  if(v>=30)   return {bg:"#007040",tx:"#fff"};
  if(v>=15)   return {bg:"#1a3d25",tx:"#88ccaa"};
  if(v>=5)    return {bg:"#252500",tx:"#aaaa44"};
  return             {bg:"#0c1018",tx:"#2a3a48"};
}

const ROWS = [
  {key:"score", label:"📊 相場点数", colorFn:scoreColor, fmt:v=>v!=null?Math.round(v):"",  h:28, bold:true},
  {key:"h1a",   label:"H1 avgADX",  colorFn:h1AvgColor, fmt:v=>v!=null?v.toFixed(1):"",    h:20},
  {key:"h4p20", label:"H4 ≥20%",   colorFn:pctColor,   fmt:v=>v!=null?Math.round(v):"",   h:20},
  {key:"h4p30", label:"H4 ≥30%",   colorFn:pctColor,   fmt:v=>v!=null?Math.round(v):"",   h:20},
];

function fmtWk(wk) {
  const ws = Object.values(RAW)[0]?.[wk]?.ws || "";
  return ws ? ws.slice(2,10).replace(/\./g,"/") : wk.slice(-3);
}

function getCellVal(sym, wk, key) {
  const r = RAW[sym]?.[wk];
  if(!r) return null;
  if(key==="score") return calcScore(r.h1a, r.h4p20, r.h4p30);
  return r[key] ?? null;
}

function rowAvg(sym, weeks, key) {
  const vals = weeks.map(w=>getCellVal(sym,w,key)).filter(v=>v!=null);
  return vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null;
}

// ── 直近5日スコアラベル ──
function scoreLabel(s) {
  if(s==null) return "—";
  if(s>=80) return "最強🔥";
  if(s>=65) return "超強✅";
  if(s>=50) return "★候補";
  if(s>=38) return "良い";
  if(s>=27) return "OK";
  if(s>=18) return "様子見⚠️";
  return "NG❌";
}

// ── 直近5日パネル ──
function RecentPanel() {
  if(!RECENT_5||RECENT_5.length===0) return null;
  return (
    <div style={{padding:"12px 16px",borderBottom:"1px solid #122030",background:"#07101a"}}>
      <div style={{fontSize:10,color:"#3a5a70",marginBottom:8,letterSpacing:1}}>📅 直近5営業日</div>
      <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
        {RECENT_5.map(r=>{
          const s = calcScore(r.h1_avg_adx, r.h4_pct20, r.h4_pct30);
          const c = scoreColor(s);
          const dt  = new Date(r.date + "T00:00:00Z");
          const dow = ["日","月","火","水","木","金","土"][dt.getUTCDay()];
          const lbl = r.date.slice(5).replace("-","/");
          return (
            <div key={r.date} style={{
              background:c.bg, border:"1px solid #1a3050",
              borderRadius:8, padding:"8px 12px", minWidth:90, textAlign:"center"
            }}>
              <div style={{fontSize:9,color:"#5a8aaa",marginBottom:4}}>{lbl}({dow})</div>
              <div style={{fontSize:22,fontWeight:800,color:c.tx,lineHeight:1}}>
                {s!=null ? Math.round(s) : "—"}
              </div>
              <div style={{fontSize:9,fontWeight:700,color:c.tx,marginTop:2}}>
                {scoreLabel(s)}
              </div>
              <div style={{marginTop:6,borderTop:"1px solid rgba(255,255,255,0.1)",paddingTop:4}}>
                <div style={{fontSize:8,color:"#6a9ab0"}}>H1avg <b style={{color:"#aaccff"}}>{r.h1_avg_adx}</b></div>
                <div style={{fontSize:8,color:"#6a9ab0"}}>H4≥20 <b style={{color:"#ffcc44"}}>{r.h4_pct20}%</b></div>
                <div style={{fontSize:8,color:"#6a9ab0"}}>H4≥30 <b style={{color:"#ff88cc"}}>{r.h4_pct30}%</b></div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── メインアプリ ──
function App() {
  const [symFilter, setSymFilter] = useState("ALL");
  const [range, setRange]         = useState([Math.max(0,ALL_WEEKS.length-26), ALL_WEEKS.length-1]);
  const [hov, setHov]             = useState(null);
  const [view, setView]           = useState("both");
  const gridRef = useRef();

  const weeks    = useMemo(()=>ALL_WEEKS.slice(range[0],range[1]+1),[range]);
  const dispSyms = symFilter==="ALL" ? ALL_SYMS : [symFilter];

  useEffect(()=>{
    if(gridRef.current) setTimeout(()=>{ gridRef.current.scrollLeft=gridRef.current.scrollWidth; },100);
  },[weeks,view]);

  const hovR     = hov ? RAW[hov.sym]?.[hov.wk] : null;
  const hovScore = hovR ? calcScore(hovR.h1a, hovR.h4p20, hovR.h4p30) : null;

  const visRows = view==="score"  ? [ROWS[0]] :
                  view==="detail" ? ROWS.slice(1) : ROWS;

  const Btn = (active, col="#2266aa") => ({
    background:active?"#0a2030":"transparent",
    border:`1px solid ${active?col:"#122030"}`,
    borderRadius:4, color:active?"#44aaff":"#3a5a70",
    fontSize:10, padding:"4px 10px", cursor:"pointer",
    fontFamily:"inherit", fontWeight:active?700:400,
  });

  return (
    <div style={{background:"#060b10",minHeight:"100vh"}}>

      {/* ヘッダー */}
      <div style={{background:"linear-gradient(135deg,#0a1828,#060b10)",borderBottom:"1px solid #122030",padding:"12px 18px",display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:10}}>
        <div>
          <div style={{fontSize:9,color:"#2a4a60",letterSpacing:2,marginBottom:2}}>
            ADX Score = sqrt(H1norm × H4_20) × 0.85 × (1 + H4_30×0.5)
          </div>
          <div style={{fontSize:18,fontWeight:700,color:"#d8f0ff"}}>⚡ XAUUSD ADX Score Dashboard</div>
          <div style={{fontSize:9,color:"#2a4a60",marginTop:2}}>最終更新: {UPDATED_AT} | {ALL_WEEKS.length}週のデータ蓄積</div>
        </div>
        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
          <button style={Btn(view==="score","#00aa66")}  onClick={()=>setView("score")}>スコアのみ</button>
          <button style={Btn(view==="both","#2266aa")}   onClick={()=>setView("both")}>スコア+3指標</button>
          <button style={Btn(view==="detail","#446688")} onClick={()=>setView("detail")}>3指標のみ</button>
        </div>
      </div>

      {/* 直近5日パネル */}
      <RecentPanel/>

      {/* 銘柄フィルター + 凡例 */}
      <div style={{background:"#0a1520",borderBottom:"1px solid #122030",padding:"8px 16px",display:"flex",gap:6,flexWrap:"wrap",alignItems:"center"}}>
        <span style={{fontSize:10,color:"#3a5a70"}}>銘柄:</span>
        {["ALL",...ALL_SYMS].map(s=>(
          <button key={s} onClick={()=>setSymFilter(s)} style={{
            background:symFilter===s?"#0d1e30":"transparent",
            border:`1px solid ${symFilter===s?"#2a4a70":"#122030"}`,
            borderRadius:4, color:symFilter===s?(SYM_C[s]||"#88ccee"):"#3a5a70",
            fontSize:11, padding:"3px 10px", cursor:"pointer",
            fontFamily:"inherit", fontWeight:symFilter===s?700:400,
          }}>{s}</button>
        ))}
        <div style={{marginLeft:"auto",display:"flex",gap:5,alignItems:"center",flexWrap:"wrap"}}>
          <span style={{fontSize:9,color:"#2a4a60"}}>スコア凡例:</span>
          {[["≥80🔥","#ff4400"],["≥65","#ff9900"],["≥50★","#cccc00"],["≥38","#00a85e"],["≥27","#007040"],["低","#0c1018"]].map(([l,bg])=>(
            <div key={l} style={{display:"flex",alignItems:"center",gap:3}}>
              <div style={{width:18,height:12,background:bg,borderRadius:2,border:"1px solid #1a3050"}}/>
              <span style={{fontSize:8,color:"#4a6a80"}}>{l}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 期間スライダー */}
      <div style={{background:"#07101a",borderBottom:"1px solid #0d1e2e",padding:"8px 16px",display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        <span style={{fontSize:10,color:"#3a5a70",whiteSpace:"nowrap"}}>開始:</span>
        <div style={{display:"flex",flexDirection:"column",gap:2,flex:1,minWidth:150,maxWidth:300}}>
          <input type="range" min={0} max={ALL_WEEKS.length-1} value={range[0]}
            onChange={e=>{const v=parseInt(e.target.value);if(v<range[1])setRange([v,range[1]]);}} style={{width:"100%"}}/>
          <div style={{fontSize:9,color:"#5a8aaa"}}>{fmtWk(ALL_WEEKS[range[0]])} ({ALL_WEEKS[range[0]]})</div>
        </div>
        <span style={{fontSize:10,color:"#3a5a70",whiteSpace:"nowrap"}}>終了:</span>
        <div style={{display:"flex",flexDirection:"column",gap:2,flex:1,minWidth:150,maxWidth:300}}>
          <input type="range" min={0} max={ALL_WEEKS.length-1} value={range[1]}
            onChange={e=>{const v=parseInt(e.target.value);if(v>range[0])setRange([range[0],v]);}} style={{width:"100%"}}/>
          <div style={{fontSize:9,color:"#5a8aaa"}}>{fmtWk(ALL_WEEKS[range[1]])} ({ALL_WEEKS[range[1]]})</div>
        </div>
        {[["全期間",0],["直近1年",52],["直近6ヶ月",26],["直近3ヶ月",13]].map(([lbl,offset])=>(
          <button key={lbl} onClick={()=>setRange([Math.max(0,ALL_WEEKS.length-(offset||ALL_WEEKS.length)),ALL_WEEKS.length-1])} style={{
            background:"transparent",border:"1px solid #1a3050",borderRadius:4,
            color:"#3a5a70",fontSize:10,padding:"4px 8px",cursor:"pointer",
            fontFamily:"inherit",whiteSpace:"nowrap",
          }}>{lbl}</button>
        ))}
      </div>

      {/* ツールチップ */}
      <div style={{minHeight:36,padding:"5px 16px",display:"flex",alignItems:"center"}}>
        {hov&&hovR ? (
          <div style={{display:"flex",gap:10,background:"#0a1520",border:"1px solid #122030",borderRadius:6,padding:"5px 14px",fontSize:10,flexWrap:"wrap",alignItems:"center"}}>
            <span style={{color:SYM_C[hov.sym]||"#aaa",fontWeight:700,fontSize:12}}>{hov.sym}</span>
            <span style={{color:"#2a4a60"}}>{hov.wk} ({hovR.ws}〜)</span>
            <span style={{color:"#3a5a70"}}>│</span>
            <span>📊 <b style={{color:"#00ffb3",fontSize:16}}>{hovScore!=null?Math.round(hovScore):"—"}</b>点</span>
            <span style={{color:"#3a5a70"}}>│</span>
            <span>H1avg: <b style={{color:"#aaccff"}}>{hovR.h1a!=null?hovR.h1a.toFixed(2):"—"}</b></span>
            <span>H4≥20: <b style={{color:"#ffcc44"}}>{hovR.h4p20!=null?hovR.h4p20.toFixed(1):"—"}%</b></span>
            <span>H4≥30: <b style={{color:"#ff88cc"}}>{hovR.h4p30!=null?hovR.h4p30.toFixed(1):"—"}%</b>
              <span style={{fontSize:9,color:"#3a5a70",marginLeft:4}}>
                (ボーナス×{hovR.h4p30!=null?(1+(hovR.h4p30/100)*0.5).toFixed(2):"—"})
              </span>
            </span>
          </div>
        ) : (
          <span style={{fontSize:10,color:"#1a2e40"}}>セルにカーソルで詳細表示（H4_30ボーナス乗数も確認できます）</span>
        )}
      </div>

      {/* ヒートマップグリッド */}
      <div ref={gridRef} style={{overflowX:"auto",padding:"0 16px 28px",WebkitOverflowScrolling:"touch"}}>
        {dispSyms.map(sym=>(
          <div key={sym} style={{marginBottom:view==="both"?24:14}}>
            <div style={{fontSize:13,fontWeight:700,color:SYM_C[sym]||"#aaa",marginBottom:4,paddingLeft:100,letterSpacing:1}}>
              {sym}
            </div>
            <table style={{borderCollapse:"separate",borderSpacing:2,minWidth:"max-content"}}>
              <thead>
                {sym===dispSyms[0]&&(
                  <tr>
                    <th style={{width:98,textAlign:"left",fontSize:9,color:"#2a4050",fontWeight:400,paddingBottom:5,paddingLeft:4}}></th>
                    {weeks.map((wk,wi)=>{
                      const isY = wk.endsWith("W01");
                      const ws  = Object.values(RAW)[0]?.[wk]?.ws || "";
                      const mon = ws ? parseInt(ws.slice(5,7))-1 : 0;
                      return (
                        <th key={wk} style={{width:24,textAlign:"center",fontSize:7,color:isY?"#5a8aaa":"#2a4050",fontWeight:isY?700:400,paddingBottom:5,borderLeft:isY?"1px solid #1a3050":"none"}}>
                          {isY ? `'${wk.slice(2,4)}` : wi%4===0 ? ML[mon]?.slice(0,1)||"" : ""}
                        </th>
                      );
                    })}
                    <th style={{width:46,fontSize:9,color:"#2a4050",textAlign:"center",paddingLeft:8,borderLeft:"1px solid #1a3050",position:"sticky",right:0,background:"#060b10"}}>AVG</th>
                  </tr>
                )}
              </thead>
              <tbody>
                {visRows.map((row)=>{
                  const avg = rowAvg(sym,weeks,row.key);
                  const {bg:avgBg,tx:avgTx} = row.colorFn(avg);
                  const isScore = row.key==="score";
                  return (
                    <React.Fragment key={row.key}>
                      <tr>
                        <td style={{fontSize:isScore?10:9,fontWeight:isScore?700:500,color:isScore?"#7ab8d8":"#4a7a90",paddingRight:6,paddingLeft:4,whiteSpace:"nowrap",width:98}}>
                          {row.label}
                        </td>
                        {weeks.map(wk=>{
                          const val = getCellVal(sym,wk,row.key);
                          const {bg,tx} = row.colorFn(val);
                          const isY = wk.endsWith("W01");
                          return (
                            <td key={wk} className="cell"
                              onMouseEnter={()=>setHov({sym,wk})}
                              onMouseLeave={()=>setHov(null)}
                              onClick={()=>setHov(h=>h?.sym===sym&&h?.wk===wk?null:{sym,wk})}
                              style={{background:bg,width:24,height:row.h||20,textAlign:"center",fontSize:isScore?8:7,color:tx,fontWeight:isScore?700:600,borderRadius:2,borderLeft:isY?"1px solid #1a3050":"none"}}>
                              {row.fmt(val)}
                            </td>
                          );
                        })}
                        <td style={{textAlign:"center",fontSize:isScore?11:9,fontWeight:700,paddingLeft:8,borderLeft:"1px solid #1a3050",background:avgBg,color:avgTx,position:"sticky",right:0,borderRadius:2,height:row.h||20}}>
                          {row.fmt(avg)}
                        </td>
                      </tr>
                      {isScore&&view==="both"&&<tr><td colSpan={weeks.length+2} style={{height:3}}></td></tr>}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      {/* ガイド */}
      <div style={{padding:"0 16px 32px",display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:8,maxWidth:1100}}>
        {[
          {t:"📊 スコア設計",b:"sqrt(H1norm x H4_20) x 0.85 がベース。H4_30はボーナス乗数（x1.0〜1.5）。H4_30=0でも死なない、H4_30が高いと明確に加点。"},
          {t:"🎯 点数の目安",b:"80以上🔥 / 65以上→超強 / 50以上★候補 / 38以上→良い / 27以上→OK / 18以上→様子見 / 18未満→見送り"},
          {t:"📡 状態監視",b:"H4_30が0でもH1+H4_20が強ければ中スコア。H4_30が上がってきたらボーナス加点でスコア急上昇 → シグナル前兆として活用。"},
          {t:"🔍 操作方法",b:"スライダーで表示期間を変更。セルにカーソルでH4_30ボーナス乗数を確認。右端のAVGで期間平均スコアを比較。"},
        ].map(({t,b})=>(
          <div key={t} style={{background:"#0a1520",border:"1px solid #122030",borderRadius:6,padding:"10px 12px"}}>
            <div style={{fontSize:11,fontWeight:700,color:"#5a8aaa",marginBottom:4}}>{t}</div>
            <div style={{fontSize:10,color:"#3a5a70",lineHeight:1.7}}>{b}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
</script>
</body>
</html>"""


# ── HTMLを生成してプレースホルダーを置換 ─────────────
def generate_html(records: list[dict]) -> str:
    now_jst  = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    recent_5 = records[-5:] if len(records) >= 5 else records

    # 週次集計
    raw_by_sym    = {}
    all_weeks_set = set()
    for sym in SYMBOLS:
        weekly = aggregate_to_weekly(records, sym)
        raw_by_sym[sym] = weekly
        all_weeks_set.update(weekly.keys())

    all_weeks = sorted(all_weeks_set)

    # JSON文字列化
    raw_json    = json.dumps(raw_by_sym, ensure_ascii=False)
    weeks_json  = json.dumps(all_weeks,  ensure_ascii=False)
    syms_json   = json.dumps(SYMBOLS,    ensure_ascii=False)
    recent_json = json.dumps(recent_5,   ensure_ascii=False)

    # プレースホルダー置換
    html = HTML_TEMPLATE
    html = html.replace("<<<RAW_JSON>>>",    raw_json)
    html = html.replace("<<<WEEKS_JSON>>>",  weeks_json)
    html = html.replace("<<<SYMS_JSON>>>",   syms_json)
    html = html.replace("<<<RECENT_JSON>>>", recent_json)
    html = html.replace("<<<UPDATED_AT>>>",  now_jst)

    return html


# ── メイン ───────────────────────────────────────────
def main():
    print("=== generate_html.py 開始 ===")
    if not os.path.exists(DATA_PATH):
        print("[WARN] scores.json が存在しません。空HTMLを生成します。")
        records = []
    else:
        with open(DATA_PATH, encoding="utf-8") as f:
            records = json.load(f)
    print(f"  {len(records)} 件のデータを読み込み")

    os.makedirs("docs", exist_ok=True)
    html = generate_html(records)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] {HTML_PATH} 生成完了（{len(html)//1024}KB）")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
