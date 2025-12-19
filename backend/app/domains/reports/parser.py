import re
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

def _strip(s: Optional[str]) -> str:
    return (s or "").strip()

_TS_PATTERNS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d %H:%M:%S",
]

def try_parse_timestamp(ts: str) -> Tuple[Optional[str], Optional[str]]:
    raw = _strip(ts)
    if not raw:
        return None, None
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

NUMBERED_HEADER_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$", re.IGNORECASE)
ATX_HEADER_RE = re.compile(r"^\s*#{1,6}\s*(.+?)\s*#*\s*$")

def _is_setext_underline(ln: str) -> bool:
    s = ln.strip()
    if "|" in s:
        return False
    if len(s) < 3:
        return False
    return set(s) <= set("=-") and any(ch in s for ch in "=-")

def _norm_title(title: str) -> str:
    t = title.strip()
    t = re.sub(r"[*_`]", "", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    t = t.rstrip(":").strip()
    return t

SECTION_ALIASES: Dict[str, str] = {
    "executive summary": "executive summary",

    "timeline": "timeline",
    "timeline / progression": "timeline",
    "progression": "timeline",

    "mitre att&ck": "mitre att&ck mapping",
    "mitre attack": "mitre att&ck mapping",
    "mitre att&ck mapping": "mitre att&ck mapping",
    "mitre attack mapping": "mitre att&ck mapping",

    "attack details": "attack details",
    "details": "attack details",

    "iocs & evidence": "iocs & evidence",
    "iocs and evidence": "iocs & evidence",
    "iocs": "iocs & evidence",

    "additional evidence required": "additional evidence required",
    "additional evidence": "additional evidence required",
}

KNOWN_SECTION_PREFIXES = set(SECTION_ALIASES.keys())

def _canonical_section_key(title: str) -> Optional[str]:
    n = _norm_title(title)
    if n in SECTION_ALIASES:
        return SECTION_ALIASES[n]
    for pfx in KNOWN_SECTION_PREFIXES:
        if n.startswith(pfx):
            return SECTION_ALIASES[pfx]
    return None

def _detect_section_header(lines: List[str], i: int) -> Tuple[Optional[str], int]:
    ln = lines[i]

    if "|" in ln and ln.strip().startswith("|"):
        return None, 1

    m = NUMBERED_HEADER_RE.match(ln)
    if m:
        title = m.group(2).strip()
        if _canonical_section_key(title):
            return title, 1
        return None, 1

    m = ATX_HEADER_RE.match(ln)
    if m:
        title = m.group(1).strip()
        if _canonical_section_key(title):
            return title, 1
        return None, 1

    if i + 1 < len(lines) and _is_setext_underline(lines[i + 1]):
        title = ln.strip()
        if _canonical_section_key(title):
            return title, 2
        return None, 2

    title = ln.strip()
    if _canonical_section_key(title):
        return title, 1

    return None, 1


def split_sections(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    lines = text.splitlines()

    header_line = ""
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.strip():
            header_line = ln.strip()
            body_start = i + 1
            if body_start < len(lines) and _is_setext_underline(lines[body_start]):
                body_start += 1
            break

    sections: List[Tuple[str, str]] = []
    current_title: Optional[str] = None
    current_buf: List[str] = []

    i = body_start
    while i < len(lines):
        title, consumed = _detect_section_header(lines, i)
        if title:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_buf).strip()))
            current_title = title
            current_buf = []
            i += consumed
            if i < len(lines) and _is_setext_underline(lines[i]):
                i += 1
            continue

        current_buf.append(lines[i])
        i += 1

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
            v = s.lstrip("•-—– ").strip()
        else:
            v = s

        v = re.sub(r"^\*\*(.+?)\*\*$", r"\1", v).strip()
        bullets.append(v)
    return bullets

TIMELINE_LINE_RE = re.compile(r"^\s*([^|]+?)\s*\|\s*(.+?)\s*$")

def parse_timeline(block: str) -> List[Dict[str, Any]]:
    rows = parse_markdown_table(block)
    if not rows:
        return []

    items: List[Dict[str, Any]] = []
    for r in rows:
        ts_raw = (
            r.get("Timestamp (KST)")
            or r.get("Time (KST)")
            or r.get("Timestamp")
            or r.get("Time")
            or ""
        ).strip()

        desc = (r.get("Description") or r.get("Event") or r.get("Details") or "").strip()
        src  = (r.get("Source") or r.get("Evidence") or "").strip() or None

        iso, err = try_parse_timestamp(ts_raw)

        items.append({
            "timestamp_raw": ts_raw,
            "timestamp_iso": iso,
            "timestamp_error": err,
            "description": desc,
            "source": src,
            "_row": r,
        })
    return items

def parse_attack_details(block: str) -> Dict[str, Any]:
    details: Dict[str, Any] = {"items": [], "raw_excerpts": [], "raw": block.strip()}
    for ln in block.splitlines():
        s = ln.rstrip()
        if not s:
            continue
        if s.lstrip().startswith("- "):
            details["items"].append(s.lstrip("- ").strip())
        elif s.lstrip().startswith(">"):
            details["raw_excerpts"].append(s.lstrip("> ").strip())
    return details

def parse_mitre(block: str) -> List[Dict[str, Any]]:
    rows = parse_markdown_table(block)
    out: List[Dict[str, Any]] = []

    for r in rows:
        tactic = (r.get("Tactic") or r.get("Tactics") or "").strip()
        technique_id = (r.get("Technique ID") or r.get("Modern ID") or r.get("ID") or "").strip()
        technique_name = (r.get("Technique Name") or r.get("Technique") or "").strip()
        relevance = (r.get("Relevance") or r.get("Observed Behavior") or r.get("Observed") or "").strip()

        entry = {
            "tactic": tactic,
            "technique_id": technique_id,
            "technique_name": technique_name,
            "relevance": relevance,
            "_row": r,
        }
        if any([tactic, technique_id, technique_name, relevance]):
            out.append(entry)

    return out

def parse_iocs(block: str) -> List[Dict[str, Any]]:
    rows = parse_markdown_table(block)
    out: List[Dict[str, Any]] = []

    for r in rows:
        ts_raw = (
            r.get("Timestamp (KST)")
            or r.get("Time (KST)")
            or r.get("Timestamp")
            or r.get("Time")
            or ""
        ).strip()
        iso, err = try_parse_timestamp(ts_raw)

        raw_snip = (r.get("Raw Snippet") or r.get("Context") or r.get("Notes") or "").strip()

        out.append({
            "indicator": (r.get("IOC") or r.get("Indicator") or "").strip(),
            "type": (r.get("Type") or "").strip(),
            "source": (r.get("Source") or "").strip(),
            "timestamp_raw": ts_raw,
            "timestamp_iso": iso,
            "timestamp_error": err,
            "raw_snippet": raw_snip,
            "context": raw_snip,
            "_row": r,
        })
    return out

def parse_additional_evidence(block: str) -> List[str]:
    items: List[str] = []
    for ln in block.splitlines():
        s = ln.strip()
        if not s:
            continue
        # bullet / number list 모두 흡수
        s = re.sub(r"^\s*(?:[-•–—]\s+|\d+\.\s+)", "", s).strip()
        if s and s not in ("---", "—"):
            items.append(s)
    return items


SECTION_DISPATCH = {
    "executive summary": parse_exec_summary,
    "timeline": parse_timeline,
    "mitre att&ck mapping": parse_mitre,
    "attack details": parse_attack_details,
    "iocs & evidence": parse_iocs,
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
        canon = _canonical_section_key(title)
        key_norm = canon or _norm_title(title)

        handler = SECTION_DISPATCH.get(key_norm)
        if handler:
            try:
                parsed[key_norm] = handler(body)
            except Exception as e:
                parsed[key_norm] = {"_parse_error": str(e), "raw": body}
        else:
            parsed[key_norm] = {"raw": body}

    return ParseResult(header=header_line, sections=parsed)

if __name__ == "__main__":
    import argparse, sys, json

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
    payload = {"header": result.header, "sections": result.sections}
    js = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(js)
    else:
        print(js)