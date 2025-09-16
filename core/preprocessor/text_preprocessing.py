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

def looks_like_xml(text: str) -> bool:
    try:
        ET.fromstring(text)
        return True
    except ET.ParseError:
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

def _etree_to_dict(t: ET.Element) -> Dict[str, Any]:
    d = {t.tag: {} if t.attrib else None}
    children = list(t)
    if children:
        dd: Dict[str, Any] = {}
        for dc in map(_etree_to_dict, children):
            for k, v in dc.items():
                if k in dd:
                    if not isinstance(dd[k], list):
                        dd[k] = [dd[k]]
                    dd[k].append(v)
                else:
                    dd[k] = v
        d = {t.tag: dd}
    if t.attrib:
        d[t.tag].update(('@' + k, v) for k, v in t.attrib.items())
    if t.text:
        tx = t.text.strip()
        if children or t.attrib:
            if tx:
                d[t.tag]['#text'] = tx
        else:
            d[t.tag] = tx
    return d

def parse_xml_text_to_dict(text: str) -> Dict[str, Any]:
    root = ET.fromstring(text)
    return _etree_to_dict(root)

def _is_xmlish_line(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("<") and not looks_like_json(line)

def _is_csvish_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if looks_like_json(s) or _is_xmlish_line(s):
        return False
    return ("," in s) or ("\t" in s)

def _split_mixed_block(block: str) -> List[Tuple[str, str]]:
    segments: List[Tuple[str, str]] = []
    csv_buf: List[str] = []
    xml_buf: List[str] = []

    def flush_csv():
        nonlocal csv_buf
        if csv_buf:
            segments.append(("csv", "\n".join(csv_buf)))
            csv_buf = []

    def flush_xml():
        nonlocal xml_buf
        if xml_buf:
            segments.append(("xml", "\n".join(xml_buf)))
            xml_buf = []

    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_csv()
            flush_xml()
            continue

        if looks_like_json(line):
            flush_csv()
            flush_xml()
            segments.append(("json", line))
            continue

        if _is_xmlish_line(line):
            flush_csv()
            xml_buf.append(line)
            continue

        if _is_csvish_line(line):
            flush_xml()
            csv_buf.append(line)
            continue

        flush_csv()
        flush_xml()
        if looks_like_xml(line):
            segments.append(("xml", line))
        elif _is_csvish_line(line):
            segments.append(("csv", line))
        elif looks_like_json(line):
            segments.append(("json", line))
        else:
            segments.append(("other", line))

    flush_csv()
    flush_xml()
    return segments