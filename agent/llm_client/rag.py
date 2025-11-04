"""RAG (Retrieval-Augmented Generation) 모듈

ChromaDB 기반 벡터 검색으로 사용자 요청에 맞는 MCP 도구 검색
"""
from __future__ import annotations
from typing import List, Dict, Any
from ..config import get_config
_cfg = get_config()
_RAG_DISABLED = False
_coll = None

def _seed_defaults():
    """컬렉션 초기화 (MCP 도구는 지연 로딩으로 등록됨)"""
    try:

        if _coll is None:

            return

        try:
            cnt = _coll.count()

        except Exception:
            peek = _coll.peek() if hasattr(_coll, "peek") else {"ids": []}
            cnt = len(peek.get("ids", []))

    except Exception:
        pass

try:
    import chromadb
    _client = chromadb.PersistentClient(path=_cfg.chroma.dir)
    _coll = _client.get_or_create_collection("mcp_capabilities")
    _seed_defaults()

except Exception as e:
    import os
    if os.getenv("MCP_DEBUG") == "1":
        print(f"⚠️  RAG 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
    _RAG_DISABLED = True
    _client = None
    _coll = None

def upsert_capability(docs: List[Dict[str, Any]]) -> None:
    """도구 정보를 ChromaDB에 등록

    Args:
        docs: 도구 정보 리스트
            [{"id":"elastic_1","text":"...","meta":{"tool":"elastic", ...}}, ...]
    """
    if _RAG_DISABLED or not docs:

        return
    _coll.upsert(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[d.get("meta", {}) for d in docs],
    )

    try:

        if hasattr(_client, "persist"):
            _client.persist()

    except Exception:
        pass

def _load_mcp_tools_if_needed():
    """MCP 도구를 지연 로딩으로 RAG에 등록

    ⚠️  자동 로딩 비활성화됨
    MCP 도구는 manage_rag.py의 "MCP 도구 초기 로딩"으로 한번만 저장하세요.
    자동으로 MCP 서버에 연결하지 않아 시간이 절약됩니다.
    """
    if not _cfg.mcp.enabled or _RAG_DISABLED:

        return

    try:
        res = _coll.get(where={"is_mcp": True})

        if res and res.get("ids") and len(res["ids"]) > 0:

            return
        print("⚠️  ChromaDB에 MCP 도구가 없습니다.")
        print("   → manage_rag.py를 실행하여 'MCP 도구 초기 로딩'을 선택하세요.")
        print("   → 한번만 실행하면 이후로는 빠르게 사용할 수 있습니다.")

    except Exception as e:
        print(f"⚠️  MCP 도구 확인 실패: {e}")

def query_mcp_candidates(text: str, file_meta: dict = None, top_k: int = 5) -> list[dict]:
    """쿼리에 맞는 MCP 도구 후보 검색

    Args:
        text: 검색 쿼리 (사용자 요청)
        file_meta: 파일 메타데이터 (선택)
        top_k: 반환할 최대 결과 수 (기본값: 5)

    Returns:
        list[dict]: 검색된 도구/문서 목록
            [{"id": "...", "meta": {...}, "document": "..."}, ...]
            - MCP 도구: meta에 server, tool_name, input_schema 포함
            - 사용자 문서: document에 전체 내용 포함
    """
    if _RAG_DISABLED:
        print("⚠️  RAG가 비활성화되어 있습니다. MCP 도구를 검색할 수 없습니다.")

        return []
    _load_mcp_tools_if_needed()

    if file_meta:
        q = f"{text}\nMETA:{file_meta}"

    else:
        q = text
    res = _coll.query(query_texts=[q], n_results=top_k)
    out = []

    if res and res.get("ids"):

        for i in range(len(res["ids"][0])):
            result_item = {
                "id": res["ids"][0][i],
                "meta": res["metadatas"][0][i] if res.get("metadatas") else {}
            }

            if res.get("documents") and i < len(res["documents"][0]):
                result_item["document"] = res["documents"][0][i]
            out.append(result_item)

    return out

