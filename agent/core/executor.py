"""액션 실행기 모듈

MCP 도구 호출, 타임아웃 및 재시도 관리 담당
Lazy Loading으로 필요한 MCP 서버만 초기화
"""
from __future__ import annotations
import os
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, Any, Optional, List
from ..schemas.actions import Action, ActionResult
from ..mcp_client.lazy_loader import get_mcp_client_for_server
from ..storage.evidence_logger import log_mcp_execution
from ..constants import (
    DEFAULT_RETRY_COUNT,
    MAX_BACKOFF_SECONDS,
    RETRYABLE_ERROR_PATTERNS,
    PREVIEW_MAX_LENGTH,
    SEPARATOR
)

_ghidra_import_cache: Dict[str, bool] = {}
_validation_error_cache: Dict[str, int] = {}


def _validate_file_paths(params: Dict[str, Any], action: Action) -> Optional[str]:
    """파일 경로 파라미터의 유효성 검증

    MCP 도구 호출 전에 파일 경로가 실제로 존재하는지 확인
    Windows/WSL 경로 변환도 시도

    Args:
        params: 파라미터 딕셔너리
        action: 액션 정보 (에러 메시지용)

    Returns:
        Optional[str]: 에러 메시지 (검증 실패 시), None (검증 성공 시)
    """
    # 파일 경로 관련 파라미터 키 목록
    path_keys = ["image_path", "file_path", "path", "image", "binary_path", "input_path"]

    for key in path_keys:
        if key not in params:
            continue

        path = params[key]
        if not isinstance(path, str) or not path.strip():
            continue

        path = path.strip()

        # 경로가 이미 존재하면 OK
        if os.path.exists(path):
            continue

        # Windows 경로를 WSL 경로로 변환 시도
        # C:\Users\... → /mnt/c/Users/...
        wsl_path = None
        if len(path) >= 2 and path[1] == ':':
            drive_letter = path[0].lower()
            rest_path = path[2:].replace('\\', '/')
            wsl_path = f"/mnt/{drive_letter}{rest_path}"

            if os.path.exists(wsl_path):
                # WSL 경로로 자동 변환하여 params 업데이트
                params[key] = wsl_path
                import sys
                sys.__stdout__.write(f"│ [PATH FIX] Converted Windows path to WSL: {path} → {wsl_path}\n")
                sys.__stdout__.flush()
                continue

        # WSL 경로를 Windows 경로로 변환 시도 (반대 방향)
        # /mnt/c/Users/... → C:\Users\...
        win_path = None
        if path.startswith('/mnt/') and len(path) > 6:
            drive_letter = path[5].upper()
            rest_path = path[6:].replace('/', '\\')
            win_path = f"{drive_letter}:{rest_path}"

            if os.path.exists(win_path):
                params[key] = win_path
                import sys
                sys.__stdout__.write(f"│ [PATH FIX] Converted WSL path to Windows: {path} → {win_path}\n")
                sys.__stdout__.flush()
                continue

        # 경로를 찾을 수 없음
        error_msg = (
            f"FILE NOT FOUND: Parameter '{key}' contains an invalid path\n\n"
            f"Action: {action.tool}.{action.operation}\n"
            f"Path provided: {path}\n"
        )

        if wsl_path:
            error_msg += f"Also tried WSL path: {wsl_path}\n"
        if win_path:
            error_msg += f"Also tried Windows path: {win_path}\n"

        error_msg += (
            f"\nPossible fixes:\n"
            f"  1. Check if the file exists at the specified path\n"
            f"  2. Use absolute path instead of relative path\n"
            f"  3. For disk images, ensure the .E01/.dd file is accessible\n"
            f"  4. Check file permissions"
        )

        return error_msg

    return None


def _normalize_path(path: str) -> str:
    """경로 문자열 정규화 - 이중 이스케이프된 백슬래시 수정

    LLM이 Windows 경로를 생성할 때 백슬래시를 이중 이스케이프하는 경우가 있음.
    예: "C:\\\\Users\\\\user" → "C:\\Users\\user"

    Args:
        path: 원본 경로 문자열

    Returns:
        str: 정규화된 경로 문자열
    """
    if not path or not isinstance(path, str):
        return path

    import re

    # 연속된 백슬래시 2개 이상을 1개로 줄임
    # C:\Users\\user → C:\Users\user
    # C:\\Users\\\\user → C:\Users\user
    path = re.sub(r'\\{2,}', r'\\', path)

    return path


def _sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """파라미터 값에서 trailing 콤마/공백 제거 및 불필요한 필드 제거

    LLM이 파일 경로 등을 생성할 때 trailing 콤마나 공백이 포함되는 경우가 있음.
    또한 LLM이 'finished' 등 내부용 필드를 params에 포함시키는 경우가 있음.
    MCP 도구 호출 전에 이를 정제하여 오류 방지.

    Args:
        params: 원본 파라미터 딕셔너리

    Returns:
        Dict[str, Any]: 정제된 파라미터 딕셔너리
    """
    if not params:
        return params

    # LLM이 잘못 포함시킬 수 있는 내부용 필드들 (MCP 도구 파라미터가 아님)
    internal_fields = {'finished', 'thought', 'answer', 'action'}

    # 경로 관련 파라미터 키 (이중 이스케이프 수정 대상)
    path_keys = {
        'path', 'file_path', 'dir_path', 'folder_path', 'target_path',
        'image_path', 'binary_path', 'input_path', 'output_path',
        'out_dir', 'batch_file', 'batch_dir'
    }

    sanitized = {}
    for key, value in params.items():
        # 내부용 필드는 제거
        if key in internal_fields:
            continue
        if isinstance(value, str):
            value = value.strip().rstrip(',').strip()
            # 경로 파라미터는 이중 이스케이프 수정
            if key in path_keys:
                value = _normalize_path(value)
        elif isinstance(value, list):
            value = [
                v.strip().rstrip(',').strip() if isinstance(v, str) else v
                for v in value
            ]
        sanitized[key] = value
    return sanitized


def _get_tool_schema(client, server_name: str, tool_name: str) -> Optional[Dict[str, Any]]:
    """MCP 도구의 input_schema 가져오기

    Args:
        client: MCP client instance
        server_name: 서버 이름 (elastic, ghidra 등)
        tool_name: 도구 이름 (search_documents, import_binary 등)

    Returns:
        Optional[Dict]: input_schema (JSON Schema 형식), 없으면 None
    """
    if not hasattr(client, 'tools_cache'):
        return None

    tools = client.tools_cache.get(server_name, [])
    for tool in tools:
        if tool.get('name') == tool_name:
            return tool.get('input_schema')

    return None


def _filter_params_by_schema(params: Dict[str, Any], schema: Optional[Dict[str, Any]], action_info: str = "") -> Dict[str, Any]:
    """Schema 기반 화이트리스트 필터링 (MCP 호출 직전 최종 방어선)

    MCP 도구에 전달하기 전 schema에 정의된 파라미터만 허용합니다.
    이를 통해 'finished', 'thought', 'answer' 등 ReAct 내부용 필드가
    MCP tool params로 흘러들어가는 것을 완전히 차단합니다.

    Args:
        params: 원본 파라미터 딕셔너리
        schema: JSON Schema (input_schema)
        action_info: 로깅용 액션 정보 (예: "elastic.search_documents")

    Returns:
        Dict[str, Any]: schema에 정의된 키만 포함된 파라미터

    Example:
        >>> schema = {"properties": {"index": {}, "body": {}}, "required": ["index"]}
        >>> params = {"index": "logs", "body": {}, "finished": False}
        >>> _filter_params_by_schema(params, schema)
        {"index": "logs", "body": {}}  # finished 제거됨
    """
    if not params:
        return params

    if not schema:
        # Schema가 없으면 최소한의 블랙리스트만 적용
        # (ReAct 내부 필드는 어떤 MCP 도구에서도 사용하지 않음)
        react_internal_fields = {'finished', 'thought', 'answer', 'action', 'react_state'}
        filtered = {k: v for k, v in params.items() if k not in react_internal_fields}

        removed = set(params.keys()) - set(filtered.keys())
        if removed:
            import sys
            sys.__stdout__.write(f"│ [SANITIZE] Removed internal fields from params: {removed}\n")
            sys.__stdout__.flush()

        return filtered

    # Schema가 있으면 화이트리스트 방식 적용
    properties = schema.get('properties', {})

    if not properties:
        # properties가 비어있으면 블랙리스트 방식으로 fallback
        react_internal_fields = {'finished', 'thought', 'answer', 'action', 'react_state'}
        return {k: v for k, v in params.items() if k not in react_internal_fields}

    # 화이트리스트: schema에 정의된 키만 허용
    allowed_keys = set(properties.keys())
    filtered = {k: v for k, v in params.items() if k in allowed_keys}

    # 제거된 키 로깅 (디버깅용)
    removed_keys = set(params.keys()) - allowed_keys
    if removed_keys:
        import sys
        import os
        # ReAct 내부 필드가 제거된 경우만 로깅 (불필요한 로깅 방지)
        react_internal = removed_keys & {'finished', 'thought', 'answer', 'action', 'react_state'}
        if react_internal:
            sys.__stdout__.write(f"│ [SCHEMA FILTER] {action_info}: Blocked internal fields → {react_internal}\n")
            sys.__stdout__.flush()

        # 디버그 모드에서는 모든 제거된 키 표시
        if os.getenv("DEBUG") == "1" and removed_keys:
            sys.__stdout__.write(f"│ [DEBUG] Removed params not in schema: {removed_keys}\n")
            sys.__stdout__.write(f"│ [DEBUG] Allowed by schema: {allowed_keys}\n")
            sys.__stdout__.flush()

    return filtered


def _validate_params_against_schema(params: Dict[str, Any], schema: Dict[str, Any], action: Action) -> Optional[str]:
    """파라미터를 JSON Schema로 검증

    Args:
        params: 검증할 파라미터
        schema: JSON Schema
        action: 액션 정보 (에러 메시지용)

    Returns:
        Optional[str]: 에러 메시지 (검증 실패 시), None (검증 성공 시)
    """
    if not schema:
        return None

    try:
        import jsonschema
        jsonschema.validate(params, schema)
        return None 
    except ImportError:
        return _basic_type_validation(params, schema, action)
    except jsonschema.ValidationError as e:
        return _format_jsonschema_error(e, action, schema)
    except Exception as e:
        return f"Schema validation error: {str(e)}"


def _basic_type_validation(params: Dict[str, Any], schema: Dict[str, Any], action: Action) -> Optional[str]:
    """기본적인 타입 검증 (jsonschema 없을 때 fallback)

    Args:
        params: 검증할 파라미터
        schema: JSON Schema
        action: 액션 정보

    Returns:
        Optional[str]: 에러 메시지 또는 None
    """
    properties = schema.get('properties', {})
    required = schema.get('required', [])

    for req_field in required:
        if req_field not in params:
            return (
                f"VALIDATION ERROR: Missing required parameter '{req_field}'\n\n"
                f"Action: {action.tool}.{action.operation}\n"
                f"Your params: {params}\n"
                f"Required params: {required}"
            )

    for param_name, param_value in params.items():
        if param_name in properties:
            prop_schema = properties[param_name]
            expected_type = prop_schema.get('type')

            if expected_type == 'string' and not isinstance(param_value, str):
                example_fix = ""
                if isinstance(param_value, list):
                    example_fix = f"\n  CORRECT: \"{param_name}\": \"{','.join(str(v) for v in param_value)}\""

                return (
                    f"TYPE ERROR: Parameter '{param_name}' must be a STRING\n\n"
                    f"Action: {action.tool}.{action.operation}\n"
                    f"Expected: string\n"
                    f"Got: {type(param_value).__name__} = {param_value}\n\n"
                    f"Fix:\n"
                    f"  WRONG: \"{param_name}\": {param_value}{example_fix}"
                )
            elif expected_type == 'object' and not isinstance(param_value, dict):
                return (
                    f"TYPE ERROR: Parameter '{param_name}' must be an OBJECT (dict)\n\n"
                    f"Action: {action.tool}.{action.operation}\n"
                    f"Expected: object/dict\n"
                    f"Got: {type(param_value).__name__}"
                )
            elif expected_type == 'array' and not isinstance(param_value, list):
                return (
                    f"TYPE ERROR: Parameter '{param_name}' must be an ARRAY (list)\n\n"
                    f"Action: {action.tool}.{action.operation}\n"
                    f"Expected: array/list\n"
                    f"Got: {type(param_value).__name__}"
                )

    return None


def _format_jsonschema_error(error: 'jsonschema.ValidationError', action: Action, schema: Dict[str, Any]) -> str:
    """jsonschema ValidationError를 사용자 친화적 메시지로 변환

    Args:
        error: jsonschema ValidationError
        action: 액션 정보
        schema: JSON Schema

    Returns:
        str: 사용자 친화적 에러 메시지
    """
    import json as json_module

    field_path = ".".join(str(p) for p in error.path) if error.path else "root"
    error_msg = error.message
    validator = error.validator

    expected = ""
    if validator == "type":
        expected = f"Expected type: {error.validator_value}"
    elif validator == "required":
        expected = f"Required fields: {error.validator_value}"

    return (
        f"SCHEMA VALIDATION ERROR\n\n"
        f"Action: {action.tool}.{action.operation}\n"
        f"Field: {field_path}\n"
        f"Error: {error_msg}\n"
        f"{expected}\n\n"
        f"Your params:\n{json_module.dumps(action.params, indent=2, ensure_ascii=False)}\n\n"
        f"Common fixes:\n"
        f"  1. Check parameter types (string vs list, object vs string)\n"
        f"  2. Ensure all required fields are present\n"
        f"  3. Remove unexpected/unsupported parameters"
    )


def _enhance_mcp_error_message(error_msg: str, action: Action) -> str:
    """MCP에서 반환된 에러 메시지를 개선

    Args:
        error_msg: 원본 에러 메시지
        action: 액션 정보

    Returns:
        str: 개선된 에러 메시지
    """
    import json as json_module
    error_lower = error_msg.lower()

    if "validation error" in error_lower or "type=" in error_lower:
        return (
            f"PARAMETER VALIDATION FAILED\n\n"
            f"Action: {action.tool}.{action.operation}\n"
            f"Your params:\n{json_module.dumps(action.params, indent=2, ensure_ascii=False)}\n\n"
            f"MCP Server Error:\n{error_msg}\n\n"
            f"Common issues:\n"
            f"  - Wrong parameter type (e.g., list instead of string)\n"
            f"  - Missing required parameters\n"
            f"  - Unsupported parameters"
        )

    if "missing required" in error_lower or "required argument" in error_lower:
        return (
            f"MISSING REQUIRED PARAMETER\n\n"
            f"Action: {action.tool}.{action.operation}\n"
            f"Your params:\n{json_module.dumps(action.params, indent=2, ensure_ascii=False)}\n\n"
            f"Error: {error_msg}"
        )

    if "unexpected keyword" in error_lower:
        return (
            f"UNSUPPORTED PARAMETER\n\n"
            f"Action: {action.tool}.{action.operation}\n"
            f"Your params:\n{json_module.dumps(action.params, indent=2, ensure_ascii=False)}\n\n"
            f"Error: {error_msg}\n\n"
            f"One or more parameters are not supported by this tool."
        )

    return (
        f"MCP TOOL ERROR\n\n"
        f"Action: {action.tool}.{action.operation}\n"
        f"Error: {error_msg}"
    )

def execute_action(action: Action, job_id: Optional[str] = None, task_id: Optional[str] = None) -> ActionResult:
    """액션 실행 (재시도 및 타임아웃 지원)

    MCP 도구 호출 및 액션 실행, 실패 시 자동 재시도
    재시�� 가능한 에러인 경우 지수 백오프(exponential backoff) 적용

    로직:
        1. 최대 retry_count + 1회 반복
        2. 각 시도마다:
           a. MCP 도구 호출 (타임아웃 적용)
           b. 성공 시 ActionResult 반환
           c. 실패 시 재시도 가능 여부 판단
           d. 재시도 가능하면 지수 백오프 후 재시도
           e. 재시도 불가능하면 즉시 실패 반환
        3. 모든 재시도 실패 시 최종 실패 반환

    Args:
        action: 실행할 액션 (도구 이름, 파라미터 등 포함)
        job_id: 작업 ID (MCP 로깅용)
        task_id: Task ID (task별 mcp_tools 추적용)

    Returns:
        ActionResult: 실행 결과 (성공/실패, 결과 데이터, 실행 시간 등)

    Example:
        >>> action = Action(
        ...     tool="elastic",
        ...     operation="search_documents",
        ...     params={"index": "logs-*", "body": {...}},
        ...     reason="SIEM 로그 검색",
        ...     retry_count=2,
        ...     timeout_seconds=60
        ... )
        >>> result = execute_action(action)
        >>> if result.success:
        ...     print(f"결과: {result.result}")
        ... else:
        ...     print(f"에러: {result.error}")
    """
    max_retries = action.retry_count
    timeout = action.timeout_seconds
    last_error = None

    import json as json_module
    action_signature = f"{action.tool}.{action.operation}:{json_module.dumps(action.params, sort_keys=True)}"

    if action_signature in _validation_error_cache:
        error_count = _validation_error_cache[action_signature]
        if error_count >= 2:
            return ActionResult(
                action=action,
                success=False,
                error=f"BLOCKED: This exact action has failed {error_count} times with validation errors. The parameters are incompatible with the tool schema. DO NOT retry this action - use a different tool or different parameters. Check the tool schema carefully.",
                execution_time_seconds=0.0
            )

    if action.tool == 'elastic':
        operation_lower = action.operation.lower()
        forbidden_operations = ['create', 'delete', 'update', 'insert', 'remove', 'put', 'post', 'modify', 'write']
        if any(op in operation_lower for op in forbidden_operations):
            return ActionResult(
                action=action,
                success=False,
                error=f"SECURITY BLOCK: Elasticsearch operation '{action.operation}' is forbidden. Only read-only operations are allowed (search, query, get, list, count). Elasticsearch is for forensic analysis only - treat it as read-only evidence.",
                execution_time_seconds=0.0
            )

    if action.tool == 'ghidra' and action.operation == 'import_binary':
        if job_id and job_id in _ghidra_import_cache:
            import sys
            import os
            if os.getenv("DEBUG") == "1":
                sys.__stdout__.write(f"[DEBUG] BLOCKED import_binary re-call for job {job_id}\n")
                sys.__stdout__.flush()
            return ActionResult(
                action=action,
                success=False,
                error=f"BLOCKED: import_binary already called for this job (job_id: {job_id}). Re-importing will break Ghidra analysis. The binary name is already in the first import_binary observation result. Do NOT call import_binary again - use the existing binary name.",
                execution_time_seconds=0.0
            )

    if action.params.get("_skip_execution"):
        # print(f"[!]  건너뜀: {action.tool}.{action.operation}")
        # print(f"   이유: 이전 단계 실패로 인해 실행 불가")
        return ActionResult(
            action=action,
            success=False,
            error="이전 단계에서 필요한 값을 추출하지 못해 실행을 건너뜁니다.",
            execution_time_seconds=0.0
        )

    # 파라미터 정리 (trailing 쉼표, 공백 제거) - 검증 전에 먼저 수행
    action.params = _sanitize_params(action.params)

    # 파일 경로 검증 (MCP 호출 전 경로 존재 여부 확인 및 자동 변환)
    path_validation_error = _validate_file_paths(action.params, action)
    if path_validation_error:
        return ActionResult(
            action=action,
            success=False,
            error=path_validation_error,
            execution_time_seconds=0.0
        )

    for attempt in range(max_retries + 1):
        start_time = time.time()

        try:

            if attempt > 0:
                # print(f"[!] 재시도 {attempt}/{max_retries}: {action.tool}.{action.operation}")
                sleep_time = min(2 ** (attempt - 1), 10)
                time.sleep(sleep_time)

            else:
                # print(f"   실행 중: {action.tool}.{action.operation}")
                # print(f"   이유: {action.reason}")

                client = get_mcp_client_for_server(action.tool)
                tool_schema = _get_tool_schema(client, action.tool, action.operation)

                if tool_schema:
                    validation_error = _validate_params_against_schema(action.params, tool_schema, action)
                    if validation_error:
                        return ActionResult(
                            action=action,
                            success=False,
                            error=validation_error,
                            execution_time_seconds=0.0
                        )

            result = _call_mcp_tool_with_timeout(action, timeout)
            execution_time = time.time() - start_time

            if result.get("success"):
                result_data = result.get("result", "")

                import sys
                import os
                if os.getenv("DEBUG") == "1":
                    sys.__stdout__.write(f"[DEBUG] Calling log_mcp_execution for {action.tool}.{action.operation}\n")
                    sys.__stdout__.write(f"[DEBUG] Response length: {len(str(result_data))} chars\n")
                    sys.__stdout__.flush()

                save_result = log_mcp_execution(
                    mcp_name=action.tool,
                    tool_name=action.operation,
                    request=action.params,
                    response=result_data,
                    success=True,
                    job_id=job_id
                )

                if os.getenv("DEBUG") == "1":
                    sys.__stdout__.write(f"[DEBUG] log_mcp_execution returned: {save_result}\n")
                    sys.__stdout__.flush()

                if job_id:
                    from ..storage.job_storage import add_mcp_tool
                    add_mcp_tool(job_id, action.tool, action.operation, task_id)

                if action.tool == 'ghidra' and action.operation == 'import_binary':
                    import sys
                    if os.getenv("DEBUG") == "1":
                        sys.__stdout__.write("[DEBUG] Ghidra import_binary detected, waiting for analysis...\n")
                        sys.__stdout__.flush()
                    wait_result = _wait_for_ghidra_analysis(action, job_id, task_id, timeout)
                    if wait_result.get("binary_name"):
                        binary_name = wait_result['binary_name']
                        result_data = f"SUCCESS: Binary imported and analyzed.\n\n" \
                                    f"BINARY_NAME: {binary_name}\n\n" \
                                    f"Use this exact binary name ({binary_name}) for all subsequent Ghidra operations.\n" \
                                    f"Do NOT call import_binary or list_project_binaries again - you already have the binary name above.\n\n" \
                                    f"Next steps: Use search_strings, list_imports, list_exports, search_functions_by_name with binary_name=\"{binary_name}\""
                        if os.getenv("DEBUG") == "1":
                            sys.__stdout__.write(f"[DEBUG] Analysis completed: {binary_name}\n")
                            sys.__stdout__.flush()
                    elif wait_result.get("error"):
                        result_data = result_data + f"\n\nWarning: {wait_result['error']}"
                        if os.getenv("DEBUG") == "1":
                            sys.__stdout__.write(f"[DEBUG] Analysis warning: {wait_result['error']}\n")
                            sys.__stdout__.flush()

                    if job_id:
                        _ghidra_import_cache[job_id] = True
                        if os.getenv("DEBUG") == "1":
                            sys.__stdout__.write(f"[DEBUG] Marked import_binary as called for job {job_id}\n")
                            sys.__stdout__.flush()

                if result_data:
                    preview = str(result_data)
                    if len(preview) > PREVIEW_MAX_LENGTH:
                        preview = preview[:PREVIEW_MAX_LENGTH] + f"\n... (총 {len(preview)}자, 나머지 생략)"

                    # print(f"[OK] 완료 ({execution_time:.2f}초)")
                    # print(f"\n   결과:")
                    # print(SEPARATOR)
                    # print(preview)
                    # print(SEPARATOR)
                    pass
                else:
                    # print(f"[OK] 완료 ({execution_time:.2f}초) - 결과 없음")
                    pass

                return ActionResult(
                    action=action,
                    success=True,
                    result=result_data,
                    execution_time_seconds=execution_time
                )

            else:
                error_msg = result.get("error", "Unknown error")
                last_error = error_msg

                validation_errors = ['validation error', 'unexpected keyword argument', 'missing required argument',
                                    'input should be a valid', 'type=dict_type', 'type=unexpected_keyword_argument']
                if any(err_pattern.lower() in error_msg.lower() for err_pattern in validation_errors):
                    _validation_error_cache[action_signature] = _validation_error_cache.get(action_signature, 0) + 1
                    import sys
                    import os
                    if os.getenv("DEBUG") == "1":
                        sys.__stdout__.write(f"[DEBUG] Validation error detected for {action_signature}, count: {_validation_error_cache[action_signature]}\n")
                        sys.__stdout__.flush()

                    error_msg = _enhance_mcp_error_message(error_msg, action)
                    last_error = error_msg

                log_mcp_execution(
                    mcp_name=action.tool,
                    tool_name=action.operation,
                    request=action.params,
                    response=result.get("result"),
                    success=False,
                    job_id=job_id
                )

                if attempt < max_retries and _is_retryable_error(error_msg):
                    # print(f"[X] 실패 (재시도 가능): {error_msg}")
                    continue

                else:
                    # print(f"[X] 실패: {error_msg}")
                    pass

                    return ActionResult(
                        action=action,
                        success=False,
                        error=error_msg,
                        execution_time_seconds=execution_time
                    )

        except (FuturesTimeoutError, asyncio.TimeoutError):
            execution_time = time.time() - start_time
            error_msg = f"타임아웃 ({timeout}초 초과)"
            last_error = error_msg

            if attempt < max_retries:
                # print(f"[!]  {error_msg} - 재시도 중...")
                continue

            else:
                # print(f"[X] {error_msg}")
                pass

                return ActionResult(
                    action=action,
                    success=False,
                    error=error_msg,
                    execution_time_seconds=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            last_error = error_msg

            if attempt < max_retries and _is_retryable_error(error_msg):
                # print(f"[X] 예외 발생 (재시도 가능): {e}")
                continue

            else:
                # print(f"[X] 예외 발생: {e}")
                # traceback 출력 (디버깅용)
                import traceback
                traceback.print_exc()

                return ActionResult(
                    action=action,
                    success=False,
                    error=error_msg,
                    execution_time_seconds=execution_time
                )

    return ActionResult(
        action=action,
        success=False,
        error=f"모든 재시도 실패: {last_error}",
        execution_time_seconds=0.0
    )

def _call_mcp_tool_with_timeout(action: Action, timeout: float) -> Dict[str, Any]:
    """타임아웃을 적용하여 MCP 도구 호출

    MCP client의 내장 타임아웃을 사용하여 도구를 호출합니다.
    (ThreadPoolExecutor 사용 시 이벤트 루프 스레드 바인딩 문제로 데드락 발생)

    Args:
        action: 실행할 액션
        timeout: 타임아웃 (초)

    Returns:
        Dict[str, Any]: MCP 호출 결과
            - success: 성공 여부
            - result: 결과 데이터 (성공 시)
            - error: 에러 메시지 (실패 시)

    Raises:
        FuturesTimeoutError: 타임아웃 발생 시
    """
    client = get_mcp_client_for_server(action.tool)

    # 1단계: 기본 sanitize (trailing 콤마, 공백 제거 + 내부 필드 제거)
    sanitized_params = _sanitize_params(action.params)

    # 2단계: Schema 기반 화이트리스트 필터링 (최종 방어선)
    # 'finished', 'thought', 'answer' 등 ReAct 내부 필드가 MCP로 전달되는 것을 완전 차단
    tool_schema = _get_tool_schema(client, action.tool, action.operation)
    action_info = f"{action.tool}.{action.operation}"
    filtered_params = _filter_params_by_schema(sanitized_params, tool_schema, action_info)

    # ThreadPoolExecutor 제거: asyncio 이벤트 루프는 스레드 바운드이므로
    # 다른 스레드에서 호출 시 데드락 발생. MCP client의 내장 타임아웃 사용.
    try:
        return client.call_tool(
            server_name=action.tool,
            tool_name=action.operation,
            arguments=filtered_params,
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise FuturesTimeoutError(f"MCP 도구 호출 타임아웃 ({timeout}초)")

def _call_mcp_tool(action: Action) -> Dict[str, Any]:
    """MCP 도구 호출 (Lazy Loading)

    필요한 MCP 서버만 초기화하여 도구 호출
    성능 최적화: 사용하지 않는 서버는 초기화하지 않음

    Args:
        action: 실행할 액션

    Returns:
        Dict[str, Any]: MCP 호출 결과
            - success: 성공 여부
            - result: 결과 데이터 (성공 시)
            - error: 에러 메시지 (실패 시)
    """
    client = get_mcp_client_for_server(action.tool)

    # 1단계: 기본 sanitize (trailing 콤마, 공백 제거 + 내부 필드 제거)
    sanitized_params = _sanitize_params(action.params)

    # 2단계: Schema 기반 화이트리스트 필터링 (최종 방어선)
    # 'finished', 'thought', 'answer' 등 ReAct 내부 필드가 MCP로 전달되는 것을 완전 차단
    tool_schema = _get_tool_schema(client, action.tool, action.operation)
    action_info = f"{action.tool}.{action.operation}"
    filtered_params = _filter_params_by_schema(sanitized_params, tool_schema, action_info)

    return client.call_tool(
        server_name=action.tool,
        tool_name=action.operation,
        arguments=filtered_params
    )

def _is_retryable_error(error_msg: str) -> bool:
    """재시도 가능한 에러인지 판단

    네트워크 관련 일시적 에러는 재시도 가능으로 판단

    Args:
        error_msg: 에러 메시지

    Returns:
        bool: 재시도 가능 여부
    """
    error_lower = error_msg.lower()
    return any(pattern in error_lower for pattern in RETRYABLE_ERROR_PATTERNS)

def _wait_for_ghidra_analysis(
    action: Action,
    job_id: Optional[str] = None,
    task_id: Optional[str] = None,
    timeout: float = 120.0
) -> Dict[str, Any]:
    """Ghidra 바이너리 분석 완료까지 대기 (exponential backoff)

    import_binary 호출 후 Ghidra가 바이너리를 분석하는 동안 대기
    list_project_binaries를 주기적으로 호출하여 analysis_complete 확인

    Args:
        action: import_binary 액션 (binary_path 포함)
        job_id: 작업 ID (로깅용)
        task_id: Task ID
        timeout: 최대 대기 시간 (초, 기본값: 120)

    Returns:
        Dict[str, Any]:
            - binary_name: 분석 완료된 바이너리 이름 (성공 시)
            - error: 에러 메시지 (실패 시)
            - elapsed: 소요 시간 (초)
    """
    import json
    from ..mcp_client.lazy_loader import get_mcp_client_for_server

    start_time = time.time()
    wait_intervals = [2, 3, 5, 8, 10, 15, 20]
    check_count = 0
    max_timeout = time.time() + timeout

    client = get_mcp_client_for_server('ghidra')

    while time.time() < max_timeout:
        if check_count < len(wait_intervals):
            wait_time = wait_intervals[check_count]
        else:
            wait_time = wait_intervals[-1]

        elapsed = time.time() - start_time

        if check_count > 0:
            time.sleep(wait_time)

        check_count += 1
        elapsed = time.time() - start_time

        try:
            list_result = client.call_tool(
                server_name='ghidra',
                tool_name='list_project_binaries',
                arguments={},
                timeout=30.0
            )

            log_mcp_execution(
                mcp_name='ghidra',
                tool_name='list_project_binaries',
                request={},
                response=list_result.get('result', ''),
                success=list_result.get('success', False),
                job_id=job_id
            )

            if job_id:
                from ..storage.job_storage import add_mcp_tool
                add_mcp_tool(job_id, 'ghidra', 'list_project_binaries', task_id)

            if not list_result.get('success'):
                continue

            result_text = list_result.get('result', '')
            try:
                programs_data = json.loads(result_text)
                programs = programs_data.get('programs', [])

                if not programs:
                    continue

                latest_program = programs[-1]
                binary_name = latest_program.get('name', '')
                analysis_complete = latest_program.get('analysis_complete', False)

                if analysis_complete:
                    return {
                        'binary_name': binary_name,
                        'elapsed': elapsed,
                        'checks': check_count
                    }

            except (json.JSONDecodeError, ValueError):
                continue

        except Exception as e:
            pass

    elapsed = time.time() - start_time
    return {
        'error': f'Ghidra analysis timeout after {elapsed:.1f}s ({check_count} checks)',
        'elapsed': elapsed,
        'checks': check_count
    }

