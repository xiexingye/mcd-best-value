#!/usr/bin/env python3
"""麦门性价比评分器。

输入：候选方案 JSON 文件（数组），每项字段见下。
输出：按性价比分降序的当日榜单（文本）。

用法:
    python value_score.py candidates.json
    python value_score.py -            # 从 stdin 读取

输入字段说明（每项）:
    name            str   方案名
    components      list  组成清单
    original_price  float 原价(元)
    final_price     float 实付价(元)，来自 calculate-price
    calories        int   热量 kcal（可选）
    protein_g       float 蛋白质 g（可选）
    scene           str   目标场景（可选，影响场景契合分）
    is_limited_coupon bool 是否用当日限时券（可选）
"""

import json
import sys
from dataclasses import dataclass, field, asdict


@dataclass
class Candidate:
    name: str
    components: list = field(default_factory=list)
    original_price: float = 0.0
    final_price: float = 0.0
    calories: int = 0
    protein_g: float = 0.0
    scene: str = ""
    is_limited_coupon: bool = False


def clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


def score_satiety(c: Candidate) -> float:
    """饱腹价值：以每元食物密度 + 构成丰富度为代理。"""
    if c.final_price <= 0:
        return 0.0
    n_components = len(c.components)
    # 构成越丰富基础分越高
    base = 4.0 + 1.6 * n_components
    # 每元热量（500kcal/元 视为很顶饱）
    density = c.calories / c.final_price if c.calories else 0
    density_bonus = clamp(density / 500.0, 0, 1) * 3.0
    # 只有饮料/单一构成扣分
    if n_components <= 1 and c.calories and c.calories < 300:
        base -= 2.0
    return clamp(base + density_bonus)


def score_discount(c: Candidate) -> float:
    """优惠力度。"""
    if c.original_price <= 0:
        return 2.0
    rate = (c.original_price - c.final_price) / c.original_price
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
    if c.is_limited_coupon:
        s += 0.5
    return clamp(s)


def score_nutrition(c: Candidate) -> float:
    """营养均衡：结合热量与蛋白质。"""
    if not c.calories:
        return 6.0  # 无数据给中性分
    cal, pro = c.calories, c.protein_g
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


def score_scene(c: Candidate) -> float:
    """场景契合：有明确场景关键词则按亲和度，否则中性。"""
    if not c.scene:
        return 7.0
    for key, val in SCENE_AFFINITY.items():
        if key in c.scene:
            return val
    return 7.0


def stars(total: float):
    if total >= 9.0:
        return "★★★★★", "闭眼冲"
    if total >= 8.0:
        return "★★★★☆", "强推"
    if total >= 7.0:
        return "★★★☆☆", "推荐"
    if total >= 6.0:
        return "★★☆☆☆", "尚可"
    return "★☆☆☆☆", "不推荐"


def evaluate(c: Candidate) -> dict:
    s1 = score_satiety(c)
    s2 = score_discount(c)
    s3 = score_nutrition(c)
    s4 = score_scene(c)
    total = round(s1 * 0.4 + s2 * 0.3 + s3 * 0.2 + s4 * 0.1, 1)
    star, label = stars(total)
    saved = round(c.original_price - c.final_price, 2)
    return {
        "name": c.name,
        "components": c.components,
        "original_price": c.original_price,
        "final_price": c.final_price,
        "saved": saved,
        "sub_scores": {
            "饱腹价值": round(s1, 1),
            "优惠力度": round(s2, 1),
            "营养均衡": round(s3, 1),
            "场景契合": round(s4, 1),
        },
        "total": total,
        "stars": star,
        "label": label,
        "scene": c.scene,
    }


def load_candidates(src: str) -> list:
    if src == "-":
        raw = json.load(sys.stdin)
    else:
        with open(src, "r", encoding="utf-8") as f:
            raw = json.load(f)
    if isinstance(raw, dict):
        raw = raw.get("candidates", [])
    out = []
    for item in raw:
        out.append(Candidate(
            name=item.get("name", "未命名"),
            components=item.get("components", []),
            original_price=float(item.get("original_price", 0) or 0),
            final_price=float(item.get("final_price", 0) or 0),
            calories=int(item.get("calories", 0) or 0),
            protein_g=float(item.get("protein_g", 0) or 0),
            scene=item.get("scene", "") or "",
            is_limited_coupon=bool(item.get("is_limited_coupon", False)),
        ))
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    cands = load_candidates(src)
    results = sorted((evaluate(c) for c in cands), key=lambda r: r["total"], reverse=True)

    print("=" * 52)
    print("        麦门当日性价比榜单")
    print("=" * 52)
    for i, r in enumerate(results, 1):
        medal = "🏆" if i == 1 else f"{i}."
        comp = " + ".join(r["components"]) if r["components"] else "—"
        print(f"\n{medal} {r['name']}   性价比分 {r['total']}/10")
        print(f"   组成：{comp}")
        print(f"   原价 ¥{r['original_price']:.2f} → 实付 ¥{r['final_price']:.2f}"
              f"（省 ¥{r['saved']:.2f}）")
        print(f"   子分：{r['sub_scores']}")
        if r["scene"]:
            print(f"   适合人群：{r['scene']}")
        print(f"   推荐程度：{r['stars']} {r['label']}")

    print("\n" + "-" * 52)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
