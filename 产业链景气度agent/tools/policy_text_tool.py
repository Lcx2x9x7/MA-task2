from __future__ import annotations

from pathlib import Path
from typing import Any


POLICY_DIR = Path("data") / "新能源汽车产业链"


def load_policy_texts(policy_dir: str | Path = POLICY_DIR, max_chars_per_doc: int = 6000) -> dict[str, Any]:
    policy_dir = Path(policy_dir)
    documents = []
    if not policy_dir.exists():
        return {
            "policy_dir": str(policy_dir),
            "documents": [],
            "error": f"政策文本目录不存在：{policy_dir}"
        }

    for path in sorted(policy_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        metadata, body = _split_metadata(text)
        documents.append({
            "file_name": path.name,
            "path": str(path),
            "title": metadata.get("标题") or path.stem,
            "source": metadata.get("来源", ""),
            "date": metadata.get("日期", ""),
            "url": metadata.get("URL", ""),
            "chains": metadata.get("产业链", ""),
            "text": body[:max_chars_per_doc],
            "char_count": len(text)
        })

    return {
        "policy_dir": str(policy_dir),
        "documents": documents,
        "document_count": len(documents)
    }


def _split_metadata(text: str) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    lines = text.splitlines()
    body_start = 0
    for index, line in enumerate(lines[:12]):
        stripped = line.strip()
        if stripped.startswith("="):
            body_start = index + 1
            break
        if "：" in stripped:
            key, value = stripped.split("：", 1)
            metadata[key.strip()] = value.strip()
    body = "\n".join(lines[body_start:]).strip()
    return metadata, body
