"""ReAct Think 단계 (LangGraph 노드용)

LLM이 현재 상황을 분석하고 다음 액션을 결정하는 모듈
"""
from __future__ import annotations
import json
from typing import Dict, Any, List, Optional
from ..llm_client.client import LLMClient
from ..llm_client.rag import query_mcp_candidates
from ..utils.prompt_loader import load_prompt


def generate_react_thought(
    task_description: str,
    observations: List[Dict[str, Any]],
    available_tools: List[Dict[str, Any]],
    file_paths: List[str] = None,
    max_iterations: int = 30
) -> Dict[str, Any]:
    """ReAct Think 단계: LLM이 다음 행동 결정

    Args:
        task_description: Task 설명
        observations: 이전 관찰 결과 리스트
        available_tools: 사용 가능한 MCP 도구 목록
        file_paths: 파일 경로 리스트
        max_iterations: 최대 반복 횟수

    Returns:
        Dict:
            - finished: 완료 여부 (bool)
            - thought: 현재 생각 (str)
            - action: 다음 액션 (dict) or None
            - answer: 최종 답변 (str, finished=True일 때만)
    """
    llm = LLMClient()
    current_iteration = len(observations) + 1

    system_prompt = _build_system_prompt(available_tools)

    messages = _build_conversation_context(
        task_description,
        observations,
        file_paths,
        current_iteration,
        max_iterations
    )

    if messages and messages[0]["role"] == "user":
        messages[0]["content"] = f"{system_prompt}\n\n{messages[0]['content']}"

    try:
        import sys
        response = llm.chat(
            messages,
            response_format_json=True,
            timeout=60
        )

        content = response["choices"][0]["message"]["content"]

        # DEBUG: LLM 응답 로깅
        import sys
        sys.__stdout__.write(f"\n[DEBUG] LLM Response (iteration {current_iteration}):\n")
        sys.__stdout__.write(f"{content[:500]}...\n" if len(content) > 500 else f"{content}\n")
        sys.__stdout__.flush()

        return _parse_llm_response(content, current_iteration, max_iterations)

    except TimeoutError as e:
        import sys
        sys.stderr.write(f"│ [✗] ReAct Think 타임아웃 (순환 참조 가능성) → 작업 종료\n")
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
            sys.stderr.write(f"│ [✗] ReAct Think 연결 실패 (순환 참조/타임아웃): {e}\n")
        else:
            sys.stderr.write(f"│ [✗] ReAct Think 실패: {e}\n")
        sys.stderr.flush()
        return {
            "finished": True,
            "thought": f"Error during thinking: {str(e)}",
            "action": None,
            "answer": f"Analysis failed due to LLM error: {str(e)}"
        }


def _build_system_prompt(available_tools: List[Dict[str, Any]]) -> str:
    """시스템 프롬프트 생성"""
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
        if required_params:
            param_list = []
            for param in required_params:
                param_info = properties.get(param, {})
                param_type = param_info.get('type', 'any')
                param_list.append(f"{param} ({param_type})")
            param_desc = f" | Required: {', '.join(param_list)}"

        tools_desc_list.append(f"- {server}.{tool_name}: {desc}{param_desc}")

    tools_desc = "\n".join(tools_desc_list) if tools_desc_list else "No tools available"

    try:
        from ..utils.prompt_loader import format_prompt
        return format_prompt("react_think_system.txt", tools_description=tools_desc)
    except FileNotFoundError:
        import sys
        sys.stderr.write("[WARNING] Prompt file not found, using inline fallback\n")
        return f"""DFIR analyst agent. Use ReAct pattern: Think → Act → Observe.

Available Tools:
{tools_desc}

CRITICAL: You MUST respond ONLY with valid JSON. No extra text, no markdown blocks.

Response format:

To execute an action:
{{"thought": "reasoning", "action": {{"tool": "server_name", "operation": "tool_name", "params": {{"param1": "value1", "param2": "value2"}}}}, "finished": false}}

When done:
{{"thought": "I have enough data", "finished": true, "answer": "comprehensive analysis"}}

IMPORTANT - Action Format:
- "tool": MUST be the SERVER NAME ONLY (e.g., "sleuthkit", NOT "sleuthkit.list_files")
- "operation": The specific tool/operation name (e.g., "list_files", "extract_files_by_path")
- "params": Dictionary with ALL required parameters (check tool schema above)
- Example: For sleuthkit.list_files → {{"tool": "sleuthkit", "operation": "list_files", "params": {{"image_path": "/path/to/image.E01", "fs_offset_sectors": "2048"}}}}

Common Tool Usage Patterns:
1. **File Extraction by PATH** (recommended for known file paths):
   - Use sleuthkit.extract_files_by_path
   - Params: {{"image_path": "/full/path", "fs_offset_sectors": "offset", "paths": ["C:/Users/file.txt"]}}

2. **File Extraction by INODE** (only if you have inode numbers):
   - Use sleuthkit.extract_files_by_inode
   - Params: {{"image_path": "/full/path", "fs_offset_sectors": "offset", "inodes": [12345, 67890]}}

3. **List Files** (to find files):
   - Use sleuthkit.list_files
   - Params: {{"image_path": "/full/path", "fs_offset_sectors": "offset", "directory": "/path"}}

4. **Ghidra Binary Analysis** (CRITICAL - MUST follow this exact workflow):
   STEP 1: Import binary into Ghidra project
   - Use ghidra.import_binary FIRST
   - Params: {{"binary_path": "/full/path/to/binary.exe"}}
   - This starts background analysis - you MUST wait for completion!

   STEP 2: Wait for Ghidra analysis to complete (CRITICAL - DO NOT SKIP!)
   - Use ghidra.list_project_binaries to check status
   - Response: {{"programs": [{{"name": "binary.exe-abc123", "analysis_complete": false/true}}]}}
   - If "analysis_complete": false → Analysis still running, check again in next iteration
   - If "analysis_complete": true → Analysis done, proceed to STEP 3
   - IMPORTANT: You may need to call list_project_binaries 2-5 times until analysis_complete becomes true
   - DO NOT proceed to decompile/search functions until analysis_complete is true!

   STEP 3: Get the actual binary name (IT WILL HAVE A RANDOM SUFFIX!)
   - Once "analysis_complete": true, extract the "name" field from the response
   - Example: "binary.exe-abc123" (NOT just "binary.exe")
   - Remember this name for all subsequent operations

   STEP 4: Use the exact name from STEP 3 in ALL subsequent ghidra calls
   - For decompile_function: {{"binary_name": "binary.exe-abc123", "function_name": "main"}}
   - For search_functions_by_name: {{"binary_name": "binary.exe-abc123", "pattern": ".*"}}
   - For list_exports: {{"binary_name": "binary.exe-abc123"}}
   - For list_imports: {{"binary_name": "binary.exe-abc123"}}
   - NEVER use the original filename - ALWAYS use the name with the suffix!

   Common Mistakes to AVOID:
   - ❌ Calling decompile_function before analysis_complete is true
   - ❌ Giving up after seeing analysis_complete: false (this is normal, keep checking!)
   - ❌ Calling import_binary multiple times (only import once!)
   - ❌ Using original binary name instead of the suffixed name

   Example Workflow:
   Iteration 1: ghidra.import_binary → "Importing in background"
   Iteration 2: ghidra.list_project_binaries → {{"name": "file.exe-abc123", "analysis_complete": false}}
   Iteration 3: ghidra.list_project_binaries → {{"name": "file.exe-abc123", "analysis_complete": false}}
   Iteration 4: ghidra.list_project_binaries → {{"name": "file.exe-abc123", "analysis_complete": true}}
   Iteration 5: ghidra.decompile_function with binary_name="file.exe-abc123" ✓

Rules:
- ONE action per response
- ALWAYS include complete "params" with ALL required fields
- Use exact server and operation names from the tools list above
- For file extraction, prefer extract_files_by_path over extract_files_by_inode
- First get disk partition info to find fs_offset_sectors before file operations

CRITICAL SECURITY RESTRICTIONS:
- **Elasticsearch (elastic) - READ-ONLY MODE**:
  - ✓ ALLOWED: search, query, get, list, count operations (read-only)
  - ✗ FORBIDDEN: create, delete, update, insert, modify, write operations
  - You MUST NOT modify, create, or delete any Elasticsearch data
  - If you attempt a forbidden operation, it will be blocked
  - Elasticsearch is for forensic analysis only - treat it as read-only evidence

Respond ONLY with JSON."""


def _build_conversation_context(
    task_description: str,
    observations: List[Dict[str, Any]],
    file_paths: List[str],
    current_iteration: int,
    max_iterations: int
) -> List[Dict[str, str]]:
    """대화 컨텍스트 생성"""
    messages = []

    user_message = f"**Task:** {task_description}\n\n"

    if file_paths:
        user_message += f"**Files:** {', '.join(file_paths)}\n\n"

    user_message += f"**Iteration:** {current_iteration}/{max_iterations}\n\n"

    if observations:
        user_message += "**Previous Observations:**\n\n"

        for obs in observations[-5:]:
            iteration = obs.get("iteration", 0)
            thought = obs.get("thought", "")
            action = obs.get("action", {})
            observation = obs.get("observation", "")

            action_name = f"{action.get('tool', '')}.{action.get('operation', '')}"

            user_message += f"**Iteration {iteration}:**\n"
            user_message += f"- Thought: {thought}\n"
            user_message += f"- Action: {action_name}\n"
            user_message += f"- Result: {observation[:500]}...\n\n"

            # DEBUG: observation 확인
            if iteration == 1 and action.get('operation') == 'import_binary':
                import sys
                sys.__stdout__.write(f"\n[DEBUG] import_binary observation:\n{observation}\n\n")
                sys.__stdout__.flush()

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
        parsed = json.loads(json_str)

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
            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": parsed.get("answer", "No answer provided")
            }

        action = parsed.get("action")

        if not action:
            return {
                "finished": True,
                "thought": thought or "No action generated",
                "action": None,
                "answer": "Analysis stopped - no action generated"
            }

        if not isinstance(action, dict):
            print(f"│ [✗] Action is not a dict: {type(action)}")
            return {
                "finished": True,
                "thought": thought,
                "action": None,
                "answer": "Invalid action format"
            }

        if "tool" not in action or "operation" not in action:
            print(f"│ [✗] Action missing fields. Keys: {list(action.keys())}")
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
        print(f"│ [✗] JSON 파싱 실패: {e}")
        print(f"│ Raw content (first 500 chars): {content[:500]}")
        print(f"│ Attempted to parse: {json_str[:200] if json_str else 'None'}")

        return {
            "finished": True,
            "thought": f"Failed to parse LLM response: {str(e)}",
            "action": None,
            "answer": "Analysis failed due to LLM response parsing error"
        }


def get_available_tools_for_task(task_description: str, file_meta: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Task에 맞는 MCP 도구 검색 (RAG)

    Args:
        task_description: Task 설명
        file_meta: 파일 메타데이터

    Returns:
        List[Dict]: 도구 목록
    """
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