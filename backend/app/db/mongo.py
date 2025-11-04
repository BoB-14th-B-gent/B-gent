from typing import Optional
from pymongo import MongoClient
from dotenv import load_dotenv
import os, gridfs

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("DB_NAME")

_client: Optional[MongoClient] = None

def get_client() -> MongoClient:
    global _client
    if _client is None:
        if not MONGO_URI:
            raise RuntimeError("MONGO_URI is not set")
        _client = MongoClient(MONGO_URI, retryWrites=True)
    return _client

def get_db():
    if not DB_NAME:
        raise RuntimeError("DB_NAME is not set")
    return get_client()[DB_NAME]

def get_fs(db=None) -> gridfs.GridFS:
    if db is None:
        db = get_db()
    return gridfs.GridFS(db)