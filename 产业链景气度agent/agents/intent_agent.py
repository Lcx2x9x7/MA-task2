from __future__ import annotations

from dataclasses import dataclass

from tools.enterprise_search_tool import extract_uid


@dataclass
class IntentResult:
    intent: str
    reason: str
    uid: str | None = None


class IntentAgent:
    """Route natural-language questions to chain or enterprise evaluators."""

    enterprise_keywords = ["客户uid", "客户UID", "uid", "UID", "企业", "公司", "分层", "链上地位"]
    chain_keywords = [
        "产业链", "新能源", "新能源汽车", "新能源车", "锂电", "动力电池", "景气",
        "半导体", "芯片", "集成电路", "晶圆", "封测"
    ]

    def classify(self, question: str) -> IntentResult:
        uid = extract_uid(question)
        if uid:
            return IntentResult(
                intent="enterprise_evaluation",
                reason="问题中包含客户 UID，优先进入企业分层链路。",
                uid=uid
            )
        if any(keyword in question for keyword in self.enterprise_keywords):
            return IntentResult(
                intent="enterprise_evaluation",
                reason="问题包含企业分层相关表达，但未识别到 UID。",
                uid=None
            )
        if any(keyword in question for keyword in self.chain_keywords):
            return IntentResult(
                intent="chain_evaluation",
                reason="问题包含产业链景气分析相关表达。",
                uid=None
            )
        return IntentResult(
            intent="chain_evaluation",
            reason="未识别到 UID，默认进入产业链评估链路。",
            uid=None
        )
