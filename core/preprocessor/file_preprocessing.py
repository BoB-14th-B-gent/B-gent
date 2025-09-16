from pathlib import Path
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SUPPORTED_EXTS = {".json", ".jsonl", ".xml", ".csv"}

def resolve_data_path(filename: str) -> Path:
    p = DATA_DIR / filename
    if not p.exists():
        raise FileNotFoundError(f"data 폴더에서 {filename} 을 찾을 수 없습니다: {p}")
    return p
