import argparse
import json
from pathlib import Path
from typing import List, Optional, Tuple

from .file_preprocessing import BASE_DIR, convert_files_to_json, DATA_DIR, SUPPORTED_EXTS
from .text_preprocessing import inline_to_grouped_json, write_inline_group_to_file
from infra.db import upload_file

SUPPORTED_INPUT_EXTS = {".json", ".jsonl", ".xml", ".csv"}

def is_supported_file_name(s: str) -> bool:
    p = Path(s.strip().strip('\'"'))
    return p.suffix.lower() in SUPPORTED_INPUT_EXTS

def _exists_in_data_or_abs(name: str) -> bool:
    p = Path(name.strip().strip('\'"'))
    if p.is_absolute():
        return p.exists()
    return (DATA_DIR / p).exists()

def list_data_files() -> List[str]:
    files: List[str] = []
    for p in sorted(DATA_DIR.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            files.append(str(p.relative_to(DATA_DIR)))
    return files

def read_input_blocks(input_txt: Optional[str]) -> List[str]:
    if not input_txt:
        return []
    p = Path(input_txt)
    if not p.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {p}")

    raw = p.read_text(encoding="utf-8")
    blocks: List[str] = []
    cur: List[str] = []
    for line in raw.splitlines():
        if line.strip() == "":
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    return blocks

def gather_inputs(input_txt: Optional[str], all_data: bool) -> Tuple[List[str], List[str]]:
    blocks = read_input_blocks(input_txt)

    file_names: List[str] = []
    inline_blocks: List[str] = []

    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue

        file_like = [ln for ln in lines if is_supported_file_name(ln)]
        non_file  = [ln for ln in lines if ln not in file_like]

        if file_like:
            file_names.extend(file_like)
        if non_file:
            inline_blocks.append("\n".join(non_file))

    if all_data:
        for name in list_data_files():
            if name not in file_names:
                file_names.append(name)

    file_names = sorted(set(file_names))
    return file_names, inline_blocks

def collect_unsupported_existing_files_from_input(input_txt: Optional[str]) -> List[str]:
    if not input_txt:
        return []
    p = Path(input_txt)
    if not p.exists():
        return []

    raw = p.read_text(encoding="utf-8")
    candidates: List[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        ext = Path(s).suffix.lower()
        if not ext:
            continue
        if ext not in SUPPORTED_INPUT_EXTS:
            if _exists_in_data_or_abs(s):
                candidates.append(s)
    return sorted(set(candidates))

def list_unsupported_existing_files_in_data() -> List[str]:
    out: List[str] = []
    for p in sorted(DATA_DIR.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if (not ext) or (ext not in SUPPORTED_EXTS):
            if p.name in {".gitkeep"}:
                continue
            out.append(str(p.relative_to(DATA_DIR)))
    return out

def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Preprocess files (in data/) & inline texts, then upload to MongoDB.")
    ap.add_argument("--input", "-i", help="input.txt 경로", default=None)
    ap.add_argument("--all-data", action="store_true", help="data/ 폴더의 모든 지원 파일 자동 인식 (또한 to_agents에 data 내 비지원 확장자도 포함)")
    ap.add_argument("--out", "-o", help="출력 JSON 디렉토리", default=str((BASE_DIR / "out_json")))
    ap.add_argument("--inline-filename", default="inline_batch.json", help="인라인 묶음 JSON 파일명")
    ap.add_argument("--collection", required=True, help="MongoDB 컬렉션명")
    ap.add_argument("--mode", choices=["auto","inline","gridfs"], default="auto", help="저장 전략")
    ap.add_argument("--inline-threshold", type=int, default=10*1024*1024, help="인라인 임계치(바이트)")
    return ap

if __name__ == "__main__":
    args = build_argparser().parse_args()

    file_names, inline_blocks = gather_inputs(args.input, args.all_data)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_paths: List[str] = []

    if file_names:
        out_paths += convert_files_to_json(file_names, out_dir=str(out_dir))

    if inline_blocks:
        grouped = inline_to_grouped_json(inline_blocks)
        inline_out_path = str(out_dir / args.inline_filename)
        out_paths.append(write_inline_group_to_file(grouped, inline_out_path))

    print("생성된 JSON 파일들")
    for p in out_paths:
        print(" -", p)

    input_raw = ""
    if args.input:
        ip = Path(args.input)
        if ip.exists():
            input_raw = ip.read_text(encoding="utf-8")

    unsupported_from_input = collect_unsupported_existing_files_from_input(args.input)

    files_for_agents = set(unsupported_from_input)
    if args.all_data:
        files_for_agents.update(list_unsupported_existing_files_in_data())

    to_agents_json_path = (BASE_DIR / "to_agents.json").resolve()
    with open(to_agents_json_path, "w", encoding="utf-8") as f:
        json.dump({"files": sorted(files_for_agents), "input": input_raw}, f, ensure_ascii=False, indent=2)
    print(f"\nto_agents.json 생성: {to_agents_json_path}")

    print("\nMongoDB 업로드 중...")
    results = []
    for p in out_paths:
        res = upload_file(
            file_path=p,
            collection=args.collection,
            detected_type="json",
            mode=args.mode,
            inline_threshold_bytes=args.inline_threshold,
        )
        results.append({"file": p, **res})

    print("\n업로드 결과 요약:")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))