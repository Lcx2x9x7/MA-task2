from __future__ import annotations

import re
from pathlib import Path
from typing import Any


FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def save_chain_evaluation_pdf(result: dict[str, Any], output_dir: str | Path, timestamp: str) -> dict[str, Any]:
    pdf_dir = Path(output_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        return {
            "available": False,
            "error": "缺少 PDF 依赖 reportlab。请安装：pip install reportlab 或 conda install -c conda-forge reportlab",
            "exception": str(exc),
        }

    slug = _slug_from_chain(result.get("chain_name", "chain"))
    pdf_path = pdf_dir / f"{slug}_evaluation_summary_{timestamp}.pdf"

    font_name = _register_chinese_font(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=24,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "ChineseHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=18,
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=17,
        firstLineIndent=0,
        spaceAfter=6,
    )

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{result.get('chain_name', '')}评价报告",
    )

    llm = result.get("llm_interpretation", {})
    llm_content = llm.get("content") if llm.get("available") else _chain_rule_summary(result)
    components = result.get("components", {})
    business = result.get("business_assessment", {})
    summary_rows = [
        ["项目", "结果"],
        ["产业链", result.get("chain_name", "")],
        ["综合分", str(result.get("score", ""))],
        ["综合等级", result.get("level", "")],
        ["经营优先级", str(business.get("priority_label", ""))],
        ["机会等级", str(business.get("opportunity_level", ""))],
        ["风险等级", str(business.get("risk_level", ""))],
        ["推荐措施", str(business.get("recommended_action", ""))],
    ]
    indicator_rows = _chain_indicator_pdf_rows(result)
    distribution_rows = _chain_distribution_pdf_rows(result)
    key_company_rows = _chain_key_company_pdf_rows(result)

    story = [
        Paragraph(f"{result.get('chain_name', '')}评估报告", title_style),
        Spacer(1, 6),
        _table(summary_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 10),
        Paragraph("评估结论", heading_style),
    ]
    for paragraph in _split_paragraphs(_clean_chain_conclusion_text(llm_content, result.get("chain_name", ""))):
        story.append(Paragraph(_escape(paragraph), body_style))

    story.extend([
        Spacer(1, 8),
        Paragraph("指标依据", heading_style),
        _table(indicator_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("上中下游企业统计", heading_style),
        _table(distribution_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("重点企业线索", heading_style),
        Paragraph(_escape(result.get("business_assessment", {}).get("key_company_clues", {}).get("screening_basis", "")), body_style),
        _table(key_company_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("关键分析摘要", heading_style),
        _table(_chain_analysis_pdf_rows(result), font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("产品机会与采取措施", heading_style),
    ])
    story.extend(_chain_recommendation_pdf_flowables(result, Paragraph, body_style))
    story.extend([
        Spacer(1, 8),
        Paragraph("风险核验", heading_style),
        Paragraph(_escape(_chain_risk_check_text(result)), body_style),
        Spacer(1, 8),
        Paragraph("底线说明", heading_style),
        Paragraph("本报告基于 ETF 行情、产业链表、结算链、政策文本和规则评分生成，用于对公客户经营线索识别、名单筛选和风险核验，不构成投资建议或授信审批结论。", body_style),
    ])
    doc.build(story)

    return {
        "available": True,
        "path": str(pdf_path),
    }


def save_enterprise_evaluation_pdf(result: dict[str, Any], output_dir: str | Path, timestamp: str) -> dict[str, Any]:
    pdf_dir = Path(output_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        return {
            "available": False,
            "error": "缺少 PDF 依赖 reportlab。请安装：pip install reportlab 或 conda install -c conda-forge reportlab",
            "exception": str(exc),
        }

    uid = str(result.get("uid", "enterprise"))
    pdf_path = pdf_dir / f"enterprise_position_{uid[:12]}_{timestamp}.pdf"

    font_name = _register_chinese_font(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=24,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "ChineseHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=18,
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=17,
        firstLineIndent=0,
        spaceAfter=6,
    )

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{uid[:12]}企业分层评价报告",
    )

    llm = result.get("llm_interpretation", {})
    llm_content = llm.get("content") if llm.get("available") else _enterprise_rule_summary(result)
    components = result.get("components", {})
    business = result.get("business_assessment", {})
    summary_rows = [
        ["项目", "结果"],
        ["企业名称", "企业***"],
        ["综合分", str(result.get("score", ""))],
        ["分层", str(result.get("layer", ""))],
        ["经营优先级", str(business.get("priority_label", ""))],
        ["机会等级", str(business.get("opportunity_level", ""))],
        ["风险等级", str(business.get("risk_level", ""))],
        ["推荐措施", str(business.get("recommended_action", ""))],
    ]

    chain_env = components.get("chain_environment", {}).get("detail", {})
    financial = components.get("financial_quality", {}).get("detail", {})
    source_row = financial.get("source_row", {})

    opportunity_rows = _enterprise_opportunity_rows(result)
    risk_rows = _enterprise_risk_rows(result)
    evidence_rows = _enterprise_recommendation_evidence_rows(result)
    indicator_rows = _enterprise_indicator_pdf_rows(result)
    story = [
        Paragraph("企业客户评估报告", title_style),
        Spacer(1, 6),
        _table(summary_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 10),
        Paragraph("评估结论和建议", heading_style),
    ]
    for paragraph in _split_paragraphs(_clean_enterprise_conclusion_text(llm_content)):
        story.append(Paragraph(_escape(paragraph), body_style))

    detail_rows = [
        ["项目", "结果"],
        ["所属产业链", str(chain_env.get("chain_name", ""))],
        ["信息来源", "中国**网"],
        ["企业规模", str(source_row.get("企业规模国标", ""))],
        ["注册地", f"{source_row.get('注册地址_省', '')}{source_row.get('注册地址_市', '')}{source_row.get('注册地址_区县', '')}"],
        ["行业", f"{source_row.get('国标行业1级', '')} / {source_row.get('国标行业2级', '')}"],
        ["年报日期", str(source_row.get("年报日期", ""))],
    ]
    story.extend([
        Spacer(1, 8),
        Paragraph("指标依据", heading_style),
        _table(indicator_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("建议与数据依据", heading_style),
        _table(evidence_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("产品机会", heading_style),
        _table(opportunity_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("风控清单", heading_style),
        _table(risk_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("关键依据", heading_style),
        _table(detail_rows, font_name, Table, TableStyle, colors, mm),
        Spacer(1, 8),
        Paragraph("底线说明", heading_style),
        Paragraph("本报告基于产业链表、结算链、企业财报、最近产业链评估结果和规则评分生成，用于对公客户经营线索识别、产品适配和风险核验，不构成信用评级、授信审批结论或投资建议。", body_style),
    ])
    doc.build(story)

    return {
        "available": True,
        "path": str(pdf_path),
    }


def _register_chinese_font(pdfmetrics: Any, TTFont: Any) -> str:
    for path in FONT_CANDIDATES:
        font_path = Path(path)
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("ChineseFont", str(font_path)))
            return "ChineseFont"
    return "Helvetica"


def _table(rows: list[list[str]], font_name: str, Table: Any, TableStyle: Any, colors: Any, mm: Any) -> Any:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    column_count = max((len(row) for row in rows), default=2)
    if column_count >= 5:
        widths = [26 * mm, 28 * mm, 32 * mm, 32 * mm, 32 * mm]
    elif column_count >= 3:
        widths = [32 * mm, 58 * mm, 60 * mm]
    else:
        widths = [35 * mm, 115 * mm]
    cell_style = ParagraphStyle(
        "TableCell",
        fontName=font_name,
        fontSize=9,
        leading=12,
        wordWrap="CJK",
    )
    wrapped_rows = [
        [Paragraph(_escape(str(cell)), cell_style) for cell in row]
        for row in rows
    ]
    table = Table(wrapped_rows, colWidths=widths[:column_count])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [line.strip() for line in str(text).splitlines() if line.strip()]
    return paragraphs or ["未生成智能经营建议，报告使用规则摘要。"]


def _chain_rule_summary(result: dict[str, Any]) -> str:
    components = result.get("components", {})
    business = result.get("business_assessment", {})
    distribution = business.get("enterprise_distribution", {})
    return "\n".join([
        f"评估结论：{result.get('chain_name', '')}当前综合分 {result.get('score', '')}，等级 {result.get('level', '')}，经营优先级为{business.get('priority_label', '缺失')}，机会等级为{business.get('opportunity_level', '缺失')}，风险等级为{business.get('risk_level', '缺失')}。推荐措施是：{business.get('recommended_action', '审慎跟进')}。",
        f"企业分布：链上企业数 {distribution.get('chain_enterprise_count', '缺失')}，交易对手数 {distribution.get('counterparty_count', '缺失')}，交易活跃度 {distribution.get('activity_count', '缺失')}，大额交易活跃度 {distribution.get('large_activity_count', '缺失')}。客户经理应优先排查交易活跃、连接广、处在关键环节的企业。",
        f"指标证据：链路传导 {components.get('transmission_efficiency', {}).get('score', '缺失')}，政策环境 {components.get('policy_support', {}).get('score', '缺失')}，链条丰度 {components.get('industry_abundance', {}).get('score', '缺失')}，断链风险 {components.get('chain_break_risk', {}).get('score', '缺失')}，价值分配 {components.get('value_distribution', {}).get('score', '缺失')}，供需匹配 {components.get('supply_demand_match', {}).get('score', '缺失')}。这些指标用于决定名单优先级、产品切入和风控核验重点。"
    ])


def _clean_chain_conclusion_text(text: str, chain_name: str) -> str:
    cleaned = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        stripped = line.lstrip("#").strip()
        if not stripped:
            continue
        if stripped in {f"{chain_name}评估报告", f"{chain_name}经营作战卡", chain_name}:
            continue
        if stripped.startswith("四、风险核验") or stripped.startswith("4. 风险核验") or stripped.startswith("风险核验"):
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned)


def _chain_distribution_pdf_rows(result: dict[str, Any]) -> list[list[str]]:
    distribution = result.get("business_assessment", {}).get("enterprise_distribution", {})
    rows = [["层级", "企业数", "交易活跃", "大额活跃", "交易对手"]]
    for layer in ["上游", "中游", "下游", "未知"]:
        item = distribution.get("by_layer", {}).get(layer)
        if not item:
            continue
        rows.append([
            layer,
            str(item.get("enterprise_count", 0)),
            str(item.get("activity_count", 0)),
            str(item.get("large_activity_count", 0)),
            str(item.get("counterparty_count", 0)),
        ])
    if len(rows) == 1:
        rows.append(["缺失", "0", "0", "0", "0"])
    rows.append(["区域集聚", str(distribution.get("regional_concentration", "缺失")), "", "", ""])
    return rows


def _chain_indicator_pdf_rows(result: dict[str, Any]) -> list[list[str]]:
    components = result.get("components", {})
    rows = [["指标", "得分", "指标含义"]]
    mapping = [
        ("transmission_efficiency", "判断上中下游联动、ETF市场信号和链上资金传导。"),
        ("policy_support", "判断政策支持强度和监管约束。"),
        ("industry_abundance", "判断企业数量、增长代理和区域集聚基础。"),
        ("chain_break_risk", "判断断链、卡脖子和市场价格风险，分数越高风险越高。"),
        ("value_distribution", "判断利润是否在链条中健康沉淀。"),
        ("supply_demand_match", "判断需求、供给和价格传导是否协调。"),
    ]
    for key, meaning in mapping:
        item = components.get(key, {})
        value = str(item.get("score", ""))
        rows.append([str(item.get("label", key)), value, meaning])
    return rows


def _chain_key_company_pdf_rows(result: dict[str, Any]) -> list[list[str]]:
    companies = (
        result.get("business_assessment", {})
        .get("key_company_clues", {})
        .get("companies", [])
    )
    rows = [["企业", "代码", "层级", "节点", "净利率/ROE"]]
    for item in companies[:8]:
        rows.append([
            str(item.get("company_name", "")),
            str(item.get("stock_code", "")),
            str(item.get("layer", "")),
            str(item.get("node", "")),
            f"{item.get('net_margin', '')} / {item.get('roe', '')}",
        ])
    if len(rows) == 1:
        rows.append(["缺失", "缺失", "缺失", "缺失", "缺失"])
    return rows


def _chain_recommendation_pdf_rows(result: dict[str, Any]) -> list[list[str]]:
    rows = [["建议", "数据依据", "客户经理动作"]]
    for item in result.get("business_assessment", {}).get("recommendation_evidence", []):
        rows.append([
            str(item.get("recommendation", "")),
            str(item.get("evidence", "")),
            str(item.get("action", "")),
        ])
    if len(rows) == 1:
        rows.append(["补充核验", "缺少建议证据映射", "补充数据后再判断"])
    return rows


def _chain_recommendation_pdf_flowables(result: dict[str, Any], Paragraph: Any, body_style: Any) -> list[Any]:
    items = result.get("business_assessment", {}).get("recommendation_evidence", [])
    if not items:
        return [Paragraph("补充核验：缺少建议证据映射，需补充数据后再判断。", body_style)]
    flowables = []
    for index, item in enumerate(items, start=1):
        text = (
            f"{index}. {_escape(item.get('recommendation', ''))}<br/>"
            f"数据依据：{_escape(item.get('evidence', ''))}<br/>"
            f"客户经理动作：{_escape(item.get('action', ''))}"
        )
        flowables.append(Paragraph(text, body_style))
    return flowables


def _chain_risk_check_text(result: dict[str, Any]) -> str:
    business = result.get("business_assessment", {})
    return (
        f"风险等级：{business.get('risk_level', '缺失')}。"
        f"主要风险点：{'；'.join(business.get('risk_points', []))}。"
        "业务落地前必须核验订单、合同、发票、物流、库存、价格、回款流水和核心交易对手依赖；"
        "涉及授信时还需补充企业最新财报、征信、纳税、真实贸易背景和资金用途。"
    )


def _chain_analysis_pdf_rows(result: dict[str, Any]) -> list[list[str]]:
    components = result.get("components", {})
    business = result.get("business_assessment", {})
    transmission = components.get("transmission_efficiency", {})
    risk = components.get("chain_break_risk", {})
    value = components.get("value_distribution", {})
    demand = components.get("supply_demand_match", {})
    policy = components.get("policy_support", {})
    abundance = components.get("industry_abundance", {})
    return [
        ["分析维度", "摘要"],
        [
            "链路传导",
            f"结构传导 {transmission.get('structural_score', '缺失')}，市场趋势 {transmission.get('market_trend_score', '缺失')}，链上资金传导 {transmission.get('fund_flow_score', '缺失')}。链上交易连接较活跃，但市场端趋势仍需观察。",
        ],
        [
            "企业基础",
            f"链条丰度 {abundance.get('score', '缺失')}，政策环境 {policy.get('score', '缺失')}。产业基础和政策支撑较明确，适合做客户名单筛选和区域集中拜访。",
        ],
        [
            "利润和供需",
            f"价值分配 {value.get('score', '缺失')}，供需匹配 {demand.get('score', '缺失')}。若这两个指标偏弱，需优先核验毛利、订单、库存和回款质量。",
        ],
        [
            "风险侧",
            f"断链风险 {risk.get('score', '缺失')}，风险等级 {business.get('risk_level', '缺失')}。主要风险点：{'；'.join(business.get('risk_points', []))}。",
        ],
    ]


def _enterprise_rule_summary(result: dict[str, Any]) -> str:
    components = result.get("components", {})
    business = result.get("business_assessment", {})
    position = _component_score(components, "chain_position")
    fund = _component_score(components, "fund_flow")
    financial = _component_score(components, "financial_quality")
    environment = _component_score(components, "chain_environment")
    layer = result.get("layer", "")
    return "\n".join([
        f"评估结论：企业***当前属于{layer}，具备一定链上经营价值，建议采取“{business.get('recommended_action', '审慎跟进')}”策略。具体分层、机会和风险等级以首页表格为准，本节只解释业务含义。",
        f"指标证据：资金活跃得分 {fund}，可作为结算、票据和供应链金融切入的交易证据；财务质量得分 {financial}，用于判断授信承接能力；链条环境得分 {environment}，用于判断外部产业景气是否支持持续经营。",
        "产品机会：优先从结算账户、票据池、保理、订单融资、应收账款融资和现金管理切入。若后续核验订单稳定、回款真实且上下游关系清晰，再考虑流动资金贷款或供应链白名单方案。",
        "客户跟进措施：下一次沟通应重点收集前三大客户和供应商清单、合同订单、发票、物流或交付证明、近半年银行流水、应收账款明细和票据使用情况。客户经理还应确认企业是否有扩产、备货、设备更新或账期拉长带来的融资需求。",
        "风险核验：授信或业务落地前必须核验交易真实性、交易对手集中度、现金流覆盖、财报字段完整性、应收账款回款质量和所在产业链景气变化。本报告只作为客户经营线索和尽调优先级参考，不构成信用评级或授信审批结论。",
    ])


def _clean_enterprise_conclusion_text(text: str) -> str:
    cleaned = []
    skip_prefixes = (
        "客户UID",
        "**客户UID**",
        "UID",
        "企业经营分析报告",
        "企业客户评估报告",
    )
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        stripped = line.lstrip("#").strip()
        stripped = stripped.replace("**", "")
        if not stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in skip_prefixes):
            continue
        if "客户UID" in stripped or re.search(r"[0-9a-fA-F]{18,}", stripped):
            continue
        stripped = stripped.replace("1. 经营结论", "1. 评估结论")
        stripped = stripped.replace("一、经营结论", "一、评估结论")
        stripped = stripped.replace("经营结论：", "评估结论：")
        cleaned.append(stripped)
    return "\n".join(cleaned)


def _enterprise_indicator_pdf_rows(result: dict[str, Any]) -> list[list[str]]:
    components = result.get("components", {})
    rows = [["指标", "得分", "指标含义"]]
    mapping = [
        ("chain_position", "判断企业在产业链环节中的关键程度和上下游连接广度。"),
        ("fund_flow", "判断企业结算活跃、交易对手广度、交易集中度和供应链金融切入空间。"),
        ("financial_quality", "判断企业规模、盈利、偿债、现金流和经营状态是否支撑业务承接。"),
        ("chain_environment", "判断企业所处产业链外部景气、政策、供需、价值和断链风险环境。"),
    ]
    for key, meaning in mapping:
        item = components.get(key, {})
        rows.append([str(item.get("label", key)), str(item.get("score", "")), meaning])
    return rows


def _enterprise_opportunity_rows(result: dict[str, Any]) -> list[list[str]]:
    components = result.get("components", {})
    position = _component_score(components, "chain_position")
    fund = _component_score(components, "fund_flow")
    financial = _component_score(components, "financial_quality")
    fund_detail = components.get("fund_flow", {}).get("detail", {})
    rows = [["机会方向", "数据依据与建议动作"]]
    rows.append(["结算与现金管理", f"交易对手 {fund_detail.get('counterparty_count', 0)} 个、交易经营活跃度 {fund_detail.get('activity_count', 0)}，可推动结算账户、银企直联、现金管理和代发协同。"])
    rows.append(["票据与供应链金融", f"大额交易活跃度 {fund_detail.get('large_activity_count', 0)}、资金活跃 {fund}，核验真实贸易后切入票据池、保理、订单融资或应收账款融资。"])
    rows.append(["授信切入", f"链上地位 {position}、财务质量 {financial}，适合先做资料核验和额度测算，不能直接替代授信审批。"])
    rows.append(["名单经营", f"综合分 {result.get('score', '')}、分层 {result.get('layer', '')}，可纳入客户经理跟进名单，按交易真实性和上下游质量排序拜访。"])
    return rows


def _enterprise_risk_rows(result: dict[str, Any]) -> list[list[str]]:
    components = result.get("components", {})
    business = result.get("business_assessment", {})
    fund_detail = components.get("fund_flow", {}).get("detail", {})
    financial_detail = components.get("financial_quality", {}).get("detail", {})
    rows = [["核验事项", "客户经理需要确认的材料或问题"]]
    rows.append(["风险等级", f"{business.get('risk_level', '缺失')}；主要风险点：{'；'.join(business.get('risk_points', []))}"])
    rows.append(["交易真实性", "合同、发票、物流/交付证明、回款流水是否一致，是否存在空转或异常往来。"])
    rows.append(["交易集中度", f"当前交易对手集中度 {float(fund_detail.get('counterparty_concentration', 0)):.2%}，需核验是否过度依赖单一客户或供应商。"])
    rows.append(["现金流质量", f"经营现金流和现金收入比率需结合流水复核；当前财务说明：{financial_detail.get('reason', '缺失')}"])
    rows.append(["产业链风险", "结合链条环境、断链风险、供需变化和政策环境，判断是否存在行业下行或关键环节受限。"])
    return rows


def _component_score(components: dict[str, Any], key: str) -> Any:
    return components.get(key, {}).get("score", "缺失")


def _enterprise_recommendation_evidence_rows(result: dict[str, Any]) -> list[list[str]]:
    rows = [["建议", "数据依据", "客户经理动作"]]
    for item in result.get("business_assessment", {}).get("recommendation_evidence", []):
        rows.append([
            str(item.get("recommendation", "")),
            str(item.get("evidence", "")),
            str(item.get("action", "")),
        ])
    if len(rows) == 1:
        rows.append(["补充核验", "缺少建议证据映射", "补充交易、财报和产业链数据后再判断"])
    return rows


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _slug_from_chain(chain_name: str) -> str:
    if "半导体" in chain_name:
        return "semiconductor"
    if "新能源" in chain_name:
        return "new_energy"
    return "chain"
