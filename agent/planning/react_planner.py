"""ReAct Think 단계 (LangGraph 노드용)

LLM이 현재 상황을 분석하고 다음 액션을 결정하는 모듈
"""
from __future__ import annotations
import json
import re
import os
from typing import Dict, Any, List, Optional
from ..llm_client.client import LLMClient
from ..llm_client.rag import query_mcp_candidates
from ..utils.prompt_loader import load_prompt
from ..utils.debug import debug_print, debug_write, debug_error, is_debug_mode
from ..config import get_config

_strategy_prompt_cache: Dict[str, Optional[str]] = {}


def _load_strategy_prompt(server_name: str) -> Optional[str]:
    """MCP 서버별 strategy 프롬프트 로드 (캐시 사용)

    Args:
        server_name: MCP 서버 이름 (예: "browser-db-parser", "sleuthkit")

    Returns:
        Optional[str]: strategy 프롬프트 내용, 파일이 없으면 None
    """
    global _strategy_prompt_cache

    if not server_name:
        return None

    if server_name in _strategy_prompt_cache:
        return _strategy_prompt_cache[server_name]

    strategies_dir = os.path.join(os.path.dirname(__file__), "..", "prompts", "strategies")
    strategy_path = os.path.join(strategies_dir, f"{server_name}.md")

    try:
        if os.path.exists(strategy_path):
            with open(strategy_path, "r", encoding="utf-8") as f:
                content = f.read()
                debug_write(f"│ [Strategy] Loaded {server_name}.md\n")
                _strategy_prompt_cache[server_name] = content
                return content
    except Exception as e:
        debug_error(f"│ [!] Strategy 프롬프트 로드 실패 ({server_name}): {e}\n")

    _strategy_prompt_cache[server_name] = None
    return None


def _repair_json(json_str: str) -> str:
    """LLM이 생성한 잘못된 JSON을 복구하는 함수

    다양한 일반적인 JSON 오류 패턴을 수정합니다.
    """
    if not json_str:
        return json_str

    original = json_str

    def escape_newlines_in_strings(s):
        result = []
        in_string = False
        escape_next = False
        i = 0
        while i < len(s):
            char = s[i]
            if escape_next:
                result.append(char)
                escape_next = False
            elif char == '\\':
                result.append(char)
                escape_next = True
            elif char == '"':
                result.append(char)
                in_string = not in_string
            elif char == '\n' and in_string:
                result.append('\\n')
            elif char == '\r' and in_string:
                result.append('\\r')
            elif char == '\t' and in_string:
                result.append('\\t')
            else:
                result.append(char)
            i += 1
        return ''.join(result)

    json_str = escape_newlines_in_strings(json_str)

    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)

    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)

    json_str = re.sub(r'"\s*"\s*"', '", "', json_str)
    json_str = re.sub(r'}\s*"', '}, "', json_str)
    json_str = re.sub(r']\s*"', '], "', json_str)
    json_str = re.sub(r'(true|false|null)\s*"', r'\1, "', json_str)
    json_str = re.sub(r'(\d)\s*"', r'\1, "', json_str)

    json_str = re.sub(r'"([^"]*)"(\s+)"', r'"\1",\2"', json_str)

    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')

    if open_braces > close_braces:
        json_str = json_str.rstrip() + '}' * (open_braces - close_braces)
    if open_brackets > close_brackets:
        json_str = json_str.rstrip() + ']' * (open_brackets - close_brackets)

    first_brace = json_str.find('{')
    if first_brace > 0:
        json_str = json_str[first_brace:]

    last_brace = json_str.rfind('}')
    if last_brace != -1 and last_brace < len(json_str) - 1:
        json_str = json_str[:last_brace + 1]

    json_str = re.sub(r',\s*,', ',', json_str)

    json_str = re.sub(r':\s*,', ': null,', json_str)
    json_str = re.sub(r':\s*}', ': null}', json_str)

    if json_str != original:
        debug_print(f"│ [JSON REPAIR] Applied fixes to malformed JSON")

    return json_str


def generate_react_thought(
    task_description: str,
    observations: List[Dict[str, Any]],
    available_tools: List[Dict[str, Any]],
    file_paths: List[str] = None,
    max_iterations: int = 30,
    user_prompt: str = None,
    mcp_call: Dict[str, Any] = None,
    server_hint: str = None
) -> Dict[str, Any]:
    """ReAct Think 단계: LLM이 다음 행동 결정

    Args:
        task_description: Task 설명
        observations: 이전 관찰 결과 리스트
        available_tools: 사용 가능한 MCP 도구 목록
        file_paths: 파일 경로 리스트
        max_iterations: 최대 반복 횟수
        user_prompt: 원본 사용자 쿼리 (선택)
        mcp_call: 필수 MCP 호출 정보 (server, operation, params_hint)
        server_hint: High-level plan에서 지정한 MCP 서버 이름 (strategy 프롬프트 로드용)

    Returns:
        Dict:
            - finished: 완료 여부 (bool)
            - thought: 현재 생각 (str)
            - action: 다음 액션 (dict) or None
            - answer: 최종 답변 (str, finished=True일 때만)
    """
    llm = LLMClient()
    current_iteration = len(observations) + 1

    consecutive_no_action = 0
    for obs in reversed(observations):
        action = obs.get("action", {})
        if not action or not action.get("tool") or not action.get("operation"):
            consecutive_no_action += 1
        else:
            break

    if consecutive_no_action >= 3:
        debug_write(f"\n[ReAct] 연속 {consecutive_no_action}회 action 생성 실패 → 강제 종료\n")
        return {
            "finished": True,
            "thought": f"Failed to generate valid action after {consecutive_no_action} consecutive attempts",
            "action": None,
            "answer": f"Analysis stopped: Could not generate valid MCP tool calls after {consecutive_no_action} attempts. Please check tool availability and task description."
        }

    if observations:
        error_message_counts = {}
        file_not_found_count = 0
        file_not_found_path = ""

        for obs in observations:
            success = obs.get("success", False)
            if not success:
                observation_text = obs.get("observation", "")

                if "FILE NOT FOUND" in observation_text or "file not found" in observation_text.lower():
                    file_not_found_count += 1
                    if "Path provided:" in observation_text:
                        try:
                            path_line = [l for l in observation_text.split("\n") if "Path provided:" in l][0]
                            file_not_found_path = path_line.split("Path provided:")[-1].strip()
                        except:
                            pass

                if "Error:" in observation_text:
                    error_key = observation_text.split("\n")[0][:100]
                    error_message_counts[error_key] = error_message_counts.get(error_key, 0) + 1

        if file_not_found_count >= 2:
            debug_write(f"\n[ReAct] FILE NOT FOUND {file_not_found_count}회 반복 → 즉시 종료\n")
            debug_write(f"[ReAct] Path: {file_not_found_path}\n")
            return {
                "finished": True,
                "thought": f"File not found error repeated {file_not_found_count} times - file does not exist",
                "action": None,
                "answer": f"Analysis stopped: The specified file was not found after {file_not_found_count} attempts.\n\n"
                         f"File path: {file_not_found_path}\n\n"
                         f"Please verify:\n"
                         f"1. The file exists at the specified path\n"
                         f"2. The file path is correct (absolute path recommended)\n"
                         f"3. The file is accessible (check permissions)\n"
                         f"4. For E01/DD images, ensure the forensic image file is properly placed"
            }

        for error_key, count in error_message_counts.items():
            if count >= 4:
                debug_write(f"\n[ReAct] 동일 오류 {count}회 반복 → 강제 종료\n")
                debug_write(f"[ReAct] Error: {error_key}\n")
                return {
                    "finished": True,
                    "thought": f"Same error repeated {count} times - cannot resolve",
                    "action": None,
                    "answer": f"Analysis stopped: The same error occurred {count} times. Error: {error_key}. This indicates a fundamental issue that cannot be resolved by retrying. Please check if the required files/resources exist."
                }

    system_prompt = _build_system_prompt(available_tools, observations, server_hint)

    messages = _build_conversation_context(
        task_description,
        observations,
        file_paths,
        current_iteration,
        max_iterations,
        user_prompt,
        mcp_call
    )

    if messages and messages[0]["role"] == "user":
        messages[0]["content"] = f"{system_prompt}\n\n{messages[0]['content']}"

    try:
        import sys
        response = llm.chat(
            messages,
            response_format_json=True,
            timeout=180,
            max_tokens=2048
        )

        content = response["choices"][0]["message"]["content"]

        if is_debug_mode():
            debug_write(f"\n[DEBUG] LLM Response (iteration {current_iteration}):\n")
            debug_write(f"{content[:500]}...\n" if len(content) > 500 else f"{content}\n")

        result = _parse_llm_response(content, current_iteration, max_iterations)

        if current_iteration == 1 and not result.get("action"):
            debug_write(f"\n[ENFORCE] Iteration 1 requires tool call - forcing fallback\n")
            result["finished"] = False

        if not result.get("action") and not result.get("finished"):
            server = ""
            operation = ""
            params_hint = {}

            if mcp_call:
                server = mcp_call.get("server", "")
                operation = mcp_call.get("operation", "")
                params_hint = mcp_call.get("params_hint", {})

            if not server and server_hint:
                server = server_hint

            if server and not operation:
                default_operations = {
                    "consolehost-history": "extract_consolehost_history",
                    "lnk-parser": "auto_extract_and_parse_lnk",
                    "dissect": "list_artifact_plugins",
                    "browser-db-parser": "parse_history",
                    "sleuthkit": "disk_info",
                    "virustotal": "check_hash",
                    "ghidra": "import_binary",
                    "elastic": "list_indices",
                }
                operation = default_operations.get(server, "")

            if server and operation:
                params = {}
                for key, hint in params_hint.items():
                    if file_paths and ("path" in key.lower() or "file" in key.lower() or "image" in key.lower()):
                        params[key] = file_paths[0]
                    else:
                        params[key] = hint

                if file_paths and not params:
                    if server == "consolehost-history":
                        params["image_path"] = file_paths[0]
                        params["output_dir"] = "./data/output/consolehost"
                    elif server in ["lnk-parser", "dissect", "sleuthkit"]:
                        params["image_path"] = file_paths[0]
                    elif server == "browser-db-parser":
                        params["history_file_path"] = file_paths[0]
                    elif server == "ghidra":
                        params["binary_path"] = file_paths[0]

                result["action"] = {
                    "tool": server,
                    "operation": operation,
                    "params": params
                }
                result["finished"] = False
                result["thought"] = f"Using fallback: {server}.{operation}"

                debug_write(f"│ [Fallback] Auto-generated action: {server}.{operation}\n")

        return result

    except TimeoutError as e:
        debug_error(f"│ [[X]] ReAct Think 타임아웃 (순환 참조 가능성) → 작업 종료\n")
        return {
            "finished": True,
            "thought": f"LLM timeout - possible circular dependency",
            "action": None,
            "answer": f"Analysis terminated due to LLM timeout (possible circular API reference). Please check LLM configuration."
        }

    except Exception as e:
        error_str = str(e).lower()
        if "timeout" in error_str or "recursion" in error_str or "connection" in error_str:
            debug_error(f"│ [[X]] ReAct Think 연결 실패 (순환 참조/타임아웃): {e}\n")
        else:
            debug_error(f"│ [[X]] ReAct Think 실패: {e}\n")
        return {
            "finished": True,
            "thought": f"Error during thinking: {str(e)}",
            "action": None,
            "answer": f"Analysis failed due to LLM error: {str(e)}"
        }


def _build_system_prompt(available_tools: List[Dict[str, Any]], observations: List[Dict[str, Any]] = None, server_hint: str = None) -> str:
    """시스템 프롬프트 생성

    Args:
        available_tools: 사용 가능한 MCP 도구 목록
        observations: 이전 관찰 결과 리스트
        server_hint: High-level plan에서 지정한 MCP 서버 이름 (strategy 프롬프트 로드용)

    Returns:
        완전한 시스템 프롬프트 (base + tools + strategy)
    """
    tools_desc_list = []
    for tool in available_tools[:50]:
        server = tool['server']
        tool_name = tool['tool_name']
        desc = tool.get('description', 'No description')
        schema = tool.get('input_schema', {})

        required_params = schema.get('required', []) if isinstance(schema, dict) else []
        properties = schema.get('properties', {}) if isinstance(schema, dict) else {}

        param_desc = ""
        if properties:
            import json as json_module
            schema_json = json_module.dumps(schema, ensure_ascii=False, separators=(',', ':'))
            param_desc = f"\n  Schema: {schema_json}"
        elif required_params:
            param_list = []
            for param in required_params:
                param_info = properties.get(param, {})
                param_type = param_info.get('type', 'any')
                param_list.append(f"{param} ({param_type})")
            param_desc = f" | Required: {', '.join(param_list)}"

        tools_desc_list.append(f"- {server}.{tool_name}: {desc}{param_desc}")

    tools_desc = "\n".join(tools_desc_list) if tools_desc_list else "No tools available"

    from ..utils.prompt_loader import format_prompt
    base_prompt = format_prompt("react_think_system.txt", tools_description=tools_desc)

    if server_hint:
        strategy_prompt = _load_strategy_prompt(server_hint)
        if strategy_prompt:
            base_prompt += f"\n\n---\n## MCP Server Strategy Guide ({server_hint})\n\n{strategy_prompt}"

    return base_prompt


def _build_conversation_context(
    task_description: str,
    observations: List[Dict[str, Any]],
    file_paths: List[str],
    current_iteration: int,
    max_iterations: int,
    user_prompt: str = None,
    mcp_call: Dict[str, Any] = None
) -> List[Dict[str, str]]:
    """대화 컨텍스트 생성"""
    config = get_config()
    obs_config = config.observation

    messages = []

    user_message = ""

    if user_prompt and user_prompt.strip():
        user_message += f"**Original User Query:** {user_prompt}\n\n"

    user_message += f"**Task:** {task_description}\n\n"

    if mcp_call and current_iteration == 1:
        server = mcp_call.get("server", "")
        operation = mcp_call.get("operation", "")
        params_hint = mcp_call.get("params_hint", {})
        user_message += f"**REQUIRED MCP CALL (YOU MUST USE THIS):**\n"
        user_message += f"  - Server: {server}\n"
        user_message += f"  - Operation: {operation}\n"
        if params_hint:
            user_message += f"  - Parameters: {json.dumps(params_hint, ensure_ascii=False)}\n"
        user_message += f"\n**IMPORTANT:** Call {server}.{operation} as your FIRST action!\n\n"

    if file_paths:
        clean_paths = [f.rstrip(',').strip() for f in file_paths if f is not None]
        file_list = '\n'.join(f'  - "{f}"' for f in clean_paths)
        user_message += f"**Files (COPY THESE EXACT PATHS - NO trailing commas!):**\n{file_list}\n\n"

    user_message += f"**Iteration:** {current_iteration}/{max_iterations}\n\n"

    if observations:
        if obs_config.include_action_summary:
            user_message += "**Action History Summary:**\n"
            tried_actions = {}
            for obs in observations:
                action = obs.get("action", {})
                success = obs.get("success", False)
                action_name = f"{action.get('tool', '')}.{action.get('operation', '')}"

                if action_name not in tried_actions:
                    tried_actions[action_name] = {"success": 0, "failed": 0, "iterations": []}

                if success:
                    tried_actions[action_name]["success"] += 1
                else:
                    tried_actions[action_name]["failed"] += 1

                tried_actions[action_name]["iterations"].append(obs.get("iteration", 0))

            for action_name, stats in tried_actions.items():
                status_icon = "[OK]" if stats["success"] > 0 else "[X]"
                user_message += f"- {status_icon} {action_name}: {stats['success']} successful, {stats['failed']} failed (iterations: {', '.join(map(str, stats['iterations']))})\n"

        max_obs = obs_config.max_observations
        max_result_len = obs_config.max_result_length
        recent_observations = observations[-max_obs:]

        excluded_count = len(observations) - len(recent_observations)
        if excluded_count > 0:
            user_message += f"\n*({excluded_count} older observations omitted)*\n"

        user_message += "\n**Previous Observations (Iteration 1 = most recent MCP tool result):**\n\n"

        reversed_obs = list(reversed(recent_observations))
        for display_idx, obs in enumerate(reversed_obs, start=1):
            thought = obs.get("thought", "")
            action = obs.get("action", {})
            observation = obs.get("observation", "")

            action_name = f"{action.get('tool', '')}.{action.get('operation', '')}"

            user_message += f"**Iteration {display_idx}:**\n"
            user_message += f"- Thought: {thought}\n"
            user_message += f"- Action: {action_name}\n"
            user_message += f"- Result: {observation[:max_result_len]}{'...' if len(observation) > max_result_len else ''}\n\n"

            if obs.get("iteration", 0) == 1 and action.get('operation') == 'import_binary':
                if is_debug_mode():
                    debug_write(f"\n[DEBUG] import_binary observation:\n{observation}\n\n")

        if len(observations) >= 2:
            recent_actions = []
            for obs in observations[-3:]:
                action = obs.get("action", {})
                action_sig = f"{action.get('tool')}.{action.get('operation')}:{json.dumps(action.get('params'), sort_keys=True)}"
                recent_actions.append(action_sig)

            if len(recent_actions) >= 2 and recent_actions[-1] == recent_actions[-2]:
                user_message += "\n⚠️ **WARNING**: You just repeated the same action. The previous result contains all the data you need. Analyze it carefully and either:\n"
                user_message += "1. Use a different tool/operation to get additional data, OR\n"
                user_message += "2. Finish the task with your analysis of the existing data\n\n"

        if len(observations) >= 2:
            error_message_counts = {}
            for obs in observations:
                success = obs.get("success", False)
                if not success:
                    observation_text = obs.get("observation", "")
                    if "Error:" in observation_text:
                        error_key = observation_text.split("\n")[0][:100]  # 첫 줄만
                        error_message_counts[error_key] = error_message_counts.get(error_key, 0) + 1

            for error_key, count in error_message_counts.items():
                if count >= 3:
                    user_message += f"\n🚨 **SAME ERROR REPEATED {count} TIMES**:\n"
                    user_message += f"Error: {error_key}\n\n"
                    user_message += "**The underlying issue is NOT being resolved by retrying.**\n"
                    user_message += "**STOP and FINISH the task with an explanation of what went wrong.**\n\n"

        if len(observations) >= 3:
            failure_counts = {}
            for obs in observations:
                action = obs.get("action", {})
                success = obs.get("success", False)

                if not success:
                    action_sig = f"{action.get('tool')}.{action.get('operation')}:{json.dumps(action.get('params'), sort_keys=True)}"
                    failure_counts[action_sig] = failure_counts.get(action_sig, 0) + 1

            for action_sig, count in failure_counts.items():
                if count >= 3:
                    try:
                        tool_operation, params_json = action_sig.split(":", 1)
                        tool_name, operation_name = tool_operation.split(".", 1)
                        params = json.loads(params_json)

                        user_message += f"\n🚨 **CRITICAL ERROR - REPEATED FAILURE DETECTED**:\n"
                        user_message += f"You have tried '{tool_name}.{operation_name}' with the same parameters {count} times and it FAILED every time.\n"
                        user_message += f"Failed operation: {operation_name}\n"
                        user_message += f"Failed parameters: {params}\n\n"
                        user_message += "**YOU MUST STOP TRYING THIS APPROACH!**\n\n"
                        user_message += "**Required Actions:**\n"
                        user_message += "1. DO NOT call this tool with these parameters again\n"
                        user_message += "2. Try a DIFFERENT tool or operation\n"
                        user_message += "3. If no alternative exists, FINISH with the data you already have\n"
                        user_message += "4. Analyze why this failed and choose a completely different approach\n\n"

                    except (ValueError, json.JSONDecodeError):
                        pass

        user_message += "**What should you do next?**\n"
    else:
        user_message += "**Start your analysis. What's your first step?**\n"

    messages.append({"role": "user", "content": user_message})

    return messages


def _parse_llm_response(content: str, current_iteration: int, max_iterations: int) -> Dict[str, Any]:
    """LLM 응답 파싱"""
    json_str = None

    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        json_str = content[start:end].strip()
    elif "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        json_str = content[start:end].strip()
    else:
        json_str = content.strip()

    try:
        json_str = _repair_json(json_str)

        if json_str and '"finished"' not in json_str:
            if json_str.rstrip().endswith('}'):
                json_str = json_str.rstrip()[:-1] + ', "finished": false}'
                debug_print(f"│ [FIX] Added missing 'finished' field")

        parsed = None
        parse_error = None

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            parse_error = e
            debug_print(f"│ [!] 첫 번째 파싱 실패: {e}")

            try:
                fallback_str = ' '.join(json_str.split())
                fallback_str = _repair_json(fallback_str)
                parsed = json.loads(fallback_str)
                debug_print(f"│ [OK] 재시도 파싱 성공")
            except json.JSONDecodeError as e2:
                try:
                    thought_match = re.search(r'"thought"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', json_str)
                    finished_match = re.search(r'"finished"\s*:\s*(true|false)', json_str, re.IGNORECASE)
                    answer_match = re.search(r'"answer"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', json_str)

                    if thought_match or answer_match:
                        reconstructed = {
                            "thought": thought_match.group(1) if thought_match else "Parsing recovered",
                            "finished": finished_match.group(1).lower() == "true" if finished_match else True,
                            "action": None
                        }
                        if answer_match:
                            reconstructed["answer"] = answer_match.group(1)
                        parsed = reconstructed
                        debug_print(f"│ [OK] JSON 재구성 성공")
                    else:
                        raise e2
                except Exception:
                    debug_print(f"│ [X] JSON 파싱 최종 실패: {parse_error}")
                    debug_print(f"│ Raw JSON (first 500 chars): {json_str[:500]}")
                    return {
                        "finished": True,
                        "thought": f"Failed to parse LLM response: invalid JSON",
                        "action": None,
                        "answer": f"Analysis failed due to LLM response parsing error: {str(parse_error)}"
                    }

        if not isinstance(parsed, dict):
            debug_print(f"│ [X] LLM 응답이 dict가 아님: {type(parsed)}")
            return {
                "finished": True,
                "thought": "Invalid response format",
                "action": None,
                "answer": "Analysis failed: LLM response is not a valid dictionary"
            }

        if 'thought' not in parsed:
            parsed['thought'] = "No thought provided"

        if 'finished' not in parsed:
            parsed['finished'] = False

        if 'action' in parsed and isinstance(parsed['action'], dict):
            if 'finished' in parsed['action']:
                if 'finished' not in parsed:
                    parsed['finished'] = parsed['action'].pop('finished')
                else:
                    parsed['action'].pop('finished')

            internal_fields = {'finished', 'thought', 'answer'}
            if 'params' in parsed['action'] and isinstance(parsed['action']['params'], dict):
                for field in internal_fields:
                    if field in parsed['action']['params']:
                        parsed['action']['params'].pop(field)
                        debug_print(f"│ [FIX] Removed '{field}' from action.params")

        if not parsed.get('finished', False):
            if 'action' not in parsed or parsed['action'] is None:
                debug_print(f"│ [[X]] finished=False이지만 action이 없음")
                parsed['finished'] = True
                if 'answer' not in parsed:
                    parsed['answer'] = "No action provided - task cannot continue"

            elif isinstance(parsed['action'], dict):
                if 'tool' not in parsed['action'] or 'operation' not in parsed['action']:
                    debug_print(f"│ [[X]] Action에 tool 또는 operation 필드 없음. Keys: {list(parsed['action'].keys())}")
                    parsed['finished'] = True
                    parsed['answer'] = "Invalid action format: missing tool or operation"
                    parsed['action'] = None

        thought = parsed.get("thought", "")
        finished = parsed.get("finished", False)

        if current_iteration >= max_iterations:
            return {
                "finished": True,
                "thought": thought or "Maximum iterations reached",
                "action": None,
                "answer": parsed.get("answer", "Analysis incomplete - reached maximum iterations")
            }

        if finished:
            answer = parsed.get("answer", "No answer provided")

            import sys
            import os
            is_early_termination = False

            if current_iteration <= 3:
                tool_unavailable_patterns = [
                    "no tool", "tool not found", "missing tool", "unavailable tool",
                    "no mcp", "mcp not found", "no operation", "operation not found",
                    "don't have access to", "do not have access to",
                    "lack of tool", "no suitable tool", "tool doesn't exist",
                    "cannot find tool", "unable to find tool"
                ]

                file_path_patterns = [
                    "file not found", "file does not exist", "path not found",
                    "unable to locate", "cannot locate", "image not found",
                    "no such file", "file is missing", "path does not exist",
                    "cannot access file", "unable to access", "file path",
                    "specified path", "invalid path", ".e01", ".dd", ".raw"
                ]

                answer_lower = answer.lower() if answer else ""
                thought_lower = thought.lower() if thought else ""
                combined_text = answer_lower + " " + thought_lower

                is_file_path_issue = any(
                    pattern in combined_text for pattern in file_path_patterns
                )

                if not is_file_path_issue:
                    is_early_termination = any(
                        pattern in combined_text for pattern in tool_unavailable_patterns
                    )

                if is_early_termination:
                    debug_write(f"\n[WARNING] Early termination BLOCKED at iteration {current_iteration}\n")
                    debug_write(f"[WARNING] LLM claims tools unavailable but they ARE available\n")
                    debug_write(f"[WARNING] Thought: {thought[:100]}...\n")
                    debug_write(f"[WARNING] Forcing retry - returning finished=False to trigger re-think\n")

                    return {
                        "finished": False,
                        "thought": f"[RETRY FORCED] Previous attempt incorrectly claimed tools unavailable. Available tools exist - retrying. Original: {thought[:200]}",
                        "action": None,
                        "answer": None
                    }

                if is_file_path_issue:
                    debug_write(f"\n[INFO] File/path issue detected at iteration {current_iteration}\n")
                    debug_write(f"[INFO] Thought: {thought[:100]}...\n")
                    debug_write(f"[INFO] This is a valid termination reason - file may not exist\n")

            if is_debug_mode():
                debug_write(f"\n[DEBUG] ReAct finished at iteration {current_iteration}\n")
                debug_write(f"[DEBUG] Thought: {thought[:200] if thought else 'None'}\n")
                debug_write(f"[DEBUG] Answer: {answer[:200] if answer else 'None'}\n")

            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": answer
            }

        action = parsed.get("action")

        if not action:
            if is_debug_mode():
                debug_write(f"\n[DEBUG] No action at iteration {current_iteration}\n")
                debug_write(f"[DEBUG] Thought: {thought[:100] if thought else 'None'}...\n")
            return {
                "finished": True,
                "thought": thought or "No action generated",
                "action": None,
                "answer": "Analysis stopped - no action generated"
            }

        if not isinstance(action, dict):
            debug_print(f"│ [[X]] Action is not a dict: {type(action)}")
            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": "Invalid action format"
            }

        if "tool" not in action or "operation" not in action:
            debug_print(f"│ [[X]] Action missing fields. Keys: {list(action.keys())}")
            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": "Action missing required fields (tool, operation)"
            }

        if action.get("tool") == "elastic" and action.get("operation") == "search_documents":
            params = action.get("params", {})
            body = params.get("body", {})
            
            extracted_size = None
            
            if "query" in body and isinstance(body["query"], dict):
                if "size" in body["query"]:
                    extracted_size = body["query"].pop("size")
                    debug_print(f"│ [FIX] Elastic: Moved 'size' out of 'query'")

                if "bool" in body["query"] and isinstance(body["query"]["bool"], dict):
                    if "size" in body["query"]["bool"]:
                        extracted_size = body["query"]["bool"].pop("size")
                        debug_print(f"│ [FIX] Elastic: Moved 'size' out of 'bool'")

            if extracted_size is not None:
                body["size"] = extracted_size
                
            def clean_string_values(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and v.endswith(", "):
                            obj[k] = v.rstrip(", ").strip()
                            debug_print(f"│ [FIX] Elastic: Removed trailing comma from '{k}': '{v}' -> '{obj[k]}'")
                        elif isinstance(v, (dict, list)):
                            clean_string_values(v)
                elif isinstance(obj, list):
                    for item in obj:
                        clean_string_values(item)
            
            clean_string_values(body)
            
            action["params"]["body"] = body

        return {
            "finished": False,
            "thought": thought,
            "action": action,
            "answer": None
        }

    except json.JSONDecodeError as e:
        debug_print(f"│ [[X]] JSON 파싱 실패: {e}")
        debug_print(f"│ Raw content (first 500 chars): {content[:500]}")
        debug_print(f"│ Attempted to parse: {json_str[:200] if json_str else 'None'}")

        return {
            "finished": True,
            "thought": f"Failed to parse LLM response: {str(e)}",
            "action": None,
            "answer": "Analysis failed due to LLM response parsing error"
        }


def get_available_tools_for_task(task_description: str, file_meta: Dict[str, Any] = None, server_hint: str = None) -> List[Dict[str, Any]]:
    """Task에 맞는 MCP 도구 검색

    server_hint가 제공되면: 해당 서버의 전체 도구 목록 반환 (Issue 1 해결)
    server_hint가 없으면: 기존 로직 (RAG 또는 전체 도구)

    Args:
        task_description: Task 설명
        file_meta: 파일 메타데이터
        server_hint: High-level plan에서 지정한 MCP 서버 이름

    Returns:
        List[Dict]: 도구 목록
    """
    from ..config import get_config
    cfg = get_config()

    if server_hint:
        return _get_tools_from_server(server_hint)

    if not cfg.chroma.rag_enabled:
        return _get_tools_from_mcp_client()

    candidates = query_mcp_candidates(task_description, file_meta, top_k=10)

    tools = []
    for candidate in candidates:
        meta = candidate.get("meta", {})

        if meta.get("is_mcp"):
            tools.append({
                "server": meta.get("server", ""),
                "tool_name": meta.get("tool_name", ""),
                "description": candidate.get("document", ""),
                "input_schema": meta.get("input_schema", {})
            })

    return tools


def _get_tools_from_server(server_name: str) -> List[Dict[str, Any]]:
    """특정 MCP 서버에서 전체 도구 목록 가져오기

    Args:
        server_name: MCP 서버 이름

    Returns:
        List[Dict]: 해당 서버의 전체 도구 목록 (server, tool_name, description, input_schema)
    """
    import sys
    from ..config import get_config
    from ..mcp_client.lazy_loader import get_mcp_client_for_server

    cfg = get_config()

    if not cfg.mcp.enabled:
        debug_write("[!] MCP가 비활성화되어 있습니다.\n")
        return []

    try:
        client = get_mcp_client_for_server(server_name)
        server_tools = client.get_tools_by_server(server_name)

        tools = []
        for tool in server_tools:
            tools.append({
                "server": tool.get("server", server_name),
                "tool_name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {})
            })

        debug_write(f"│ [MCP Server] {server_name}: {len(tools)}개 도구 로드\n")

        return tools

    except Exception as e:
        import traceback
        debug_error(f"│ [!] MCP 서버 '{server_name}' 도구 로드 실패: {e}\n")
        debug_error(traceback.format_exc())
        return []


def _get_tools_from_mcp_client() -> List[Dict[str, Any]]:
    """MCP 클라이언트에서 직접 모든 도구 목록 가져오기 (RAG 비활성화 시 사용)

    Returns:
        List[Dict]: 도구 목록 (server, tool_name, description, input_schema)
    """
    import sys
    from ..config import get_config
    from ..mcp_client.lazy_loader import get_mcp_clients_for_servers

    cfg = get_config()

    if not cfg.mcp.enabled:
        debug_print("[!]  MCP가 비활성화되어 있습니다.")
        return []

    enabled_servers = [srv.name for srv in cfg.mcp.servers if srv.enabled]

    if not enabled_servers:
        debug_print("[!]  활성화된 MCP 서버가 없습니다.")
        return []

    try:
        client = get_mcp_clients_for_servers(enabled_servers)
        all_tools = client.get_all_tools()

        tools = []
        for tool in all_tools:
            tools.append({
                "server": tool.get("server", ""),
                "tool_name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {})
            })

        debug_write(f"│ [MCP Direct] {len(tools)}개 도구 로드 (RAG 비활성화)\n")

        return tools

    except Exception as e:
        import traceback
        debug_error(f"│ [!] MCP 도구 로드 실패: {e}\n")
        debug_error(traceback.format_exc())
        return []