import json
import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parents[5]
DATA_DIR = BASE_DIR / "data"
SUPPORTED_EXTS = {".json", ".jsonl", ".xml", ".csv"}

def resolve_data_path(filename: str) -> Path:
    p = DATA_DIR / filename
    if not p.exists():
        raise FileNotFoundError(f"data 폴더에서 {filename} 을 찾을 수 없습니다: {p}")
    return p

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

def xml_to_json(xml_file: str, json_file: str) -> None:
    tree = ET.parse(xml_file)
    root = tree.getroot()
    data_dict = _etree_to_dict(root)
    Path(json_file).write_text(json.dumps(data_dict, ensure_ascii=False, indent=2), encoding="utf-8")

def jsonl_to_json(jsonl_file: str, json_file: str) -> None:
    decoder = json.JSONDecoder()
    out = []
    bad_lines = 0

    with open(jsonl_file, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue

            i, n = 0, len(s)
            parsed_any = False

            while i < n:
                while i < n and (s[i].isspace() or s[i] in ",;"):
                    i += 1
                if i >= n:
                    break

                try:
                    obj, end = decoder.raw_decode(s, i)
                    out.append(obj)
                    parsed_any = True
                    i = end
                except json.JSONDecodeError:
                    i += 1

            if not parsed_any:
                bad_lines += 1

    Path(json_file).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

def csv_to_json(csv_file: str, json_file: str) -> None:
    text = Path(csv_file).read_text(encoding="utf-8", errors="ignore")
    rows = parse_csv_text(text)
    Path(json_file).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

def convert_files_to_json(
    file_names: List[str],
    out_dir: str,
    failed_list: Optional[List[str]] = None
) -> List[str]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_paths: List[str] = []

    for name in file_names:
        try:
            p = resolve_data_path(name)
        except FileNotFoundError as e:
            msg = f"{name} → 파일 없음 ({e})"
            if failed_list is not None:
                failed_list.append(msg)
            print(f"[WARN] {msg}\n")
            continue

        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            msg = f"{name} → 지원하지 않는 확장자"
            if failed_list is not None:
                failed_list.append(msg)
            print(f"[WARN] {msg}\n")
            continue

        out_path = Path(out_dir) / f"{p.stem}.json"
        try:
            if ext == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            elif ext == ".jsonl":
                jsonl_to_json(str(p), str(out_path))
            elif ext == ".xml":
                xml_to_json(str(p), str(out_path))
            elif ext == ".csv":
                csv_to_json(str(p), str(out_path))
            out_paths.append(str(out_path))
        except Exception as e:
            msg = f"{name} → 변환 실패 ({e})"
            if failed_list is not None:
                failed_list.append(msg)
            print(f"[WARN] 파일 변환 실패: {p} -> {e}\n")

    return out_paths