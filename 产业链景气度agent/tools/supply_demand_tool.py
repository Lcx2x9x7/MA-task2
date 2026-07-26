from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean
from typing import Any


SUPPLY_DEMAND_DIR = Path("data") / "供需匹配"
VALUE_DIR = Path("data") / "价值分配"
PRODUCTION_SALES_FILE = SUPPLY_DEMAND_DIR / "production_sales.csv"
CAPACITY_UTIL_FILE = SUPPLY_DEMAND_DIR / "capacity_util.csv"
PMI_FILE = SUPPLY_DEMAND_DIR / "pmi_detail.csv"
PRICE_SCISSORS_FILE = SUPPLY_DEMAND_DIR / "price_scissors.csv"
INDUSTRY_PROFIT_FILE = VALUE_DIR / "industry_profit.csv"


def calculate_supply_demand_match(chain_name: str) -> dict[str, Any]:
    sales = _sales_signal(chain_name)
    industrial_growth = _industrial_growth_signal(chain_name)
    capacity = _capacity_signal(chain_name)
    pmi = _pmi_signal()
    scissors = _price_scissors_signal(chain_name)

    demand_score = sales["score"] if sales["available"] else industrial_growth["score"]
    demand_signal = sales if sales["available"] else industrial_growth
    score = (
        demand_score * 0.35
        + capacity["score"] * 0.25
        + pmi["score"] * 0.20
        + scissors["score"] * 0.20
    )
    return {
        "metric": "供需匹配",
        "score": round(_clip(score, 0, 100), 2),
        "reason": (
            f"需求侧采用{demand_signal['label']}，得分 {demand_score:.2f}；"
            f"产能利用率得分 {capacity['score']:.2f}，PMI 得分 {pmi['score']:.2f}，"
            f"价格剪刀差得分 {scissors['score']:.2f}。"
        ),
        "source_files": {
            "production_sales": str(PRODUCTION_SALES_FILE),
            "capacity_util": str(CAPACITY_UTIL_FILE),
            "pmi": str(PMI_FILE),
            "price_scissors": str(PRICE_SCISSORS_FILE),
            "industry_profit": str(INDUSTRY_PROFIT_FILE),
        },
        "sub_scores": {
            "demand_growth": demand_signal,
            "capacity_utilization": capacity,
            "manufacturing_pmi": pmi,
            "price_scissors": scissors,
        },
        "data_limitations": [
            "PMI 当前只有制造业总指数，不是产业链专属新订单指数，因此作为宏观需求环境代理。",
            "产销数据当前主要覆盖新能源汽车产业链；缺失产销序列时使用相关行业工业增加值同比作为需求增长代理。",
            "价格剪刀差使用上游原料同比与出厂PPI同比的差值，差值过大代表利润被成本挤压或价格传导不畅。"
        ],
    }


def _sales_signal(chain_name: str) -> dict[str, Any]:
    rows = _read_csv(PRODUCTION_SALES_FILE)
    chain_rows = [row for row in rows if row.get("产业链") == chain_name and row.get("数据类型") == "销量_万辆"]
    values = []
    for row in chain_rows:
        value = _to_float(row.get("数值"))
        if value is not None:
            values.append({
                "year": row.get("年份", ""),
                "month": _month_num(row.get("月份", "")),
                "value": value,
                "raw": row,
            })
    if not values:
        return {
            "label": "产销增长",
            "available": False,
            "score": 50.0,
            "reason": "未读取到该产业链产销序列。",
            "latest": {},
        }
    latest = max(values, key=lambda row: (row["year"], row["month"]))
    same_month_prev = next(
        (
            row for row in values
            if row["year"] == str(int(latest["year"]) - 1) and row["month"] == latest["month"]
        ),
        None
    )
    yoy = None
    if same_month_prev and same_month_prev["value"]:
        yoy = (latest["value"] - same_month_prev["value"]) / same_month_prev["value"] * 100
    score = _clip(50 + (yoy or 0) * 2.2, 0, 100)
    return {
        "label": "产销增长",
        "available": True,
        "score": round(score, 2),
        "reason": (
            f"最新月份 {latest['year']}年{latest['month']}月销量 {latest['value']:.2f} 万辆，"
            f"同比 {_fmt_pct(yoy)}。"
        ),
        "latest": latest["raw"],
        "same_month_previous_year": same_month_prev["raw"] if same_month_prev else {},
        "yoy": round(yoy, 4) if yoy is not None else None,
    }


def _industrial_growth_signal(chain_name: str) -> dict[str, Any]:
    rows = _read_csv(INDUSTRY_PROFIT_FILE)
    rows = [
        row for row in rows
        if row.get("产业链") == chain_name and row.get("数据类型") == "工业增加值YoY_%"
    ]
    values = [_to_float(row.get("数值")) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {
            "label": "工业增加值同比代理",
            "available": False,
            "score": 50.0,
            "reason": "未读取到产销或工业增加值同比数据，按中性处理。",
            "source_rows": rows,
        }
    avg_growth = mean(values)
    score = _clip(50 + avg_growth * 2.5, 0, 100)
    return {
        "label": "工业增加值同比代理",
        "available": True,
        "score": round(score, 2),
        "reason": f"相关行业工业增加值同比均值 {avg_growth:.2f}%。",
        "source_rows": rows,
        "avg_growth": round(avg_growth, 4),
    }


def _capacity_signal(chain_name: str) -> dict[str, Any]:
    rows = _read_csv(CAPACITY_UTIL_FILE)
    chain_rows = [
        row for row in rows
        if chain_name in (row.get("产业链标签") or "")
    ]
    values = [_to_float(row.get("产能利用率_%")) for row in chain_rows]
    values = [value for value in values if value is not None]
    if not values:
        return {
            "label": "产能利用率",
            "available": False,
            "score": 50.0,
            "reason": "未读取到产业链相关产能利用率，按中性处理。",
            "source_rows": [],
        }
    avg_util = mean(values)
    score = _score_capacity(avg_util)
    return {
        "label": "产能利用率",
        "available": True,
        "score": round(score, 2),
        "reason": f"相关行业平均产能利用率 {avg_util:.2f}%。",
        "source_rows": chain_rows,
        "avg_capacity_utilization": round(avg_util, 4),
    }


def _pmi_signal() -> dict[str, Any]:
    rows = [
        row for row in _read_csv(PMI_FILE)
        if row.get("PMI分项") == "制造业-指数" and _to_float(row.get("指数值")) is not None
    ]
    if not rows:
        return {
            "label": "制造业PMI",
            "available": False,
            "score": 50.0,
            "reason": "未读取到制造业PMI，按中性处理。",
            "latest": {},
        }
    latest = rows[0]
    latest_value = _to_float(latest.get("指数值")) or 50
    recent_values = [_to_float(row.get("指数值")) for row in rows[:6]]
    recent_values = [value for value in recent_values if value is not None]
    avg_recent = mean(recent_values) if recent_values else latest_value
    score = _clip(50 + (latest_value - 50) * 8 + (avg_recent - 50) * 5, 0, 100)
    return {
        "label": "制造业PMI",
        "available": True,
        "score": round(score, 2),
        "reason": f"最新制造业PMI {latest_value:.2f}，近6个月均值 {avg_recent:.2f}。",
        "latest": latest,
        "six_month_average": round(avg_recent, 4),
    }


def _price_scissors_signal(chain_name: str) -> dict[str, Any]:
    rows = [
        row for row in _read_csv(PRICE_SCISSORS_FILE)
        if row.get("产业链") == chain_name and _to_float(row.get("价格剪刀差")) is not None
    ]
    if not rows:
        return {
            "label": "价格剪刀差",
            "available": False,
            "score": 50.0,
            "reason": "未读取到该产业链价格剪刀差，按中性处理。",
            "latest_rows": [],
        }
    latest_month = max(row.get("月份", "") for row in rows)
    latest_rows = [row for row in rows if row.get("月份") == latest_month]
    diffs = [_to_float(row.get("价格剪刀差")) for row in latest_rows]
    diffs = [value for value in diffs if value is not None]
    avg_diff = mean(diffs) if diffs else 0.0
    score = _clip(85 - abs(avg_diff) * 4.0 - max(avg_diff, 0) * 2.0, 0, 100)
    return {
        "label": "价格剪刀差",
        "available": True,
        "score": round(score, 2),
        "reason": f"最新月份 {latest_month} 平均价格剪刀差 {avg_diff:.2f} 个百分点。",
        "latest_rows": latest_rows,
        "avg_price_scissors": round(avg_diff, 4),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _score_capacity(value: float) -> float:
    if value < 65:
        return _clip(35 + (value - 55) * 2.5, 20, 60)
    if value <= 82:
        return _clip(60 + (value - 65) / 17 * 30, 60, 90)
    return _clip(90 - (value - 82) * 2.0, 55, 90)


def _month_num(text: str) -> int:
    try:
        return int(str(text).replace("月", "").strip())
    except ValueError:
        return 0


def _to_float(value: Any) -> float | None:
    try:
        text = str(value or "").replace(",", "").replace("%", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _fmt_pct(value: float | None) -> str:
    return "缺失" if value is None else f"{value:.2f}%"


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
