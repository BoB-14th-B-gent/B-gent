"""Job Storage 모듈

Agent 상태 관리
- AGENT_STATES: 작업 상태 및 available_resources 저장
"""
import json
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson import ObjectId

from ..config import get_config

_cfg = get_config()
_client: Optional[MongoClient] = None
_db = None

_state_update_callback: Optional[Callable[[Dict[str, Any]], None]] = None


def set_state_update_callback(callback: Optional[Callable[[Dict[str, Any]], None]]):
    global _state_update_callback
    _state_update_callback = callback

def _convert_for_json(obj: Any) -> Any:
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_for_json(v) for v in obj]
    return obj

def _print_state_json(state_doc: Dict[str, Any]):
    try:
        import sys
        output_doc = state_doc.copy()
        output_doc.pop('_id', None)

        output_doc = _convert_for_json(output_doc)

        json_str = json.dumps(output_doc, ensure_ascii=False)
        sys.__stdout__.write(json_str + '\n')
        sys.__stdout__.flush()
    except Exception:
        pass


def _get_client():
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
        except ConnectionFailure as e:
            print(f"[X]  MongoDB 연결 실패 (작업은 계속됨): {e}")
            _client = None
            _db = None

    return _db

def _to_oid_or_keep(val: Optional[str | ObjectId]) -> Optional[ObjectId | str]:
    if val is None:
        return None
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return val

def save_agent_state(
    agent_id: str,
    stage_id: Optional[int] = None,
    plan: Optional[list] = None,
    status: str = "running",
    mcp_tools: Optional[list] = None,  # deprecated
    trigger_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    available_resources: Optional[Dict[str, Any]] = None
) -> bool:
    """Agent 상태 저장

    Args:
        agent_id: Agent(Job) ID
        stage_id: Stage 번호
        plan: Task 계획 목록
        status: 상태 (running, done, failed)
        mcp_tools: deprecated
        trigger_id: 트리거 ID
        conversation_id: 대화 ID
        available_resources: 사용 가능한 리소스 (disk_images, extracted_files)
    """
    import sys
    try:
        db = _get_client()
        if db is None:
            return False

        existing_doc = db.AGENT_STATES.find_one({"agent_id": agent_id})

        if trigger_id is None and existing_doc:
            trigger_id = existing_doc.get("trigger_id")
        if conversation_id is None and existing_doc:
            conversation_id = existing_doc.get("conversation_id")

        trigger_id = _to_oid_or_keep(trigger_id)
        conversation_id = _to_oid_or_keep(conversation_id)

        sys.stderr.write(f"[DEBUG save_agent_state] agent_id={agent_id}, stage_id={stage_id}, conversation_id={conversation_id}, type={type(conversation_id)}\n")

        state_doc = {
            "agent_id": agent_id,
            "trigger_id": trigger_id,
            "conversation_id": conversation_id,
            "stage_id": stage_id if stage_id is not None else 0,
            "status": status,
            "plan": plan or [],
            "updated_at": datetime.utcnow()
        }

        # available_resources가 제공된 경우에만 저장
        if available_resources is not None:
            state_doc["available_resources"] = available_resources

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$set": state_doc,
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )

        _print_state_json(state_doc)

        if _state_update_callback:
            try:
                _state_update_callback(state_doc)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  AGENT_STATES 저장 실패: {e}")
        return False

def update_agent_status(agent_id: str, status: str) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        update_doc = {
            "status": status,
            "updated_at": datetime.utcnow()
        }

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {"$set": update_doc}
        )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  상태 업데이트 실패: {e}")
        return False


def update_agent_resources(agent_id: str, available_resources: Dict[str, Any]) -> bool:
    """Agent의 available_resources 업데이트

    Args:
        agent_id: Agent(Job) ID
        available_resources: 사용 가능한 리소스
            - disk_images: 디스크 이미지 경로 목록
            - extracted_files: 추출된 파일 정보 목록

    Returns:
        bool: 업데이트 성공 여부
    """
    try:
        db = _get_client()
        if db is None:
            return False

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$set": {
                    "available_resources": available_resources,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return True

    except Exception as e:
        print(f"[X]  리소스 업데이트 실패: {e}")
        return False


def add_mcp_tool(agent_id: str, mcp_name: str, tool_name: str, task_id: Optional[str] = None) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        if not task_id:
            return True

        tool_identifier = f"{tool_name}"

        state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if not state:
            return False

        plan = state.get("plan", [])
        updated = False

        for task in plan:
            if task.get("task_id") == task_id:
                if "mcp_server" not in task or not task["mcp_server"]:
                    task["mcp_server"] = mcp_name

                if "mcp_tools" not in task:
                    task["mcp_tools"] = []
                if tool_identifier not in task["mcp_tools"]:
                    task["mcp_tools"].append(tool_identifier)

                updated = True
                break

        if updated:
            db.AGENT_STATES.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "plan": plan,
                        "updated_at": datetime.utcnow()
                    },
                    "$unset": {"mcp_tools": ""}
                }
            )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  MCP 도구 추가 실패: {e}")
        return False

def update_stage(agent_id: str, stage_id: int) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$set": {
                    "stage_id": stage_id,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  스테이지 업데이트 실패: {e}")
        return False

def update_task_status(agent_id: str, task_id: str, task_status: str) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id, "plan.task_id": task_id},
            {
                "$set": {
                    "plan.$.status": task_status,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  Task 상태 업데이트 실패: {e}")
        return False

def get_agent_state(agent_id: str) -> Optional[Dict[str, Any]]:
    try:
        db = _get_client()
        if db is None:
            return None

        return db.AGENT_STATES.find_one({"agent_id": agent_id})

    except Exception as e:
        print(f"[X]  상태 조회 실패: {e}")
        return None

def is_first_execution_in_conversation(conversation_id: Optional[str]) -> bool:
    import sys

    if not conversation_id:
        sys.stderr.write(f"[DEBUG is_first_execution] conversation_id is None or empty\n")
        return True

    try:
        db = _get_client()
        if db is None:
            sys.stderr.write(f"[DEBUG is_first_execution] db is None\n")
            return True

        conv_id = _to_oid_or_keep(conversation_id)
        sys.stderr.write(f"[DEBUG is_first_execution] conversation_id={conversation_id}, conv_id={conv_id}, type={type(conv_id)}\n")

        existing = db.AGENT_STATES.find_one({"conversation_id": conv_id})
        sys.stderr.write(f"[DEBUG is_first_execution] existing={existing is not None}, agent_id={existing.get('agent_id') if existing else None}\n")

        return existing is None

    except Exception as e:
        sys.stderr.write(f"[DEBUG is_first_execution] Exception: {e}\n")
        print(f"[X]  첫 실행 여부 확인 실패: {e}")
        return True


# =============================================================================
# Available Resources 관리 (AGENT_STATES 컬렉션에 저장)
# =============================================================================

def _merge_available_resources(
    existing: Dict[str, Any],
    new: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """available_resources 병합 (중복 제거)"""
    if not new:
        return existing

    merged = {
        "disk_images": list(existing.get("disk_images", [])),
        "extracted_files": list(existing.get("extracted_files", []))
    }

    # 디스크 이미지 병합 (경로 기준 중복 제거)
    existing_image_paths = set(merged["disk_images"])
    for img_path in new.get("disk_images", []):
        if img_path not in existing_image_paths:
            merged["disk_images"].append(img_path)
            existing_image_paths.add(img_path)

    # 추출된 파일 병합 (경로 기준 중복 제거)
    existing_file_paths = {f.get("path") for f in merged["extracted_files"]}
    for file_info in new.get("extracted_files", []):
        if file_info.get("path") not in existing_file_paths:
            merged["extracted_files"].append(file_info)
            existing_file_paths.add(file_info.get("path"))

    return merged


def get_available_resources(conversation_id: str) -> Dict[str, Any]:
    """대화에서 사용 가능한 리소스 조회 (AGENT_STATES에서 조회)

    동일 conversation_id를 가진 모든 AGENT_STATES에서 available_resources를 병합하여 반환

    Args:
        conversation_id: 대화 ID

    Returns:
        Dict[str, Any]: 사용 가능한 리소스
            - disk_images: 디스크 이미지 경로 목록
            - extracted_files: 추출된 파일 정보 목록
    """
    default_resources = {
        "disk_images": [],
        "extracted_files": []
    }

    try:
        db = _get_client()
        if db is None:
            return default_resources

        conv_id = _to_oid_or_keep(conversation_id)

        # 해당 conversation의 모든 agent_states 조회
        agent_states = db.AGENT_STATES.find({"conversation_id": conv_id})

        merged_resources = {
            "disk_images": [],
            "extracted_files": []
        }

        for state in agent_states:
            resources = state.get("available_resources")
            if resources:
                merged_resources = _merge_available_resources(merged_resources, resources)

        return merged_resources if merged_resources["disk_images"] or merged_resources["extracted_files"] else default_resources

    except Exception as e:
        import sys
        sys.stderr.write(f"[Storage] 리소스 조회 실패: {e}\n")
        return default_resources
