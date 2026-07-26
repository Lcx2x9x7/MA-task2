from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


CHOKEPOINT_FILE = Path("data") / "卡脖子" / "卡脖子评级表.csv"


def calculate_chain_break_risk(crawl_bundle: dict[str, Any]) -> dict[str, Any]:
    chain_name = crawl_bundle.get("chain_name", "")
    histories = crawl_bundle.get("histories", {})
    etfs = crawl_bundle.get("etfs", [])
    policy_support = crawl_bundle.get("policy_support", {})
    abundance = crawl_bundle.get("industry_abundance", {})

    policy_risk = _policy_risk(policy_support)
    market_risk = _market_price_risk(histories, etfs, abundance)
    geopolitics_risk = _geopolitical_chokepoint_risk(chain_name)

    risk_score = (
        policy_risk["score"] * 0.30
        + market_risk["score"] * 0.35
        + geopolitics_risk["score"] * 0.35
    )
    risk_score = round(_clip(risk_score, 0, 100), 2)
    return {
        "metric": "断链风险",
        "risk_score": risk_score,
        "safety_score": round(100 - risk_score, 2),
        "reason": (
            f"政策监管风险 {policy_risk['score']}，市场价格风险 {market_risk['score']}，"
            f"卡脖子/地缘风险 {geopolitics_risk['score']}。"
        ),
        "components": {
            "policy_regulatory_risk": policy_risk,
            "market_price_risk": market_risk,
            "geopolitical_chokepoint_risk": geopolitics_risk,
        },
        "source_files": {
            "chokepoint_rating": str(CHOKEPOINT_FILE),
            "policy_text_dir": policy_support.get("policy_dir", ""),
            "etf_history": crawl_bundle.get("saved_files", {}).get("combined_history", ""),
            "indicator_system": abundance.get("source_file", ""),
        },
        "scoring_note": "断链风险为风险向指标，分数越高代表风险越高；综合景气分中使用 safety_score=100-risk_score 参与加权。"
    }


def _policy_risk(policy_support: dict[str, Any]) -> dict[str, Any]:
    signals = policy_support.get("signals", {})
    constraint = float(signals.get("constraint_risk") or 0)
    policy_score = float(policy_support.get("score") or 50)
    score = _clip(constraint * 0.70 + max(0, 70 - policy_score) * 0.30, 0, 100)
    return {
        "label": "政策与监管风险",
        "score": round(score, 2),
        "reason": (
            f"政策环境得分 {policy_score:.2f}，政策文本中的监管/约束风险信号 {constraint:.2f}。"
            "政策方向变化当前由政策文本的约束词、监管词和政策环境强弱共同代理。"
        ),
        "raw_signals": signals,
    }


def _market_price_risk(histories: dict[str, list[dict[str, Any]]], etfs: list[dict[str, Any]], abundance: dict[str, Any]) -> dict[str, Any]:
    etf_risks = []
    for etf in etfs:
        code = etf["code"]
        rows = sorted(histories.get(code, []), key=lambda row: row.get("date", ""))
        closes = [_to_float(row.get("close")) for row in rows]
        closes = [value for value in closes if value is not None]
        if len(closes) < 25:
            continue
        returns = [
            (closes[index] - closes[index - 1]) / closes[index - 1] * 100
            for index in range(1, len(closes))
            if closes[index - 1]
        ]
        recent_returns = returns[-20:]
        volatility = pstdev(recent_returns) if len(recent_returns) >= 2 else 0.0
        return_20d = (closes[-1] - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 and closes[-21] else 0.0
        drawdown_risk = _clip(-return_20d * 2.2, 0, 70)
        volatility_risk = _clip(volatility * 10, 0, 40)
        etf_risks.append({
            "code": code,
            "layer": etf.get("layer", ""),
            "return_20d": round(return_20d, 4),
            "volatility_20d": round(volatility, 4),
            "risk": round(_clip(drawdown_risk + volatility_risk, 0, 100), 2),
        })

    avg_etf_risk = mean([row["risk"] for row in etf_risks]) if etf_risks else 50.0
    ppi_value = _to_float(abundance.get("source_row", {}).get("PPI近期同比均值%（价格代理）"))
    ppi_risk = _clip(-ppi_value * 8, 0, 30) if ppi_value is not None else 10.0
    score = _clip(avg_etf_risk * 0.85 + ppi_risk * 0.15, 0, 100)
    return {
        "label": "市场与价格风险",
        "score": round(score, 2),
        "reason": (
            f"ETF 近20日下行和波动风险均值 {avg_etf_risk:.2f}，"
            f"PPI价格代理风险 {ppi_risk:.2f}。核心原材料价格波动率当前用上游/相关ETF波动率代理，产品价格下行趋势用ETF近20日收益和PPI代理。"
        ),
        "etf_risks": etf_risks,
        "ppi_proxy": {
            "source_field": "PPI近期同比均值%（价格代理）",
            "source_value": abundance.get("source_row", {}).get("PPI近期同比均值%（价格代理）", ""),
        }
    }


def _geopolitical_chokepoint_risk(chain_name: str) -> dict[str, Any]:
    rows = _load_chokepoint_rows(chain_name)
    if not rows:
        return {
            "label": "地缘政治与卡脖子风险",
            "score": 35.0,
            "reason": "卡脖子评级表没有命中该产业链，按中低风险处理。",
            "matched_count": 0,
            "top_risk_nodes": [],
            "source_file": str(CHOKEPOINT_FILE),
        }
    scores = [_to_float(row.get("总分(0-16)")) or 0 for row in rows]
    normalized = [score / 16 * 100 for score in scores]
    high_count = sum(1 for row in rows if row.get("卡脖子等级") in {"S级", "A级"})
    high_ratio = high_count / len(rows)
    score = _clip(mean(normalized) * 0.65 + high_ratio * 100 * 0.35, 0, 100)
    top_nodes = sorted(rows, key=lambda row: _to_float(row.get("总分(0-16)")) or 0, reverse=True)[:10]
    return {
        "label": "地缘政治与卡脖子风险",
        "score": round(score, 2),
        "reason": (
            f"卡脖子评级表命中 {len(rows)} 个节点，其中 S/A 级高风险节点 {high_count} 个，"
            f"高风险占比 {high_ratio:.2%}。"
        ),
        "matched_count": len(rows),
        "high_risk_count": high_count,
        "high_risk_ratio": round(high_ratio, 4),
        "top_risk_nodes": [
            {
                "node_name": row.get("节点名称", ""),
                "chain": row.get("产业链", ""),
                "layer": row.get("层级", ""),
                "score_0_16": row.get("总分(0-16)", ""),
                "level": row.get("卡脖子等级", ""),
                "description": row.get("等级说明", ""),
                "evidence": row.get("判断依据", ""),
            }
            for row in top_nodes
        ],
        "source_file": str(CHOKEPOINT_FILE),
    }


def _load_chokepoint_rows(chain_name: str) -> list[dict[str, str]]:
    if not CHOKEPOINT_FILE.exists():
        return []
    chain_key = "半导体" if "半导体" in chain_name else "新能源汽车" if "新能源" in chain_name else chain_name
    with CHOKEPOINT_FILE.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [row for row in rows if row.get("产业链") == chain_key]


def _to_float(value: Any) -> float | None:
    try:
        text = str(value or "").replace(",", "").replace("%", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
