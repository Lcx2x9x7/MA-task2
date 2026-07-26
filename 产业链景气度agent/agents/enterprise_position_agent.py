from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from tools.llm_client import LLMClient


class EnterprisePositionAgent:
    """Evaluate one enterprise by its position in chain and settlement networks."""

    metric_name = "链上地位"

    def score(self, search_bundle: dict[str, Any]) -> dict[str, Any]:
        uid = search_bundle["uid"]
        chain_rows = search_bundle.get("chain_rows", [])
        settlement_rows = search_bundle.get("settlement_rows", [])
        fund_flow = search_bundle.get("fund_flow") or {
            "score": 50.0,
            "reason": "未接入资金活跃度数据，按中性处理。"
        }
        financial_quality = search_bundle.get("financial_quality") or {
            "score": 50.0,
            "reason": "未接入财务质量数据，按中性处理。"
        }
        chain_environment = search_bundle.get("chain_environment") or {
            "score": 50.0,
            "reason": "未接入链条环境数据，按中性处理。"
        }

        chain_score = self._score_chain_criticality(chain_rows)
        connection_score = self._score_connection_breadth(settlement_rows)
        position_score = chain_score["score"] * 0.60 + connection_score["score"] * 0.40
        fund_flow_score = float(fund_flow.get("score", 50.0))
        financial_score = float(financial_quality.get("score", 50.0))
        environment_score = float(chain_environment.get("score", 50.0))
        score = (
            position_score * 0.35
            + fund_flow_score * 0.25
            + financial_score * 0.20
            + environment_score * 0.20
        )
        business_assessment = _build_business_assessment(
            score=score,
            position_score=position_score,
            fund_flow=fund_flow,
            financial_quality=financial_quality,
            chain_environment=chain_environment
        )

        result = {
            "uid": uid,
            "metric": "企业链上分层综合评价",
            "score": round(score, 2),
            "layer": self._classify(score),
            "business_assessment": business_assessment,
            "components": {
                "chain_position": {
                    "label": self.metric_name,
                    "weight": 0.35,
                    "score": round(position_score, 2),
                    "reason": "由环节关键程度和上下游连接广度共同计算。",
                    "sub_components": {
                        "chain_criticality": chain_score,
                        "connection_breadth": connection_score
                    }
                },
                "fund_flow": {
                    "label": "资金活跃",
                    "weight": 0.25,
                    "score": round(fund_flow_score, 2),
                    "reason": fund_flow.get("reason", ""),
                    "detail": fund_flow
                },
                "financial_quality": {
                    "label": "财务质量",
                    "weight": 0.20,
                    "score": round(financial_score, 2),
                    "reason": financial_quality.get("reason", ""),
                    "detail": financial_quality
                },
                "chain_environment": {
                    "label": "链条环境",
                    "weight": 0.20,
                    "score": round(environment_score, 2),
                    "reason": chain_environment.get("reason", ""),
                    "detail": chain_environment
                }
            },
            "summary": self._summary(uid, score, chain_score, connection_score, fund_flow, financial_quality, chain_environment),
            "evidence": {
                "chain_rows_count": len(chain_rows),
                "settlement_rows_count": len(settlement_rows),
                "top_chains": self._top_values(chain_rows, "产业链名称"),
                "top_nodes": self._top_values(chain_rows, "节点名称"),
                "top_node_layers": self._top_values(chain_rows, "节点上中下属性"),
                "settlement_direction": self._top_values(settlement_rows, "交易方向名称")
            },
            "sample_records": {
                "chain_rows": chain_rows[:20],
                "settlement_rows": settlement_rows[:20]
            },
            "data_files": search_bundle.get("data_files", {})
        }
        if search_bundle.get("cache"):
            result["cache"] = search_bundle["cache"]
        return result

    def enrich_with_llm(self, result: dict[str, Any], llm_client: LLMClient | None) -> dict[str, Any]:
        if llm_client is None:
            result["llm_interpretation"] = {
                "available": False,
                "content": "未配置或未启用 LLM，跳过企业分层解读。"
            }
            return result

        prompt_payload = {
            "metric": result["metric"],
            "score": result["score"],
            "layer": result["layer"],
            "business_assessment": result.get("business_assessment", {}),
            "components": result["components"],
            "evidence": result["evidence"]
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是银行对公客户经营分析专家，服务对象是银行对公客户经理。你的任务不是写行业研究报告，而是把企业分层结果转化为客户经理能直接执行的经营作战卡。"
                    "只能基于给出的产业链命中、结算链连接、财报字段、产业链环境和规则评分，不要编造企业名称、信用评级或确定性授信结论。"
                    "报告中的企业名称统一写为“企业***”，严禁输出客户UID或任何长串脱敏编号。"
                    "必须关注真实工作动作：是否值得跟、推什么产品、拜访问什么、授信前核验什么。"
                    "输出中文，控制在900字以内，务实、克制、可落地。不要输出报告标题。"
                )
            },
            {
                "role": "user",
                "content": (
                    "请严格按以下六个小节输出，每个小节 2-4 句；不要输出 Markdown 一级标题，不要输出客户UID，不要重复首页表格中的字段清单：\n"
                    "1. 评估结论：基于经营优先级、风险等级、机会等级和企业分层给出判断，避免机械重复分数表内容。\n"
                    "2. 指标证据：用链上地位、资金活跃、财务质量、链条环境四个指标解释结论，每个判断都要回到给定的数据依据。\n"
                    "3. 产品机会：给出可落地的银行产品组合，至少覆盖结算、票据/保理/供应链金融、授信或现金管理中的合适项，并说明切入逻辑。\n"
                    "4. 客户跟进措施：列出下一次沟通要问的关键问题和要收集的材料，例如订单、合同、发票、流水、应收账款、主要客户/供应商清单。\n"
                    "5. 风险核验：说明授信或业务落地前必须核验的底线，包括交易真实性、交易对手集中度、现金流、财报质量和产业链风险。\n"
                    "6. 底线结论：明确本报告不能替代信用评级和授信审批，只能作为客户经营线索和尽调优先级参考。\n"
                    f"评分数据如下：{prompt_payload}"
                )
            }
        ]
        try:
            result["llm_interpretation"] = {
                "available": True,
                "model": llm_client.model,
                "role": "bank_enterprise_relationship_manager_advisor",
                "content": llm_client.chat(messages, max_tokens=1200)
            }
        except Exception as exc:
            result["llm_interpretation"] = {
                "available": False,
                "content": f"LLM 企业分层解读调用失败：{exc}"
            }
        return result

    def save_report(self, result: dict[str, Any], output_root: str | Path = "outputs/enterprise_reports") -> dict[str, str]:
        output_dir = Path(output_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"enterprise_position_{result['uid'][:12]}_{stamp}"
        json_path = output_dir / f"{prefix}.json"
        md_path = output_dir / f"{prefix}.md"
        report_files = dict(result.get("report_files", {}))
        report_files.update({
            "json": str(json_path),
            "markdown": str(md_path)
        })
        result["report_files"] = report_files
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(self.to_markdown(result), encoding="utf-8")
        return result["report_files"]

    def to_markdown(self, result: dict[str, Any]) -> str:
        components = result["components"]
        chain_position = components["chain_position"]
        chain_sub = chain_position["sub_components"]
        fund = components["fund_flow"]
        fund_detail = fund.get("detail", {})
        financial = components["financial_quality"]
        financial_detail = financial.get("detail", {})
        chain_env = components["chain_environment"]
        chain_env_detail = chain_env.get("detail", {})
        business = result.get("business_assessment", {})
        lines = [
            f"# 企业客户评估报告",
            "",
            "## 评估结论",
            "",
            "- 企业名称：企业***",
            f"- 指标：{result['metric']}",
            f"- 得分：{result['score']}",
            f"- 分层：{result['layer']}",
            f"- 经营优先级：{business.get('priority_label', '缺失')}",
            f"- 机会等级：{business.get('opportunity_level', '缺失')}",
            f"- 风险等级：{business.get('risk_level', '缺失')}",
            f"- 建议动作：{business.get('recommended_action', '缺失')}",
            f"- 一句话总结：{result['summary']}",
            "",
            "## 建议-证据映射",
            "",
            "| 建议 | 数据依据 | 客户经理动作 |",
            "|---|---|---|",
            *_recommendation_rows(business.get("recommendation_evidence", [])),
            "",
            "## 评估结论和建议",
            "",
            result.get("llm_interpretation", {}).get("content", "未生成 LLM 解读。"),
            "",
            "## 指标得分",
            "",
            "| 子项 | 权重 | 得分 | 说明 |",
            "|---|---:|---:|---|",
            f"| 链上地位 | 35% | {chain_position['score']} | {chain_position['reason']} |",
            f"| 资金活跃 | 25% | {fund['score']} | {fund['reason']} |",
            f"| 财务质量 | 20% | {financial['score']} | {financial['reason']} |",
            f"| 链条环境 | 20% | {chain_env['score']} | {chain_env['reason']} |",
            f"| 环节关键程度 | 链上地位子项60% | {chain_sub['chain_criticality']['score']} | {chain_sub['chain_criticality']['reason']} |",
            f"| 上下游连接广度 | 链上地位子项40% | {chain_sub['connection_breadth']['score']} | {chain_sub['connection_breadth']['reason']} |",
            "",
            "## 资金活跃明细",
            "",
            f"- 交易对手数：{fund_detail.get('counterparty_count', 0)}",
            f"- 交易对手集中度：{fund_detail.get('counterparty_concentration', 0):.2%}",
            f"- 链上交易金额代理占比：{fund_detail.get('chain_amount_share', 0):.4%}",
            f"- 交易经营活跃度：{fund_detail.get('activity_count', 0)}",
            f"- 大额交易活跃度：{fund_detail.get('large_activity_count', 0)}",
            "",
            "## 财务质量明细",
            "",
            "| 子项 | 得分 | 说明 |",
            "|---|---:|---|",
            *_financial_rows(financial_detail.get("sub_scores", {})),
            "",
            f"- 年报日期：{financial_detail.get('source_row', {}).get('年报日期', '缺失')}",
            f"- 企业规模：{financial_detail.get('source_row', {}).get('企业规模国标', '缺失')}",
            f"- 注册地：{financial_detail.get('source_row', {}).get('注册地址_省', '')}{financial_detail.get('source_row', {}).get('注册地址_市', '')}{financial_detail.get('source_row', {}).get('注册地址_区县', '')}",
            f"- 行业：{financial_detail.get('source_row', {}).get('国标行业1级', '')} / {financial_detail.get('source_row', {}).get('国标行业2级', '')}",
            f"- 数据来源：{financial_detail.get('source_file', '缺失')}",
            "",
            "## 链条环境明细",
            "",
            f"- 所属产业链：{chain_env_detail.get('chain_name', '缺失')}",
            f"- 外部环境分：{chain_env_detail.get('score', chain_env['score'])}",
            f"- 外部环境等级：{chain_env_detail.get('level', '缺失') or '缺失'}",
            f"- 数据来源：{chain_env_detail.get('source_file', '缺失') or '缺失'}",
            f"- 计算说明：{chain_env_detail.get('reason', chain_env['reason'])}",
            "",
            "| 产业链指标 | 得分 | 权重 |",
            "|---|---:|---:|",
            *_chain_environment_rows(chain_env_detail.get("components_summary", [])),
            "",
            "## 证据摘要",
            "",
            f"- 命中产业链记录数：{result['evidence']['chain_rows_count']}",
            f"- 命中结算链记录数：{result['evidence']['settlement_rows_count']}",
            f"- 主要产业链：{_fmt_counter(result['evidence']['top_chains'])}",
            f"- 主要节点：{_fmt_counter(result['evidence']['top_nodes'])}",
            f"- 上中下游属性：{_fmt_counter(result['evidence']['top_node_layers'])}",
            f"- 结算方向：{_fmt_counter(result['evidence']['settlement_direction'])}",
            f"- 缓存命中：{result.get('cache', {}).get('hit', '未知')}",
            "",
            "## 分层标准",
            "",
            "| 得分 | 层级 | 含义 |",
            "|---:|---|---|",
            "| >= 80 | 核心层 | 链上地位、交易活跃、财务质量和外部环境整体较强 |",
            "| 65-80 | 骨干层 | 具备较稳定链上角色，至少一个经营或环境维度较强 |",
            "| 45-65 | 基础层 | 有明确链上角色，但经营质量或外部环境仍需核验 |",
            "| < 45 | 边缘层 | 链上证据、资金连接或经营质量偏弱 |",
            "",
            "## 说明",
            "",
            "- 当前企业分层使用链上地位、资金活跃、财务质量和链条环境四个指标。",
            "- 链上地位由产业链表中的节点/层级/分值，以及结算链中的上下游交易连接共同决定。",
            "- 资金活跃由交易对手集中度、上下游链接广度、链上交易金额代理占比、大额交易活跃度共同决定。",
            "- 财务质量来自企业财报表，链条环境来自最近产业链评估结果或指标体系结果表。",
            "- 当前企业名称不可见，报告统一使用“企业***”作为脱敏展示名称。",
            "- 该分层不是信用评级，不直接代表授信结论。"
        ]
        return "\n".join(lines)

    def _score_chain_criticality(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        if not rows:
            return {"score": 0.0, "reason": "产业链表中没有命中该 UID"}

        raw_scores = [_to_float(row.get("分值")) for row in rows]
        raw_scores = [value for value in raw_scores if value is not None]
        avg_raw = mean(raw_scores) if raw_scores else 50.0
        unique_chains = len({row.get("产业链名称") for row in rows if row.get("产业链名称")})
        unique_nodes = len({row.get("节点代码") for row in rows if row.get("节点代码")})
        max_node_level = max((_to_float(row.get("节点层级")) or 0 for row in rows), default=0)

        breadth_bonus = min(unique_chains * 4 + unique_nodes * 1.5, 20)
        level_bonus = min(max_node_level * 2, 10)
        score = _clip(avg_raw * 0.75 + 15 + breadth_bonus + level_bonus, 0, 100)
        return {
            "score": round(score, 2),
            "reason": (
                f"产业链命中 {len(rows)} 条，覆盖 {unique_chains} 个产业链、{unique_nodes} 个节点，"
                f"平均节点分值 {avg_raw:.2f}，最高节点层级 {max_node_level:.0f}"
            )
        }

    def _score_connection_breadth(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        if not rows:
            return {"score": 0.0, "reason": "结算链表中没有命中该 UID"}

        counterparties = set()
        total_tx_count = 0
        directions = Counter()
        amount_score_sum = 0.0
        for row in rows:
            if row.get("交易对手客户UID"):
                counterparties.add(row["交易对手客户UID"])
            total_tx_count += int(_to_float(row.get("现金+票据交易笔数")) or 0)
            directions[row.get("交易方向名称") or "未知"] += 1
            amount_score_sum += _amount_bucket_score(row.get("现金+票据交易金额区间", ""))

        counterparty_score = min(len(counterparties) * 8, 45)
        tx_count_score = min(total_tx_count / 10, 25)
        direction_score = 15 if len([k for k in directions if k in {"入账", "出账"}]) >= 2 else 8
        amount_score = min(amount_score_sum / max(len(rows), 1), 15)
        score = _clip(counterparty_score + tx_count_score + direction_score + amount_score, 0, 100)
        return {
            "score": round(score, 2),
            "reason": (
                f"结算链命中 {len(rows)} 条，唯一交易对手 {len(counterparties)} 个，"
                f"现金+票据交易笔数合计 {total_tx_count}，方向分布 {dict(directions)}"
            )
        }

    @staticmethod
    def _top_values(rows: list[dict[str, str]], field: str, limit: int = 8) -> list[dict[str, Any]]:
        counter = Counter(row.get(field) or "缺失" for row in rows)
        return [{"value": value, "count": count} for value, count in counter.most_common(limit)]

    @staticmethod
    def _summary(
        uid: str,
        score: float,
        chain_score: dict[str, Any],
        connection_score: dict[str, Any],
        fund_flow: dict[str, Any],
        financial_quality: dict[str, Any],
        chain_environment: dict[str, Any]
    ) -> str:
        return (
            f"企业***分层综合得分 {score:.2f}，"
            f"环节关键程度 {chain_score['score']}，上下游连接广度 {connection_score['score']}，"
            f"资金活跃 {fund_flow.get('score', 50.0)}，财务质量 {financial_quality.get('score', 50.0)}，"
            f"链条环境 {chain_environment.get('score', 50.0)}。"
        )

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 80:
            return "核心层"
        if score >= 65:
            return "骨干层"
        if score >= 45:
            return "基础层"
        return "边缘层"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return float(text)
    except ValueError:
        return None


def _amount_bucket_score(bucket: str) -> float:
    bucket = bucket.strip()
    if not bucket or bucket == "0元":
        return 0
    if "1,10" in bucket:
        return 4
    if "10,100" in bucket:
        return 8
    if "100,500" in bucket:
        return 12
    if "500,1000" in bucket:
        return 15
    if "1000" in bucket:
        return 18
    return 5


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fmt_counter(items: list[dict[str, Any]]) -> str:
    if not items:
        return "无"
    return "；".join(f"{item['value']}({item['count']})" for item in items)


def _build_business_assessment(
    score: float,
    position_score: float,
    fund_flow: dict[str, Any],
    financial_quality: dict[str, Any],
    chain_environment: dict[str, Any]
) -> dict[str, Any]:
    fund_score = float(fund_flow.get("score", 50.0))
    financial_score = float(financial_quality.get("score", 50.0))
    environment_score = float(chain_environment.get("score", 50.0))
    concentration = float(fund_flow.get("counterparty_concentration", 0) or 0)
    cashflow_score = float(
        financial_quality.get("sub_scores", {})
        .get("cashflow", {})
        .get("score", 50.0)
    )

    if score >= 80:
        priority_label = "高优先级"
        recommended_action = "重点维护，推进综合金融方案"
    elif score >= 65:
        priority_label = "中高优先级"
        recommended_action = "积极拓展，先从结算和供应链金融切入"
    elif score >= 45:
        priority_label = "中优先级"
        recommended_action = "审慎跟进，先核验交易和财务质量"
    else:
        priority_label = "低优先级"
        recommended_action = "观察等待，暂不作为重点授信客户"

    opportunity_level = "高" if position_score >= 75 and fund_score >= 60 else "中" if position_score >= 55 or fund_score >= 45 else "低"
    risk_points = []
    if financial_score < 55:
        risk_points.append("财务质量偏弱")
    if cashflow_score < 50:
        risk_points.append("现金流质量需重点核验")
    if concentration >= 0.45:
        risk_points.append("交易对手集中度偏高")
    if environment_score < 55:
        risk_points.append("链条环境偏弱或缺少有效外部景气支撑")

    if len(risk_points) >= 3:
        risk_level = "高"
    elif risk_points:
        risk_level = "中"
    else:
        risk_level = "低"

    recommendation_evidence = [
        {
            "recommendation": "纳入客户经理跟进名单",
            "evidence": f"综合分 {score:.2f}，分层 {EnterprisePositionAgent._classify(score)}，链上地位 {position_score:.2f}。",
            "action": recommended_action,
        },
        {
            "recommendation": "优先核验结算、票据和供应链金融机会",
            "evidence": (
                f"交易对手 {fund_flow.get('counterparty_count', 0)} 个，交易经营活跃度 "
                f"{fund_flow.get('activity_count', 0)}，大额交易活跃度 {fund_flow.get('large_activity_count', 0)}。"
            ),
            "action": "拜访时确认主结算行、票据使用、应收账款、订单和回款链路。",
        },
        {
            "recommendation": "授信前先做财务和现金流复核",
            "evidence": f"财务质量 {financial_score:.2f}，现金流质量 {cashflow_score:.2f}；{financial_quality.get('reason', '')}",
            "action": "补充最新财报、近半年流水、征信、纳税和主要合同，避免直接给出授信结论。",
        },
        {
            "recommendation": "结合产业链环境决定资源投入强度",
            "evidence": f"链条环境 {environment_score:.2f}；{chain_environment.get('reason', '')}",
            "action": "若产业链环境走弱，优先做低风险结算和存量维护；若改善，再推进融资方案。",
        },
    ]
    return {
        "priority_label": priority_label,
        "opportunity_level": opportunity_level,
        "risk_level": risk_level,
        "risk_points": risk_points or ["未识别出高强度规则风险，但仍需做授信前尽调核验。"],
        "recommended_action": recommended_action,
        "recommendation_evidence": recommendation_evidence,
    }


def _financial_rows(sub_scores: dict[str, Any]) -> list[str]:
    if not sub_scores:
        return ["| 缺失 | 50.0 | 未读取到财报子项，按中性处理 |"]
    rows = []
    for item in sub_scores.values():
        if not isinstance(item, dict):
            continue
        rows.append(f"| {item.get('label', '缺失')} | {item.get('score', '')} | {item.get('reason', '')} |")
    return rows or ["| 缺失 | 50.0 | 未读取到财报子项，按中性处理 |"]


def _chain_environment_rows(summary: list[dict[str, Any]]) -> list[str]:
    if not summary:
        return ["| 缺失 | 50.0 |  |"]
    rows = []
    for item in summary:
        rows.append(f"| {item.get('label', '缺失')} | {item.get('score', '')} | {_fmt_weight(item.get('weight', ''))} |")
    return rows


def _recommendation_rows(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["| 缺失 | 缺少建议证据映射 | 补充数据后再判断 |"]
    return [
        f"| {item.get('recommendation', '')} | {item.get('evidence', '')} | {item.get('action', '')} |"
        for item in items
    ]


def _fmt_weight(value: Any) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return ""
    return f"{numeric:.0%}" if numeric <= 1 else str(value)
