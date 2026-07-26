from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator
from xml.etree.ElementTree import iterparse
from zipfile import ZipFile


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def iter_xlsx_rows(path: str | Path, sheet_xml: str = "xl/worksheets/sheet1.xml") -> Iterator[list[str]]:
    """Stream rows from a simple XLSX sheet without loading the worksheet into memory."""
    path = Path(path)
    with ZipFile(path) as workbook:
        shared_strings = _load_shared_strings(workbook)
        with workbook.open(sheet_xml) as sheet:
            for _, row_elem in iterparse(sheet, events=("end",)):
                if row_elem.tag != NS + "row":
                    continue
                row: list[str] = []
                for cell in row_elem.findall(NS + "c"):
                    index = _column_index(cell.attrib.get("r", ""))
                    if index is not None:
                        while len(row) <= index:
                            row.append("")
                    value = _cell_value(cell, shared_strings)
                    if index is None:
                        row.append(value)
                    else:
                        row[index] = value
                row_elem.clear()
                yield row


def iter_xlsx_dicts(path: str | Path) -> Iterator[dict[str, str]]:
    rows = iter_xlsx_rows(path)
    try:
        header = next(rows)
    except StopIteration:
        return
    header = [str(value).strip() for value in header]
    for row in rows:
        item = {}
        for index, key in enumerate(header):
            if not key:
                continue
            item[key] = row[index] if index < len(row) else ""
        yield item


def _load_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    strings: list[str] = []
    with workbook.open("xl/sharedStrings.xml") as shared:
        for _, elem in iterparse(shared, events=("end",)):
            if elem.tag == NS + "si":
                strings.append("".join(text.text or "" for text in elem.iter(NS + "t")))
                elem.clear()
    return strings


def _cell_value(cell: object, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_elem = cell.find(NS + "v")
    if cell_type == "s" and value_elem is not None:
        index = int(value_elem.text or 0)
        return shared_strings[index] if index < len(shared_strings) else ""
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.iter(NS + "t"))
    if value_elem is not None:
        return value_elem.text or ""
    inline = cell.find(NS + "is")
    if inline is not None:
        return "".join(text.text or "" for text in inline.iter(NS + "t"))
    return ""


def _column_index(cell_ref: str) -> int | None:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return None
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    return value - 1
