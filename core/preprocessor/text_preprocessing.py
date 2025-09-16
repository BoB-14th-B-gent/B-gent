import json
import csv
import io
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
from pathlib import Path

def looks_like_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False

def sniff_csv_dialect_and_header(sample_text: str) -> Tuple[Optional[csv.Dialect], bool]:
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample_text, delimiters=",\t")
        if getattr(dialect, "delimiter", None) not in [",", "\t"]:
            return None, False
        try:
            has_header = sniffer.has_header(sample_text)
        except Exception:
            has_header = False
        return dialect, has_header
    except Exception:
        return None, False

def parse_csv_text(text: str) -> List[Dict[str, Any]]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    sample = "\n".join(lines[:40])
    dialect, has_header = sniff_csv_dialect_and_header(sample)
    if dialect is None:
        raise ValueError("CSV 구분자는 tab 또는 ,만 지원")

    buf = io.StringIO("\n".join(lines))
    reader = csv.reader(buf, dialect=dialect)
    rows = list(reader)
    if not rows:
        return []

    if len(rows) > 1 and len(rows[0]) != len(rows[1]):
        headers = rows[0]
        data_rows = rows[1:]
        return [
            {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
            for row in data_rows
        ]

    if has_header:
        buf2 = io.StringIO("\n".join(lines))
        dict_reader = csv.DictReader(buf2, dialect=dialect)
        return [dict(row) for row in dict_reader]

    max_cols = max(len(r) for r in rows)
    headers = [f"c{i}" for i in range(max_cols)]
    return [{headers[i]: (r[i] if i < len(r) else None) for i in range(max_cols)} for r in rows]

def _is_csvish_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    return ("," in s) or ("\t" in s)