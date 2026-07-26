from __future__ import annotations

import math
from statistics import mean
from typing import Any

from tools.llm_client import LLMClient


class IndustryTrendAgent:
    indicator_weights = {
        "transmission_efficiency": 0.30,
        "policy_support": 0.12,
        "industry_abundance": 0.13,
        "chain_break_risk": 0.15,
        "value_distribution": 0.15,
        "supply_demand_match": 0.15
    }
    indicator_labels = {
        "transmission_efficiency": "链路传导",
        "policy_support": "政策环境",
        "industry_abundance": "链条丰度",
        "chain_break_risk": "断链风险",
        "value_distribution": "价值分配",
        "supply_demand_match": "供需匹配"
    }
    trend_factor_weights = {
        "short_momentum": 0.25,
        "medium_momentum": 0.35,
        "ma_structure": 0.25,
        "volume_confirmation": 0.15
    }
    def score(self, crawl_bundle: dict[str, Any]) -> dict[str, Any]:
        etfs = crawl_bundle.get("etfs", [])
        histories = crawl_bundle.get("histories", {})
        quotes = crawl_bundle.get("quotes", [])
        quotes_by_code = {row.get("code"): row for row in quotes}

        etf_trend_scores = []
        for etf in etfs:
            code = etf["code"]
            history = histories.get(code, [])
            if len(history) < 25:
                raise ValueError(f"ETF {code} 历史行情少于 25 个交易日，无法稳定计算ETF趋势信号")
            etf_trend_scores.append(
                self._score_single_etf_trend(etf, quotes_by_code.get(code, {}), history)
            )

        trend_score = self._weighted_trend_score(etf_trend_scores)
        fund_flow = crawl_bundle.get("fund_flow") or {
            "metric": "资金活跃度",
            "score": 50.0,
            "reason": "未接入结算链资金流数据，链上资金传导按中性处理。"
        }
        transmission = self._score_transmission(histories, etfs, trend_score, etf_trend_scores, fund_flow)
        policy_support = crawl_bundle.get("policy_support") or {
            "label": self.indicator_labels["policy_support"],
            "score": 50.0,
            "reason": "未接入政策文本，政策环境按中性处理。",
            "evidence_docs": [],
            "signals": {}
        }
        industry_abundance = crawl_bundle.get("industry_abundance") or {
            "metric": self.indicator_labels["industry_abundance"],
            "score": 50.0,
            "reason": "未接入指标体系结果表，链条丰度按中性处理。"
        }
        chain_break_risk = crawl_bundle.get("chain_break_risk") or {
            "metric": self.indicator_labels["chain_break_risk"],
            "risk_score": 50.0,
            "safety_score": 50.0,
            "reason": "未接入断链风险数据，按中性风险处理。"
        }
        value_distribution = crawl_bundle.get("value_distribution") or {
            "metric": self.indicator_labels["value_distribution"],
            "score": 50.0,
            "reason": "未接入价值分配数据，按中性处理。"
        }
        supply_demand_match = crawl_bundle.get("supply_demand_match") or {
            "metric": self.indicator_labels["supply_demand_match"],
            "score": 50.0,
            "reason": "未接入供需匹配数据，按中性处理。"
        }
        overall_score = (
            transmission["score"] * self.indicator_weights["transmission_efficiency"]
            + policy_support["score"] * self.indicator_weights["policy_support"]
            + industry_abundance["score"] * self.indicator_weights["industry_abundance"]
            + chain_break_risk["safety_score"] * self.indicator_weights["chain_break_risk"]
            + value_distribution["score"] * self.indicator_weights["value_distribution"]
            + supply_demand_match["score"] * self.indicator_weights["supply_demand_match"]
        )

        components = {
            "transmission_efficiency": {
                "label": self.indicator_labels["transmission_efficiency"],
                "weight": self.indicator_weights["transmission_efficiency"],
                "score": round(transmission["score"], 2),
                "reason": transmission["reason"],
                "structural_score": transmission["structural_score"],
                "market_trend_score": transmission["market_trend_score"],
                "fund_flow_score": transmission["fund_flow_score"],
                "etf_scores": etf_trend_scores,
                "fund_flow": transmission["fund_flow"],
                "edges": transmission["edges"],
                "direction_score": transmission["direction_score"],
                "return_dates": transmission["return_dates"]
            },
            "policy_support": {
                "label": self.indicator_labels["policy_support"],
                "weight": self.indicator_weights["policy_support"],
                "score": round(float(policy_support.get("score", 50.0)), 2),
                "reason": policy_support.get("reason", ""),
                "document_count": policy_support.get("document_count", 0),
                "signals": policy_support.get("signals", {}),
                "evidence_docs": policy_support.get("evidence_docs", []),
                "policy_dir": policy_support.get("policy_dir", "")
            },
            "industry_abundance": {
                "label": self.indicator_labels["industry_abundance"],
                "weight": self.indicator_weights["industry_abundance"],
                "score": round(float(industry_abundance.get("score", 50.0)), 2),
                "reason": industry_abundance.get("reason", ""),
                "source_file": industry_abundance.get("source_file", ""),
                "source_row": industry_abundance.get("source_row", {}),
                "sub_scores": industry_abundance.get("sub_scores", {}),
                "data_limitations": industry_abundance.get("data_limitations", [])
            },
            "chain_break_risk": {
                "label": self.indicator_labels["chain_break_risk"],
                "weight": self.indicator_weights["chain_break_risk"],
                "score": round(float(chain_break_risk.get("risk_score", 50.0)), 2),
                "contribution_score": round(float(chain_break_risk.get("safety_score", 50.0)), 2),
                "reason": chain_break_risk.get("reason", ""),
                "components": chain_break_risk.get("components", {}),
                "source_files": chain_break_risk.get("source_files", {}),
                "scoring_note": chain_break_risk.get("scoring_note", "")
            },
            "value_distribution": {
                "label": self.indicator_labels["value_distribution"],
                "weight": self.indicator_weights["value_distribution"],
                "score": round(float(value_distribution.get("score", 50.0)), 2),
                "reason": value_distribution.get("reason", ""),
                "by_layer": value_distribution.get("by_layer", {}),
                "top_profit_companies": value_distribution.get("top_profit_companies", []),
                "sub_scores": value_distribution.get("sub_scores", {}),
                "source_files": value_distribution.get("source_files", {}),
                "data_limitations": value_distribution.get("data_limitations", [])
            },
            "supply_demand_match": {
                "label": self.indicator_labels["supply_demand_match"],
                "weight": self.indicator_weights["supply_demand_match"],
                "score": round(float(supply_demand_match.get("score", 50.0)), 2),
                "reason": supply_demand_match.get("reason", ""),
                "sub_scores": supply_demand_match.get("sub_scores", {}),
                "source_files": supply_demand_match.get("source_files", {}),
                "data_limitations": supply_demand_match.get("data_limitations", [])
            }
        }
        business_assessment = _build_chain_business_assessment(
            chain_name=crawl_bundle["chain_name"],
            overall_score=overall_score,
            level=self._level(overall_score),
            components=components
        )

        result = {
            "chain_name": crawl_bundle["chain_name"],
            "question": crawl_bundle["question"],
            "score": round(overall_score, 2),
            "level": self._level(overall_score),
            "business_assessment": business_assessment,
            "components": components,
            "summary": self._summary(overall_score, components),
            "etfs": etfs,
            "quotes": quotes,
            "latest_trade_dates": self._latest_trade_dates(quotes),
            "indicator_rationale": self._indicator_rationale(etfs),
            "data_files": crawl_bundle.get("saved_files", {}),
            "data_source": crawl_bundle.get("data_source"),
            "fetch_time": crawl_bundle.get("fetch_time")
        }
        return result

    def enrich_with_llm(self, result: dict[str, Any], llm_client: LLMClient | None) -> dict[str, Any]:
        if llm_client is None:
            result["llm_interpretation"] = {
                "available": False,
                "content": "未生成智能经营建议，报告将使用规则摘要。"
            }
            return result

        prompt_payload = {
            "chain_name": result["chain_name"],
            "score": result["score"],
            "level": result["level"],
            "business_assessment": result.get("business_assessment", {}),
            "summary": result["summary"],
            "components": {
                key: {
                    "label": value["label"],
                    "score": value["score"],
                    "reason": value["reason"]
                }
                for key, value in result["components"].items()
            },
            "transmission_efficiency": {
                "score": result["components"]["transmission_efficiency"]["score"],
                "reason": result["components"]["transmission_efficiency"]["reason"],
                "structural_score": result["components"]["transmission_efficiency"]["structural_score"],
                "market_trend_score": result["components"]["transmission_efficiency"]["market_trend_score"],
                "fund_flow_score": result["components"]["transmission_efficiency"]["fund_flow_score"],
                "edges": result["components"]["transmission_efficiency"]["edges"],
                "etf_scores": [
                    {
                        "code": row["code"],
                        "layer": row["layer"],
                        "score": row["score"],
                        "return_5d": row["metrics"]["return_5d"],
                        "return_20d": row["metrics"]["return_20d"]
                    }
                    for row in result["components"]["transmission_efficiency"]["etf_scores"]
                ],
                "fund_flow": {
                    "score": result["components"]["transmission_efficiency"]["fund_flow_score"],
                    "overall": result["components"]["transmission_efficiency"]["fund_flow"].get("overall", {}),
                    "by_layer": result["components"]["transmission_efficiency"]["fund_flow"].get("by_layer", {})
                }
            },
            "policy_support": {
                "score": result["components"]["policy_support"]["score"],
                "reason": result["components"]["policy_support"]["reason"],
                "signals": result["components"]["policy_support"]["signals"],
                "top_policy_docs": result["components"]["policy_support"]["evidence_docs"][:5]
            },
            "industry_abundance": {
                "score": result["components"]["industry_abundance"]["score"],
                "reason": result["components"]["industry_abundance"]["reason"],
                "source_row": result["components"]["industry_abundance"]["source_row"],
                "sub_scores": result["components"]["industry_abundance"]["sub_scores"],
                "data_limitations": result["components"]["industry_abundance"]["data_limitations"]
            },
            "chain_break_risk": {
                "risk_score": result["components"]["chain_break_risk"]["score"],
                "safety_score": result["components"]["chain_break_risk"]["contribution_score"],
                "reason": result["components"]["chain_break_risk"]["reason"],
                "components": result["components"]["chain_break_risk"]["components"]
            },
            "value_distribution": {
                "score": result["components"]["value_distribution"]["score"],
                "reason": result["components"]["value_distribution"]["reason"],
                "by_layer": result["components"]["value_distribution"]["by_layer"],
                "sub_scores": result["components"]["value_distribution"]["sub_scores"]
            },
            "supply_demand_match": {
                "score": result["components"]["supply_demand_match"]["score"],
                "reason": result["components"]["supply_demand_match"]["reason"],
                "sub_scores": result["components"]["supply_demand_match"]["sub_scores"]
            }
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是银行对公业务产品经理，服务对象是客户经理和经营团队。"
                    "你的任务不是写投资研报，而是把产业链评分转化为对公业务可落地判断和客户经理行动方案："
                    "客户经理应该关注什么客群、用什么产品切入、如何设计拜访和名单经营动作、可能有什么盈利机会、需要规避什么风险、下一步怎么验证。"
                    "只能基于给出的 ETF 行情和规则评分，不要编造政策、订单、产能、公司财务、个股结论或确定性投资建议。"
                    "输出中文，必须务实、克制、可执行。严格控制在750字以内，不要写长篇研报。"
                )
            },
            {
                "role": "user",
                "content": (
                    "请基于以下评分结果生成银行对公产品经理视角的产业链评估报告。"
                    "输出结构必须包含三段，每段 2-4 句；不要输出报告标题，不要使用 Markdown 一级标题：\n"
                    "1. 评估结论：引用综合等级、经营优先级、机会等级和风险等级，判断该产业链应重点布局、审慎拓展还是观察跟踪。\n"
                    "2. 企业分布：说明上游/中游/下游企业和交易活跃分布，指出客户经理应该优先看哪类环节和企业。\n"
                    "3. 指标证据：简要使用六个指标支撑结论，不要展开公式，不要写成技术说明。\n"
                    "不要在本段输出具体产品清单、详细行动步骤或风险核验段落，产品措施和风险核验由后续结构化模块承接。\n"
                    f"评分数据如下：{prompt_payload}"
                )
            }
        ]
        try:
            result["llm_interpretation"] = {
                "available": True,
                "model": llm_client.model,
                "role": "bank_corporate_product_manager",
                "content": llm_client.chat(messages, max_tokens=950)
            }
        except Exception as exc:
            result["llm_interpretation"] = {
                "available": False,
                "content": f"智能经营建议生成失败：{exc}"
            }
        return result

    def to_markdown(self, result: dict[str, Any]) -> str:
        components = result["components"]
        business = result.get("business_assessment", {})
        lines = [
            f"# {result['chain_name']}评估报告",
            "",
            "## 评估结论",
            "",
            f"- 综合分：{result['score']}",
            f"- 综合等级：{result['level']}",
            f"- 经营优先级：{business.get('priority_label', '缺失')}",
            f"- 机会等级：{business.get('opportunity_level', '缺失')}",
            f"- 风险等级：{business.get('risk_level', '缺失')}",
            f"- 数据来源：{result.get('data_source')}",
            f"- 最新交易日：{', '.join(result.get('latest_trade_dates', []))}",
            f"- 一句话总结：{result['summary']}",
            f"- 推荐措施：{business.get('recommended_action', '缺失')}",
            f"- PDF报告：`{result.get('report_files', {}).get('evaluation_pdf', result.get('report_files', {}).get('evaluation_pdf_error', '未生成'))}`",
            "",
            "## 指标依据",
            "",
            f"- 链路传导：{components['transmission_efficiency']['score']}，反映上中下游联动、ETF市场信号和链上资金传导。",
            f"- 政策环境：{components['policy_support']['score']}，反映政策文本中的支持强度和监管约束。",
            f"- 链条丰度：{components['industry_abundance']['score']}，反映链上企业数量、增长代理和区域集聚。",
            f"- 断链风险：{components['chain_break_risk']['score']}，风险分越高代表断链风险越高。",
            f"- 价值分配：{components['value_distribution']['score']}，反映上中下游利润是否健康沉淀。",
            f"- 供需匹配：{components['supply_demand_match']['score']}，反映需求、供给、PMI和价格传导是否协调。",
            "",
            "## 上中下游企业统计",
            "",
            f"- 链上企业数：{business.get('enterprise_distribution', {}).get('chain_enterprise_count', '缺失')}",
            f"- 交易对手数：{business.get('enterprise_distribution', {}).get('counterparty_count', '缺失')}",
            f"- 交易活跃度：{business.get('enterprise_distribution', {}).get('activity_count', '缺失')}",
            f"- 大额交易活跃度：{business.get('enterprise_distribution', {}).get('large_activity_count', '缺失')}",
            f"- 区域集聚：{business.get('enterprise_distribution', {}).get('regional_concentration', '缺失')}",
            "",
            "| 层级 | 企业数 | 交易活跃度 | 大额交易活跃度 | 交易对手数 | 最高对手集中度 |",
            "|---|---:|---:|---:|---:|---:|",
            *_chain_distribution_rows(business.get("enterprise_distribution", {}).get("by_layer", {})),
            "",
            "## 重点企业线索",
            "",
            f"- 筛选说明：{business.get('key_company_clues', {}).get('screening_basis', '缺失')}",
            "",
            "| 企业 | 股票代码 | 层级 | 节点 | 净利率% | ROE% |",
            "|---|---|---|---|---:|---:|",
            *_key_company_rows(business.get("key_company_clues", {})),
            "",
            "## 关键分析摘要",
            "",
            *_chain_analysis_summary_lines(components, business),
            "",
            "## 产品机会与采取措施",
            "",
            *_chain_recommendation_blocks(business.get("recommendation_evidence", [])),
            "",
            "## 风险核验",
            "",
            f"- 风险等级：{business.get('risk_level', '缺失')}",
            f"- 主要风险点：{'；'.join(business.get('risk_points', []))}",
            "- 业务落地前必须核验订单、合同、发票、物流、库存、价格、回款流水和核心交易对手依赖。",
            "",
            "## 固定 ETF 映射",
            "",
            "| 层级 | 代码 | 名称 | 跟踪对象 | 趋势权重 | 选择理由 |",
            "|---|---|---|---|---:|---|"
        ]
        for etf in result["etfs"]:
            lines.append(
                f"| {etf['layer']} | {etf['code']} | {etf['name']} | "
                f"{etf['tracked_index']} | {etf['trend_weight']:.0%} | {etf['reason']} |"
            )

        lines.extend([
            "",
            "## 指标得分",
            "",
            "| 指标 | 权重 | 得分 | 说明 |",
            "|---|---:|---:|---|"
        ])
        for key in [
            "transmission_efficiency",
            "policy_support",
            "industry_abundance",
            "chain_break_risk",
            "value_distribution",
            "supply_demand_match"
        ]:
            item = components[key]
            score_text = item["score"]
            lines.append(f"| {item['label']} | {item['weight']:.0%} | {score_text} | {item['reason']} |")

        transmission = components["transmission_efficiency"]
        lines.extend([
            "",
            "## 链路传导明细",
            "",
            f"- 结构传导得分：{transmission.get('structural_score')}",
            f"- ETF 趋势吸收得分：{transmission.get('market_trend_score')}",
            f"- 链上资金传导吸收得分：{transmission.get('fund_flow_score')}",
            "",
            "### ETF 趋势信号（并入链路传导）",
            "",
            "| 层级 | 代码 | 趋势得分 | 5日收益 | 20日收益 | MA20 | 20日量比 |",
            "|---|---|---:|---:|---:|---:|---:|"
        ])
        for row in transmission["etf_scores"]:
            metrics = row["metrics"]
            lines.append(
                f"| {row['layer']} | {row['code']} | {row['score']} | "
                f"{_fmt_pct(metrics.get('return_5d'))} | {_fmt_pct(metrics.get('return_20d'))} | "
                f"{_fmt_num(metrics.get('ma20'))} | {_fmt_ratio(metrics.get('volume_ratio_20d'))} |"
            )

        lines.extend([
            "",
            "### 上中下游价格传导链路",
            "",
            "| 链路 | 最优滞后 | 相关系数 | 链路得分 | 近20日同向率 |",
            "|---|---:|---:|---:|---:|"
        ])
        for edge in transmission["edges"]:
            lines.append(
                f"| {edge['name']} | {edge['best_lag_days']} 日 | "
                f"{_fmt_num(edge['correlation'])} | {edge['score']} | {_fmt_pct(edge['direction_agreement'])} |"
            )

        lines.extend([
            "",
            "## 政策环境明细",
            "",
            f"- 政策文本目录：`{components['policy_support'].get('policy_dir', '')}`",
            f"- 文本数量：{components['policy_support'].get('document_count', 0)}",
            "",
            "| 标题 | 来源 | 日期 | 得分 | 主要依据 |",
            "|---|---|---|---:|---|"
        ])
        for doc in components["policy_support"].get("evidence_docs", [])[:8]:
            lines.append(
                f"| {doc.get('title', '')} | {doc.get('source', '')} | {doc.get('date', '')} | "
                f"{doc.get('score', '')} | {doc.get('snippet', '')} |"
            )

        fund = transmission.get("fund_flow", {})
        overall = fund.get("overall", {})
        lines.extend([
            "",
            "### 链上资金传导信号（并入链路传导）",
            "",
            f"- 总体交易经营活跃度：{overall.get('activity_count', 0)}",
            f"- 总体大额交易活跃度：{overall.get('large_activity_count', 0)}",
            f"- 链上交易对手数：{overall.get('counterparty_count', 0)}",
            f"- 最高交易对手集中度：{_fmt_pct((overall.get('top_counterparty_concentration') or 0) * 100)}",
            "",
            "| 层级 | 企业数 | 交易经营活跃度 | 大额交易活跃度 | 交易对手数 | 最高对手集中度 |",
            "|---|---:|---:|---:|---:|---:|"
        ])
        for layer, row in fund.get("by_layer", {}).items():
            lines.append(
                f"| {layer} | {row.get('enterprise_count', 0)} | {row.get('activity_count', 0)} | "
                f"{row.get('large_activity_count', 0)} | {row.get('counterparty_count', 0)} | "
                f"{_fmt_pct((row.get('top_counterparty_concentration') or 0) * 100)} |"
            )

        abundance = components["industry_abundance"]
        lines.extend([
            "",
            "## 链条丰度明细",
            "",
            f"- 数据来源文件：`{abundance.get('source_file', '')}`",
            f"- 评分说明：{abundance.get('reason', '')}",
            "",
            "| 子项 | 得分 | 原始字段 | 原始值 | 方法说明 |",
            "|---|---:|---|---|---|"
        ])
        for item in abundance.get("sub_scores", {}).values():
            lines.append(
                f"| {item.get('label', '')} | {item.get('score', '')} | "
                f"{item.get('source_field', '')} | {item.get('source_value', '')} | {item.get('method', '')} |"
            )
        lines.extend(["", "### 链条丰度原始字段", ""])
        for key, value in abundance.get("source_row", {}).items():
            lines.append(f"- {key}: `{value}`")
        if abundance.get("data_limitations"):
            lines.extend(["", "### 链条丰度数据限制", ""])
            for item in abundance["data_limitations"]:
                lines.append(f"- {item}")

        break_risk = components["chain_break_risk"]
        risk_components = break_risk.get("components", {})
        lines.extend([
            "",
            "## 断链风险明细",
            "",
            f"- 断链风险分：{break_risk.get('score', 0)}",
            f"- 说明：{break_risk.get('scoring_note', '')}",
            "",
            "| 风险维度 | 风险分 | 判断说明 |",
            "|---|---:|---|"
        ])
        for item in risk_components.values():
            lines.append(f"| {item.get('label', '')} | {item.get('score', '')} | {item.get('reason', '')} |")

        choke = risk_components.get("geopolitical_chokepoint_risk", {})
        if choke.get("top_risk_nodes"):
            lines.extend([
                "",
                "### 卡脖子高风险节点",
                "",
                f"- 来源文件：`{choke.get('source_file', '')}`",
                "",
                "| 节点 | 层级 | 总分(0-16) | 等级 | 等级说明 | 判断依据 |",
                "|---|---|---:|---|---|---|"
            ])
            for node in choke.get("top_risk_nodes", [])[:10]:
                lines.append(
                    f"| {node.get('node_name', '')} | {node.get('layer', '')} | "
                    f"{node.get('score_0_16', '')} | {node.get('level', '')} | "
                    f"{node.get('description', '')} | {node.get('evidence', '')} |"
                )

        value_dist = components["value_distribution"]
        lines.extend([
            "",
            "## 价值分配明细",
            "",
            f"- 数据来源文件：`{value_dist.get('source_files', {}).get('layer_margin', '')}` / `{value_dist.get('source_files', {}).get('company_margin', '')}`",
            f"- 评分说明：{value_dist.get('reason', '')}",
            "",
            "| 子项 | 得分 | 方法说明 |",
            "|---|---:|---|"
        ])
        for item in value_dist.get("sub_scores", {}).values():
            lines.append(f"| {item.get('label', '')} | {item.get('score', '')} | {item.get('method', '')} |")
        lines.extend([
            "",
            "| 层级 | 样本数 | 平均毛利率 | 平均净利率 | 平均ROE | 净利率为正比例 |",
            "|---|---:|---:|---:|---:|---:|"
        ])
        for layer, row in value_dist.get("by_layer", {}).items():
            lines.append(
                f"| {layer} | {row.get('sample_count', 0)} | {_fmt_num(row.get('avg_gross_margin'))} | "
                f"{_fmt_num(row.get('avg_net_margin'))} | {_fmt_num(row.get('avg_roe'))} | "
                f"{_fmt_pct((row.get('positive_net_ratio') or 0) * 100)} |"
            )
        if value_dist.get("data_limitations"):
            lines.extend(["", "### 价值分配数据限制", ""])
            for item in value_dist["data_limitations"]:
                lines.append(f"- {item}")

        supply_demand = components["supply_demand_match"]
        lines.extend([
            "",
            "## 供需匹配明细",
            "",
            f"- 评分说明：{supply_demand.get('reason', '')}",
            "",
            "| 子项 | 得分 | 判断说明 |",
            "|---|---:|---|"
        ])
        for item in supply_demand.get("sub_scores", {}).values():
            lines.append(f"| {item.get('label', '')} | {item.get('score', '')} | {item.get('reason', '')} |")
        lines.extend(["", "### 供需匹配数据来源", ""])
        for name, path in supply_demand.get("source_files", {}).items():
            lines.append(f"- {name}: `{path}`")
        if supply_demand.get("data_limitations"):
            lines.extend(["", "### 供需匹配数据限制", ""])
            for item in supply_demand["data_limitations"]:
                lines.append(f"- {item}")

        lines.extend([
            "",
            "## 爬取文件",
            ""
        ])
        for name, path in result["data_files"].items():
            lines.append(f"- {name}: `{path}`")

        rationale = result["indicator_rationale"]
        lines.extend([
            "",
            "## 指标选择与计算理由",
            "",
            "### 为什么选这四个 ETF",
            ""
        ])
        for item in rationale["etf_selection"]:
            lines.append(f"- {item}")
        lines.extend(["", "### 为什么选这六个指标", ""])
        for item in rationale["indicator_selection"]:
            lines.append(f"- {item}")
        lines.extend(["", "### 为什么这样分配权重", ""])
        for item in rationale["weighting"]:
            lines.append(f"- {item}")
        lines.extend(["", "### 为什么这样计算", ""])
        for item in rationale["calculation"]:
            lines.append(f"- {item}")

        lines.extend([
            "",
            "## 说明",
            "",
            "- 当前版本只使用四个固定 ETF 的新浪行情数据，评价的是市场价格视角下的产业链趋势和环节联动。",
            "- ETF 行情不能单独代表真实供需、利润、产能或政策景气，后续可叠加销量、价格、库存、财报、政策原文和产业数据。",
            "- 非交易日或盘后数据通常对应最近交易日或最后更新时间。",
            "- 当前版本不构成投资建议。"
        ])
        return "\n".join(lines)

    def _score_single_etf_trend(
        self,
        etf: dict[str, Any],
        quote: dict[str, Any],
        history: list[dict[str, Any]]
    ) -> dict[str, Any]:
        rows = sorted(history, key=lambda row: row.get("date", ""))
        latest_row = rows[-1]
        latest_close = _num(quote.get("latest")) or _num(latest_row.get("close"))
        latest_volume = _num(latest_row.get("volume")) or _num(quote.get("volume"))
        if latest_close is None:
            raise ValueError(f"ETF {etf['code']} 最新价格缺失，无法计算产业趋势")

        closes = [_num(row.get("close")) for row in rows]
        closes = [value for value in closes if value is not None]
        volumes = [_num(row.get("volume")) for row in rows]
        volumes = [value for value in volumes if value is not None]

        return_5d = _return_pct(latest_close, closes[-6] if len(closes) >= 6 else None)
        return_20d = _return_pct(latest_close, closes[-21] if len(closes) >= 21 else None)
        ma5 = _ma(closes, 5)
        ma20 = _ma(closes, 20)
        ma60 = _ma(closes, 60)
        avg_volume_20 = mean(volumes[-21:-1]) if len(volumes) >= 21 else mean(volumes[:-1]) if len(volumes) > 1 else None
        volume_ratio = latest_volume / avg_volume_20 if latest_volume and avg_volume_20 else None

        sub_scores = {
            "short_momentum": {
                "label": "短期动量",
                "score": _clip(50 + (return_5d or 0) * 4, 0, 100),
                "reason": f"近 5 个交易日收益率 {_fmt_pct(return_5d)}"
            },
            "medium_momentum": {
                "label": "中期趋势",
                "score": _clip(50 + (return_20d or 0) * 2.5, 0, 100),
                "reason": f"近 20 个交易日收益率 {_fmt_pct(return_20d)}"
            },
            "ma_structure": {
                "label": "均线结构",
                "score": self._score_ma_structure(latest_close, ma5, ma20, ma60),
                "reason": self._ma_reason(latest_close, ma5, ma20, ma60)
            },
            "volume_confirmation": {
                "label": "成交量确认",
                "score": self._score_volume_confirmation(volume_ratio, return_5d),
                "reason": f"最新成交量 / 过去 20 日均量 = {_fmt_ratio(volume_ratio)}"
            }
        }
        score = sum(
            sub_scores[key]["score"] * weight
            for key, weight in self.trend_factor_weights.items()
        )
        return {
            "code": etf["code"],
            "symbol": etf["symbol"],
            "name": etf["name"],
            "layer": etf["layer"],
            "trend_weight": etf["trend_weight"],
            "score": round(score, 2),
            "latest_trade": {
                "date": quote.get("date") or latest_row.get("date"),
                "time": quote.get("time"),
                "latest": latest_close
            },
            "metrics": {
                "return_5d": _round(return_5d),
                "return_20d": _round(return_20d),
                "ma5": _round(ma5),
                "ma20": _round(ma20),
                "ma60": _round(ma60),
                "volume_ratio_20d": _round(volume_ratio)
            },
            "sub_scores": {
                key: {
                    "label": value["label"],
                    "score": round(value["score"], 2),
                    "weight": self.trend_factor_weights[key],
                    "reason": value["reason"]
                }
                for key, value in sub_scores.items()
            }
        }

    def _weighted_trend_score(self, etf_scores: list[dict[str, Any]]) -> float:
        total_weight = sum(_num(row.get("trend_weight")) or 0 for row in etf_scores)
        if total_weight <= 0:
            return mean([row["score"] for row in etf_scores])
        return sum(row["score"] * row["trend_weight"] for row in etf_scores) / total_weight

    def _score_transmission(
        self,
        histories: dict[str, list[dict[str, Any]]],
        etfs: list[dict[str, Any]],
        trend_score: float,
        etf_trend_scores: list[dict[str, Any]],
        fund_flow: dict[str, Any]
    ) -> dict[str, Any]:
        returns_by_code, return_dates = _aligned_daily_returns(histories)
        if len(return_dates) < 25:
            raise ValueError("四个 ETF 的共同交易日不足，无法计算链路传导")

        transmission_edges = self._transmission_edges(etfs)
        edges = []
        edge_scores = []
        direction_scores = []
        for source, target, name in transmission_edges:
            source_returns = returns_by_code[source]
            target_returns = returns_by_code[target]
            best = _best_lag_correlation(source_returns, target_returns)
            direction_score = _direction_agreement(source_returns, target_returns, window=20)
            edge = {
                "source": source,
                "target": target,
                "name": name,
                "best_lag_days": best["lag_days"],
                "correlation": _round(best["correlation"]),
                "correlation_score": _round(best["correlation_score"]),
                "direction_agreement": _round(direction_score),
                "score": round(best["score"] or 50.0, 2)
            }
            edges.append(edge)
            edge_scores.append(best["score"] or 50.0)
            direction_scores.append(direction_score)

        avg_edge_score = mean(edge_scores)
        avg_direction_score = mean(direction_scores)
        structural_score = avg_edge_score * 0.70 + avg_direction_score * 0.30
        fund_flow_score = float(fund_flow.get("score") or 50.0)
        score = structural_score * 0.55 + trend_score * 0.25 + fund_flow_score * 0.20
        strongest = max(etf_trend_scores, key=lambda row: row["score"])
        weakest = min(etf_trend_scores, key=lambda row: row["score"])
        return {
            "score": round(score, 2),
            "structural_score": round(structural_score, 2),
            "market_trend_score": round(trend_score, 2),
            "fund_flow_score": round(fund_flow_score, 2),
            "fund_flow": fund_flow,
            "edges": edges,
            "direction_score": round(avg_direction_score, 2),
            "return_dates": {
                "start": return_dates[0],
                "end": return_dates[-1],
                "count": len(return_dates)
            },
            "reason": (
                f"按{self._transmission_path_text(etfs)}计算上中下游滞后相关，结构传导得分 {structural_score:.2f}；"
                f"ETF趋势吸收得分 {trend_score:.2f}（最强{strongest['layer']}，最弱{weakest['layer']}）；"
                f"链上资金传导吸收得分 {fund_flow_score:.2f}，平均近20日同向率 {_fmt_pct(avg_direction_score)}。"
            )
        }

    @staticmethod
    def _transmission_edges(etfs: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
        by_layer = {etf.get("layer"): etf for etf in etfs}
        anchor = next((etf for etf in etfs if etf.get("layer") == "全链总锚"), etfs[0])
        non_anchor = [etf for etf in etfs if etf.get("code") != anchor.get("code")]
        ordered = non_anchor + [anchor]
        edges = []
        for source, target in zip(ordered, ordered[1:]):
            edges.append((
                source["code"],
                target["code"],
                f"{source['layer']} -> {target['layer']}"
            ))
        return edges

    @staticmethod
    def _transmission_path_text(etfs: list[dict[str, Any]]) -> str:
        anchor = next((etf for etf in etfs if etf.get("layer") == "全链总锚"), etfs[0])
        non_anchor = [etf for etf in etfs if etf.get("code") != anchor.get("code")]
        return "->".join(etf["layer"] for etf in [*non_anchor, anchor])

    @staticmethod
    def _score_ma_structure(latest_close: float, ma5: float | None, ma20: float | None, ma60: float | None) -> float:
        score = 0.0
        if ma5 is not None and latest_close >= ma5:
            score += 20
        if ma20 is not None and latest_close >= ma20:
            score += 30
        if ma5 is not None and ma20 is not None and ma5 >= ma20:
            score += 25
        if ma20 is not None and ma60 is not None and ma20 >= ma60:
            score += 25
        return score

    @staticmethod
    def _score_volume_confirmation(volume_ratio: float | None, return_5d: float | None) -> float:
        if volume_ratio is None:
            return 50.0
        base = _clip(50 + (volume_ratio - 1) * 35, 20, 100)
        if return_5d is not None and return_5d < 0 and volume_ratio > 1.2:
            base -= min((volume_ratio - 1.2) * 20, 20)
        return _clip(base, 0, 100)

    @staticmethod
    def _ma_reason(latest_close: float, ma5: float | None, ma20: float | None, ma60: float | None) -> str:
        return (
            f"最新价 {_fmt_num(latest_close)}，"
            f"MA5 {_fmt_num(ma5)}，MA20 {_fmt_num(ma20)}，MA60 {_fmt_num(ma60)}"
        )

    @staticmethod
    def _trend_summary(etf_scores: list[dict[str, Any]], score: float) -> str:
        strongest = max(etf_scores, key=lambda row: row["score"])
        weakest = min(etf_scores, key=lambda row: row["score"])
        return (
            f"四个 ETF 加权趋势得分 {score:.2f}；"
            f"最强环节为{strongest['layer']}({strongest['code']})，"
            f"最弱环节为{weakest['layer']}({weakest['code']})。"
        )

    @staticmethod
    def _summary(overall_score: float, components: dict[str, dict[str, Any]]) -> str:
        transmission = components["transmission_efficiency"]["score"]
        policy = components["policy_support"]["score"]
        abundance = components["industry_abundance"]["score"]
        break_risk = components["chain_break_risk"]["score"]
        value = components["value_distribution"]["score"]
        supply = components["supply_demand_match"]["score"]
        return (
            f"链路传导得分 {transmission}，政策环境得分 {policy}，"
            f"链条丰度得分 {abundance}，断链风险分 {break_risk}，"
            f"价值分配得分 {value}，供需匹配得分 {supply}，"
            f"综合分 {overall_score:.2f}，反映环节联动、市场趋势吸收、链上资金传导、"
            "政策环境、产业基础、链条韧性、利润分配和供需协调的综合判断。"
        )

    @staticmethod
    def _latest_trade_dates(quotes: list[dict[str, Any]]) -> list[str]:
        dates = sorted({str(row.get("date")) for row in quotes if row.get("date")})
        return dates or ["缺失"]

    @staticmethod
    def _indicator_rationale(etfs: list[dict[str, Any]]) -> dict[str, list[str]]:
        etf_selection = [
            f"{etf['code']} 作为{etf['layer']}，{etf['reason']}"
            for etf in etfs
        ]
        etf_weight_text = "、".join(
            f"{etf['layer']} {etf['trend_weight']:.0%}"
            for etf in etfs
        )
        return {
            "etf_selection": etf_selection,
            "indicator_selection": [
                "链路传导用于回答景气信号是否能在上中下游之间顺畅传递；当前版本将 ETF 趋势和链上资金活跃信息并入该指标，避免同一类市场和交易信号重复计分。",
                "政策环境用于回答政策、标准、税费优惠、基础设施、技术攻关和监管方向是否支撑产业链中长期落地。",
                "链条丰度用于回答产业链规模是否足够大、是否有增长代理信号、区域是否形成集聚，以及产业生态是否有政策和治理基础。",
                "断链风险用于回答政策监管、市场价格、地缘卡脖子等因素是否可能导致链条中断或关键环节受限；该指标是风险向指标，分数越高代表风险越高。",
                "价值分配用于回答产业链利润是否集中在少数环节、上中下游是否出现利润挤压，以及链条是否具备可持续的价值创造空间。",
                "供需匹配用于回答需求增长、产能利用率、制造业景气和价格传导是否协调；供给过剩、成本传导不畅或需求走弱都会降低景气可信度。",
                "这六个指标分别覆盖链条传导、政策环境、产业基础、链条韧性、利润分配和供需协调，适合当前实时行情、离线政策文本、银行结算数据、指标体系结果表、卡脖子评级表、利润率表和供需数据表的 MVP。"
            ],
            "weighting": [
                "综合分中链路传导占 30%、政策环境占 12%、链条丰度占 13%、断链风险占 15%、价值分配占 15%、供需匹配占 15%；链路传导仍是最高权重，因为它整合市场信号、价格联动和真实交易活动，但不会过度压制风险、利润和供需这些经营质量指标。",
                f"ETF 趋势权重为{etf_weight_text}；全链总锚代表整体方向，核心中游环节代表价值和技术壁垒，上游和下游分别作为供给约束与需求扩散补充。",
                "单只 ETF 趋势分中，中期趋势 35% 高于短期动量 25%，因为 20 日趋势比 5 日波动更稳定；均线结构 25% 用于确认趋势结构，成交量确认 15% 作为辅助验证。",
                "链路传导内部由结构传导 55%、ETF 趋势吸收 25%、链上资金传导 20% 组成；结构传导衡量上中下游价格联动，ETF 趋势补充市场方向，资金传导补充银行结算视角下的真实经营活跃。",
                "结构传导中，链路滞后相关占 70%、近20日同向率占 30%；前者衡量结构性传导关系，后者校验近期是否发生明显分化。",
                "单条链路中，相关得分占 75%、滞后速度占 25%；传导快是加分项，但必须以相关关系存在为前提。",
                "断链风险提升到 15%，因为赛题强调可靠性和底线性；该项按风险反向分参与综合计算，保持综合分方向一致。",
                "价值分配和供需匹配各占 15%，因为它们分别回答利润能否留在链上、需求能否消化供给，是银行客户经理判断授信、结算和供应链金融机会时必须补充的经营质量指标。"
            ],
            "calculation": [
                "ETF 趋势不再作为独立指标，而是并入链路传导：每只 ETF 仍按 5 日收益、20 日收益、均线结构和成交量确认计算趋势分，再按固定 ETF 权重聚合为链路传导的市场趋势吸收子项。",
                f"四个 ETF 的市场趋势吸收分按{etf_weight_text}加权；权重较高的环节用于代表整体方向和核心价值环节，权重较低的环节用于补充供给约束和需求扩散信号。",
                "每条传导链路先按 0-2 日滞后相关和滞后速度计算链路分；相关性越高、最优滞后越短，说明市场信号传导越快。",
                "链路传导再加入近 20 日同向率，防止历史相关性较高但近期环节明显分化时被误判为高传导。",
                "政策环境基于离线政策/新闻文本中的直接产业链相关词、支持性政策词、约束监管词、权威来源和近期政策数量计算；直接相关、支持性强、权威且近期的政策文本越多，得分越高，监管约束越强则扣分。",
                "产业链资金活跃度不再作为独立指标，而是并入链路传导：基于产业链表中的客户 UID 匹配结算链1、结算链2，计算交易经营活跃度、大额交易活跃度、交易对手数、交易集中度和上中下游分层活跃度，作为链上资金传导子项。",
                "链条丰度基于指标体系结果表中的链上企业总数、ETF增长代理、最高省集聚比例、近三年国家级政策数计算；当前没有 NBS 市场规模原始序列和三年市场规模序列，因此报告会明确展示所用原始字段和值。",
                "断链风险由政策与监管风险、市场与价格风险、地缘政治与卡脖子风险三部分构成；政策风险使用政策环境结果中的约束/监管信号，市场价格风险使用 ETF 近20日下行、波动率和PPI价格代理，地缘风险使用卡脖子评级表中的总分、S/A级高风险节点占比和判断依据。",
                "价值分配基于价值分配目录下的 layer_margin.csv 和 company_margin.csv，计算整体盈利能力、上中下游分配均衡度、健康环节覆盖度和利润趋势；毛利率、净利率、ROE越好且上中下游差异越合理，得分越高。",
                "供需匹配基于供需匹配目录下的 production_sales.csv、capacity_util.csv、pmi_detail.csv、price_scissors.csv，以及行业增加值代理数据；产销或工业增加值改善、产能利用率处于合理区间、PMI站上荣枯线、价格剪刀差不过度扩大，则得分更高。"
            ]
        }

    @staticmethod
    def _level(score: float) -> str:
        if score >= 85:
            return "景气强劲"
        if score >= 70:
            return "景气偏强"
        if score >= 55:
            return "景气中性偏强"
        if score >= 40:
            return "景气中性偏弱"
        return "景气偏弱"


def _aligned_daily_returns(histories: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, list[float]], list[str]]:
    close_by_code: dict[str, dict[str, float]] = {}
    for code, rows in histories.items():
        close_by_date = {}
        for row in rows:
            date = str(row.get("date", ""))
            close = _num(row.get("close"))
            if date and close is not None:
                close_by_date[date] = close
        close_by_code[code] = close_by_date

    common_dates: set[str] | None = None
    for close_by_date in close_by_code.values():
        dates = set(close_by_date.keys())
        common_dates = dates if common_dates is None else common_dates & dates
    sorted_dates = sorted(common_dates or [])
    if len(sorted_dates) < 2:
        return {}, []

    returns_by_code = {code: [] for code in close_by_code}
    return_dates = []
    for index in range(1, len(sorted_dates)):
        date = sorted_dates[index]
        prev_date = sorted_dates[index - 1]
        daily_returns = {}
        valid = True
        for code, close_by_date in close_by_code.items():
            current = close_by_date.get(date)
            previous = close_by_date.get(prev_date)
            value = _return_pct(current, previous)
            if value is None:
                valid = False
                break
            daily_returns[code] = value
        if not valid:
            continue
        return_dates.append(date)
        for code, value in daily_returns.items():
            returns_by_code[code].append(value)
    return returns_by_code, return_dates


def _best_lag_correlation(source_returns: list[float], target_returns: list[float]) -> dict[str, float | int | None]:
    best: dict[str, float | int | None] = {
        "lag_days": None,
        "correlation": None,
        "correlation_score": 50.0,
        "score": 50.0
    }
    lag_speed_score = {0: 100.0, 1: 80.0, 2: 65.0}
    for lag in [0, 1, 2]:
        count = min(len(source_returns), len(target_returns) - lag)
        if count < 10:
            continue
        source_window = source_returns[:count]
        target_window = target_returns[lag:lag + count]
        correlation = _corr(source_window, target_window)
        if correlation is None:
            continue
        corr_score = _clip(50 + correlation * 50, 0, 100)
        score = corr_score * 0.75 + lag_speed_score[lag] * 0.25
        if score > (best["score"] or 0):
            best = {
                "lag_days": lag,
                "correlation": correlation,
                "correlation_score": corr_score,
                "score": score
            }
    return best


def _direction_agreement(source_returns: list[float], target_returns: list[float], window: int) -> float:
    count = min(len(source_returns), len(target_returns), window)
    if count <= 0:
        return 50.0
    source_window = source_returns[-count:]
    target_window = target_returns[-count:]
    agreements = 0
    for source, target in zip(source_window, target_window):
        if _sign(source) == _sign(target):
            agreements += 1
    return agreements / count * 100


def _corr(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    x_mean = mean(x_values)
    y_mean = mean(y_values)
    x_diff = [value - x_mean for value in x_values]
    y_diff = [value - y_mean for value in y_values]
    denominator = math.sqrt(sum(value * value for value in x_diff) * sum(value * value for value in y_diff))
    if denominator == 0:
        return None
    return sum(x * y for x, y in zip(x_diff, y_diff)) / denominator


def _sign(value: float, neutral_threshold: float = 0.03) -> int:
    if value > neutral_threshold:
        return 1
    if value < -neutral_threshold:
        return -1
    return 0


def _return_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous * 100


def _ma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return mean(values[-window:])


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").replace("%", "").strip()
        if text in {"", "-", "None", "nan"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    return "缺失" if number is None else f"{number:.2f}%"


def _fmt_ratio(value: Any) -> str:
    number = _num(value)
    return "缺失" if number is None else f"{number:.2f}"


def _fmt_num(value: Any) -> str:
    number = _num(value)
    return "缺失" if number is None else f"{number:.4f}"


def _build_chain_business_assessment(
    chain_name: str,
    overall_score: float,
    level: str,
    components: dict[str, Any]
) -> dict[str, Any]:
    transmission = components["transmission_efficiency"]
    fund_flow = transmission.get("fund_flow", {})
    overall = fund_flow.get("overall", {})
    abundance = components["industry_abundance"]
    source_row = abundance.get("source_row", {})
    risk_score = float(components["chain_break_risk"].get("score", 50.0))
    value_score = float(components["value_distribution"].get("score", 50.0))
    demand_score = float(components["supply_demand_match"].get("score", 50.0))

    if overall_score >= 75:
        priority_label = "高优先级"
        recommended_action = "重点布局，围绕核心企业和高活跃环节做名单经营"
    elif overall_score >= 60:
        priority_label = "中高优先级"
        recommended_action = "积极拓展，但授信和供应链金融需先做环节筛选"
    elif overall_score >= 45:
        priority_label = "中优先级"
        recommended_action = "审慎跟进，优先做结算、存量维护和低风险产品"
    else:
        priority_label = "低优先级"
        recommended_action = "观察跟踪，暂不作为重点新增投放方向"

    opportunity_level = "高" if float(transmission.get("score", 50.0)) >= 70 and demand_score >= 55 else "中" if overall_score >= 50 else "低"
    risk_points = []
    if risk_score >= 65:
        risk_points.append("断链风险偏高")
    if value_score < 50:
        risk_points.append("价值分配承压")
    if demand_score < 50:
        risk_points.append("供需匹配偏弱")
    if float(overall.get("top_counterparty_concentration", 0) or 0) >= 0.45:
        risk_points.append("链上交易集中度偏高")
    risk_level = "高" if len(risk_points) >= 3 else "中" if risk_points else "低"

    distribution = {
        "chain_enterprise_count": fund_flow.get("chain_enterprise_count") or source_row.get("链上企业总数（含财报）", ""),
        "counterparty_count": overall.get("counterparty_count", 0),
        "activity_count": overall.get("activity_count", 0),
        "large_activity_count": overall.get("large_activity_count", 0),
        "regional_concentration": _regional_text(source_row),
        "by_layer": fund_flow.get("by_layer", {}),
        "top_enterprises": fund_flow.get("top_enterprises", [])[:10],
    }
    key_company_clues = _build_key_company_clues(components)
    recommendation_evidence = [
        {
            "recommendation": "建立产业链客户经营名单",
            "evidence": f"{chain_name} 综合分 {overall_score:.2f}，等级 {level}，经营优先级 {priority_label}。",
            "action": "按上游/中游/下游分层拉取客户 UID，优先排查交易活跃和链上连接广的企业。",
        },
        {
            "recommendation": "优先排查交易活跃环节",
            "evidence": (
                f"链上企业数 {distribution['chain_enterprise_count']}，交易对手 {distribution['counterparty_count']} 个，"
                f"交易活跃度 {distribution['activity_count']}，大额交易活跃度 {distribution['large_activity_count']}。"
            ),
            "action": "用结算流水、票据、应收账款和上下游交易清单筛出供应链金融切入客户。",
        },
        {
            "recommendation": "根据分布选择区域和环节切入",
            "evidence": f"区域集聚信息：{distribution['regional_concentration']}；分层交易分布见上中下游企业分布表。",
            "action": "对集聚区域做批量拜访，对高活跃环节做核心企业及配套企业联动营销。",
        },
        {
            "recommendation": "业务落地前保留风险核验",
            "evidence": f"断链风险 {risk_score:.2f}，价值分配 {value_score:.2f}，供需匹配 {demand_score:.2f}；风险点：{'；'.join(risk_points) if risk_points else '暂无高强度规则风险'}。",
            "action": "授信前核验订单、库存、价格、核心客户依赖、回款和政策约束，避免只看景气分投放。",
        },
    ]
    return {
        "priority_label": priority_label,
        "opportunity_level": opportunity_level,
        "risk_level": risk_level,
        "risk_points": risk_points or ["暂无高强度规则风险，但仍需核验订单、回款和交易真实性。"],
        "recommended_action": recommended_action,
        "enterprise_distribution": distribution,
        "key_company_clues": key_company_clues,
        "recommendation_evidence": recommendation_evidence,
    }


def _regional_text(source_row: dict[str, Any]) -> str:
    province = source_row.get("集聚度最高省份")
    count = source_row.get("最高省企业数")
    ratio = source_row.get("最高省集聚比例")
    if province or count or ratio:
        return f"{province or '缺失'}，企业数 {count or '缺失'}，集聚比例 {ratio or '缺失'}"
    return "缺失"


def _chain_distribution_rows(by_layer: dict[str, Any]) -> list[str]:
    if not by_layer:
        return ["| 缺失 | 0 | 0 | 0 | 0 | 0.00% |"]
    rows = []
    for layer in ["上游", "中游", "下游", "未知"]:
        row = by_layer.get(layer)
        if not row:
            continue
        rows.append(
            f"| {layer} | {row.get('enterprise_count', 0)} | {row.get('activity_count', 0)} | "
            f"{row.get('large_activity_count', 0)} | {row.get('counterparty_count', 0)} | "
            f"{_fmt_pct((row.get('top_counterparty_concentration') or 0) * 100)} |"
        )
    return rows or ["| 缺失 | 0 | 0 | 0 | 0 | 0.00% |"]


def _build_key_company_clues(components: dict[str, Any]) -> dict[str, Any]:
    companies = components.get("value_distribution", {}).get("top_profit_companies", [])[:8]
    return {
        "screening_basis": "本地数据未提供市值字段，当前使用价值分配表中的上市样本盈利能力作为重点企业线索，不等同于市值超过500亿筛选。",
        "companies": companies,
    }


def _key_company_rows(clues: dict[str, Any]) -> list[str]:
    companies = clues.get("companies", [])
    if not companies:
        return ["| 缺失 | 缺失 | 缺失 | 缺失 | 缺失 | 缺失 |"]
    rows = []
    for item in companies:
        rows.append(
            f"| {item.get('company_name', '')} | {item.get('stock_code', '')} | "
            f"{item.get('layer', '')} | {item.get('node', '')} | "
            f"{item.get('net_margin', '')} | {item.get('roe', '')} |"
        )
    return rows


def _chain_recommendation_blocks(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return [
            "### 补充核验",
            "",
            "- 数据依据：缺少建议证据映射。",
            "- 客户经理动作：补充数据后再判断。",
        ]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.extend([
            f"### {index}. {item.get('recommendation', '')}",
            "",
            f"- 数据依据：{item.get('evidence', '')}",
            f"- 客户经理动作：{item.get('action', '')}",
            "",
        ])
    return lines


def _chain_analysis_summary_lines(components: dict[str, Any], business: dict[str, Any]) -> list[str]:
    transmission = components["transmission_efficiency"]
    risk = components["chain_break_risk"]
    value = components["value_distribution"]
    demand = components["supply_demand_match"]
    policy = components["policy_support"]
    abundance = components["industry_abundance"]
    return [
        f"- 链路传导：结构传导 {transmission.get('structural_score')}，市场趋势 {transmission.get('market_trend_score')}，链上资金传导 {transmission.get('fund_flow_score')}。这说明链上交易连接较活跃，但市场端 ETF 趋势仍需谨慎观察。",
        f"- 企业基础：链条丰度 {abundance.get('score')}，政策环境 {policy.get('score')}。产业基础和政策支撑较明确，适合做客户名单筛选和区域集中拜访。",
        f"- 利润和供需：价值分配 {value.get('score')}，供需匹配 {demand.get('score')}。这两个指标偏弱时，客户经理应优先核验毛利、订单、库存和回款质量。",
        f"- 风险侧：断链风险 {risk.get('score')}，风险等级 {business.get('risk_level', '缺失')}。主要风险点：{'；'.join(business.get('risk_points', []))}。",
    ]
