import re
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

def _strip(s: Optional[str]) -> str:
    return (s or "").strip()

_TS_PATTERNS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y.%m.%d %H:%M",
]

def try_parse_timestamp(ts: str) -> Tuple[Optional[str], Optional[str]]:
    raw = _strip(ts)
    for pat in _TS_PATTERNS:
        try:
            dt = datetime.strptime(raw, pat)
            return dt.isoformat(), None
        except Exception:
            pass
    return None, f"unparsed timestamp: {raw}"


def parse_markdown_table(block: str) -> List[Dict[str, str]]:
    lines = [ln for ln in block.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    header_idx = 0

    while header_idx < len(lines) and "|" not in lines[header_idx]:
        header_idx += 1
    if header_idx >= len(lines):
        return []

    header_line = lines[header_idx]

    sep_idx = header_idx + 1
    while sep_idx < len(lines) and not set(lines[sep_idx].replace(" ", "")) <= set("|-:"):
        sep_idx += 1
    if sep_idx >= len(lines):
        return []

    headers = [h.strip() for h in header_line.strip().strip("|").split("|")]

    rows: List[Dict[str, str]] = []
    for ln in lines[sep_idx + 1 :]:
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]

        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        if len(cells) > len(headers):
            cells = cells[: len(headers)]
        row = {headers[i]: cells[i] for i in range(len(headers))}

        if any(v for v in row.values()):
            rows.append(row)
    return rows

SECTION_HEADER_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$", re.IGNORECASE)


def split_sections(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    lines = text.splitlines()

    header_line = ""
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.strip():
            header_line = ln.strip()
            body_start = i + 1
            break

    sections: List[Tuple[str, str]] = []
    current_title = None
    current_buf: List[str] = []

    for ln in lines[body_start:]:
        m = SECTION_HEADER_RE.match(ln)
        if m:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_buf).strip()))
            current_title = m.group(2).strip().rstrip("- ")
            current_buf = []
        else:
            current_buf.append(ln)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_buf).strip()))

    return header_line, sections

def parse_exec_summary(block: str) -> List[str]:
    bullets: List[str] = []
    for ln in block.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("- ", "•", "– ", "— ")):
            bullets.append(s.lstrip("•-—– ").strip())
        else:
            bullets.append(s)
    return bullets

TIMELINE_LINE_RE = re.compile(r"^\s*([^|]+?)\s*\|\s*(.+?)\s*$")

def parse_timeline(block: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for ln in block.splitlines():
        s = ln.strip()
        if not s:
            continue
        m = TIMELINE_LINE_RE.match(s)
        if not m:
            continue
        ts_raw, rest = m.group(1).strip(), m.group(2).strip()
        iso, err = try_parse_timestamp(ts_raw)

        src = None
        desc = rest

        paren = re.search(r"\(([^()]+)\)\s*$", rest)
        if paren:
            src = paren.group(1).strip()
            desc = rest[: paren.start()].strip().rstrip("-:")

        items.append({
            "timestamp_raw": ts_raw,
            "timestamp_iso": iso,
            "timestamp_error": err,
            "description": desc,
            "source": src,
        })
    return items

def parse_attack_details(block: str) -> Dict[str, Any]:
    details: Dict[str, Any] = {"items": [], "raw_excerpts": []}
    for ln in block.splitlines():
        s = ln.rstrip()
        if not s:
            continue
        if s.lstrip().startswith("- "):
            details["items"].append(s.lstrip("- ").strip())
        elif s.lstrip().startswith(">"):
            details["raw_excerpts"].append(s.lstrip("> ").strip())
    return details

def parse_mitre(block: str) -> List[Dict[str, str]]:
    rows = parse_markdown_table(block)
    normalized: List[Dict[str, str]] = []
    for r in rows:
        entry = {
            "action": r.get("Action", "").strip(),
            "ttp_id": r.get("TTP ID", r.get("TTP", "")).strip(),
            "evidence": r.get("Explanation/Evidence", r.get("Explanation", "")).strip(),
        }
        if any(entry.values()):
            normalized.append(entry)
    return normalized

def parse_iocs(block: str) -> List[Dict[str, Any]]:
    rows = parse_markdown_table(block)
    out: List[Dict[str, Any]] = []
    for r in rows:
        ts_raw = r.get("Timestamp", "").strip()
        iso, err = try_parse_timestamp(ts_raw)
        out.append({
            "indicator": r.get("IOC", "").strip(),
            "type": r.get("Type", "").strip(),
            "timestamp_raw": ts_raw,
            "timestamp_iso": iso,
            "timestamp_error": err,
            "source": r.get("Source", "").strip(),
            "context": r.get("Context", "").strip(),
        })
    return out


def parse_additional_evidence(block: str) -> List[str]:
    items: List[str] = []
    for ln in block.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("- ", "•", "– ", "— ")):
            items.append(s.lstrip("•-—– ").strip())
        else:
            items.append(s)
    return items

SECTION_DISPATCH = {
    "executive summary": parse_exec_summary,
    "timeline": parse_timeline,
    "timeline / progression": parse_timeline,
    "mitre att&ck mapping": parse_mitre,
    "attack details": parse_attack_details,
    "iocs & evidence": parse_iocs,
    "iocs": parse_iocs,
    "additional evidence required": parse_additional_evidence,
}

@dataclass
class ParseResult:
    header: str
    sections: Dict[str, Any]

def parse_incident_report(text: str) -> ParseResult:
    header_line, sections = split_sections(text)

    parsed: Dict[str, Any] = {}
    for title, body in sections:
        key = title.strip().lower()
        key_norm = key
        key_norm = re.sub(r"\s+", " ", key_norm)
        key_norm = key_norm.strip("- ")

        handler = None
        if key_norm in SECTION_DISPATCH:
            handler = SECTION_DISPATCH[key_norm]
        else:
            for k, fn in SECTION_DISPATCH.items():
                if key_norm.startswith(k):
                    handler = fn
                    key_norm = k
                    break

        if handler:
            try:
                parsed[key_norm] = handler(body)
            except Exception as e:
                parsed[key_norm] = {"_parse_error": str(e), "raw": body}
        else:
            parsed[key_norm] = {"raw": body}

    return ParseResult(header=header_line, sections=parsed)

if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="Parse an Incident Analysis Report into structured JSON")
    ap.add_argument("file", nargs="?", help="Path to a .txt/.md file. If omitted, read stdin")
    ap.add_argument("-o", "--output", help="Write JSON to this file (default: stdout)")
    args = ap.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = parse_incident_report(text)
    payload = {
        "header": result.header,
        "sections": result.sections,
    }
    js = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(js)
    else:
        print(js)
