"""MongoDB 스토리지 모듈

작업과 결과를 MongoDB에 저장하고 조회하는 기능 제공
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from ..config import get_config
_cfg = get_config()
_client: Optional[MongoClient] = None
_db = None

def _get_client():
    """MongoDB 클라이언트 가져오기 (지연 초기화)"""
    global _client, _db

    if _client is None:

        try:
            _client = MongoClient(
                _cfg.mongo.uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            _client.admin.command('ping')
            _db = _client[_cfg.mongo.db]
            print(f"✓ MongoDB 연결됨: {_cfg.mongo.uri}")

        except ConnectionFailure as e:
            print(f"⚠️  MongoDB 연결 실패 (작업은 계속됨): {e}")
            _client = None
            _db = None

    return _db

def save_job(job_id: str, data: Dict[str, Any]) -> bool:
    """작업을 MongoDB에 저장

    Args:
        job_id: 작업 ID
        data: 저장할 작업 데이터

    Returns:
        bool: 저장 성공 여부
    """
    try:
        db = _get_client()

        if db is None:

            return False
        doc = {
            "_id": job_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            **data
        }
        db.jobs.replace_one({"_id": job_id}, doc, upsert=True)

        return True

    except Exception as e:
        print(f"⚠️  MongoDB 저장 실패: {e}")

        return False

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """작업을 MongoDB에서 조회

    Args:
        job_id: 작업 ID

    Returns:
        Optional[Dict[str, Any]]: 작업 데이터 (없으면 None)
    """
    try:
        db = _get_client()

        if db is None:

            return None

        return db.jobs.find_one({"_id": job_id})

    except Exception as e:
        print(f"⚠️  MongoDB 조회 실패: {e}")

        return None

def save_result(job_id: str, result_data: Dict[str, Any]) -> bool:
    """작업 결과를 MongoDB에 저장 (작업 업데이트)

    Args:
        job_id: 작업 ID
        result_data: 저장할 결과 데이터

    Returns:
        bool: 저장 성공 여부
    """
    try:
        db = _get_client()

        if db is None:

            return False
        db.jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "result": result_data
                }
            }
        )

        return True

    except Exception as e:
        print(f"⚠️  MongoDB 결과 저장 실패: {e}")

        return False

