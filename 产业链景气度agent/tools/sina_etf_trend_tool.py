from __future__ import annotations

import ast
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


CHAIN_CONFIGS = {
    "new_energy": {
        "chain_name": "新能源汽车产业链",
        "slug": "new_energy",
        "policy_dir": "data/新能源汽车产业链",
        "etfs": [
            {
                "symbol": "sh515030",
                "code": "515030",
                "name": "华夏中证新能源汽车ETF",
                "sina_name": "新能源车ETF华夏",
                "layer": "全链总锚",
                "tracked_index": "中证新能源汽车指数",
                "trend_weight": 0.30,
                "reason": "覆盖新能源汽车产业链核心上市公司，用于判断全链整体市场预期。"
            },
            {
                "symbol": "sz159671",
                "code": "159671",
                "name": "工银中证稀有金属主题ETF",
                "sina_name": "稀金属",
                "layer": "上游资源",
                "tracked_index": "中证稀有金属主题指数",
                "trend_weight": 0.20,
                "reason": "锂、钴、镍、稀土等关键金属是新能源车电池链的重要上游输入。"
            },
            {
                "symbol": "sz159755",
                "code": "159755",
                "name": "广发国证新能源车电池ETF",
                "sina_name": "电池ETF",
                "layer": "中游电池",
                "tracked_index": "国证新能源车电池指数",
                "trend_weight": 0.30,
                "reason": "动力电池是新能源汽车产业链价值和技术壁垒最高的中游核心环节。"
            },
            {
                "symbol": "sz159565",
                "code": "159565",
                "name": "中证汽车零部件ETF",
                "sina_name": "汽零ETF",
                "layer": "下游零部件",
                "tracked_index": "中证汽车零部件主题指数",
                "trend_weight": 0.20,
                "reason": "零部件环节反映整车生产配套、智能化和供应链扩散情况。"
            }
        ]
    },
    "semiconductor": {
        "chain_name": "半导体产业链",
        "slug": "semiconductor",
        "policy_dir": "data/半导体产业链",
        "etfs": [
            {
                "symbol": "sh512480",
                "code": "512480",
                "name": "国联安中证全指半导体ETF",
                "sina_name": "半导体ETF国联安",
                "layer": "全链总锚",
                "tracked_index": "中证全指半导体产品与设备指数",
                "trend_weight": 0.30,
                "reason": "覆盖半导体产品与设备上市公司，用于观察半导体产业链整体市场预期。"
            },
            {
                "symbol": "sz159516",
                "code": "159516",
                "name": "国泰中证半导体材料设备主题ETF",
                "sina_name": "半导设备",
                "layer": "上游设备材料",
                "tracked_index": "中证半导体材料设备主题指数",
                "trend_weight": 0.25,
                "reason": "设备和材料是晶圆制造扩产、国产替代和资本开支的前置环节。"
            },
            {
                "symbol": "sz159995",
                "code": "159995",
                "name": "华夏国证半导体芯片ETF",
                "sina_name": "芯片ETF",
                "layer": "中游芯片",
                "tracked_index": "国证半导体芯片指数",
                "trend_weight": 0.30,
                "reason": "芯片设计、制造和封测是半导体产业链的核心价值环节。"
            },
            {
                "symbol": "sz159732",
                "code": "159732",
                "name": "华宝中证消费电子主题ETF",
                "sina_name": "消费电子",
                "layer": "下游电子应用",
                "tracked_index": "中证消费电子主题指数",
                "trend_weight": 0.15,
                "reason": "消费电子是芯片需求的重要下游应用，可观察终端需求对半导体景气的拉动。"
            }
        ]
    }
}


def select_chain_config(question: str) -> dict[str, Any]:
    if any(keyword in question for keyword in ["半导体", "芯片", "集成电路", "晶圆", "封测"]):
        return CHAIN_CONFIGS["semiconductor"]
    if any(keyword in question for keyword in ["新能源", "新能源汽车", "新能源车", "锂电", "动力电池", "充电桩"]):
        return CHAIN_CONFIGS["new_energy"]
    raise ValueError("当前产业链评估只支持新能源汽车产业链和半导体产业链，请在 question 中包含相关行业关键词。")


def crawl_sina_etf_trend(
    question: str,
    output_root: str | Path = "outputs/crawled",
    datalen: int = 120
) -> dict[str, Any]:
    config = select_chain_config(question)
    chain_name = config["chain_name"]
    etfs = config["etfs"]
    fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(output_root) / f"sina_{config['slug']}_etf_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    quotes: list[dict[str, Any]] = []
    histories: dict[str, list[dict[str, Any]]] = {}
    combined_history: list[dict[str, Any]] = []
    history_files: dict[str, str] = {}

    for etf in etfs:
        quote_row = _call_with_retry(
            lambda symbol=etf["symbol"]: _fetch_sina_quote(symbol),
            f"新浪 ETF 最新行情 {etf['code']}"
        )
        quote_row.update({
            "layer": etf["layer"],
            "configured_name": etf["name"],
            "tracked_index": etf["tracked_index"]
        })
        quotes.append(quote_row)

        history_rows = _call_with_retry(
            lambda symbol=etf["symbol"]: _fetch_sina_kline(symbol, datalen=datalen),
            f"新浪 ETF 日 K 历史行情 {etf['code']}"
        )
        if not history_rows:
            raise RuntimeError(f"新浪没有返回有效 ETF 日 K 数据：{etf['code']}")

        enriched_history = []
        for row in history_rows:
            enriched_row = {
                "code": etf["code"],
                "symbol": etf["symbol"],
                "name": etf["name"],
                "layer": etf["layer"],
                **row
            }
            enriched_history.append(enriched_row)
            combined_history.append(enriched_row)
        histories[etf["code"]] = enriched_history

        history_path = output_dir / f"etf_history_{etf['code']}.csv"
        _records_to_csv(enriched_history, history_path)
        history_files[f"history_{etf['code']}"] = str(history_path)

    quotes_json = output_dir / "etf_latest_quotes.json"
    quotes_csv = output_dir / "etf_latest_quotes.csv"
    combined_history_csv = output_dir / "etf_histories_combined.csv"
    raw_path = output_dir / "raw_bundle.json"

    quotes_json.write_text(json.dumps(quotes, ensure_ascii=False, indent=2), encoding="utf-8")
    _records_to_csv(quotes, quotes_csv)
    _records_to_csv(combined_history, combined_history_csv)

    saved_files = {
        "output_dir": str(output_dir),
        "quotes_json": str(quotes_json),
        "quotes_csv": str(quotes_csv),
        "combined_history": str(combined_history_csv),
        **history_files,
        "raw_bundle": str(raw_path)
    }
    bundle = {
        "question": question,
        "chain_name": chain_name,
        "chain_slug": config["slug"],
        "chain_config": config,
        "fetch_time": fetch_time,
        "data_source": "sina_http",
        "etfs": etfs,
        "quotes": quotes,
        "histories": histories,
        "saved_files": saved_files
    }
    raw_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def _fetch_sina_quote(symbol: str) -> dict[str, Any]:
    url = "https://hq.sinajs.cn/list=" + symbol
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
            "Accept": "*/*"
        }
    )
    with urlopen(request, timeout=15) as response:
        text = response.read().decode("gbk", errors="ignore")

    match = re.search(r'var hq_str_([a-z]{2}\d{6})="(.*?)";', text)
    if not match:
        raise RuntimeError(f"新浪最新行情返回格式异常：{text[:120]}")
    fields = match.group(2).split(",")
    if len(fields) < 32 or not fields[0]:
        raise RuntimeError(f"新浪最新行情字段不足：{fields[:8]}")

    latest = _num(fields[3])
    prev_close = _num(fields[2])
    pct_change = None
    if latest is not None and prev_close not in (None, 0):
        pct_change = round((latest - prev_close) / prev_close * 100, 4)

    return {
        "symbol": symbol,
        "code": symbol[-6:],
        "name": fields[0],
        "latest": latest,
        "pct_change": pct_change,
        "open": _num(fields[1]),
        "prev_close": prev_close,
        "high": _num(fields[4]),
        "low": _num(fields[5]),
        "volume": _num(fields[8]),
        "amount": _num(fields[9]),
        "date": fields[30] if len(fields) > 30 else "",
        "time": fields[31] if len(fields) > 31 else "",
        "_source": "sina_http"
    }


def _fetch_sina_kline(symbol: str, datalen: int = 120) -> list[dict[str, Any]]:
    callback = "var data="
    url = (
        "https://quotes.sina.cn/cn/api/jsonp_v2.php/"
        f"{quote(callback, safe='=')}/CN_MarketDataService.getKLineData"
        f"?symbol={symbol}&scale=240&ma=no&datalen={datalen}"
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
            "Accept": "*/*"
        }
    )
    with urlopen(request, timeout=15) as response:
        text = response.read().decode("utf-8", errors="ignore")

    start = text.find("([")
    end = text.rfind(")")
    if start < 0 or end < 0:
        raise RuntimeError(f"新浪 K 线返回格式异常：{text[:160]}")
    payload = text[start + 1:end]
    rows = ast.literal_eval(payload)
    if not isinstance(rows, list):
        raise RuntimeError("新浪 K 线返回不是列表")

    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        close = _num(row.get("close"))
        if close is None:
            continue
        normalized.append({
            "date": row.get("day", ""),
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": close,
            "volume": _num(row.get("volume")),
            "_source": "sina_http"
        })
    return normalized


def _call_with_retry(fn: Any, label: str, attempts: int = 3, wait_seconds: float = 1.5) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                time.sleep(wait_seconds * attempt)
    raise RuntimeError(f"{label}抓取失败，已重试 {attempts} 次：{last_exc}") from last_exc


def _records_to_csv(records: list[dict[str, Any]], path: Path) -> None:
    if not records:
        path.write_text("", encoding="utf-8")
        return
    columns = list(records[0].keys())
    for row in records[1:]:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


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
