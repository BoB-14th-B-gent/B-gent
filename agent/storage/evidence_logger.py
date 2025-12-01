from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import csv
import io
import xml.etree.ElementTree as ET
from bson import ObjectId
from .job_storage import _get_client, add_mcp_tool, get_agent_state

def _parse_json_string(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None

def _parse_xml_to_dict(text: str) -> Optional[Dict[str, Any]]:
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
    return _parse_generic_response(response)

def _parse_generic_response(response: Any) -> Dict[str, Any]:
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
    elif isinstance(obj, ObjectId):
        return obj
    else:
        try:
            return str(obj)
        except Exception:
            return None

def _normalize_response(response: Any, mcp_name: str, tool_name: str) -> Dict[str, Any]:
    if mcp_name == "elastic":
        return _parse_elastic_response(response, tool_name)
    elif mcp_name == "velociraptor":
        return _parse_velociraptor_response(response, tool_name)
    elif mcp_name == "sleuthkit":
        return _parse_sleuthkit_response(response, tool_name)
    elif mcp_name == "ghidra":
        return _parse_ghidra_response(response, tool_name)

    return _parse_generic_response(response)

def _to_object_id_or_none(val: Any) -> Optional[ObjectId]:
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return None

def log_mcp_execution(
    mcp_name: str,
    tool_name: str,
    request: Dict[str, Any],
    response: Any,
    success: bool,
    stage: Optional[int] = None,
    job_id: Optional[str] = None
) -> bool:
    try:
        import sys
        import os
        debug_mode = os.getenv("DEBUG") == "1"

        db = _get_client()
        if db is None:
            if debug_mode:
                sys.__stdout__.write("[DEBUG evidence_logger] DB is None\n")
                sys.__stdout__.flush()
            return False

        trigger_raw: Optional[Any] = None
        conv_raw: Optional[Any] = None
        stage_id: Optional[int] = stage

        if job_id:
            try:
                state = get_agent_state(job_id)
            except Exception:
                state = None

            if state:
                trigger_raw = state.get("trigger_id")
                conv_raw = state.get("conversation_id")
                if stage_id is None:
                    stage_id = state.get("stage_id")

        trig_doc = None
        trigger_oid: Optional[ObjectId] = _to_object_id_or_none(trigger_raw)

        if trigger_oid:
            trig_doc = db.TRIGGERS.find_one({"_id": trigger_oid})

        if trig_doc:
            if conv_raw is None:
                conv_raw = trig_doc.get("conversation_id")
            if stage_id is None:
                stage_id = trig_doc.get("stage_id")

        if debug_mode:
            sys.__stdout__.write(
                f"[DEBUG evidence_logger] resolved trigger_raw={trigger_raw}, "
                f"conv_raw={conv_raw}, stage_id={stage_id}\n"
            )
            sys.__stdout__.flush()

        trigger_id_val = _to_object_id_or_none(trigger_raw)
        conversation_id_val = _to_object_id_or_none(conv_raw)

        normalized_response = _normalize_response(response, mcp_name, tool_name)

        evidence = {
            "mcp_name": mcp_name,
            "tool_name": tool_name,
            "trigger_id": trigger_id_val,
            "conversation_id": conversation_id_val,
            "agent_id": job_id,
            "stage_id": stage_id,
            "request": request,
            "response": normalized_response,
            "success": success,
            "created_at": datetime.utcnow(),
        }

        sanitized_evidence = _sanitize_for_mongodb(evidence)
        db.MCP_EVIDENCES.insert_one(sanitized_evidence)

        if debug_mode:
            sys.__stdout__.write("[DEBUG evidence_logger] MCP_EVIDENCES insert OK\n")
            sys.__stdout__.flush()

        if job_id and success:
            add_mcp_tool(job_id, mcp_name, tool_name)

        return True

    except Exception as e:
        import traceback, sys
        sys.__stdout__.write(f"[X] log_mcp_execution failed: {e}\n")
        sys.__stdout__.write(f"[X] Traceback:\n{traceback.format_exc()}\n")
        sys.__stdout__.flush()
        return False