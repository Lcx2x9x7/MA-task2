from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from agents.enterprise_position_agent import EnterprisePositionAgent
from agents.industry_trend_agent import IndustryTrendAgent
from agents.intent_agent import IntentAgent
from agents.policy_support_agent import PolicySupportAgent
from tools.chain_break_risk_tool import calculate_chain_break_risk
from tools.chain_environment_tool import calculate_chain_environment, select_chain_name_for_environment
from tools.enterprise_financial_tool import calculate_enterprise_financial_quality
from tools.enterprise_search_tool import search_enterprise_by_question
from tools.fund_flow_tool import calculate_chain_fund_flow, calculate_enterprise_fund_flow, infer_chain_name_from_rows
from tools.industry_abundance_tool import calculate_industry_abundance
from tools.llm_client import LLMClient
from tools.pdf_report_tool import save_chain_evaluation_pdf, save_enterprise_evaluation_pdf
from tools.policy_text_tool import load_policy_texts
from tools.sina_etf_trend_tool import crawl_sina_etf_trend, select_chain_config
from tools.supply_demand_tool import calculate_supply_demand_match
from tools.value_distribution_tool import calculate_value_distribution


def run_chain_evaluation(
    question: str,
    report_output: str = "outputs/reports",
    crawl_output: str = "outputs/crawled",
    output: str = "",
    output_format: str = "markdown",
    eva_pdf_output: str = "outputs/eva_pdf",
    no_llm: bool = False
) -> dict[str, object]:
    chain_config = select_chain_config(question)

    crawl_bundle = crawl_sina_etf_trend(
        question=question,
        output_root=crawl_output
    )
    policy_bundle = load_policy_texts(chain_config["policy_dir"])
    crawl_bundle["policy_support"] = PolicySupportAgent.for_chain(chain_config["slug"]).score(policy_bundle)
    crawl_bundle["fund_flow"] = calculate_chain_fund_flow(chain_config["chain_name"])
    crawl_bundle["industry_abundance"] = calculate_industry_abundance(chain_config["chain_name"])
    crawl_bundle["chain_break_risk"] = calculate_chain_break_risk(crawl_bundle)
    crawl_bundle["value_distribution"] = calculate_value_distribution(chain_config["chain_name"])
    crawl_bundle["supply_demand_match"] = calculate_supply_demand_match(chain_config["chain_name"])
    crawl_bundle.setdefault("saved_files", {})["policy_text_dir"] = policy_bundle.get("policy_dir", "")
    crawl_bundle.setdefault("saved_files", {})["fund_flow_cache"] = crawl_bundle["fund_flow"].get("cache", {}).get("path", "")

    agent = IndustryTrendAgent()
    result = agent.score(crawl_bundle)
    llm_client = None if no_llm else LLMClient.from_env()
    result = agent.enrich_with_llm(result, llm_client)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(report_output)
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / f"{chain_config['slug']}_chain_etf_report_{timestamp}.md"
    json_path = report_dir / f"{chain_config['slug']}_chain_etf_report_{timestamp}.json"

    result["report_files"] = {
        "markdown": str(markdown_path),
        "json": str(json_path)
    }
    pdf_result = save_chain_evaluation_pdf(result, eva_pdf_output, timestamp)
    result["pdf_report"] = pdf_result
    if pdf_result.get("available"):
        result["report_files"]["evaluation_pdf"] = str(pdf_result["path"])
    else:
        result["report_files"]["evaluation_pdf_error"] = str(pdf_result.get("error", "PDF 生成失败"))
    if not no_llm and not result.get("llm_interpretation", {}).get("available"):
        llm_error = result.get("llm_interpretation", {}).get("content", "智能经营建议未生成。")
        result["pdf_report"]["llm_warning"] = f"PDF 已生成，但智能经营建议未生成：{llm_error}"
    elif no_llm:
        result["pdf_report"]["llm_warning"] = "PDF 已生成，但已关闭智能经营建议。"

    markdown_text = agent.to_markdown(result)
    json_text = json.dumps(result, ensure_ascii=False, indent=2)
    markdown_path.write_text(markdown_text, encoding="utf-8")
    json_path.write_text(json_text, encoding="utf-8")

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_text = json_text if output_format == "json" else markdown_text
        output_path.write_text(output_text, encoding="utf-8")

    return result


def run_enterprise_evaluation(
    question: str,
    output_root: str = "outputs/enterprise_reports",
    eva_pdf_output: str = "outputs/eva_pdf",
    max_chain_rows: int = 500,
    max_settlement_rows: int = 500,
    no_llm: bool = False,
    use_cache: bool = True,
    refresh_cache: bool = False
) -> dict[str, object]:
    search_bundle = search_enterprise_by_question(
        question,
        max_chain_rows=max_chain_rows,
        max_settlement_rows=max_settlement_rows,
        use_cache=use_cache,
        refresh_cache=refresh_cache
    )
    chain_name = infer_chain_name_from_rows(search_bundle.get("chain_rows", []))
    chain_name = select_chain_name_for_environment(search_bundle.get("chain_rows", []), chain_name)
    chain_fund_flow = calculate_chain_fund_flow(chain_name) if chain_name else None
    search_bundle["financial_quality"] = calculate_enterprise_financial_quality(search_bundle["uid"])
    search_bundle["chain_environment"] = calculate_chain_environment(chain_name)
    search_bundle["fund_flow"] = calculate_enterprise_fund_flow(
        search_bundle["uid"],
        search_bundle.get("settlement_rows", []),
        chain_fund_flow=chain_fund_flow
    )
    if chain_fund_flow:
        search_bundle["fund_flow"]["chain_name"] = chain_name
        search_bundle["fund_flow"]["chain_cache"] = chain_fund_flow.get("cache", {})
    agent = EnterprisePositionAgent()
    result = agent.score(search_bundle)
    llm_client = None if no_llm else LLMClient.from_env()
    result = agent.enrich_with_llm(result, llm_client)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_result = save_enterprise_evaluation_pdf(result, eva_pdf_output, timestamp)
    result["pdf_report"] = pdf_result
    if pdf_result.get("available"):
        result.setdefault("report_files", {})["evaluation_pdf"] = str(pdf_result["path"])
    else:
        result.setdefault("report_files", {})["evaluation_pdf_error"] = str(pdf_result.get("error", "PDF 生成失败"))
    if not no_llm and not result.get("llm_interpretation", {}).get("available"):
        llm_error = result.get("llm_interpretation", {}).get("content", "LLM 未生成评价总结。")
        result["pdf_report"]["llm_warning"] = f"PDF 已生成，但 LLM 企业评价总结未生成：{llm_error}"
    elif no_llm:
        result["pdf_report"]["llm_warning"] = "PDF 已生成，但已关闭智能经营建议。"
    agent.save_report(result, output_root=output_root)
    return result


def route_and_run(args: argparse.Namespace) -> dict[str, object]:
    intent = IntentAgent().classify(args.question)
    if intent.intent == "enterprise_evaluation":
        result = run_enterprise_evaluation(
            question=args.question,
            output_root=args.enterprise_output_root,
            max_chain_rows=args.max_chain_rows,
            max_settlement_rows=args.max_settlement_rows,
            eva_pdf_output=args.eva_pdf_output,
            no_llm=args.no_llm,
            use_cache=not args.no_cache,
            refresh_cache=args.refresh_cache
        )
        return {
            "intent": intent.intent,
            "intent_reason": intent.reason,
            "uid": result["uid"],
            "score": result["score"],
            "layer": result["layer"],
            "llm_available": result.get("llm_interpretation", {}).get("available"),
            "pdf_report": result.get("pdf_report"),
            "cache": result.get("cache"),
            "report_files": result.get("report_files")
        }

    result = run_chain_evaluation(
        question=args.question,
        report_output=args.chain_report_output,
        crawl_output=args.chain_crawl_output,
        output=args.output,
        output_format=args.format,
        eva_pdf_output=args.eva_pdf_output,
        no_llm=args.no_llm
    )
    return {
        "intent": intent.intent,
        "intent_reason": intent.reason,
        "score": result["score"],
        "level": result["level"],
        "llm_available": result.get("llm_interpretation", {}).get("available"),
        "pdf_report": result.get("pdf_report"),
        "report_files": result.get("report_files")
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一产业链/企业评价 Orchestrator")
    parser.add_argument("--question", required=True, help="自然语言问题")
    parser.add_argument("--no-llm", action="store_true", help="关闭 LLM 报告解读")
    parser.add_argument("--output", default="", help="可选，额外保存一份产业链报告")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="配合 --output 使用的额外输出格式")
    parser.add_argument("--refresh-cache", action="store_true", help="企业 UID 链路重新扫描 Excel 并刷新缓存")
    parser.add_argument("--no-cache", action="store_true", help="企业 UID 链路不使用缓存")
    parser.add_argument("--chain-report-output", default="outputs/reports", help="产业链报告输出目录")
    parser.add_argument("--chain-crawl-output", default="outputs/crawled", help="产业链爬虫输出目录")
    parser.add_argument("--eva-pdf-output", default="outputs/eva_pdf", help="评价 PDF 输出目录")
    parser.add_argument("--enterprise-output-root", default="outputs/enterprise_reports", help="企业分层报告输出目录")
    parser.add_argument("--max-chain-rows", type=int, default=500, help="企业链路最多保留的产业链命中记录")
    parser.add_argument("--max-settlement-rows", type=int, default=500, help="企业链路最多保留的结算链命中记录")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        response = route_and_run(args)
    except Exception as exc:
        print(f"Orchestrator 执行失败：{exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
