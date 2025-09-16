from pathlib import Path
from typing import List, Optional, Tuple
from file_preprocessing import BASE_DIR, convert_files_to_json, DATA_DIR, SUPPORTED_EXTS

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