from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.xlsx_stream import iter_xlsx_dicts


FINANCIAL_FILE = Path("data") / "企业财报.xlsx"


def calculate_enterprise_financial_quality(uid: str) -> dict[str, Any]:
    row = find_enterprise_financial_row(uid)
    if not row:
        return {
            "metric": "财务质量",
            "score": 50.0,
            "reason": "企业财报表中未命中该 UID，按中性处理。",
            "source_file": str(FINANCIAL_FILE),
            "source_row": {},
            "sub_scores": {},
            "data_limitations": ["未命中企业财报数据，不能据此判断企业真实财务质量。"],
        }

    scale = _score_scale(row)
    profitability = _score_profitability(row)
    solvency = _score_solvency(row)
    cashflow = _score_cashflow(row)
    status = _score_status(row)
    score = (
        scale["score"] * 0.20
        + profitability["score"] * 0.25
        + solvency["score"] * 0.25
        + cashflow["score"] * 0.20
        + status["score"] * 0.10
    )
    return {
        "metric": "财务质量",
        "score": round(_clip(score, 0, 100), 2),
        "reason": (
            f"企业规模 {row.get('企业规模国标', '缺失')}，资产负债率 {row.get('资产负债率', '缺失')}，"
            f"营业收入 {row.get('营业收入', '缺失')}，净利润 {row.get('净利润', '缺失')}，"
            f"经营现金流净额 {row.get('经营活动产生的现金流量净额', '缺失')}。"
        ),
        "source_file": str(FINANCIAL_FILE),
        "source_row": _compact_row(row),
        "sub_scores": {
            "scale": scale,
            "profitability": profitability,
            "solvency": solvency,
            "cashflow": cashflow,
            "status": status,
        },
        "data_limitations": [
            "财务质量仅使用本地财报表字段，不代表正式审计判断或信用评级。",
            "部分企业财务字段可能为空，缺失项按中性处理并在子项原因中说明。",
        ],
    }


def find_enterprise_financial_row(uid: str) -> dict[str, str]:
    if not FINANCIAL_FILE.exists():
        return {}
    for row in iter_xlsx_dicts(FINANCIAL_FILE):
        if row.get("客户UID") == uid:
            return row
    return {}


def _score_scale(row: dict[str, str]) -> dict[str, Any]:
    assets = _to_float(row.get("资产合计"))
    revenue = _to_float(row.get("营业收入"))
    employees = _to_float(row.get("员工人数"))
    registered_capital = _to_float(row.get("注册资本"))
    values = [
        _log_score(assets, 1_000_000, 200_000_000),
        _log_score(revenue, 500_000, 100_000_000),
        _log_score(registered_capital, 500_000, 80_000_000),
        _clip((employees or 0) / 300 * 100, 0, 100) if employees is not None else 50,
    ]
    score = sum(values) / len(values)
    return {
        "label": "规模实力",
        "score": round(score, 2),
        "reason": f"资产 {assets or '缺失'}，收入 {revenue or '缺失'}，注册资本 {registered_capital or '缺失'}，员工 {employees or '缺失'}。",
    }


def _score_profitability(row: dict[str, str]) -> dict[str, Any]:
    revenue = _to_float(row.get("营业收入"))
    gross_margin = _to_float(row.get("销售毛利率"))
    net_profit = _to_float(row.get("净利润"))
    operating_profit = _to_float(row.get("营业利润"))
    if gross_margin is None and revenue and net_profit is not None:
        gross_margin = net_profit / revenue * 100
    margin_score = _clip(50 + (gross_margin or 0) * 1.5, 0, 100) if gross_margin is not None else 50
    profit_score = _clip(50 + ((net_profit or 0) / max(revenue or 1, 1)) * 300, 0, 100) if revenue and net_profit is not None else 50
    positive_score = 70 if (net_profit or 0) > 0 and (operating_profit or 0) > 0 else 35 if net_profit is not None else 50
    score = margin_score * 0.35 + profit_score * 0.40 + positive_score * 0.25
    return {
        "label": "盈利能力",
        "score": round(score, 2),
        "reason": f"销售毛利率 {row.get('销售毛利率', '缺失')}，营业利润 {row.get('营业利润', '缺失')}，净利润 {row.get('净利润', '缺失')}。",
    }


def _score_solvency(row: dict[str, str]) -> dict[str, Any]:
    debt_ratio = _to_float(row.get("资产负债率"))
    current_assets = _to_float(row.get("流动资产合计"))
    current_liabilities = _to_float(row.get("流动负债合计"))
    equity = _to_float(row.get("所有者权益合计"))
    liabilities = _to_float(row.get("负债合计"))
    if debt_ratio is None:
        assets = _to_float(row.get("资产合计"))
        if assets and liabilities is not None:
            debt_ratio = liabilities / assets * 100
    debt_score = 50 if debt_ratio is None else _clip(100 - abs(debt_ratio - 45) * 1.5, 20, 95)
    current_ratio = current_assets / current_liabilities if current_assets and current_liabilities else None
    current_score = 50 if current_ratio is None else _clip(45 + min(current_ratio, 3) / 3 * 45, 20, 90)
    equity_score = 70 if (equity or 0) > 0 else 35 if equity is not None else 50
    score = debt_score * 0.45 + current_score * 0.35 + equity_score * 0.20
    return {
        "label": "偿债压力",
        "score": round(score, 2),
        "reason": f"资产负债率 {debt_ratio if debt_ratio is not None else '缺失'}，流动比率 {round(current_ratio, 4) if current_ratio else '缺失'}，所有者权益 {equity if equity is not None else '缺失'}。",
    }


def _score_cashflow(row: dict[str, str]) -> dict[str, Any]:
    revenue = _to_float(row.get("营业收入"))
    cash_in_ratio = _to_float(row.get("现金收入比率"))
    operating_cashflow = _to_float(row.get("经营活动产生的现金流量净额"))
    cash_balance = _to_float(row.get("期末现金及现金等价物余额")) or _to_float(row.get("货币资金"))
    ratio_score = _clip((cash_in_ratio or 0) * 80, 0, 100) if cash_in_ratio is not None else 50
    cashflow_score = 50
    if operating_cashflow is not None:
        if revenue:
            cashflow_score = _clip(50 + operating_cashflow / revenue * 200, 0, 100)
        else:
            cashflow_score = 70 if operating_cashflow > 0 else 35
    cash_balance_score = _log_score(cash_balance, 100_000, 30_000_000)
    score = ratio_score * 0.35 + cashflow_score * 0.45 + cash_balance_score * 0.20
    return {
        "label": "现金流质量",
        "score": round(score, 2),
        "reason": f"现金收入比率 {row.get('现金收入比率', '缺失')}，经营现金流净额 {row.get('经营活动产生的现金流量净额', '缺失')}，现金余额 {cash_balance if cash_balance is not None else '缺失'}。",
    }


def _score_status(row: dict[str, str]) -> dict[str, Any]:
    status = row.get("经营状态", "")
    tax_rank = _to_float(row.get("纳税总额排名（市）"))
    status_score = 75 if status in {"A", "B", "正常", "存续", "在业"} else 45 if status else 50
    tax_score = 50
    if tax_rank is not None and tax_rank > 0:
        tax_score = _clip(80 - tax_rank / 200000 * 40, 35, 80)
    score = status_score * 0.70 + tax_score * 0.30
    return {
        "label": "经营状态",
        "score": round(score, 2),
        "reason": f"经营状态 {status or '缺失'}，市纳税排名 {tax_rank if tax_rank is not None else '缺失'}。",
    }


def _compact_row(row: dict[str, str]) -> dict[str, str]:
    fields = [
        "客户UID", "注册资本", "实收资本", "纳税总额排名（市）", "企业规模国标", "员工人数",
        "经营状态", "注册地址_省", "注册地址_市", "注册地址_区县", "国标行业1级", "国标行业2级",
        "年报日期", "资产负债率", "资产合计", "负债合计", "流动资产合计", "流动负债合计",
        "所有者权益合计", "营业收入", "营业成本", "营业利润", "净利润", "销售毛利率",
        "现金收入比率", "经营活动产生的现金流量净额", "期末现金及现金等价物余额",
    ]
    return {field: row.get(field, "") for field in fields}


def _log_score(value: float | None, low: float, high: float) -> float:
    if value is None or value <= 0:
        return 50.0
    import math
    return _clip((math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low)) * 100, 0, 100)


def _to_float(value: Any) -> float | None:
    try:
        text = str(value or "").replace(",", "").replace("%", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
