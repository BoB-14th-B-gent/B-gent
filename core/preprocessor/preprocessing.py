import argparse
import json
from pathlib import Path
from typing import List, Optional, Tuple

from .file_preprocessing import BASE_DIR, convert_files_to_json, DATA_DIR, SUPPORTED_EXTS
from .text_preprocessing import inline_to_grouped_json, write_inline_group_to_file
from infra.db import preprocessor_upload_file, preprocessor_save_prompt

SUPPORTED_INPUT_EXTS = {".json", ".jsonl", ".xml", ".csv"}

def is_supported_file_name(s: str) -> bool:
    p = Path(s.strip().strip('\'"'))
    return p.suffix.lower() in SUPPORTED_INPUT_EXTS

def _exists_in_data_or_abs(name: str) -> bool:
    s = name.strip().strip('\'"')

    if len(s) > 255:
        return False

    if s.startswith("{") or s.startswith("[") or s.startswith("<") or "\t" in s or "," in s:
        return False

    p = Path(s)
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
            if p.name in {".gitkeep", ".DS_Store"}:
                continue
            out.append(str(p.relative_to(DATA_DIR)))
    return out

def looks_like_structured_data(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if s.startswith("{") or s.startswith("["):
        try:
            json.loads(s)
            return True
        except Exception:
            pass
    if s.startswith("<") and s.endswith(">"):
        return True
    if ("," in s or "\t" in s) and not any(ch in s for ch in "{}<>"):
        return True
    return False


def clean_prompt_text(
    input_txt: Optional[str],
    file_names: List[str],
    inline_blocks: List[str],
    files_for_agents: List[str]
) -> str:
    if not input_txt:
        return ""

    p = Path(input_txt)
    if not p.exists():
        return ""

    raw = p.read_text(encoding="utf-8")
    lines = raw.splitlines()
    cleaned_lines = []

    known_files = set(file_names) | set(files_for_agents)
    known_files_lower = {Path(f).name.lower() for f in known_files}

    for ln in lines:
        s = ln.strip()
        if not s:
            continue

        if Path(s).name.lower() in known_files_lower:
            continue

        if looks_like_structured_data(s):
            continue

        cleaned_lines.append(s)

    return "\n".join(cleaned_lines).strip()

def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Preprocess files (in data/) & inline texts, then upload to MongoDB.")
    ap.add_argument("--input", "-i", help="input.txt 경로", default=None)
    ap.add_argument("--all-data", action="store_true", help="data/ 폴더의 모든 지원 파일 자동 인식 (또한 to_agents에 data 내 비지원 확장자도 포함)")
    ap.add_argument("--out", "-o", help="출력 JSON 디렉토리", default=str((BASE_DIR / "out_json")))
    ap.add_argument("--inline-filename", default="inline_batch.json", help="인라인 묶음 JSON 파일명")
    ap.add_argument("--no-inline-output", action="store_true", help="인라인 텍스트 묶음 파일(inline_batch.json) 생성을 건너뜁니다.")
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

    if inline_blocks and not args.no_inline_output:
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

    clean_prompt = clean_prompt_text(args.input, file_names, inline_blocks, sorted(files_for_agents))

    prompt_id = preprocessor_save_prompt(
        user_prompt=clean_prompt,
        unprocessed_filenames=sorted(files_for_agents),
        inline_text_blobs=[],
        attachments=[],
        context_tags=[],
    )
    print(f"\nPROMPT 저장 완료: _id={prompt_id}")

    cleaned: List[str] = []
    for p in out_paths:
        pp = Path(p)
        if pp.is_file():
            cleaned.append(str(pp))
        else:
            t = "dir" if pp.is_dir() else "other"
            print(f"[WARN] 산출물이 파일이 아님(스킵): {pp} (type={t})")
    out_paths = cleaned

    print("\nMongoDB 업로드 중...")
    results = []
    for p in out_paths:
        try:
            res = preprocessor_upload_file(
                file_path=p,
                detected_type="json",
                mode=args.mode,
                inline_threshold_bytes=args.inline_threshold,
                extra_meta={"prompt_ref": prompt_id},
            )
            results.append({"file": p, **res})
        except Exception as e:
            results.append({"file": p, "error": str(e)})
            print(f"[WARN] 업로드 실패: {p} -> {e}")

    print("\n업로드 결과 요약:")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))