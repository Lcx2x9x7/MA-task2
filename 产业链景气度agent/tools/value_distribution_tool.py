from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


VALUE_DIR = Path("data") / "价值分配"
LAYER_MARGIN_FILE = VALUE_DIR / "layer_margin.csv"
COMPANY_MARGIN_FILE = VALUE_DIR / "company_margin.csv"


def calculate_value_distribution(chain_name: str) -> dict[str, Any]:
    layer_rows = _read_csv(LAYER_MARGIN_FILE, chain_name)
    company_rows = _read_csv(COMPANY_MARGIN_FILE, chain_name)
    if not layer_rows and not company_rows:
        return {
            "metric": "价值分配",
            "score": 50.0,
            "reason": "未读取到价值分配数据，按中性处理。",
            "source_files": {
                "layer_margin": str(LAYER_MARGIN_FILE),
                "company_margin": str(COMPANY_MARGIN_FILE),
            },
            "by_layer": {},
            "sub_scores": {},
        }

    latest_rows = _latest_company_rows(company_rows) or layer_rows
    by_layer = _aggregate_by_layer(latest_rows)
    all_gross = [_to_float(row.get("毛利率%")) for row in latest_rows]
    all_net = [_to_float(row.get("净利率%")) for row in latest_rows]
    all_roe = [_to_float(row.get("ROE加权%")) or _to_float(row.get("ROE_%")) for row in latest_rows]
    all_gross = [value for value in all_gross if value is not None]
    all_net = [value for value in all_net if value is not None]
    all_roe = [value for value in all_roe if value is not None]

    profitability_score = _score_profitability(
        mean(all_gross) if all_gross else None,
        mean(all_net) if all_net else None,
        mean(all_roe) if all_roe else None,
    )
    balance_score = _score_layer_balance(by_layer)
    healthy_layer_score = _score_healthy_layers(by_layer)
    trend_score = _score_margin_trend(company_rows)
    score = (
        profitability_score * 0.40
        + balance_score * 0.25
        + healthy_layer_score * 0.20
        + trend_score * 0.15
    )

    return {
        "metric": "价值分配",
        "score": round(_clip(score, 0, 100), 2),
        "reason": (
            f"读取最新利润样本 {len(latest_rows)} 条，平均毛利率 {_fmt(mean(all_gross) if all_gross else None)}%，"
            f"平均净利率 {_fmt(mean(all_net) if all_net else None)}%，"
            f"上中下游利润分配均衡度 {balance_score:.2f}。"
        ),
        "source_files": {
            "layer_margin": str(LAYER_MARGIN_FILE),
            "company_margin": str(COMPANY_MARGIN_FILE),
        },
        "by_layer": by_layer,
        "top_profit_companies": _top_companies(latest_rows, "净利率%"),
        "sub_scores": {
            "profitability": {
                "label": "整体盈利能力",
                "score": round(profitability_score, 2),
                "method": "使用最新报告期样本的毛利率、净利率和ROE加权评分；盈利能力越强，说明链条价值创造空间越好。",
            },
            "layer_balance": {
                "label": "上中下游分配均衡度",
                "score": round(balance_score, 2),
                "method": "比较上游、中游、下游平均净利率差异；差异越小且没有单环节长期挤压，分配越健康。",
            },
            "healthy_layers": {
                "label": "健康环节覆盖度",
                "score": round(healthy_layer_score, 2),
                "method": "统计上中下游中净利率为正且ROE不明显为负的环节占比；覆盖越广，链条盈利韧性越强。",
            },
            "margin_trend": {
                "label": "利润趋势",
                "score": round(trend_score, 2),
                "method": "用最新报告期净利率相对四个季度前的变化作为趋势代理；利润改善则加分，恶化则扣分。",
            },
        },
        "data_limitations": [
            "当前价值分配使用上市公司或代理公司财务指标，不能完全代表全量链上企业利润。",
            "部分节点使用代理公司映射，报告应结合企业真实财务和订单数据复核。",
        ],
    }


def _read_csv(path: Path, chain_name: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [row for row in rows if row.get("产业链") == chain_name]


def _latest_company_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    latest_period = max(row.get("报告期", "") for row in rows)
    return [row for row in rows if row.get("报告期") == latest_period]


def _aggregate_by_layer(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("上中下游") or "未分层"].append(row)
    result = {}
    for layer, items in grouped.items():
        gross = [_to_float(row.get("毛利率%")) for row in items]
        net = [_to_float(row.get("净利率%")) for row in items]
        roe = [_to_float(row.get("ROE加权%")) or _to_float(row.get("ROE_%")) for row in items]
        gross = [value for value in gross if value is not None]
        net = [value for value in net if value is not None]
        roe = [value for value in roe if value is not None]
        result[layer] = {
            "sample_count": len(items),
            "avg_gross_margin": round(mean(gross), 2) if gross else None,
            "avg_net_margin": round(mean(net), 2) if net else None,
            "avg_roe": round(mean(roe), 2) if roe else None,
            "positive_net_ratio": round(sum(1 for value in net if value > 0) / len(net), 4) if net else None,
        }
    return result


def _score_profitability(gross: float | None, net: float | None, roe: float | None) -> float:
    gross_score = _clip((gross or 0) * 1.8, 0, 100) if gross is not None else 50
    net_score = _clip(50 + (net or 0) * 2.5, 0, 100) if net is not None else 50
    roe_score = _clip(50 + (roe or 0) * 5.0, 0, 100) if roe is not None else 50
    return gross_score * 0.35 + net_score * 0.40 + roe_score * 0.25


def _score_layer_balance(by_layer: dict[str, dict[str, Any]]) -> float:
    margins = [
        row["avg_net_margin"]
        for layer, row in by_layer.items()
        if layer in {"上游", "中游", "下游"} and row.get("avg_net_margin") is not None
    ]
    if len(margins) < 2:
        return 50.0
    spread = max(margins) - min(margins)
    dispersion = pstdev(margins) if len(margins) >= 2 else 0.0
    return _clip(90 - spread * 1.8 - dispersion * 1.2, 20, 100)


def _score_healthy_layers(by_layer: dict[str, dict[str, Any]]) -> float:
    layers = [row for layer, row in by_layer.items() if layer in {"上游", "中游", "下游"}]
    if not layers:
        return 50.0
    healthy = 0
    for row in layers:
        if (row.get("avg_net_margin") or 0) > 0 and (row.get("avg_roe") or 0) > -2:
            healthy += 1
    return 40 + healthy / len(layers) * 60


def _score_margin_trend(company_rows: list[dict[str, str]]) -> float:
    if not company_rows:
        return 50.0
    by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in company_rows:
        by_code[row.get("股票代码", "")].append(row)
    deltas = []
    for rows in by_code.values():
        sorted_rows = sorted(rows, key=lambda row: row.get("报告期", ""))
        if len(sorted_rows) < 5:
            continue
        latest = _to_float(sorted_rows[-1].get("净利率%"))
        previous_year = _to_float(sorted_rows[-5].get("净利率%"))
        if latest is not None and previous_year is not None:
            deltas.append(latest - previous_year)
    if not deltas:
        return 50.0
    return _clip(50 + mean(deltas) * 3, 0, 100)


def _top_companies(rows: list[dict[str, str]], field: str) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda row: _to_float(row.get(field)) or -9999, reverse=True)[:8]
    return [
        {
            "company_name": row.get("公司名称", ""),
            "stock_code": row.get("股票代码", ""),
            "node": row.get("节点", ""),
            "layer": row.get("上中下游", ""),
            "gross_margin": row.get("毛利率%", ""),
            "net_margin": row.get("净利率%", ""),
            "roe": row.get("ROE加权%", row.get("ROE_%", "")),
        }
        for row in sorted_rows
    ]


def _to_float(value: Any) -> float | None:
    try:
        text = str(value or "").replace(",", "").replace("%", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _fmt(value: float | None) -> str:
    return "缺失" if value is None else f"{value:.2f}"


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
