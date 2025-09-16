from typing import Any, Dict, Optional
from pathlib import Path
import time, json, mimetypes
from pymongo import MongoClient
from bson.binary import Binary
import gridfs

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "test"

def get_client() -> MongoClient:
    return MongoClient(MONGO_URI)

def get_db(client: MongoClient):
    return client[DB_NAME]

def get_fs(db) -> gridfs.GridFS:
    return gridfs.GridFS(db)

def store_file_to_gridfs(fs: gridfs.GridFS, path: str, extra_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)

    content_type, _ = mimetypes.guess_type(p.name)
    meta = {
        "filename": p.name,
        "content_type": content_type or "application/octet-stream",
        "size": p.stat().st_size,
        "ingested_at": int(time.time()),
    }
    if extra_meta:
        meta.update(extra_meta)

    with p.open("rb") as f:
        file_id = fs.put(f, filename=p.name, metadata=meta)

    files_doc = fs._GridFS__files.find_one({"_id": file_id}, {"chunkSize": 0})
    return files_doc

def insert_file_meta(db, collection: str, meta_doc: Dict[str, Any]) -> str:
    res = db[collection].insert_one(meta_doc)
    return str(res.inserted_id)

def choose_strategy(size_bytes: int, mode: str, inline_threshold_bytes: int) -> str:
    mode = mode.lower()
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

    client = get_client()
    db = get_db(client)

    size = p.stat().st_size
    content_type, _ = mimetypes.guess_type(p.name)
    dtype = (detected_type or "").lower() if detected_type else None
    strategy = choose_strategy(size, mode, inline_threshold_bytes)

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
                meta_doc["data"] = json.loads(p.read_text(encoding="utf-8"))
            else:
                meta_doc["raw"] = Binary(p.read_bytes())
        except Exception as e:
            meta_doc["stats"]["parse_error"] = str(e)
            meta_doc["raw"] = Binary(p.read_bytes())

        result["meta_id"] = insert_file_meta(db, collection, meta_doc)
        return result

    fs = get_fs(db)
    files_doc = store_file_to_gridfs(fs, str(p), extra_meta={"detected_type": dtype})
    meta_doc = {
        "source_type": "file",
        "gridfs_id": files_doc["_id"],
        "filename": files_doc.get("filename"),
        "content_type": (files_doc.get("metadata") or {}).get("content_type"),
        "size": files_doc.get("length"),
        "detected_type": dtype,
        "ingested_at": int(time.time()),
        "stats": {},
        "sample": None,
    }
    result["meta_id"] = insert_file_meta(db, collection, meta_doc)
    result["gridfs_id"] = str(files_doc["_id"])
    return result