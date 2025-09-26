from typing import Any, Dict, Optional
from pathlib import Path
import time, json, mimetypes, hashlib
from pymongo import MongoClient
from bson.binary import Binary
import gridfs

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "test"

MAX_INLINE_JSON_BYTES = 1 * 1024 * 1024
GRIDFS_SAMPLE_BYTES   = 64 * 1024
BSON_DOC_HARD_LIMIT   = 16 * 1024 * 1024

def get_client() -> MongoClient:
    return MongoClient(MONGO_URI)

def get_db(client: MongoClient):
    return client[DB_NAME]

def get_fs(db) -> gridfs.GridFS:
    return gridfs.GridFS(db)

def _infer_dtype(path: Path, content_type: Optional[str]) -> Optional[str]:
    if content_type:
        if "json" in content_type:
            return "json"
        if "xml" in content_type:
            return "xml"
        if "csv" in content_type:
            return "csv"
    suf = path.suffix.lower()
    if suf == ".json":  return "json"
    if suf == ".xml":   return "xml"
    if suf == ".csv":   return "csv"
    if suf == ".jsonl": return "json"
    return None

def store_file_to_gridfs(fs: gridfs.GridFS, path: str, extra_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    if p.is_dir():
        raise IsADirectoryError(f"{p} is a directory (expected a file)")

    content_type, _ = mimetypes.guess_type(p.name)
    meta = {
        "filename": p.name,
        "content_type": content_type or "application/octet-stream",
        "size": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()[:GRIDFS_SAMPLE_BYTES]).hexdigest(),
        "ingested_at": int(time.time()),
    }
    if extra_meta:
        meta.update(extra_meta)

    with p.open("rb") as f:
        file_id = fs.put(f, filename=p.name, metadata=meta)

    gout = fs.get(file_id)
    return {
        "_id": file_id,
        "filename": gout.filename,
        "length": gout.length,
        "uploadDate": getattr(gout, "upload_date", None),
        "metadata": getattr(gout, "metadata", None),
        "contentType": getattr(gout, "content_type", None),
    }

def insert_file_meta(db, collection: str, meta_doc: Dict[str, Any]) -> str:
    res = db[collection].insert_one(meta_doc)
    return str(res.inserted_id)

def choose_strategy(size_bytes: int, mode: str, inline_threshold_bytes: int) -> str:
    mode = (mode or "").lower()
    if mode in ("inline", "gridfs"):
        return mode
    return "inline" if size_bytes <= inline_threshold_bytes else "gridfs"

def upload_file(
    file_path: str,
    collection: str,
    *,
    detected_type: Optional[str] = None,
    mode: str = "auto",
    inline_threshold_bytes: int = 10 * 1024 * 1024,
) -> Dict[str, Any]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(file_path)
    if p.is_dir():
        raise IsADirectoryError(f"{p} is a directory (expected a file)")

    client = get_client()
    try:
        db = get_db(client)

        size = p.stat().st_size
        content_type, _ = mimetypes.guess_type(p.name)
        dtype = (detected_type or _infer_dtype(p, content_type))

        strategy = choose_strategy(size, mode, inline_threshold_bytes)

        if strategy == "inline" and dtype == "json" and size > MAX_INLINE_JSON_BYTES:
            strategy = "gridfs"

        result: Dict[str, Any] = {"strategy": strategy}

        if strategy == "inline":
            meta_doc: Dict[str, Any] = {
                "source_type": "file_inline",
                "filename": p.name,
                "content_type": content_type or "application/octet-stream",
                "size": size,
                "detected_type": dtype,
                "ingested_at": int(time.time()),
                "stats": {},
            }
            try:
                if dtype == "json":
                    txt = p.read_text(encoding="utf-8", errors="strict")
                    meta_doc["data"] = json.loads(txt)
                else:
                    raw = p.read_bytes()
                    if len(raw) >= BSON_DOC_HARD_LIMIT - 1024:
                        raise ValueError("inline BSON size would exceed limit; use gridfs")
                    meta_doc["raw"] = Binary(raw)
            except Exception as e:
                meta_doc["stats"]["parse_error"] = str(e)
                raw = p.read_bytes()
                if len(raw) >= BSON_DOC_HARD_LIMIT - 1024:
                    # 그래도 너무 크면 gridfs로 전환
                    strategy = "gridfs"
                else:
                    meta_doc["raw"] = Binary(raw)

            if strategy == "inline":
                result["meta_id"] = insert_file_meta(db, collection, meta_doc)
                return result

        fs = get_fs(db)
        files_doc = store_file_to_gridfs(fs, str(p), extra_meta={"detected_type": dtype})

        sample: Optional[Any] = None
        try:
            if dtype == "json" or (content_type and "text" in content_type):
                sample = (p.read_text(encoding="utf-8", errors="ignore"))[:GRIDFS_SAMPLE_BYTES]
            else:
                sample = Binary(p.read_bytes()[:GRIDFS_SAMPLE_BYTES])
        except Exception:
            sample = None

        meta_doc = {
            "source_type": "file",
            "gridfs_id": files_doc["_id"],
            "filename": files_doc.get("filename"),
            "content_type": (files_doc.get("metadata") or {}).get("content_type"),
            "size": files_doc.get("length"),
            "detected_type": dtype,
            "ingested_at": int(time.time()),
            "stats": {},
            "sample": sample,
        }
        result["meta_id"] = insert_file_meta(db, collection, meta_doc)
        result["gridfs_id"] = str(files_doc["_id"])
        return result
    finally:
        try:
            client.close()
        except Exception:
            pass