"""MCP 실행 로깅 모듈

MCP 도구 호출 결과를 MongoDB MCP_EVIDENCES 컬렉션에 저장
"""
from __future__ import annotations
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import csv
import io
import xml.etree.ElementTree as ET
from .job_storage import _get_client, add_mcp_tool


def _parse_json_string(text: str) -> Optional[Any]:
    """JSON 문자열 파싱 시도"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_xml_to_dict(text: str) -> Optional[Dict[str, Any]]:
    """XML 문자열을 dict로 변환"""
    try:
        def etree_to_dict(element: ET.Element) -> Dict[str, Any]:
            result = {element.tag: {} if element.attrib else None}
            children = list(element)

            if children:
                child_dict: Dict[str, Any] = {}
                for child in children:
                    child_data = etree_to_dict(child)
                    for key, value in child_data.items():
                        if key in child_dict:
                            if not isinstance(child_dict[key], list):
                                child_dict[key] = [child_dict[key]]
                            child_dict[key].append(value)
                        else:
                            child_dict[key] = value
                result = {element.tag: child_dict}

            if element.attrib:
                result[element.tag].update(('@' + k, v) for k, v in element.attrib.items())

            if element.text:
                text_content = element.text.strip()
                if children or element.attrib:
                    if text_content:
                        result[element.tag]['#text'] = text_content
                else:
                    result[element.tag] = text_content

            return result

        root = ET.fromstring(text)
        return etree_to_dict(root)
    except (ET.ParseError, Exception):
        return None


def _parse_csv_to_list(text: str) -> Optional[List[Dict[str, Any]]]:
    """CSV 문자열을 list of dict로 변환"""
    try:
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            return None

        sample = "\n".join(lines[:min(10, len(lines))])
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=",\t")
            has_header = sniffer.has_header(sample)
        except Exception:
            dialect = csv.excel
            has_header = True

        buf = io.StringIO("\n".join(lines))

        if has_header:
            reader = csv.DictReader(buf, dialect=dialect)
            return [
                {k: v for k, v in row.items() if k is not None}
                for row in reader
            ]
        else:
            reader = csv.reader(buf, dialect=dialect)
            rows = list(reader)
            if not rows:
                return None
            max_cols = max(len(row) for row in rows)
            headers = [f"c{i}" for i in range(max_cols)]
            return [
                {headers[i]: (row[i] if i < len(row) else None) for i in range(max_cols)}
                for row in rows
            ]
    except Exception:
        return None


def _parse_space_separated_table(text: str) -> Optional[List[Dict[str, Any]]]:
    """공백으로 구분된 테이블을 파싱 (Elasticsearch _cat API 등)

    Args:
        text: 공백 구분 테이블 텍스트

    Returns:
        List[Dict]: 파싱된 데이터 또는 None
    """
    try:
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 1:
            return None

        result = []
        for line in lines:
            values = line.split()
            if len(values) >= 3:  
                row = {
                    "health": values[0] if len(values) > 0 else None,
                    "status": values[1] if len(values) > 1 else None,
                    "index": values[2] if len(values) > 2 else None,
                }
                if len(values) > 3:
                    row["uuid"] = values[3]
                if len(values) > 4:
                    row["pri"] = values[4]
                if len(values) > 5:
                    row["rep"] = values[5]
                if len(values) > 6:
                    row["docs.count"] = values[6]
                if len(values) > 7:
                    row["docs.deleted"] = values[7]
                if len(values) > 8:
                    row["store.size"] = values[8]
                if len(values) > 9:
                    row["pri.store.size"] = values[9]

                result.append(row)

        return result if result else None
    except Exception:
        return None


def _parse_elastic_response(response: Any, tool_name: str) -> Dict[str, Any]:
    """Elasticsearch MCP 응답 파싱"""
    if isinstance(response, dict):
        return response

    if isinstance(response, str):
        text = response.strip()

        if not text:
            return {"type": "empty", "raw": ""}

        parsed_json = _parse_json_string(text)
        if parsed_json is not None:
            if isinstance(parsed_json, dict):
                return parsed_json
            elif isinstance(parsed_json, list):
                return {"type": "list", "data": parsed_json, "count": len(parsed_json)}
            elif isinstance(parsed_json, str):
                text = parsed_json
            else:
                return {"type": "json", "data": parsed_json}

        if tool_name in ["list_indices"] or "_cat" in tool_name.lower():
            parsed_table = _parse_space_separated_table(text)
            if parsed_table is not None:
                return {
                    "type": "table",
                    "data": parsed_table,
                    "count": len(parsed_table)
                }

        return {"type": "string", "raw": text, "length": len(text)}

    return _parse_generic_response(response)


def _parse_velociraptor_response(response: Any, tool_name: str) -> Dict[str, Any]:
    """Velociraptor MCP 응답 파싱"""
    if isinstance(response, dict):
        return response

    if isinstance(response, str):
        text = response.strip()

        if not text:
            return {"type": "empty", "raw": ""}

        parsed_json = _parse_json_string(text)
        if parsed_json is not None:
            if isinstance(parsed_json, dict):
                return parsed_json
            elif isinstance(parsed_json, list):
                return {"type": "list", "data": parsed_json, "count": len(parsed_json)}
            elif isinstance(parsed_json, str):
                text = parsed_json
            else:
                return {"type": "json", "data": parsed_json}

        if text.startswith("[") and text.endswith("]"):
            try:
                import ast
                parsed_list = ast.literal_eval(text)
                if isinstance(parsed_list, list):
                    return {
                        "type": "list",
                        "data": parsed_list,
                        "count": len(parsed_list)
                    }
            except (ValueError, SyntaxError):
                pass

        return {"type": "string", "raw": text, "length": len(text)}

    if isinstance(response, list):
        return {
            "type": "list",
            "data": response,
            "count": len(response)
        }

    return _parse_generic_response(response)


def _parse_sleuthkit_response(response: Any, tool_name: str) -> Dict[str, Any]:
    """Sleuthkit MCP 응답 파싱"""
    if isinstance(response, str):
        text = response.strip()

        if not text:
            return {"type": "empty", "raw": ""}

        parsed_json = _parse_json_string(text)
        if parsed_json is not None:
            if isinstance(parsed_json, dict):
                return parsed_json
            elif isinstance(parsed_json, list):
                return {"type": "list", "data": parsed_json, "count": len(parsed_json)}
            else:
                return {"type": "json", "data": parsed_json}

        return {"type": "string", "raw": text, "length": len(text)}

    if isinstance(response, dict):
        return response

    return _parse_generic_response(response)


def _parse_ghidra_response(response: Any, tool_name: str) -> Dict[str, Any]:
    """Ghidra MCP 응답 파싱 (추후 구현)"""
    return _parse_generic_response(response)


def _parse_generic_response(response: Any) -> Dict[str, Any]:
    """범용 response 파서

    Args:
        response: MCP 도구 실행 결과 (다양한 타입 가능)

    Returns:
        Dict: 정규화된 JSON 구조

    처리 우선순위:
        1. 이미 dict → 그대로 반환
        2. list → {"type": "list", "data": [...]}
        3. 문자열 → JSON 파싱 시도, 실패하면 그대로 문자열로 저장
        4. 기타 → {"type": "...", "raw": "..."}
    """
    if isinstance(response, dict):
        return response

    if isinstance(response, list):
        return {
            "type": "list",
            "data": response,
            "count": len(response)
        }

    if isinstance(response, str):
        text = response.strip()

        if not text:
            return {"type": "empty", "raw": ""}

        parsed_json = _parse_json_string(text)
        if parsed_json is not None and isinstance(parsed_json, (dict, list)):
            if isinstance(parsed_json, dict):
                return parsed_json
            else:
                return {"type": "json", "data": parsed_json}

        return {
            "type": "string",
            "raw": text,
            "length": len(text)
        }

    if response is None:
        return {"type": "null", "raw": None}

    if isinstance(response, (int, float, bool)):
        return {"type": type(response).__name__, "value": response}

    return {
        "type": type(response).__name__,
        "raw": str(response)
    }


def _sanitize_for_mongodb(obj: Any) -> Any:
    """MongoDB에 저장하기 위해 document를 정리

    Args:
        obj: 정리할 객체 (dict, list, 기타)

    Returns:
        정리된 객체 (None 키 제거, 재귀적 처리)
    """
    if isinstance(obj, dict):
        return {
            (str(k) if k is not None else "_none_key_"): _sanitize_for_mongodb(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [_sanitize_for_mongodb(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, datetime):
        return obj
    else:
        try:
            return str(obj)
        except Exception:
            return None


def _normalize_response(response: Any, mcp_name: str, tool_name: str) -> Dict[str, Any]:
    """MCP별 커스텀 파싱을 적용한 response 정규화

    Args:
        response: MCP 도구 실행 결과
        mcp_name: MCP 서버 이름
        tool_name: 도구 이름

    Returns:
        Dict: 정규화된 JSON 구조
    """
    if mcp_name == "elastic":
        return _parse_elastic_response(response, tool_name)
    elif mcp_name == "velociraptor":
        return _parse_velociraptor_response(response, tool_name)
    elif mcp_name == "sleuthkit":
        return _parse_sleuthkit_response(response, tool_name)
    elif mcp_name == "ghidra":
        return _parse_ghidra_response(response, tool_name)

    return _parse_generic_response(response)


def log_mcp_execution(
    mcp_name: str,
    tool_name: str,
    request: Dict[str, Any],
    response: Any,
    success: bool,
    stage: Optional[int] = None,
    job_id: Optional[str] = None
) -> bool:
    """MCP 도구 실행 결과를 MongoDB에 저장

    Args:
        mcp_name: MCP 서버 이름 (elastic, velociraptor, sleuthkit, ghidra)
        tool_name: 사용된 도구 이름
        request: 도구에 전달된 파라미터
        response: 도구 실행 결과 데이터
        success: 실행 성공 여부
        stage: 스테이지 번호 (선택사항)
        job_id: Job ID (선택사항, AGENT_STATES 업데이트용)

    Returns:
        bool: 저장 성공 여부
    """
    try:
        import sys
        import os
        debug_mode = os.getenv("DEBUG") == "1"

        if debug_mode:
            sys.__stdout__.write(f"[DEBUG evidence_logger] Starting log_mcp_execution for {mcp_name}.{tool_name}\n")
            sys.__stdout__.flush()

        db = _get_client()
        if db is None:
            if debug_mode:
                sys.__stdout__.write(f"[DEBUG evidence_logger] DB connection is None!\n")
                sys.__stdout__.flush()
            return False

        if debug_mode:
            sys.__stdout__.write(f"[DEBUG evidence_logger] Normalizing response...\n")
            sys.__stdout__.flush()

        normalized_response = _normalize_response(response, mcp_name, tool_name)

        if debug_mode:
            sys.__stdout__.write(f"[DEBUG evidence_logger] Creating evidence document...\n")
            sys.__stdout__.flush()

        evidence = {
            "stage": stage,
            "mcp_name": mcp_name,
            "tool_name": tool_name,
            "request": request,
            "response": normalized_response,
            "success": success,
            "timestamp": datetime.utcnow()
        }

        if debug_mode:
            sys.__stdout__.write(f"[DEBUG evidence_logger] Sanitizing document for MongoDB...\n")
            sys.__stdout__.flush()

        sanitized_evidence = _sanitize_for_mongodb(evidence)

        if debug_mode:
            sys.__stdout__.write(f"[DEBUG evidence_logger] Inserting to MongoDB...\n")
            sys.__stdout__.flush()

        db.MCP_EVIDENCES.insert_one(sanitized_evidence)

        if debug_mode:
            sys.__stdout__.write(f"[DEBUG evidence_logger] MongoDB insert successful!\n")
            sys.__stdout__.flush()

        if job_id and success:
            add_mcp_tool(job_id, mcp_name, tool_name)

        return True

    except Exception as e:
        import sys
        import traceback
        sys.__stdout__.write(f"[X]  MCP 실행 로그 저장 실패: {e}\n")
        sys.__stdout__.write(f"[X]  Traceback:\n{traceback.format_exc()}\n")
        sys.__stdout__.flush()
        print(f"[X]  MCP 실행 로그 저장 실패: {e}")
        return False
