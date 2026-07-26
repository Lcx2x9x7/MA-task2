from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from tools.xlsx_stream import iter_xlsx_rows


INDICATOR_FILE = Path("data") / "指标体系结果.xlsx"


def calculate_industry_abundance(chain_name: str) -> dict[str, Any]:
    source_row = load_indicator_system_row(chain_name)
    if not source_row:
        return {
            "metric": "产业链丰度",
            "score": 50.0,
            "reason": "未在指标体系结果表中读取到该产业链记录，按中性处理。",
            "source_file": str(INDICATOR_FILE),
            "source_row": {},
            "sub_scores": {}
        }

    enterprise_count = _to_float(source_row.get("链上企业总数（含财报）"))
    growth_proxy = _to_float(source_row.get("ETF近3月涨跌%"))
    concentration = _to_float(source_row.get("最高省集聚比例"))
    policy_count = _to_float(source_row.get("近3年国家级政策数"))

    scale_score = _score_market_scale(enterprise_count)
    growth_score = _score_growth_proxy(growth_proxy)
    concentration_score = _score_regional_concentration(concentration)
    support_score = _score_supporting_ecology(policy_count)
    score = (
        scale_score * 0.35
        + growth_score * 0.25
        + concentration_score * 0.25
        + support_score * 0.15
    )

    return {
        "metric": "产业链丰度",
        "score": round(_clip(score, 0, 100), 2),
        "reason": (
            f"指标体系结果表显示链上企业总数 {source_row.get('链上企业总数（含财报）', '缺失')}，"
            f"ETF近3月涨跌 {source_row.get('ETF近3月涨跌%', '缺失')}%，"
            f"最高省份 {source_row.get('集聚度最高省份', '缺失')} 集聚比例 {source_row.get('最高省集聚比例', '缺失')}。"
        ),
        "source_file": str(INDICATOR_FILE),
        "source_row": source_row,
        "sub_scores": {
            "market_scale": {
                "label": "产业链市场整体规模代理",
                "score": round(scale_score, 2),
                "source_field": "链上企业总数（含财报）",
                "source_value": source_row.get("链上企业总数（含财报）", ""),
                "method": "当前本地数据未提供 NBS 市场规模原始序列，使用指标体系结果表中的链上企业总数作为产业链规模代理。"
            },
            "growth": {
                "label": "近三年复合增长率代理",
                "score": round(growth_score, 2),
                "source_field": "ETF近3月涨跌%",
                "source_value": source_row.get("ETF近3月涨跌%", ""),
                "method": "当前本地数据未提供三年市场规模序列；按题意使用可得的 ETF 增长数据作为增长代理。现有指标体系结果表只有近3月涨跌，暂用近3月 ETF 涨跌率替代。"
            },
            "regional_concentration": {
                "label": "区域产业集聚度",
                "score": round(concentration_score, 2),
                "source_field": "集聚度最高省份/最高省企业数/最高省集聚比例",
                "source_value": (
                    f"{source_row.get('集聚度最高省份', '')} / "
                    f"{source_row.get('最高省企业数', '')} / "
                    f"{source_row.get('最高省集聚比例', '')}"
                ),
                "method": "当前使用指标体系结果表中由产业链企业区域分布计算出的最高省集聚比例；若后续有区县级产值，可替换为区域该产业产值/全国该产业总产值。"
            },
            "supporting_ecology": {
                "label": "政策和治理生态补充",
                "score": round(support_score, 2),
                "source_field": "近3年国家级政策数",
                "source_value": source_row.get("近3年国家级政策数", ""),
                "method": "政策数量不直接代表规模，但可作为产业链生态完善度的弱补充。"
            }
        },
        "data_limitations": [
            "当前未接入 NBS 市场规模原始数据，因此没有直接使用国家统计局市场规模原文。",
            "当前未拿到三年市场规模序列，因此没有计算严格意义的三年复合增长率。",
            "区域集聚度目前来自指标体系结果表的最高省集聚比例，尚未细化到区县产值口径。"
        ]
    }


def load_indicator_system_row(chain_name: str) -> dict[str, str]:
    if not INDICATOR_FILE.exists():
        return {}
    raw_rows = []
    for row in iter_xlsx_rows(INDICATOR_FILE):
        raw_rows.append(row)
        if len(raw_rows) >= 8:
            break
    if len(raw_rows) < 3:
        return {}
    header = raw_rows[1]
    for row in raw_rows[2:]:
        if row and row[0] == chain_name:
            return {
                header[index]: row[index] if index < len(row) else ""
                for index in range(len(header))
                if header[index]
            }
    return {}


def _score_market_scale(value: float | None) -> float:
    if not value or value <= 0:
        return 50.0
    return _clip((math.log10(value) - 3.5) / 1.6 * 100, 0, 100)


def _score_growth_proxy(value: float | None) -> float:
    if value is None:
        return 50.0
    return _clip(50 + value * 2.0, 0, 100)


def _score_regional_concentration(value: float | None) -> float:
    if value is None:
        return 50.0
    if value < 0.08:
        return 45 + value / 0.08 * 15
    if value <= 0.30:
        return 60 + (value - 0.08) / 0.22 * 30
    return _clip(90 - (value - 0.30) / 0.40 * 20, 50, 90)


def _score_supporting_ecology(value: float | None) -> float:
    if value is None:
        return 50.0
    return _clip(45 + value * 3, 0, 85)


def _to_float(value: Any) -> float | None:
    try:
        text = str(value or "").replace(",", "").replace("%", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
