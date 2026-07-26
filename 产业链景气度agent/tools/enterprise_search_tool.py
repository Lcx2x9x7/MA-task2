from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

from tools.xlsx_stream import iter_xlsx_dicts


DATA_DIR = Path("data")
CHAIN_FILE = DATA_DIR / "产业链.xlsx"
SETTLEMENT_FILES = [
    DATA_DIR / "结算链1.xlsx",
    DATA_DIR / "结算链2.xlsx"
]
CACHE_DIR = Path("outputs/cache/enterprise_uid")


UID_PATTERN = re.compile(r"[0-9a-fA-F]{24,}\d{8,}")


def search_enterprise_by_question(
    question: str,
    max_chain_rows: int = 500,
    max_settlement_rows: int = 500,
    use_cache: bool = True,
    refresh_cache: bool = False
) -> dict[str, Any]:
    uid = extract_uid(question)
    if not uid:
        raise ValueError("问题中没有识别到客户 UID。请在 question 中包含完整客户UID。")
    return search_enterprise_by_uid(
        uid,
        max_chain_rows=max_chain_rows,
        max_settlement_rows=max_settlement_rows,
        use_cache=use_cache,
        refresh_cache=refresh_cache
    )


def search_enterprise_by_uid(
    uid: str,
    max_chain_rows: int = 500,
    max_settlement_rows: int = 500,
    use_cache: bool = True,
    refresh_cache: bool = False
) -> dict[str, Any]:
    cache_path = _cache_path(uid)
    if use_cache and not refresh_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["cache"] = {
            "hit": True,
            "path": str(cache_path)
        }
        return cached

    chain_rows = _search_chain_rows(uid, max_rows=max_chain_rows)
    settlement_rows = _search_settlement_rows(uid, max_rows=max_settlement_rows)
    bundle = {
        "uid": uid,
        "chain_rows": chain_rows,
        "settlement_rows": settlement_rows,
        "data_files": {
            "chain": str(CHAIN_FILE),
            "settlement": [str(path) for path in SETTLEMENT_FILES]
        },
        "cache": {
            "hit": False,
            "path": str(cache_path)
        }
    }
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def extract_uid(question: str) -> str | None:
    match = UID_PATTERN.search(question)
    return match.group(0) if match else None


def _search_chain_rows(uid: str, max_rows: int) -> list[dict[str, str]]:
    rows = []
    for row in iter_xlsx_dicts(CHAIN_FILE):
        if row.get("客户UID") == uid:
            rows.append(row)
            if len(rows) >= max_rows:
                break
    return rows


def _search_settlement_rows(uid: str, max_rows: int) -> list[dict[str, str]]:
    rows = []
    for path in SETTLEMENT_FILES:
        for row in iter_xlsx_dicts(path):
            if row.get("客户UID") == uid or row.get("交易对手客户UID") == uid:
                row = dict(row)
                row["_source_file"] = str(path)
                row["_uid_role"] = "本方客户" if row.get("客户UID") == uid else "交易对手"
                rows.append(row)
                if len(rows) >= max_rows:
                    return rows
    return rows


def _cache_path(uid: str) -> Path:
    safe_uid = re.sub(r"[^0-9a-zA-Z_-]", "_", uid)
    return CACHE_DIR / f"{safe_uid}.json"
