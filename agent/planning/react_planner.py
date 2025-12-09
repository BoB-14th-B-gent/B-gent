"""ReAct Think 단계 (LangGraph 노드용)

LLM이 현재 상황을 분석하고 다음 액션을 결정하는 모듈
"""
from __future__ import annotations
import json
import re
from typing import Dict, Any, List, Optional
from ..llm_client.client import LLMClient
from ..llm_client.rag import query_mcp_candidates
from ..utils.prompt_loader import load_prompt


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
        print(f"│ [JSON REPAIR] Applied fixes to malformed JSON")

    return json_str


def generate_react_thought(
    task_description: str,
    observations: List[Dict[str, Any]],
    available_tools: List[Dict[str, Any]],
    file_paths: List[str] = None,
    max_iterations: int = 30,
    user_prompt: str = None,
    tool_hint: str = ""
) -> Dict[str, Any]:
    """ReAct Think 단계: LLM이 다음 행동 결정

    Args:
        task_description: Task 설명
        observations: 이전 관찰 결과 리스트
        available_tools: 사용 가능한 MCP 도구 목록
        file_paths: 파일 경로 리스트
        max_iterations: 최대 반복 횟수
        user_prompt: 원본 사용자 쿼리 (선택)
        tool_hint: MCP 전략 힌트 (예: "elastic", "ghidra") - 첫 iteration부터 전략 로딩용

    Returns:
        Dict:
            - finished: 완료 여부 (bool)
            - thought: 현재 생각 (str)
            - action: 다음 액션 (dict) or None
            - answer: 최종 답변 (str, finished=True일 때만)
    """
    llm = LLMClient()
    current_iteration = len(observations) + 1

    system_prompt = _build_system_prompt(available_tools, observations, tool_hint)

    messages = _build_conversation_context(
        task_description,
        observations,
        file_paths,
        current_iteration,
        max_iterations,
        user_prompt
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

        # DEBUG: LLM 응답 로깅
        import sys
        import os
        if os.getenv("DEBUG") == "1":
            sys.__stdout__.write(f"\n[DEBUG] LLM Response (iteration {current_iteration}):\n")
            sys.__stdout__.write(f"{content[:500]}...\n" if len(content) > 500 else f"{content}\n")
            sys.__stdout__.flush()

        return _parse_llm_response(content, current_iteration, max_iterations)

    except TimeoutError as e:
        import sys
        sys.stderr.write(f"│ [[X]] ReAct Think 타임아웃 (순환 참조 가능성) → 작업 종료\n")
        sys.stderr.flush()
        return {
            "finished": True,
            "thought": f"LLM timeout - possible circular dependency",
            "action": None,
            "answer": f"Analysis terminated due to LLM timeout (possible circular API reference). Please check LLM configuration."
        }

    except Exception as e:
        import sys
        error_str = str(e).lower()
        if "timeout" in error_str or "recursion" in error_str or "connection" in error_str:
            sys.stderr.write(f"│ [[X]] ReAct Think 연결 실패 (순환 참조/타임아웃): {e}\n")
        else:
            sys.stderr.write(f"│ [[X]] ReAct Think 실패: {e}\n")
        sys.stderr.flush()
        return {
            "finished": True,
            "thought": f"Error during thinking: {str(e)}",
            "action": None,
            "answer": f"Analysis failed due to LLM error: {str(e)}"
        }


def _build_system_prompt(available_tools: List[Dict[str, Any]], observations: List[Dict[str, Any]] = None, tool_hint: str = "") -> str:
    """시스템 프롬프트 생성 (동적 전략 로딩)

    Args:
        available_tools: 사용 가능한 MCP 도구 목록
        observations: 이전 관찰 결과 리스트 (사용된 도구 감지용)
        tool_hint: 사전에 결정된 MCP 서버 힌트 (예: "elastic", "ghidra") - 첫 iteration부터 전략 로딩용

    Returns:
        완전한 시스템 프롬프트 (base + strategies + tools)
    """
    tools_desc_list = []
    for tool in available_tools[:15]:
        server = tool['server']
        tool_name = tool['tool_name']
        desc = tool.get('description', 'No description')
        schema = tool.get('input_schema', {})

        if server == 'elastic':
            tool_lower = tool_name.lower()
            forbidden_operations = ['create', 'delete', 'update', 'insert', 'remove', 'put', 'post', 'modify', 'write']
            if any(op in tool_lower for op in forbidden_operations):
                continue

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

    used_tools = set()

    if tool_hint:
        used_tools.add(tool_hint)

    if observations:
        for obs in observations:
            action = obs.get("action", {})
            tool = action.get("tool")
            if tool:
                used_tools.add(tool)

    strategies = _load_tool_strategies(used_tools)

    from ..utils.prompt_loader import format_prompt
    base_prompt = format_prompt("react_think_system.txt", tools_description=tools_desc)

    if strategies:
        full_prompt = base_prompt + "\n\n" + "="*80 + "\n"
        full_prompt += "TOOL-SPECIFIC STRATEGIES (Loaded dynamically based on your actions)\n"
        full_prompt += "="*80 + "\n\n"
        full_prompt += strategies
    else:
        full_prompt = base_prompt

    return full_prompt


def _load_tool_strategies(used_tools: set) -> str:
    """사용된 도구의 전략 파일을 로드

    Args:
        used_tools: 사용된 도구 이름 set (예: {"elastic", "ghidra"})

    Returns:
        조합된 전략 텍스트
    """
    if not used_tools:
        return ""

    import os
    strategies = []

    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.join(current_dir, "..", "prompts", "strategies")

    for tool in used_tools:
        strategy_file = os.path.join(strategies_dir, f"{tool}.md")

        if os.path.exists(strategy_file):
            try:
                with open(strategy_file, 'r', encoding='utf-8') as f:
                    strategy_content = f.read()
                    strategies.append(strategy_content)
            except Exception as e:
                import sys
                sys.stderr.write(f"[WARNING] Failed to load strategy for {tool}: {e}\n")
        else:
            pass

    return "\n\n".join(strategies) if strategies else ""


def _build_conversation_context(
    task_description: str,
    observations: List[Dict[str, Any]],
    file_paths: List[str],
    current_iteration: int,
    max_iterations: int,
    user_prompt: str = None
) -> List[Dict[str, str]]:
    """대화 컨텍스트 생성"""
    messages = []

    user_message = ""

    if user_prompt and user_prompt.strip():
        user_message += f"**Original User Query:** {user_prompt}\n\n"

    user_message += f"**Task:** {task_description}\n\n"

    if file_paths:
        file_list = '\n'.join(f'  - "{f}"' for f in file_paths if f is not None)
        user_message += f"**Files (use these EXACT paths without any trailing commas or modifications):**\n{file_list}\n\n"

    user_message += f"**Iteration:** {current_iteration}/{max_iterations}\n\n"

    if observations:
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

        user_message += "\n**Previous Observations:**\n\n"

        for obs in observations[-5:]:
            iteration = obs.get("iteration", 0)
            thought = obs.get("thought", "")
            action = obs.get("action", {})
            observation = obs.get("observation", "")

            action_name = f"{action.get('tool', '')}.{action.get('operation', '')}"

            user_message += f"**Iteration {iteration}:**\n"
            user_message += f"- Thought: {thought}\n"
            user_message += f"- Action: {action_name}\n"
            user_message += f"- Result: {observation[:5000]}{'...' if len(observation) > 5000 else ''}\n\n"

            if iteration == 1 and action.get('operation') == 'import_binary':
                import sys
                import os
                if os.getenv("DEBUG") == "1":
                    sys.__stdout__.write(f"\n[DEBUG] import_binary observation:\n{observation}\n\n")
                    sys.__stdout__.flush()

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
                print(f"│ [FIX] Added missing 'finished' field")

        parsed = None
        parse_error = None

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            parse_error = e
            print(f"│ [!] 첫 번째 파싱 실패: {e}")

            try:
                fallback_str = ' '.join(json_str.split())
                fallback_str = _repair_json(fallback_str)
                parsed = json.loads(fallback_str)
                print(f"│ [OK] 재시도 파싱 성공")
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
                        print(f"│ [OK] JSON 재구성 성공")
                    else:
                        raise e2
                except Exception:
                    print(f"│ [X] JSON 파싱 최종 실패: {parse_error}")
                    print(f"│ Raw JSON (first 500 chars): {json_str[:500]}")
                    return {
                        "finished": True,
                        "thought": f"Failed to parse LLM response: invalid JSON",
                        "action": None,
                        "answer": f"Analysis failed due to LLM response parsing error: {str(parse_error)}"
                    }

        if not isinstance(parsed, dict):
            print(f"│ [X] LLM 응답이 dict가 아님: {type(parsed)}")
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

        if not parsed.get('finished', False):
            if 'action' not in parsed or parsed['action'] is None:
                print(f"│ [[X]] finished=False이지만 action이 없음")
                parsed['finished'] = True
                if 'answer' not in parsed:
                    parsed['answer'] = "No action provided - task cannot continue"

            elif isinstance(parsed['action'], dict):
                if 'tool' not in parsed['action'] or 'operation' not in parsed['action']:
                    print(f"│ [[X]] Action에 tool 또는 operation 필드 없음. Keys: {list(parsed['action'].keys())}")
                    parsed['finished'] = True
                    parsed['answer'] = "Invalid action format: missing tool or operation"
                    parsed['action'] = None

        thought = parsed.get("thought", "")
        finished = parsed.get("finished", False)

        if current_iteration >= max_iterations:
            # import sys
            # sys.__stdout__.write(
            #     f"[ReAct] Max iterations reached ({max_iterations}). Forcing finish.\n"
            # )
            # sys.__stdout__.flush()
            return {
                "finished": True,
                "thought": thought or "Maximum iterations reached",
                "action": None,
                "answer": parsed.get("answer", "Analysis incomplete - reached maximum iterations")
            }

        if finished:
            # import sys
            answer = parsed.get("answer", "No answer provided")
            # if current_iteration == 1:
            #     sys.__stdout__.write(
            #         f"\n[ReAct First-Iteration Finish] LLM decided to finish immediately\n"
            #         f"  Iteration: {current_iteration}\n"
            #         f"  Thought: {thought[:200] if thought else 'None'}...\n"
            #         f"  Answer: {answer[:300] if answer else 'None'}...\n\n"
            #     )
            # else:
            #     sys.__stdout__.write(
            #         f"[ReAct Finish] LLM finished at iteration {current_iteration}\n"
            #         f"  Thought: {thought[:100] if thought else 'None'}...\n"
            #     )
            # sys.__stdout__.flush()
            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": answer
            }

        action = parsed.get("action")

        if not action:
            # import sys
            # sys.__stdout__.write(
            #     f"[ReAct No Action] LLM returned no action at iteration {current_iteration}\n"
            #     f"  Thought: {thought[:100] if thought else 'None'}...\n"
            # )
            # sys.__stdout__.flush()
            return {
                "finished": True,
                "thought": thought or "No action generated",
                "action": None,
                "answer": "Analysis stopped - no action generated"
            }

        if not isinstance(action, dict):
            print(f"│ [[X]] Action is not a dict: {type(action)}")
            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": "Invalid action format"
            }

        if "tool" not in action or "operation" not in action:
            print(f"│ [[X]] Action missing fields. Keys: {list(action.keys())}")
            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": "Action missing required fields (tool, operation)"
            }

        return {
            "finished": False,
            "thought": thought,
            "action": action,
            "answer": None
        }

    except json.JSONDecodeError as e:
        print(f"│ [[X]] JSON 파싱 실패: {e}")
        print(f"│ Raw content (first 500 chars): {content[:500]}")
        print(f"│ Attempted to parse: {json_str[:200] if json_str else 'None'}")

        return {
            "finished": True,
            "thought": f"Failed to parse LLM response: {str(e)}",
            "action": None,
            "answer": "Analysis failed due to LLM response parsing error"
        }


def get_available_tools_for_task(task_description: str, file_meta: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Task에 맞는 MCP 도구 검색

    RAG_ENABLED=true (기본값): ChromaDB 벡터 검색으로 관련 도구 검색
    RAG_ENABLED=false: MCP 클라이언트에서 직접 모든 도구 목록 가져옴

    Args:
        task_description: Task 설명
        file_meta: 파일 메타데이터

    Returns:
        List[Dict]: 도구 목록
    """
    from ..config import get_config
    cfg = get_config()

    # RAG 비활성화 시 MCP 클라이언트에서 직접 도구 가져오기
    if not cfg.chroma.rag_enabled:
        return _get_tools_from_mcp_client()

    # RAG 활성화 시 기존 벡터 검색 사용
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
        print("[!]  MCP가 비활성화되어 있습니다.")
        return []

    enabled_servers = [srv.name for srv in cfg.mcp.servers if srv.enabled]

    if not enabled_servers:
        print("[!]  활성화된 MCP 서버가 없습니다.")
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

        sys.__stdout__.write(f"│ [MCP Direct] {len(tools)}개 도구 로드 (RAG 비활성화)\n")
        sys.__stdout__.flush()

        return tools

    except Exception as e:
        import traceback
        sys.__stderr__.write(f"│ [!] MCP 도구 로드 실패: {e}\n")
        sys.__stderr__.write(traceback.format_exc())
        sys.__stderr__.flush()
        return []