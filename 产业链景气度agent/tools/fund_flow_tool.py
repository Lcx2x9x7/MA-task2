from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tools.xlsx_stream import iter_xlsx_dicts


DATA_DIR = Path("data")
CHAIN_FILE = DATA_DIR / "产业链.xlsx"
INDICATOR_FILE = DATA_DIR / "指标体系结果.xlsx"
SETTLEMENT_FILES = [
    DATA_DIR / "结算链1.xlsx",
    DATA_DIR / "结算链2.xlsx",
]
CACHE_DIR = Path("outputs/cache/fund_flow")

HIGH_AMOUNT_BUCKETS = ("100,500", "500,1000", "1000")


def calculate_chain_fund_flow(chain_name: str, use_cache: bool = True) -> dict[str, Any]:
    cache_path = CACHE_DIR / f"{_safe_name(chain_name)}.json"
    if use_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached.setdefault("indicator_system_context", _load_indicator_system_row(chain_name))
        cached.setdefault("data_files", {}).setdefault("indicator_system", str(INDICATOR_FILE))
        cached["cache"] = {"hit": True, "path": str(cache_path)}
        return cached

    uid_layers, chain_rows_count = _load_chain_uids(chain_name)
    uid_set = set(uid_layers)
    layer_stats = {
        layer: _empty_stats()
        for layer in ["上游", "中游", "下游", "未知"]
    }
    total_stats = _empty_stats()
    enterprise_stats: dict[str, dict[str, Any]] = defaultdict(_empty_enterprise_stats)

    for row in _iter_settlement_rows():
        uid = row.get("客户UID", "")
        counterparty = row.get("交易对手客户UID", "")
        participants = []
        if uid in uid_set:
            participants.append((uid, counterparty))
        if counterparty in uid_set and counterparty != uid:
            participants.append((counterparty, uid))
        if not participants:
            continue

        tx_count = _transaction_activity_count(row)
        combined_count = _to_int(row.get("现金+票据交易笔数"))
        amount_proxy = _amount_proxy(row.get("现金+票据交易金额区间", ""), combined_count)
        is_large = _is_high_amount(row.get("现金+票据交易金额区间", ""))
        direction = row.get("交易方向名称") or "未知"

        for subject_uid, other_uid in participants:
            layer = uid_layers.get(subject_uid) or "未知"
            _update_stats(layer_stats[layer], subject_uid, other_uid, tx_count, amount_proxy, is_large, direction)
            _update_stats(total_stats, subject_uid, other_uid, tx_count, amount_proxy, is_large, direction)
            _update_enterprise_stats(enterprise_stats[subject_uid], other_uid, tx_count, amount_proxy, is_large, direction)

    layer_result = {
        layer: _finalize_stats(stats)
        for layer, stats in layer_stats.items()
        if stats["enterprise_uids"]
    }
    total_result = _finalize_stats(total_stats)
    top_enterprises = sorted(
        (
            _finalize_enterprise_stats(uid, stats, total_result["amount_proxy"])
            for uid, stats in enterprise_stats.items()
        ),
        key=lambda item: item["amount_proxy"],
        reverse=True,
    )[:20]
    score = _score_chain_flow(total_result)
    result = {
        "metric": "资金活跃度",
        "chain_name": chain_name,
        "score": score["score"],
        "reason": score["reason"],
        "chain_rows_count": chain_rows_count,
        "chain_enterprise_count": len(uid_set),
        "overall": total_result,
        "by_layer": layer_result,
        "top_enterprises": top_enterprises,
        "indicator_system_context": _load_indicator_system_row(chain_name),
        "data_files": {
            "chain": str(CHAIN_FILE),
            "indicator_system": str(INDICATOR_FILE),
            "settlement": [str(path) for path in SETTLEMENT_FILES],
        },
        "cache": {"hit": False, "path": str(cache_path)},
    }
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def calculate_enterprise_fund_flow(
    uid: str,
    settlement_rows: list[dict[str, str]],
    chain_fund_flow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats = _empty_enterprise_stats()
    for row in settlement_rows:
        own_uid = row.get("客户UID")
        counterparty = row.get("交易对手客户UID")
        if own_uid == uid:
            other_uid = counterparty or ""
        elif counterparty == uid:
            other_uid = own_uid or ""
        else:
            other_uid = counterparty or own_uid or ""

        tx_count = _transaction_activity_count(row)
        combined_count = _to_int(row.get("现金+票据交易笔数"))
        amount_proxy = _amount_proxy(row.get("现金+票据交易金额区间", ""), combined_count)
        is_large = _is_high_amount(row.get("现金+票据交易金额区间", ""))
        direction = row.get("交易方向名称") or "未知"
        _update_enterprise_stats(stats, other_uid, tx_count, amount_proxy, is_large, direction)

    chain_amount = 0.0
    if chain_fund_flow:
        chain_amount = float(chain_fund_flow.get("overall", {}).get("amount_proxy") or 0)
    result = _finalize_enterprise_stats(uid, stats, chain_amount)
    result["metric"] = "资金活跃度"
    result["score"] = _score_enterprise_flow(result)["score"]
    result["reason"] = _score_enterprise_flow(result)["reason"]
    return result


def infer_chain_name_from_rows(chain_rows: list[dict[str, str]]) -> str | None:
    counter = Counter(row.get("产业链名称") for row in chain_rows if row.get("产业链名称"))
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _load_indicator_system_row(chain_name: str) -> dict[str, str]:
    if not INDICATOR_FILE.exists():
        return {}
    rows = iter_xlsx_dicts(INDICATOR_FILE)
    # 指标体系结果第一行是标题，第二行才是表头；这里直接用行读取规避非标准表头。
    raw_rows = list()
    from tools.xlsx_stream import iter_xlsx_rows
    for row in iter_xlsx_rows(INDICATOR_FILE):
        raw_rows.append(row)
        if len(raw_rows) >= 5:
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


def _load_chain_uids(chain_name: str) -> tuple[dict[str, str], int]:
    uid_layers: dict[str, str] = {}
    count = 0
    for row in iter_xlsx_dicts(CHAIN_FILE):
        if row.get("产业链名称") != chain_name:
            continue
        uid = row.get("客户UID")
        if not uid:
            continue
        count += 1
        layer = row.get("节点上中下属性") or "未知"
        if uid not in uid_layers or uid_layers[uid] == "未知":
            uid_layers[uid] = layer if layer in {"上游", "中游", "下游"} else "未知"
    return uid_layers, count


def _iter_settlement_rows() -> Any:
    for path in SETTLEMENT_FILES:
        for row in iter_xlsx_dicts(path):
            yield row


def _empty_stats() -> dict[str, Any]:
    return {
        "enterprise_uids": set(),
        "counterparties": set(),
        "counterparty_amount": defaultdict(float),
        "activity_count": 0,
        "large_activity_count": 0,
        "amount_proxy": 0.0,
        "direction_count": Counter(),
    }


def _empty_enterprise_stats() -> dict[str, Any]:
    return {
        "counterparties": set(),
        "counterparty_amount": defaultdict(float),
        "activity_count": 0,
        "large_activity_count": 0,
        "amount_proxy": 0.0,
        "direction_count": Counter(),
    }


def _update_stats(
    stats: dict[str, Any],
    uid: str,
    other_uid: str,
    tx_count: int,
    amount_proxy: float,
    is_large: bool,
    direction: str,
) -> None:
    stats["enterprise_uids"].add(uid)
    if other_uid:
        stats["counterparties"].add(other_uid)
        stats["counterparty_amount"][other_uid] += amount_proxy
    stats["activity_count"] += tx_count
    stats["amount_proxy"] += amount_proxy
    stats["direction_count"][direction] += tx_count
    if is_large:
        stats["large_activity_count"] += tx_count


def _update_enterprise_stats(
    stats: dict[str, Any],
    other_uid: str,
    tx_count: int,
    amount_proxy: float,
    is_large: bool,
    direction: str,
) -> None:
    if other_uid:
        stats["counterparties"].add(other_uid)
        stats["counterparty_amount"][other_uid] += amount_proxy
    stats["activity_count"] += tx_count
    stats["amount_proxy"] += amount_proxy
    stats["direction_count"][direction] += tx_count
    if is_large:
        stats["large_activity_count"] += tx_count


def _finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    amount_proxy = round(float(stats["amount_proxy"]), 2)
    top_amount = max(stats["counterparty_amount"].values(), default=0.0)
    concentration = top_amount / amount_proxy if amount_proxy > 0 else 0.0
    return {
        "enterprise_count": len(stats["enterprise_uids"]),
        "counterparty_count": len(stats["counterparties"]),
        "activity_count": int(stats["activity_count"]),
        "large_activity_count": int(stats["large_activity_count"]),
        "large_activity_ratio": round(stats["large_activity_count"] / stats["activity_count"], 4) if stats["activity_count"] else 0.0,
        "amount_proxy": amount_proxy,
        "top_counterparty_amount_proxy": round(top_amount, 2),
        "top_counterparty_concentration": round(concentration, 4),
        "direction_count": dict(stats["direction_count"]),
    }


def _finalize_enterprise_stats(uid: str, stats: dict[str, Any], chain_amount: float) -> dict[str, Any]:
    amount_proxy = round(float(stats["amount_proxy"]), 2)
    top_amount = max(stats["counterparty_amount"].values(), default=0.0)
    concentration = top_amount / amount_proxy if amount_proxy > 0 else 0.0
    share = amount_proxy / chain_amount if chain_amount > 0 else 0.0
    return {
        "uid": uid,
        "counterparty_count": len(stats["counterparties"]),
        "activity_count": int(stats["activity_count"]),
        "large_activity_count": int(stats["large_activity_count"]),
        "large_activity_ratio": round(stats["large_activity_count"] / stats["activity_count"], 4) if stats["activity_count"] else 0.0,
        "amount_proxy": amount_proxy,
        "chain_amount_share": round(share, 6),
        "top_counterparty_amount_proxy": round(top_amount, 2),
        "counterparty_concentration": round(concentration, 4),
        "direction_count": dict(stats["direction_count"]),
    }


def _score_chain_flow(result: dict[str, Any]) -> dict[str, Any]:
    activity_score = min(result["activity_count"] / 5000 * 100, 100)
    large_score = min(result["large_activity_count"] / 1200 * 100, 100)
    density_score = min(result["counterparty_count"] / max(result["enterprise_count"], 1) / 3 * 100, 100)
    concentration_score = max(0, 100 - result["top_counterparty_concentration"] * 100)
    score = activity_score * 0.40 + large_score * 0.25 + density_score * 0.25 + concentration_score * 0.10
    return {
        "score": round(_clip(score, 0, 100), 2),
        "reason": (
            f"总体交易活跃笔数 {result['activity_count']}，大额交易活跃笔数 {result['large_activity_count']}，"
            f"交易对手 {result['counterparty_count']} 个，最高交易对手集中度 {result['top_counterparty_concentration']:.2%}。"
        ),
    }


def _score_enterprise_flow(result: dict[str, Any]) -> dict[str, Any]:
    breadth_score = min(result["counterparty_count"] / 20 * 100, 100)
    concentration_score = max(0, 100 - result["counterparty_concentration"] * 100)
    share_score = min(result["chain_amount_share"] / 0.02 * 100, 100) if result["chain_amount_share"] else min(result["amount_proxy"] / 5000 * 100, 100)
    score = breadth_score * 0.35 + concentration_score * 0.35 + share_score * 0.30
    return {
        "score": round(_clip(score, 0, 100), 2),
        "reason": (
            f"交易对手 {result['counterparty_count']} 个，交易对手集中度 {result['counterparty_concentration']:.2%}，"
            f"链上交易金额代理占比 {result['chain_amount_share']:.4%}，大额交易活跃笔数 {result['large_activity_count']}。"
        ),
    }


def _transaction_activity_count(row: dict[str, str]) -> int:
    return _to_int(row.get("现金交易笔数")) + _to_int(row.get("现金+票据交易笔数"))


def _amount_proxy(bucket: str, count: int) -> float:
    return _amount_bucket_midpoint(bucket) * max(count, 0)


def _amount_bucket_midpoint(bucket: str) -> float:
    bucket = str(bucket).strip()
    if not bucket or bucket == "0元":
        return 0.0
    if "1,10" in bucket:
        return 5.5
    if "10,100" in bucket:
        return 55.0
    if "100,500" in bucket:
        return 300.0
    if "500,1000" in bucket:
        return 750.0
    if "1000" in bucket:
        return 1500.0
    match = re.search(r"(\d+(?:\.\d+)?)", bucket)
    return float(match.group(1)) if match else 0.0


def _is_high_amount(bucket: str) -> bool:
    return any(token in str(bucket) for token in HIGH_AMOUNT_BUCKETS)


def _to_int(value: Any) -> int:
    try:
        text = str(value or "").replace(",", "").strip()
        return int(float(text)) if text else 0
    except ValueError:
        return 0


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]", "_", value)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
