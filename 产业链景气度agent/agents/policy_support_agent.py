from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any


class PolicySupportAgent:
    metric_name = "政策环境"

    supportive_keywords = [
        "支持", "促进", "推动", "加快", "鼓励", "提升", "完善", "建设", "推广", "试点",
        "示范", "补贴", "财政", "金融", "专项债", "减免", "购置税", "车船税", "下乡",
        "充电基础设施", "车网互动", "高质量发展", "扩大内需", "设备更新", "以旧换新"
    ]
    primary_relevance_keywords = [
        "新能源汽车", "新能源车", "动力电池", "充电", "充电基础设施", "车网互动",
        "智能网联", "汽车消费", "汽车产业", "乘用车", "纯电动", "电动汽车"
    ]
    strategic_keywords = [
        "绿色低碳", "双碳", "可再生能源", "新型电力系统", "循环经济", "绿色电力",
        "配电网", "储能", "绿色技术"
    ]
    constraint_keywords = [
        "安全", "监管", "准入", "标准", "强制性", "风险", "限制", "无序投建",
        "质量", "合规", "主体责任"
    ]
    authoritative_sources = ["NDRC", "MIIT", "国家发展改革委", "工信部", "国家能源局", "市场监管"]

    @classmethod
    def for_chain(cls, chain_slug: str) -> "PolicySupportAgent":
        agent = cls()
        if chain_slug == "semiconductor":
            agent.supportive_keywords = [
                "支持", "促进", "推动", "加快", "鼓励", "提升", "完善", "建设", "培育",
                "突破", "攻关", "创新", "研发", "首台套", "补贴", "财政", "税收优惠",
                "减免", "专项", "重大项目", "产业基础", "强链补链", "高质量发展",
                "扩大投资", "制造业", "数字经济"
            ]
            agent.primary_relevance_keywords = [
                "半导体", "芯片", "集成电路", "晶圆", "封测", "光刻", "刻蚀", "薄膜",
                "离子注入", "电子特气", "硅片", "EDA", "存储器", "先进封装", "功率器件",
                "第三代半导体", "电子信息制造业", "软件企业"
            ]
            agent.strategic_keywords = [
                "科技创新", "关键核心技术", "基础研究", "新型工业化", "数字经济",
                "人工智能", "算力", "高端制造", "产业链供应链", "国产替代", "战略性新兴产业"
            ]
            agent.constraint_keywords = [
                "安全", "监管", "准入", "标准", "强制性", "风险", "限制", "合规",
                "出口管制", "贸易摩擦", "实体清单", "质量", "主体责任"
            ]
        return agent

    def score(self, policy_bundle: dict[str, Any]) -> dict[str, Any]:
        documents = policy_bundle.get("documents", [])
        if not documents:
            return {
                "label": self.metric_name,
                "score": 50.0,
                "reason": "未读取到政策文本，按中性处理。",
                "document_count": 0,
                "evidence_docs": [],
                "signals": {}
            }

        scored_docs = [self._score_document(doc) for doc in documents]
        relevant_docs = [doc for doc in scored_docs if doc["relevance_score"] >= 50]
        high_relevance_docs = [doc for doc in scored_docs if doc["relevance_score"] >= 65]
        docs_for_average = sorted(relevant_docs or scored_docs, key=lambda item: item["score"], reverse=True)[:12]

        avg_doc_score = mean(doc["score"] for doc in docs_for_average)
        coverage_score = _clip(len(relevant_docs) / 20 * 100, 0, 100)
        recent_score = _clip(
            sum(1 for doc in relevant_docs if doc["recent"]) / 8 * 100,
            0,
            100
        )
        authority_score = _clip(
            sum(1 for doc in relevant_docs if doc["authoritative"]) / max(len(relevant_docs), 1) * 100,
            0,
            100
        )
        constraint_risk = mean(doc["constraint_score"] for doc in docs_for_average)

        score = (
            avg_doc_score * 0.55
            + coverage_score * 0.15
            + recent_score * 0.15
            + authority_score * 0.10
            - constraint_risk * 0.05
        )
        score = _clip(score, 0, 95)

        top_docs = sorted(scored_docs, key=lambda item: (item["score"], item["relevance_score"]), reverse=True)[:8]
        source_counter = Counter(doc.get("source") or "未知" for doc in documents)
        return {
            "label": self.metric_name,
            "score": round(score, 2),
            "reason": (
                f"读取政策/新闻文本 {len(documents)} 篇，"
                f"相关政策 {len(relevant_docs)} 篇，高相关政策 {len(high_relevance_docs)} 篇，"
                f"近期相关政策 {sum(1 for doc in relevant_docs if doc['recent'])} 篇，"
                f"权威来源相关文本 {sum(1 for doc in relevant_docs if doc['authoritative'])} 篇。"
            ),
            "document_count": len(documents),
            "policy_dir": policy_bundle.get("policy_dir"),
            "signals": {
                "average_top_document_score": round(avg_doc_score, 2),
                "relevant_policy_count": len(relevant_docs),
                "high_relevance_policy_count": len(high_relevance_docs),
                "recent_relevant_policy_count": sum(1 for doc in relevant_docs if doc["recent"]),
                "authoritative_relevant_source_count": sum(1 for doc in relevant_docs if doc["authoritative"]),
                "coverage_score": round(coverage_score, 2),
                "recent_score": round(recent_score, 2),
                "authority_score": round(authority_score, 2),
                "constraint_risk": round(constraint_risk, 2),
                "top_sources": [{"source": source, "count": count} for source, count in source_counter.most_common(8)]
            },
            "evidence_docs": top_docs
        }

    def _score_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        title = doc.get("title", "")
        source = doc.get("source", "")
        text = f"{title}\n{doc.get('text', '')}"
        normalized_length = max(len(text) / 1000, 1)
        supportive_hits = _count_hits(text, self.supportive_keywords)
        primary_relevance_hits = _count_hits(text, self.primary_relevance_keywords)
        strategic_hits = _count_hits(text, self.strategic_keywords)
        constraint_hits = _count_hits(text, self.constraint_keywords)
        authoritative = any(keyword in source or keyword in title for keyword in self.authoritative_sources)
        recent = _is_recent_policy(doc.get("date", ""), title)

        supportive_density = supportive_hits / normalized_length
        primary_relevance_density = primary_relevance_hits / normalized_length
        strategic_density = strategic_hits / normalized_length
        constraint_density = constraint_hits / normalized_length

        title_primary_relevance = _count_hits(title, self.primary_relevance_keywords) * 12
        chain_relevance = 10 if "新能源汽车" in doc.get("chains", "") else 0
        relevance_score = _clip(
            15
            + title_primary_relevance
            + chain_relevance
            + min(primary_relevance_density * 28, 60)
            + min(strategic_density * 3, 15),
            0,
            100
        )
        support_score = _clip(35 + supportive_density * 9, 0, 100)
        constraint_score = _clip(constraint_density * 10, 0, 100)
        source_score = 100 if authoritative else 40
        recent_score = 100 if recent else 45

        score = (
            relevance_score * 0.35
            + support_score * 0.35
            + source_score * 0.12
            + recent_score * 0.08
            - constraint_score * 0.10
        )
        score = _clip(score, 0, 100)

        return {
            "title": title,
            "source": source,
            "date": doc.get("date", ""),
            "url": doc.get("url", ""),
            "file_name": doc.get("file_name", ""),
            "score": round(score, 2),
            "relevance_score": round(relevance_score, 2),
            "support_score": round(support_score, 2),
            "constraint_score": round(constraint_score, 2),
            "recent": recent,
            "authoritative": authoritative,
            "primary_relevance_hits": primary_relevance_hits,
            "supportive_hits": supportive_hits,
            "strategic_hits": strategic_hits,
            "constraint_hits": constraint_hits,
            "snippet": _snippet(text)
        }


def _count_hits(text: str, keywords: list[str]) -> int:
    return sum(text.count(keyword) for keyword in keywords)


def _is_recent_policy(date: str, title: str) -> bool:
    text = f"{date} {title}"
    return any(year in text for year in ["2026", "2025", "2024"])


def _snippet(text: str, length: int = 160) -> str:
    clean = " ".join(text.split())
    return clean[:length]


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
