from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from tools.industry_abundance_tool import load_indicator_system_row


REPORT_DIR = Path("outputs") / "reports"


def calculate_chain_environment(chain_name: str | None) -> dict[str, Any]:
    """Use the latest chain evaluation as the enterprise's external chain environment."""
    if not chain_name:
        return _neutral("未识别企业所属产业链，链条环境按中性处理。")

    latest_report = _find_latest_chain_report(chain_name)
    if latest_report:
        try:
            data = json.loads(latest_report.read_text(encoding="utf-8"))
            score = _to_float(data.get("score")) or 50.0
            return {
                "metric": "链条环境",
                "score": round(_clip(score, 0, 100), 2),
                "reason": (
                    f"读取最近一次产业链评估报告 {latest_report.name}，"
                    f"产业链综合分 {score:.2f}，等级 {data.get('level', '缺失')}。"
                ),
                "chain_name": chain_name,
                "level": data.get("level", ""),
                "source_type": "latest_chain_evaluation_report",
                "source_file": str(latest_report),
                "components_summary": _summarize_components(data.get("components", {})),
                "data_limitations": [
                    "链条环境为企业外部环境代理指标，继承最近一次产业链评估的实时行情和离线数据口径。",
                    "若产业链评估报告不是当前运行即时生成，结果会受到报告时间影响。",
                ],
            }
        except Exception as exc:
            return _neutral(f"读取最近产业链评估报告失败：{exc}")

    fallback = _indicator_system_fallback(chain_name)
    if fallback:
        return fallback
    return _neutral(f"未找到 {chain_name} 的历史产业链评估报告或指标体系结果，链条环境按中性处理。")


def select_chain_name_for_environment(chain_rows: list[dict[str, str]], fallback: str | None = None) -> str | None:
    """Prefer a matched chain that has a usable chain environment report."""
    chain_names = []
    seen = set()
    for row in chain_rows:
        name = row.get("产业链名称")
        if name and name not in seen:
            seen.add(name)
            chain_names.append(name)
    if fallback and fallback not in seen:
        chain_names.append(fallback)

    for name in chain_names:
        if _find_latest_chain_report(name):
            return name
    for name in chain_names:
        if load_indicator_system_row(name):
            return name
    return fallback or (chain_names[0] if chain_names else None)


def _find_latest_chain_report(chain_name: str) -> Path | None:
    if not REPORT_DIR.exists():
        return None
    candidates = sorted(REPORT_DIR.glob("*_chain_etf_report_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("chain_name") == chain_name:
            return path
    return None


def _indicator_system_fallback(chain_name: str) -> dict[str, Any]:
    row = load_indicator_system_row(chain_name)
    if not row:
        return {}

    enterprise_count = _to_float(row.get("链上企业总数（含财报）"))
    etf_change = _to_float(row.get("ETF近3月涨跌%"))
    concentration = _to_float(row.get("最高省集聚比例"))
    policy_count = _to_float(row.get("近3年国家级政策数"))

    scale_score = _log_score(enterprise_count, 3_000, 200_000)
    trend_score = 50.0 if etf_change is None else _clip(50 + etf_change * 2, 0, 100)
    concentration_score = 50.0 if concentration is None else _clip(60 + min(concentration, 0.30) / 0.30 * 25, 40, 85)
    policy_score = 50.0 if policy_count is None else _clip(45 + policy_count * 3, 0, 85)
    score = scale_score * 0.35 + trend_score * 0.25 + concentration_score * 0.25 + policy_score * 0.15

    return {
        "metric": "链条环境",
        "score": round(_clip(score, 0, 100), 2),
        "reason": (
            "未找到最近产业链评估报告，使用指标体系结果表作为弱代理："
            f"链上企业数 {row.get('链上企业总数（含财报）', '缺失')}，"
            f"ETF近3月涨跌 {row.get('ETF近3月涨跌%', '缺失')}%，"
            f"最高省集聚比例 {row.get('最高省集聚比例', '缺失')}。"
        ),
        "chain_name": chain_name,
        "level": "",
        "source_type": "indicator_system_fallback",
        "source_file": str(Path("data") / "指标体系结果.xlsx"),
        "source_row": row,
        "components_summary": [
            {"label": "规模代理", "score": round(scale_score, 2)},
            {"label": "趋势代理", "score": round(trend_score, 2)},
            {"label": "集聚代理", "score": round(concentration_score, 2)},
            {"label": "政策代理", "score": round(policy_score, 2)},
        ],
        "data_limitations": [
            "未复用到完整产业链评估报告，链条环境仅由指标体系结果表弱代理。",
            "该指标用于企业外部环境修正，不代表企业自身经营能力。",
        ],
    }


def _summarize_components(components: dict[str, Any]) -> list[dict[str, Any]]:
    summary = []
    for component in components.values():
        if not isinstance(component, dict):
            continue
        summary.append({
            "label": component.get("label", ""),
            "score": component.get("score", ""),
            "weight": component.get("weight", ""),
        })
    return summary


def _neutral(reason: str) -> dict[str, Any]:
    return {
        "metric": "链条环境",
        "score": 50.0,
        "reason": reason,
        "chain_name": "",
        "level": "",
        "source_type": "neutral",
        "source_file": "",
        "components_summary": [],
        "data_limitations": ["链条环境缺少可用数据，暂按中性分处理。"],
    }


def _log_score(value: float | None, low: float, high: float) -> float:
    if value is None or value <= 0:
        return 50.0
    return _clip((math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low)) * 100, 0, 100)


def _to_float(value: Any) -> float | None:
    try:
        text = str(value or "").replace(",", "").replace("%", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
