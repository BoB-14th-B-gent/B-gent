import json
import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Iterable
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SUPPORTED_EXTS = {".json", ".jsonl", ".xml", ".csv"}

ROWS_PER_CHUNK_CSV = 50_000
ROWS_PER_CHUNK_JSONL = 50_000
ROWS_PER_CHUNK_XML = 20_000
MAX_BYTES_PER_CHUNK_JSON = 5 * 1024 * 1024  # 5MB

def _write_json_array_chunk(out_path: Path, rows: Iterable[dict]) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("[\n")
        first = True
        for row in rows:
            if not first:
                f.write(",\n")
            f.write(json.dumps(row, ensure_ascii=False))
            first = False
        f.write("\n]\n")
    return str(out_path)

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

def xml_to_json(xml_file: str, out_dir: str, record_tag: Optional[str] = None) -> List[str]:
    src = Path(xml_file)
    out_root = Path(out_dir)
    out_paths: List[str] = []

    # (선택) record_tag 추정
    guess = record_tag
    if guess is None:
        try:
            counts = {}
            for ev, el in ET.iterparse(str(src), events=("start",)):
                if list(el):
                    counts[el.tag] = counts.get(el.tag, 0) + 1
                if sum(counts.values()) > 30_000:
                    break
            if counts:
                guess = max(counts, key=counts.get)
        except Exception:
            guess = None

    def _elem_to_obj(e: ET.Element) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if e.attrib:
            d.update(e.attrib)
        text = (e.text or "").strip()
        if text:
            d["_text"] = text
        for child in e:
            obj = _elem_to_obj(child)
            d.setdefault(child.tag, [])
            d[child.tag].append(obj)
        return d

    batch: List[dict] = []
    part = 0
    for ev, el in ET.iterparse(str(src), events=("end",)):
        if guess and el.tag != guess:
            continue
        if not list(el) and not el.attrib and not (el.text or "").strip():
            el.clear()
            continue
        batch.append(_elem_to_obj(el))
        el.clear()
        if len(batch) >= ROWS_PER_CHUNK_XML:
            part += 1
            out_path = out_root / f"{src.stem}.part{part:04d}.json"
            out_paths.append(_write_json_array_chunk(out_path, batch))
            batch.clear()

    if batch:
        part += 1
        out_path = out_root / f"{src.stem}.part{part:04d}.json"
        out_paths.append(_write_json_array_chunk(out_path, batch))

    return out_paths

def jsonl_to_json(jsonl_file: str, out_dir: str) -> List[str]:
    src = Path(jsonl_file)
    out_root = Path(out_dir)
    out_paths: List[str] = []

    batch: List[dict] = []
    part = 0
    with src.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                batch.append(json.loads(s))
            except Exception:
                batch.append({"_raw": s})
            if len(batch) >= ROWS_PER_CHUNK_JSONL:
                part += 1
                out_path = out_root / f"{src.stem}.part{part:04d}.json"
                out_paths.append(_write_json_array_chunk(out_path, batch))
                batch.clear()

    if batch:
        part += 1
        out_path = out_root / f"{src.stem}.part{part:04d}.json"
        out_paths.append(_write_json_array_chunk(out_path, batch))

    return out_paths

def csv_to_json(csv_file: str, out_dir: str) -> List[str]:
    src = Path(csv_file)
    out_root = Path(out_dir)
    out_paths: List[str] = []

    with src.open("r", encoding="utf-8", newline="") as f:
        sample = f.read(65536)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        except Exception:
            class _D: ...
            dialect = _D(); dialect.delimiter=","; dialect.quotechar='"'
        try:
            has_header = csv.Sniffer().has_header(sample)
        except Exception:
            has_header = True

        reader = csv.reader(f, delimiter=dialect.delimiter, quotechar=getattr(dialect, "quotechar", '"'))
        first_row = next(reader, None)
        if first_row is None:
            return out_paths

        if has_header:
            headers = first_row
            iter_rows = reader
        else:
            headers = [f"col_{i}" for i in range(len(first_row))]
            iter_rows = iter([first_row] + list(reader))

        batch: List[dict] = []
        part = 0
        for row in iter_rows:
            doc = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
            batch.append(doc)
            if len(batch) >= ROWS_PER_CHUNK_CSV:
                part += 1
                out_path = out_root / f"{src.stem}.part{part:04d}.json"
                out_paths.append(_write_json_array_chunk(out_path, batch))
                batch.clear()

        if batch:
            part += 1
            out_path = out_root / f"{src.stem}.part{part:04d}.json"
            out_paths.append(_write_json_array_chunk(out_path, batch))

    return out_paths

def _json_to_json_chunks(json_file: str, out_dir: str) -> List[str]:
    src = Path(json_file)
    out_root = Path(out_dir)
    out_paths: List[str] = []
    text = src.read_text(encoding="utf-8", errors="ignore").strip()

    if text.startswith("{"):
        obj = json.loads(text)
        out_path = out_root / f"{src.stem}.part0001.json"
        _write_json_array_chunk(out_path, [obj])
        return [str(out_path)]

    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]

    buf: List[dict] = []
    cur_bytes = 0
    part = 0
    depth = 0
    in_str = False
    esc = False
    obj_buf: List[str] = []

    for ch in text:
        if in_str:
            obj_buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True; obj_buf.append(ch)
        elif ch == "{":
            depth += 1; obj_buf.append(ch)
        elif ch == "}":
            depth -= 1; obj_buf.append(ch)
            if depth == 0:
                try:
                    obj = json.loads("".join(obj_buf))
                except Exception:
                    obj = {"_raw": "".join(obj_buf)}
                s = json.dumps(obj, ensure_ascii=False)
                if cur_bytes + len(s) > MAX_BYTES_PER_CHUNK_JSON and buf:
                    part += 1
                    out_path = out_root / f"{src.stem}.part{part:04d}.json"
                    out_paths.append(_write_json_array_chunk(out_path, buf))
                    buf, cur_bytes = [], 0
                buf.append(obj)
                cur_bytes += len(s)
                obj_buf = []
        else:
            if depth > 0 or ch not in " \n\r\t,":
                obj_buf.append(ch)

    if buf:
        part += 1
        out_path = out_root / f"{src.stem}.part{part:04d}.json"
        out_paths.append(_write_json_array_chunk(out_path, buf))

    return out_paths

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

        try:
            if ext == ".json":
                out_paths += _json_to_json_chunks(str(p), out_dir)
            elif ext == ".jsonl":
                out_paths += jsonl_to_json(str(p), out_dir)
            elif ext == ".xml":
                out_paths += xml_to_json(str(p), out_dir)
            elif ext == ".csv":
                out_paths += csv_to_json(str(p), out_dir)
        except Exception as e:
            msg = f"{name} → 변환 실패 ({e})"
            if failed_list is not None:
                failed_list.append(msg)
            print(f"[WARN] 파일 변환 실패: {p} -> {e}\n")

    return out_paths