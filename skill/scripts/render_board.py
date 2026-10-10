#!/usr/bin/env python3
"""麦门性价比榜单 —— 交互式查询页渲染器。

把候选方案 JSON 渲染成一张自包含的【可交互查询网页】：
  - 预算滑块筛选（实时过滤）
  - 排序方式切换（性价比 / 价格 / 省钱 / 热量）
  - 场景标签筛选
  - 套餐详情展开（点击卡片看完整组成、营养、用券明细）
  - 星级/推荐度可视化

页面为纯静态 HTML（内联 CSS/JS），无需联网、无需服务器，双击即可用。
数据由 AI 在生成时实时从麦当劳接口取得（页面本身不调接口）。

用法:
    python render_board.py candidates.json -o board.html
    python render_board.py candidates.json -o board.html --store "北京·国贸店（到店自取）" --when "2026-10-11 12:00"

输入 JSON 结构:
{
  "store": "门店名（取餐方式）",
  "when": "2026-10-11 12:00",          // 可选，查询时间
  "candidates": [
    {
      "name": "1+1随心配",
      "components": [
        {"cat":"主食","name":"双层吉士堡","qty":1},
        {"cat":"小食","name":"中薯条","qty":1,"options":["大薯条 +3元"]}
      ],
      "original_price": 25.5,          // 元
      "final_price": 13.9,             // 元（含券实付）
      "calories": 620,                 // kcal
      "protein_g": 24,                 // g
      "scene": "学生党 / 预算敏感",      // 适合人群
      "coupon": "随心配13.9元券",        // 可选
      "is_limited_coupon": true,       // 可选，当日限时
      "scene_tags": ["学生党","预算敏感"],// 可选，用于标签筛选；缺省则由 scene 拆分
      "sold_for": "1人食"              // 可选
    }
  ]
}
"""

import argparse
import html
import json
import sys
from datetime import datetime

# ---------------------------------------------------------------- 评分

def clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


def score_satiety(c):
    if c.get("final_price", 0) <= 0:
        return 0.0
    n = len(c.get("components", []))
    base = 4.0 + 1.6 * n
    density = (c.get("calories", 0) or 0) / c["final_price"]
    base += clamp(density / 500.0, 0, 1) * 3.0
    if n <= 1 and (c.get("calories", 0) or 0) < 300:
        base -= 2.0
    return clamp(base)


def score_discount(c):
    op = c.get("original_price", 0) or 0
    fp = c.get("final_price", 0) or 0
    if op <= 0:
        return 2.0
    rate = (op - fp) / op
    if rate >= 0.30:
        s = 9.0 + clamp((rate - 0.30) / 0.20, 0, 1)
    elif rate >= 0.20:
        s = 7.0 + (rate - 0.20) / 0.10 * 1.9
    elif rate >= 0.10:
        s = 5.0 + (rate - 0.10) / 0.10 * 1.9
    elif rate > 0:
        s = 3.0 + rate / 0.10 * 1.9
    else:
        s = 2.0
    if c.get("is_limited_coupon"):
        s += 0.5
    return clamp(s)


def score_nutrition(c):
    cal = c.get("calories", 0) or 0
    pro = c.get("protein_g", 0) or 0
    if not cal:
        return 6.0
    if 500 <= cal <= 800 and pro >= 20:
        return 9.5
    if cal <= 550 and pro >= 20:
        return 9.0
    if cal <= 550:
        return 7.0
    if 500 <= cal <= 800:
        return 7.5
    if cal <= 900:
        return 6.0
    if cal > 1000:
        return 3.0
    return 5.5


SCENE_AFFINITY = {
    "学生党": 9.0, "预算敏感": 9.0, "上班族": 8.5, "赶时间": 8.5,
    "减脂": 9.0, "健身": 9.0, "管饱": 8.5, "双人": 8.0,
    "下午茶": 8.0, "家庭": 8.0, "尝鲜": 8.0,
}


def score_scene(c):
    scene = c.get("scene", "") or ""
    if not scene:
        return 7.0
    for k, v in SCENE_AFFINITY.items():
        if k in scene:
            return v
    return 7.0


def evaluate(c):
    s1, s2, s3, s4 = score_satiety(c), score_discount(c), score_nutrition(c), score_scene(c)
    total = round(s1 * 0.4 + s2 * 0.3 + s3 * 0.2 + s4 * 0.1, 1)
    op = c.get("original_price", 0) or 0
    fp = c.get("final_price", 0) or 0
    return {
        **c,
        "sub": [round(s1, 1), round(s2, 1), round(s3, 1), round(s4, 1)],
        "total": total,
        "saved": round(op - fp, 2),
        "rate": round((op - fp) / op * 100) if op else 0,
    }


def tier_of(total):
    if total >= 9.0:
        return "top", 5, "闭眼冲"
    if total >= 8.0:
        return "great", 4, "强推"
    if total >= 7.0:
        return "good", 3, "推荐"
    if total >= 6.0:
        return "meh", 2, "尚可"
    return "bad", 1, "不推荐"


def scene_tags(c):
    if c.get("scene_tags"):
        return c["scene_tags"]
    s = c.get("scene", "") or ""
    return [t.strip() for t in s.replace("、", "/").replace("，", "/").split("/") if t.strip()]


CAT_EMOJI = {"主食": "🍔", "小食": "🍟", "饮料": "🥤", "甜品": "🍦", "其他": "•"}


def norm_components(comps):
    out = []
    for item in comps or []:
        if isinstance(item, dict):
            out.append({
                "cat": item.get("cat", "其他"),
                "name": item.get("name", ""),
                "qty": item.get("qty", 1),
                "options": item.get("options", []) or [],
            })
        else:
            out.append({"cat": "其他", "name": str(item), "qty": 1, "options": []})
    return out


def build_payload(results, store, when):
    """把结果整理成前端需要的精简 JSON。"""
    cards = []
    all_tags = set()
    for r in results:
        tags = scene_tags(r)
        all_tags.update(tags)
        tier, n_star, label = tier_of(r["total"])
        comps = norm_components(r.get("components"))
        cards.append({
            "name": r.get("name", "未命名"),
            "components": comps,
            "original_price": round(r.get("original_price", 0) or 0, 2),
            "final_price": round(r.get("final_price", 0) or 0, 2),
            "saved": r["saved"],
            "rate": r["rate"],
            "total": r["total"],
            "sub": r["sub"],
            "tier": tier,
            "stars": n_star,
            "star_label": label,
            "scene": r.get("scene", ""),
            "tags": tags,
            "coupon": r.get("coupon", ""),
            "is_limited_coupon": bool(r.get("is_limited_coupon")),
            "calories": r.get("calories", 0) or 0,
            "protein_g": r.get("protein_g", 0) or 0,
            "sold_for": r.get("sold_for", ""),
        })
    return {
        "store": store,
        "when": when,
        "count": len(cards),
        "tags": sorted(all_tags),
        "cards": cards,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦门性价比查询</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  :root{
    --red:#d92b2b; --orange:#e8762c; --gold:#c9a227; --gray:#7a8b99;
    --bg:#f5f2ec; --card:#fff; --ink:#2b2b2b; --muted:#8a857c; --line:#eee9e0;
  }
  body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
       background:var(--bg);color:var(--ink);padding:20px;line-height:1.5}
  .wrap{max-width:920px;margin:0 auto}
  header{text-align:center;margin-bottom:6px}
  header h1{font-size:26px;letter-spacing:1px}
  header h1 .m{color:var(--red)}
  .meta{text-align:center;color:var(--muted);font-size:13px}
  .live{text-align:center;margin:8px 0 18px}
  .live span{display:inline-flex;align-items:center;gap:6px;background:#eaf7ee;color:#1a7f45;
             font-size:12.5px;padding:4px 12px;border-radius:14px}
  .live .dot{width:7px;height:7px;border-radius:50%;background:#22a05a;animation:pulse 1.8s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,160,90,.5)}70%{box-shadow:0 0 0 8px rgba(34,160,90,0)}100%{box-shadow:0 0 0 0 rgba(34,160,90,0)}}

  /* 控制面板 */
  .panel{background:var(--card);border-radius:16px;padding:16px 18px;margin-bottom:18px;
         box-shadow:0 3px 14px rgba(0,0,0,.06)}
  .row{display:flex;flex-wrap:wrap;gap:14px;align-items:center}
  .row + .row{margin-top:14px;padding-top:14px;border-top:1px dashed var(--line)}
  .label{font-size:12.5px;color:var(--muted);min-width:56px;font-weight:600}
  .budget{display:flex;align-items:center;gap:10px;flex:1;min-width:240px}
  input[type=range]{flex:1;-webkit-appearance:none;height:6px;border-radius:4px;
                    background:linear-gradient(90deg,var(--red),var(--orange));outline:none}
  input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;border-radius:50%;
                    background:#fff;border:3px solid var(--red);cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,.2)}
  .budget b{color:var(--red);font-size:16px;min-width:64px;text-align:right}
  .chips{display:flex;flex-wrap:wrap;gap:7px;flex:1}
  .chip{font-size:12.5px;padding:5px 12px;border-radius:14px;background:#f3f0ea;color:#5c564d;
        cursor:pointer;border:1px solid transparent;transition:.15s;user-select:none}
  .chip:hover{background:#ece7de}
  .chip.on{background:var(--red);color:#fff;border-color:var(--red)}
  .seg{display:flex;background:#f3f0ea;border-radius:12px;padding:3px;gap:2px;flex-wrap:wrap}
  .seg button{font-size:12.5px;padding:6px 14px;border:none;background:transparent;border-radius:9px;
              cursor:pointer;color:#5c564d;font-weight:600;transition:.15s}
  .seg button.on{background:#fff;color:var(--red);box-shadow:0 1px 4px rgba(0,0,0,.12)}
  .stat{font-size:12.5px;color:var(--muted);text-align:right;margin-top:10px}
  .stat b{color:var(--red)}

  /* 卡片 */
  .card{display:flex;background:var(--card);border-radius:16px;margin-bottom:16px;overflow:hidden;
        box-shadow:0 3px 14px rgba(0,0,0,.07);border-left:6px solid #ccc;transition:.18s}
  .card:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(0,0,0,.11)}
  .tier-top{border-left-color:var(--red)} .tier-great{border-left-color:var(--orange)}
  .tier-good{border-left-color:var(--gold)} .tier-meh{border-left-color:var(--gray)}
  .tier-bad{border-left-color:#9aa5ad}
  .rank{flex:0 0 54px;display:flex;align-items:center;justify-content:center;font-size:22px;
        color:#fff;font-weight:700;flex-direction:column}
  .body{flex:1;padding:14px 18px}
  .head{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:6px}
  .head h2{font-size:18px}
  .badges{display:flex;gap:6px;flex-wrap:wrap}
  .limited{background:#ffefe8;color:var(--red);font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}
  .coupon{background:#eef4ff;color:#2f6bd9;font-size:11px;padding:2px 8px;border-radius:10px}
  .comps{list-style:none;margin:10px 0;display:flex;flex-wrap:wrap;gap:6px 14px}
  .comps li{font-size:13px;color:#444;display:flex;align-items:center;gap:5px}
  .comps .cat{color:var(--muted)}
  .comps .cname{font-weight:600}
  .comps .qty{color:#2f6bd9;font-weight:700}
  .comps .opt{color:#9a958c;font-size:12px}
  .metrics{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin:10px 0 8px}
  .price{font-size:13px;color:#777;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  .price .orig{text-decoration:line-through}
  .price .arrow{color:#bbb}
  .price .final{font-size:22px;font-weight:800;color:var(--red)}
  .price .save{background:#fff2f0;color:var(--red);padding:2px 8px;border-radius:8px;font-weight:600}
  .scorewrap{display:flex;align-items:center;gap:8px}
  .score{font-size:24px;font-weight:800}
  .score small{font-size:12px;color:#aaa;font-weight:400}
  .bar{width:90px;height:7px;background:#eee;border-radius:4px;overflow:hidden}
  .bar i{display:block;height:100%;border-radius:4px}
  .foot{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;
        margin-top:10px;padding-top:8px;border-top:1px dashed var(--line);font-size:13px}
  .stars b{font-size:12px}
  .toggle{font-size:12.5px;color:#2f6bd9;cursor:pointer;user-select:none;font-weight:600}
  .detail{display:none;margin-top:10px;padding:12px;background:#faf8f4;border-radius:12px;font-size:13px}
  .detail.open{display:block}
  .detail h4{font-size:12.5px;color:var(--muted);margin-bottom:6px;font-weight:600}
  .detail .grid{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}
  .detail .grid span{background:#fff;padding:4px 10px;border-radius:8px;color:#444}
  .subs{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
  .subs span{background:#f6f4f0;padding:3px 9px;border-radius:8px;font-size:11.5px;color:var(--muted)}
  .tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
  .tags i{font-style:normal;font-size:11.5px;background:#fff2f0;color:var(--red);padding:2px 8px;border-radius:8px}
  footer{text-align:center;color:#aaa;font-size:12px;margin-top:22px}
  .empty{text-align:center;color:var(--muted);padding:40px 0;font-size:14px}
</style></head>
<body><div class="wrap">
  <header><h1><span class="m">麦</span>门性价比查询</h1></header>
  <div class="meta" id="meta"></div>
  <div class="live"><span><i class="dot"></i>实时数据 · 查询于 <b id="when"></b></span></div>

  <div class="panel">
    <div class="row">
      <span class="label">预算上限</span>
      <div class="budget">
        <input type="range" id="budget" min="0" max="100" step="1" value="100">
        <b id="budgetVal">不限</b>
      </div>
    </div>
    <div class="row">
      <span class="label">场景</span>
      <div class="chips" id="chips"></div>
    </div>
    <div class="row">
      <span class="label">排序</span>
      <div class="seg" id="sortSeg">
        <button data-sort="value" class="on">性价比↓</button>
        <button data-sort="price">价格↑</button>
        <button data-sort="save">省最多</button>
        <button data-sort="cal">热量↓</button>
      </div>
    </div>
    <div class="stat" id="stat"></div>
  </div>

  <div id="list"></div>
  <footer>价格与优惠以麦当劳实时接口为准 · 数据由 AI 当次查询生成 · 评分为参考值</footer>
</div>

<script>
const DATA = __DATA__;
const TIER_COLOR = {top:"#d92b2b",great:"#e8762c",good:"#c9a227",meh:"#7a8b99",bad:"#9aa5ad"};
const CAT_EMOJI = {主食:"🍔",小食:"🍟",饮料:"🥤",甜品:"🍦",其他:"•"};
const state = {budget:Infinity, tags:new Set(), sort:"value"};

function init(){
  document.getElementById("meta").textContent = DATA.store || "麦当劳";
  document.getElementById("when").textContent = DATA.when || "";
  const maxPrice = Math.ceil(Math.max(...DATA.cards.map(c=>c.final_price), 10));
  const b = document.getElementById("budget");
  b.max = maxPrice; b.value = maxPrice;
  b.oninput = ()=>{
    const v = +b.value;
    state.budget = (v >= maxPrice) ? Infinity : v;
    document.getElementById("budgetVal").textContent = state.budget===Infinity ? "不限" : "¥"+v;
    render();
  };
  document.getElementById("budgetVal").textContent = "不限";
  // 场景 chips
  const chips = document.getElementById("chips");
  DATA.tags.forEach(t=>{
    const el = document.createElement("div");
    el.className="chip"; el.textContent=t;
    el.onclick = ()=>{
      if(state.tags.has(t)){state.tags.delete(t);el.classList.remove("on");}
      else{state.tags.add(t);el.classList.add("on");}
      render();
    };
    chips.appendChild(el);
  });
  // 排序
  document.querySelectorAll("#sortSeg button").forEach(btn=>{
    btn.onclick = ()=>{
      document.querySelectorAll("#sortSeg button").forEach(x=>x.classList.remove("on"));
      btn.classList.add("on"); state.sort = btn.dataset.sort; render();
    };
  });
  render();
}

function pass(c){
  if(c.final_price > state.budget) return false;
  if(state.tags.size){
    return c.tags.some(t=>state.tags.has(t));
  }
  return true;
}

function sortFn(a,b){
  if(state.sort==="price") return a.final_price-b.final_price;
  if(state.sort==="save")  return b.saved-a.saved;
  if(state.sort==="cal")   return (a.calories||9e9)-(b.calories||9e9);
  return b.total-a.total;
}

function starStr(n){ return "★".repeat(n)+"☆".repeat(5-n); }

function cardHTML(c, idx){
  const color = TIER_COLOR[c.tier];
  const medal = idx===0?"🥇":(idx===1?"🥈":(idx===2?"🥉":(idx+1)));
  const comps = c.components.map(x=>{
    const opt = x.options && x.options.length
      ? `<span class="opt">（可选：${x.options.join(" / ")}）</span>` : "";
    return `<li><span class="cat">${CAT_EMOJI[x.cat]||"•"} ${x.cat}</span>
            <span class="cname">${esc(x.name)}</span>
            <span class="qty">×${x.qty}</span>${opt}</li>`;
  }).join("");
  const limited = c.is_limited_coupon ? `<span class="limited">今日限定</span>` : "";
  const coupon = c.coupon ? `<span class="coupon">🎟 ${esc(c.coupon)}</span>` : "";
  const tags = c.tags.map(t=>`<i>${esc(t)}</i>`).join("");
  const barW = Math.min(100, c.total*10);
  return `
  <div class="card tier-${c.tier}">
    <div class="rank" style="background:${color}">${medal}</div>
    <div class="body">
      <div class="head">
        <h2>${esc(c.name)}</h2>
        <div class="badges">${limited}${coupon}</div>
      </div>
      <ul class="comps">${comps}</ul>
      <div class="metrics">
        <div class="price">
          <span class="orig">原价 ¥${c.original_price.toFixed(2)}</span>
          <span class="arrow">→</span>
          <span class="final">¥${c.final_price.toFixed(2)}</span>
          <span class="save">省 ¥${c.saved.toFixed(2)}（${c.rate}%）</span>
        </div>
        <div class="scorewrap">
          <div class="score" style="color:${color}">${c.total}<small>/10</small></div>
          <div class="bar"><i style="width:${barW}%;background:${color}"></i></div>
        </div>
      </div>
      <div class="subs">
        <span>饱腹 ${c.sub[0]}</span><span>优惠 ${c.sub[1]}</span>
        <span>营养 ${c.sub[2]}</span><span>场景 ${c.sub[3]}</span>
      </div>
      <div class="foot">
        <span>👥 ${esc(c.scene)||"—"}</span>
        <span class="stars" style="color:${color}">${starStr(c.stars)} <b>${c.star_label}</b></span>
        <span class="toggle" onclick="toggleDetail(this)">详情 ▾</span>
      </div>
      <div class="detail">
        <h4>套餐组成</h4>
        <div class="grid">${c.components.map(x=>`<span>${CAT_EMOJI[x.cat]||"•"} ${esc(x.name)} ×${x.qty}</span>`).join("")}</div>
        <h4>营养与信息</h4>
        <div class="grid">
          <span>🔥 热量 ${c.calories||"—"} kcal</span>
          <span>💪 蛋白质 ${c.protein_g||"—"} g</span>
          <span>💰 实付 ¥${c.final_price.toFixed(2)}</span>
          ${c.coupon?`<span>🎟 ${esc(c.coupon)}</span>`:""}
          ${c.sold_for?`<span>🍽 ${esc(c.sold_for)}</span>`:""}
        </div>
        <h4>适合人群</h4>
        <div class="tags">${tags||"<i>通用</i>"}</div>
      </div>
    </div>
  </div>`;
}

function esc(s){ return String(s).replace(/[&<>"]/g, m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m])); }

function toggleDetail(el){
  const d = el.closest(".body").querySelector(".detail");
  const open = d.classList.toggle("open");
  el.textContent = open ? "收起 ▴" : "详情 ▾";
}

function render(){
  const list = document.getElementById("list");
  const cards = DATA.cards.filter(pass).sort(sortFn);
  const total = DATA.cards.length;
  document.getElementById("stat").innerHTML =
    `共 ${total} 个方案，当前显示 <b>${cards.length}</b> 个`;
  if(!cards.length){
    list.innerHTML = `<div class="empty">没有符合条件的套餐，试试放宽预算或取消场景筛选 🍔</div>`;
    return;
  }
  list.innerHTML = cards.map((c,i)=>cardHTML(c,i)).join("");
}

init();
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="候选 JSON 文件路径，或 - 表示 stdin")
    ap.add_argument("-o", "--output", default="mcd_board.html")
    ap.add_argument("--store", default="")
    ap.add_argument("--when", default=datetime.now().strftime("%Y-%m-%d %H:%M"))
    args = ap.parse_args()

    if args.src == "-":
        raw = json.load(sys.stdin)
    else:
        with open(args.src, "r", encoding="utf-8") as f:
            raw = json.load(f)

    if isinstance(raw, dict):
        args.store = args.store or raw.get("store", "")
        args.when = raw.get("when", args.when)
        raw = raw.get("candidates", [])

    results = [evaluate(c) for c in raw]
    payload = build_payload(results, args.store, args.when)

    out_html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(out_html)
    print(args.output)


if __name__ == "__main__":
    main()
