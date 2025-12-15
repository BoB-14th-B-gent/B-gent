"""LangGraph 워크플로우 정의 모듈

Hybrid Mode
- High-level Planning: LLM이 추상적 Task 생성
- ReAct Execution: 각 Task를 ReAct Agent가 동적으로 실행
- IoC 분석: Task 완료 시 AI 기반 IoC 분석 및 VirusTotal Task 동적 생성
"""
from __future__ import annotations
import json
from typing import Dict, Any, Literal, List
from langgraph.graph import StateGraph, END
from ..schemas.common import AgentState
from ..utils.prompt_loader import format_prompt
from ..utils.debug import debug_write
from ..llm_client.client import LLMClient


def _analyze_task_result_for_iocs(
    task_result: str,
    mcp_name: str,
    task_description: str
) -> Dict[str, Any]:
    """AI가 MCP 실행 결과를 분석하여 의심스러운 IoC 판단

    정규표현식 기반이 아닌 AI 기반으로 컨텍스트를 이해하여
    의미 있는 IoC만 선별합니다.

    Args:
        task_result: MCP 실행 결과 텍스트
        mcp_name: 실행된 MCP 이름 (velociraptor, elasticsearch 등)
        task_description: Task 설명

    Returns:
        Dict[str, Any]: IoC 분석 결과
    """
    llm = LLMClient()

    truncated_result = task_result[:8000] if len(task_result) > 8000 else task_result

    prompt = f"""You are a Digital Forensics and Incident Response (DFIR) expert.
Analyze the MCP execution results below and determine which **suspicious IoCs** warrant checking on VirusTotal.

## Analysis Target
- MCP: {mcp_name}
- Task: {task_description}
- Execution Results:
```
{truncated_result}
```

## Judgment Criteria

### Cases requiring VirusTotal query (should_query_virustotal: true)
- File hashes from suspicious paths (AppData, Temp, Startup, Downloads, ProgramData, etc.)
- Unknown external IP communication (suspected C2 server)
- Suspicious domains (DGA patterns, recently registered domains, etc.)
- Hash of abnormal processes
- Obfuscated script files
- Executable files running at abnormal times

### Cases where VirusTotal query is unnecessary (should_query_virustotal: false)
- Normal hash of Windows system files (notepad.exe, cmd.exe, explorer.exe, etc.)
- Internal IPs (192.168.x.x, 10.x.x.x, 172.16-31.x.x, 127.x.x.x)
- Known legitimate domains (microsoft.com, google.com, windows.com, etc.)
- Items deemed legitimate based on context
- Legitimate programs in legitimate paths (e.g., C:\Windows\System32, C:\Program Files)

## Response Format (JSON)
```json
{{
    “should_query_virustotal”: true,
    “reason”: “Reason for judgment (1-2 sentences)”,
    “suspicious_iocs”: [
        {{
            “type”: “sha256”,
            “value”: “actual hash value”,
            “context”: “explanation of why it's suspicious”,
            “confidence”: “high”
        }}
    ],
    “benign_iocs_excluded”: [
        {{
            “type”: “ip”,
            “value”: “192.168.1.1”,
            “reason”: “Internal network IP”
        }}
    ]
}}
```

**Important**:
- Do not query simply because a hash/IP exists. Judge based on the **context**.
- Only include IoCs with confidence high/medium in suspicious_iocs.
- Include items that are definitely normal in benign_iocs_excluded.
- If no IoC is found, set should_query_virustotal: false.
- The suspicious_iocs array should contain a maximum of 10 entries (in order of priority).

Translated with DeepL.com (free version)"""

    try:
        response = llm.chat(
            [{"role": "user", "content": prompt}],
            response_format_json=True,
            timeout=60
        )

        content = response["choices"][0]["message"]["content"]
        result = json.loads(content)

        return {
            "should_query_virustotal": result.get("should_query_virustotal", False),
            "reason": result.get("reason", "분석 완료"),
            "suspicious_iocs": result.get("suspicious_iocs", [])[:10],
            "benign_iocs_excluded": result.get("benign_iocs_excluded", [])
        }

    except json.JSONDecodeError as e:
        return {
            "should_query_virustotal": False,
            "reason": f"JSON 파싱 실패: {str(e)}",
            "suspicious_iocs": [],
            "benign_iocs_excluded": []
        }

    except Exception as e:
        return {
            "should_query_virustotal": False,
            "reason": f"IoC 분석 실패: {str(e)}",
            "suspicious_iocs": [],
            "benign_iocs_excluded": []
        }


def _create_virustotal_task(
    suspicious_iocs: List[Dict[str, Any]],
    reason: str,
    task_id_prefix: str = "task_vt"
) -> Dict[str, Any]:
    """VirusTotal 조회 Task 동적 생성"""
    hashes = [ioc for ioc in suspicious_iocs if ioc.get("type") in ["sha256", "md5", "sha1"]]
    ips = [ioc for ioc in suspicious_iocs if ioc.get("type") == "ip"]
    domains = [ioc for ioc in suspicious_iocs if ioc.get("type") == "domain"]

    description_parts = []
    if hashes:
        hash_values = [h["value"][:16] + "..." for h in hashes[:3]]
        description_parts.append(f"파일 해시 {len(hashes)}개 ({', '.join(hash_values)})")
    if ips:
        ip_values = [ip["value"] for ip in ips[:3]]
        description_parts.append(f"IP {len(ips)}개 ({', '.join(ip_values)})")
    if domains:
        domain_values = [d["value"] for d in domains[:3]]
        description_parts.append(f"도메인 {len(domains)}개 ({', '.join(domain_values)})")

    description = f"VirusTotal로 의심 IoC 조회: {', '.join(description_parts)}"

    return {
        "task_id": f"{task_id_prefix}_001",
        "description": description,
        "task_type": "file_analysis",
        "target_files": [],
        "dependencies": [],
        "status": "pending",
        "metadata": {
            "tool_hint": "virustotal",
            "priority": "high",
            "auto_generated": True,
            "generation_reason": reason,
            "iocs": {
                "hashes": [h["value"] for h in hashes],
                "ips": [ip["value"] for ip in ips],
                "domains": [d["value"] for d in domains]
            }
        }
    }


def create_workflow(mode: Literal["two_stage"] = "two_stage") -> StateGraph:
    """하이브리드 워크플로우 생성 (모드 고정)

    Args:
        mode: 워크플로우 모드 (항상 "two_stage" - 하이브리드 모드)

    Returns:
        StateGraph: 컴파일된 하이브리드 워크플로우

    Example:
        >>> workflow = create_workflow()
        >>> initial_state = {
        ...     "job_id": "abc123",
        ...     "user_prompt": "SIEM 로그 분석 후 디스크 이미지 조사",
        ...     "file_paths": ["/path/to/disk.E01"],
        ...     "completed": False
        ... }
        >>> final_state = workflow.invoke(initial_state)
    """
    return _create_hybrid_workflow()


def _create_hybrid_workflow() -> StateGraph:
    """하이브리드 워크플로우 생성 (고정 모드)

    워크플로우 구조:
        [START]
          ↓
        [high_level_plan] → TaskQueue 생성 (LLM으로 추상적 Task 생성)
          ↓
        [get_next_task] → 다음 Task 꺼내기
          ↓
        [react_init] → ReAct 컨텍스트 초기화
          ↓
        [react_think] → LLM이 다음 액션 결정 (Think)
          ↓
        should_continue_react?
          ├─ finish → [task_complete] → [get_next_task]
          └─ act → [react_execute] → Action 실행 (Execute)
                      ↓
                   [react_observe] → 결과 관찰 (Observe)
                      ↓
                   [react_think] (루프)

    로직:
        1. high_level_plan: 사용자 프롬프트 → High-level Task 리스트 생성
        2. get_next_task: TaskQueue에서 실행 가능한 Task 꺼내기
        3. react_init: ReAct 컨텍스트 초기화 (반복 준비)
        4. react_think: LLM이 현재 상황 분석 및 다음 액션 결정
        5. react_execute: 결정된 액션 실행 (lazy MCP 사용)
        6. react_observe: 실행 결과 관찰 및 컨텍스트 업데이트
        7. 반복: think → execute → observe → think...
        8. task_complete: Task 완료 시 결과 저장

    Returns:
        StateGraph: 컴파일된 LangGraph 워크플로우
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("high_level_plan", node_high_level_plan)
    workflow.add_node("get_next_task", node_get_next_task)
    workflow.add_node("react_init", node_react_init)
    workflow.add_node("react_think", node_react_think)
    workflow.add_node("react_execute", node_react_execute)
    workflow.add_node("react_observe", node_react_observe)
    workflow.add_node("task_complete", node_task_complete)
    workflow.add_node("finish", node_finish_two_stage)

    workflow.set_entry_point("high_level_plan")
    workflow.add_edge("high_level_plan", "get_next_task")

    workflow.add_conditional_edges(
        "get_next_task",
        should_get_next_task,
        {
            "execute": "react_init",
            "finish": "finish"
        }
    )

    workflow.add_edge("react_init", "react_think")
    workflow.add_conditional_edges(
        "react_think",
        should_continue_react,
        {
            "act": "react_execute",
            "finish": "task_complete"
        }
    )
    workflow.add_edge("react_execute", "react_observe")
    workflow.add_edge("react_observe", "react_think")

    workflow.add_edge("task_complete", "get_next_task")
    workflow.add_edge("finish", END)

    return workflow.compile()


def node_high_level_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 1: High-level Task 생성

    사용자 프롬프트 + 파일 목록 → LLM → High-level Task 리스트
    TaskQueue 초기화

    Args:
        state: 현재 상태
            - user_prompt: 사용자 요청
            - file_paths: 파일 경로 리스트
            - file_meta: 파일 메타데이터

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - high_level_tasks: High-level Task 리스트 (dict)
            - task_queue_state: TaskQueue 상태
    """
    import time
    from ..planning.high_level_planner import generate_high_level_plan
    from ..planning.task_queue import TaskQueue
    from ..storage.job_storage import save_agent_state, update_stage

    user_prompt = state["user_prompt"]
    file_paths = state.get("file_paths", [])
    file_meta = state.get("file_meta", {})
    is_first_execution = state.get("is_first_execution", True)
    previous_context = state.get("previous_context")

    start_time = time.time()

    try:
        high_level_tasks = generate_high_level_plan(
            user_prompt, file_paths, file_meta, is_first_execution, previous_context
        )

        if not high_level_tasks:
            error_msg = "High-level 계획을 생성할 수 없습니다."
            return {
                **state,
                "high_level_tasks": [],
                "completed": True,
                "error": error_msg
            }

        task_queue = TaskQueue()
        task_queue.add_tasks(high_level_tasks)

        if not task_queue.validate_dependencies():
            error_msg = "Task 간 순환 의존성이 감지되었습니다!"
            return {
                **state,
                "high_level_tasks": [],
                "completed": True,
                "error": error_msg
            }

        high_level_planning_time = time.time() - start_time

        timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
        timing["high_level_planning"] = high_level_planning_time

        job_id = state.get("job_id")
        current_stage_id = state.get("stage_id", 1)
        if job_id:
            plan_list = [
                {
                    "task_id": t.task_id,
                    "description": t.description,
                    "mcp_server": t.metadata.get("tool_hint", "") or (t.mcp_call.get("server", "") if t.mcp_call else ""),
                    "mcp_tools": [],
                    "status": "pending"
                }
                for t in high_level_tasks
            ]
            save_agent_state(
                agent_id=job_id,
                stage_id=current_stage_id,
                plan=plan_list,
                status="running"
            )

        return {
            **state,
            "high_level_tasks": [t.to_dict() for t in high_level_tasks],
            "task_queue_state": {
                "all_tasks": {t.task_id: t.to_dict() for t in task_queue.get_all_tasks()},
                "completed_ids": list(task_queue._completed_task_ids)
            },
            "completed_tasks": [],
            "current_task": None,
            "timing": timing
        }

    except Exception as e:
        error_msg = f"High-level 계획 생성 실패: {str(e)}"
        import traceback
        traceback.print_exc()

        return {
            **state,
            "high_level_tasks": [],
            "completed": True,
            "error": error_msg
        }


def node_get_next_task(state: Dict[str, Any]) -> Dict[str, Any]:
    """다음 실행 가능한 Task 가져오기

    TaskQueue에서 의존성이 충족된 Task 꺼내기

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - current_task: 다음 Task (dict) 또�� None
    """
    from ..schemas.task import HighLevelTask, TaskStatus
    from ..planning.task_queue import TaskQueue

    task_queue_state = state.get("task_queue_state", {})
    all_tasks_dict = task_queue_state.get("all_tasks", {})
    completed_ids = set(task_queue_state.get("completed_ids", []))

    task_queue = TaskQueue()
    for task_dict in all_tasks_dict.values():
        task = HighLevelTask.from_dict(task_dict)
        if task.status == TaskStatus.PENDING:
            task_queue.add_task(task)
        elif task.status == TaskStatus.DONE:
            task_queue._completed_task_ids.add(task.task_id)

    next_task = task_queue.get_next_ready_task()

    if next_task:
        import time

        all_tasks_dict[next_task.task_id] = next_task.to_dict()

        timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
        if "tasks" not in timing:
            timing["tasks"] = {}
        timing["tasks"][next_task.task_id] = {
            "start_time": time.time(),
            "mcp_search": 0.0,
            "low_level_planning": 0.0,
            "execution": 0.0,
            "total": 0.0
        }

        job_id = state.get("job_id")
        if job_id:
            try:
                stage_num = int(next_task.task_id.split("_")[1])
                update_stage(job_id, stage_num + 1)
            except:
                pass

            from ..storage.job_storage import update_task_status
            update_task_status(job_id, next_task.task_id, "in_progress")

        return {
            **state,
            "current_task": next_task.to_dict(),
            "task_queue_state": {
                "all_tasks": all_tasks_dict,
                "completed_ids": list(task_queue._completed_task_ids)
            },
            "plan": [],
            "results": [],
            "current_step": 0,
            "timing": timing
        }
    else:
        return {
            **state,
            "current_task": None
        }


def node_react_init(state: Dict[str, Any]) -> Dict[str, Any]:
    """ReAct 컨텍스트 초기화

    새로운 Task 시작 시 ReAct 반복 컨텍스트 초기화

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - react_context: ReAct 컨텍스트 초기화
    """
    from ..schemas.task import HighLevelTask
    from ..planning.react_planner import get_available_tools_for_task

    current_task_dict = state.get("current_task")
    if not current_task_dict:
        return state

    task = HighLevelTask.from_dict(current_task_dict)
    completed_tasks = state.get("completed_tasks", [])

    dependency_context = ""
    if task.dependencies:
        dependency_context = "\n\n**Previous Task Results (IMPORTANT - use these outputs):**\n"
        for dep_id in task.dependencies:
            for completed in completed_tasks:
                if completed.get("task_id") == dep_id:
                    dep_desc = completed.get("description", "")
                    dep_results = completed.get("execution_results", [])
                    react_answer = completed.get("react_answer", "")
                    dep_tool_hint = completed.get("metadata", {}).get("tool_hint", "")
                    success_count = sum(1 for r in dep_results if r.get("success"))
                    dep_success = completed.get("react_success", False)

                    dependency_context += f"\n### {dep_id}: {dep_desc}\n"
                    dependency_context += f"- Tool: {dep_tool_hint}\n"
                    dependency_context += f"- Status: {success_count}/{len(dep_results)} successful\n"
                    dependency_context += f"- Task Success: {'YES' if dep_success else 'NO - DEPENDENCY FAILED'}\n"

                    if not dep_success or success_count == 0:
                        dependency_context += f"\n**⚠️ WARNING: Dependency task {dep_id} FAILED or produced no results.**\n"
                        dependency_context += f"**You may not be able to proceed with this task. Report the dependency failure.**\n"

                    if dep_results:
                        dependency_context += f"\n**MCP Execution Results (use these paths/data):**\n"
                        for idx, exec_result in enumerate(dep_results[-3:], 1):
                            action = exec_result.get("action", {})
                            result_data = exec_result.get("result", "")
                            exec_success = exec_result.get("success", False)

                            action_name = f"{action.get('tool', '')}.{action.get('operation', '')}"
                            dependency_context += f"\n{idx}. {action_name} ({'SUCCESS' if exec_success else 'FAILED'}):\n"

                            if exec_success and result_data:
                                result_preview = str(result_data)[:1500]
                                dependency_context += f"```\n{result_preview}\n```\n"

                    if react_answer:
                        answer_preview = react_answer[:500] if len(react_answer) > 500 else react_answer
                        dependency_context += f"\n**Analysis Result:**\n```\n{answer_preview}\n```\n"

                    break

    try:
        task_prompt = format_prompt(
            "react_task_template.txt",
            task_description=task.description,
            dependency_context=dependency_context
        )
    except FileNotFoundError:
        import sys
        sys.stderr.write("[WARNING] Prompt file not found, using inline fallback\n")
        task_prompt = f"""{task.description}{dependency_context}

**Your Goal:** Complete the task described above using available MCP tools.
Think step by step, observe results, and adapt your actions accordingly."""

    file_meta = state.get("file_meta", {})

    tool_hint = task.metadata.get("tool_hint") or None
    available_tools = get_available_tools_for_task(task.description, file_meta, server_hint=tool_hint)

    if tool_hint and not available_tools:
        debug_write(f"│ [WARNING] tool_hint '{tool_hint}' specified but no tools loaded. Check MCP server status.\n")

    tool_hint = task.metadata.get("tool_hint", "")

    if tool_hint == "velociraptor":
        return {
            **state,
            "react_context": {
                "use_velociraptor_sequence": True,
                "task_prompt": task_prompt,
                "file_paths": task.target_files if task.target_files else []
            }
        }

    if tool_hint == "sleuthkit":
        target_path = task.metadata.get("target_path")
        if target_path:
            return {
                **state,
                "react_context": {
                    "use_sleuthkit_sequence": True,
                    "task_prompt": task_prompt,
                    "file_paths": task.target_files if task.target_files else [],
                    "target_path": target_path,
                    "user_prompt": task.metadata.get("user_prompt", "")
                }
            }

    if tool_hint == "dissect" and task.metadata.get("use_dissect_sequence", False):
        debug_write(f"│ Using predefined Dissect artifact sequence (skipping ReAct loop)\n")
        return {
            **state,
            "react_context": {
                "use_dissect_sequence": True,
                "task_prompt": task_prompt,
                "file_paths": task.target_files if task.target_files else [],
                "user_prompt": state.get("user_prompt", "")
            }
        }

    if tool_hint == "consolehost-history" and task.metadata.get("use_consolehost_sequence", False):
        debug_write(f"│ Using predefined ConsoleHost_history sequence (skipping ReAct loop)\n")
        return {
            **state,
            "react_context": {
                "use_consolehost_sequence": True,
                "task_prompt": task_prompt,
                "file_paths": task.target_files if task.target_files else [],
                "user_prompt": state.get("user_prompt", "")
            }
        }

    react_context = {
        "iteration": 0,
        "max_iterations": 30,
        "task_prompt": task_prompt,
        "file_paths": task.target_files if task.target_files else [],
        "available_tools": available_tools,
        "observations": [],
        "current_thought": "",
        "current_action": None,
        "finished": False,
        "answer": None,
        "use_velociraptor_sequence": False
    }

    return {
        **state,
        "react_context": react_context
    }


def node_react_think(state: Dict[str, Any]) -> Dict[str, Any]:
    """ReAct Think 노드: LLM이 다음 액션 결정

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - react_context: updated with thought and action
    """
    from ..planning.react_planner import generate_react_thought
    import time
    import os

    react_context = state.get("react_context", {})

    if react_context.get("use_velociraptor_sequence"):
        return state

    iteration = react_context.get("iteration", 0) + 1
    react_context["iteration"] = iteration

    task_prompt = react_context.get("task_prompt", "")
    observations = react_context.get("observations", [])
    available_tools = react_context.get("available_tools", [])
    file_paths = react_context.get("file_paths", [])
    max_iterations = react_context.get("max_iterations", 30)


    start_time = time.time()

    current_task_dict = state.get("current_task", {})
    mcp_call = current_task_dict.get("mcp_call") if current_task_dict else None
    server_hint = current_task_dict.get("metadata", {}).get("tool_hint") if current_task_dict else None

    thought_result = generate_react_thought(
        task_description=task_prompt,
        observations=observations,
        available_tools=available_tools,
        file_paths=file_paths,
        max_iterations=max_iterations,
        user_prompt=state.get("user_prompt"),
        mcp_call=mcp_call,
        server_hint=server_hint
    )

    think_time = time.time() - start_time

    finished = thought_result.get("finished", False)
    thought = thought_result.get("thought", "")
    action = thought_result.get("action")
    answer = thought_result.get("answer")


    react_context["current_thought"] = thought
    react_context["current_action"] = action
    react_context["finished"] = finished
    react_context["answer"] = answer

    return {
        **state,
        "react_context": react_context
    }


def node_react_execute(state: Dict[str, Any]) -> Dict[str, Any]:
    """ReAct Execute 노드: Action 실행

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - react_context: updated with execution result
    """
    from ..schemas.actions import Action
    from .executor import execute_action
    import time

    react_context = state.get("react_context", {})
    action_dict = react_context.get("current_action")
    iteration = react_context.get("iteration", 0)
    max_iterations = react_context.get("max_iterations", 30)

    if not action_dict:
        if iteration > max_iterations // 2:
            react_context["finished"] = True
            react_context["answer"] = "No valid action provided after multiple attempts - cannot continue"
            return {
                **state,
                "react_context": react_context
            }

        debug_write(f"│ [EXECUTE] No action at iteration {iteration} - will retry in next think\n")

        react_context["current_action"] = {}

        react_context["current_execution_result"] = {
            "success": False,
            "error": "No action was generated. Please review available tools and try again with a valid action."
        }
        react_context["current_execution_time"] = 0
        return {
            **state,
            "react_context": react_context
        }

    job_id = state.get("job_id")
    current_task_dict = state.get("current_task", {})
    task_id = current_task_dict.get("task_id") if current_task_dict else None

    tool_name = action_dict.get("tool", "").strip()
    operation_name = action_dict.get("operation", "").strip()

    invalid_tools = ["none", "null", "undefined", "", "n/a"]
    if tool_name.lower() in invalid_tools or not tool_name:
        react_context["finished"] = True
        react_context["answer"] = f"Invalid tool name provided: '{tool_name}'. No tools available to execute."
        return {
            **state,
            "react_context": react_context
        }

    action = Action(
        tool=tool_name,
        operation=operation_name,
        params=action_dict.get("params", {}),
        reason=react_context.get("current_thought", ""),
        timeout_seconds=action_dict.get("timeout_seconds", 120)
    )

    action_name = f"{action.tool}.{action.operation}"

    start_time = time.time()

    result = execute_action(action, job_id=job_id, task_id=task_id)

    exec_time = time.time() - start_time

    react_context["current_execution_result"] = result.to_dict()
    react_context["current_execution_time"] = exec_time

    success_marker = "[OK]" if result.success else "[X]"

    return {
        **state,
        "react_context": react_context
    }


def node_react_observe(state: Dict[str, Any]) -> Dict[str, Any]:
    """ReAct Observe 노드: 실행 결과 관찰 및 기록

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - react_context: observation added
    """
    react_context = state.get("react_context", {})

    iteration = react_context.get("iteration", 0)
    thought = react_context.get("current_thought", "")
    action_dict = react_context.get("current_action") or {}  # None 방어 처리
    exec_result = react_context.get("current_execution_result", {})
    exec_time = react_context.get("current_execution_time", 0)

    result_data = exec_result.get("result", "")
    error = exec_result.get("error", "")
    success = exec_result.get("success", False)

    if success:
        observation = str(result_data)
    else:
        observation = f"Error: {error}"

    observations = react_context.get("observations", [])
    observations.append({
        "iteration": iteration,
        "thought": thought,
        "action": action_dict,
        "observation": observation,
        "success": success,
        "execution_time": exec_time
    })

    react_context["observations"] = observations

    timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
    current_task_dict = state.get("current_task", {})
    task_id = current_task_dict.get("task_id") if current_task_dict else None

    if task_id and task_id in timing.get("tasks", {}):
        timing["tasks"][task_id]["execution"] = timing["tasks"][task_id].get("execution", 0.0) + exec_time

    obs_preview = observation[:200] if len(observation) > 200 else observation

    import sys
    import os
    if os.getenv("DEBUG") == "1":
        sys.__stdout__.write(f"\n[DEBUG] Observation (iteration {iteration}, success={success}):\n")
        sys.__stdout__.write(f"{obs_preview}\n")
        if len(observation) > 200:
            sys.__stdout__.write(f"... (total {len(observation)} chars)\n")
        sys.__stdout__.write("\n")
        sys.__stdout__.flush()

    return {
        **state,
        "react_context": react_context,
        "timing": timing
    }


def should_continue_react(state: Dict[str, Any]) -> str:
    """ReAct 루프 계속 여부 판단

    Args:
        state: 현재 상태

    Returns:
        str: "act" (계속 실행) 또는 "finish" (완료)
    """
    react_context = state.get("react_context", {})

    if (react_context.get("use_velociraptor_sequence") or
        react_context.get("use_sleuthkit_sequence") or
        react_context.get("use_dissect_sequence") or
        react_context.get("use_consolehost_sequence")):
        return "finish"

    finished = react_context.get("finished", False)

    if finished:
        return "finish"
    else:
        return "act"


def _execute_velociraptor_sequence(user_prompt: str, file_paths: list = None, job_id: str = None, task_id: str = None) -> Dict[str, Any]:
    """Velociraptor 아티팩트를 정해진 순서대로 수집

    Velociraptor는 미리 정의된 순서대로 Windows 아티팩트를 수집합니다.
    ReAct Agent가 랜덤하게 선택하는 것보다 효율적입니다.

    Args:
        user_prompt: 사용자 요청
        file_paths: 디스크 이미지 경로 리스트
        job_id: 작업 ID
        task_id: Task ID (task별 mcp_tools 추적용)

    Returns:
        Dict: ReAct 결과 형식과 동일
            - observations: 각 도구 실행 결과
            - iterations: 실행 횟수
            - answer: 최종 분석 결과
    """
    from ..mcp_client.singleton import get_mcp_client
    from ..storage.evidence_logger import log_mcp_execution
    from ..llm_client.client import LLMClient
    import time

    VELOCIRAPTOR_SEQUENCE = [
        {
            "operation": "client_info",
            "description": "Virtual Host - Get Client Info and extract Client ID",
            "params": {"hostname": "Virtual Host"},
            "is_client_info": True
        },
        {
            "operation": "windows_scheduled_tasks",
            "description": "Windows Scheduled Tasks",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_services",
            "description": "Windows Services",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_recentdocs",
            "description": "Windows RecentDocs",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_shellbags",
            "description": "Windows Shellbags",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_evidence_of_download",
            "description": "Windows Evidence of Download",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_mountpoints2",
            "description": "Windows MountPoints2",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_execution_bam",
            "description": "Windows Execution - BAM (Background Activity Moderator)",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_execution_userassist",
            "description": "Windows Execution - UserAssist",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_execution_shimcache",
            "description": "Windows Execution - Shimcache",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_execution_prefetch",
            "description": "Windows Execution - Prefetch",
            "params": {},
            "requires_client_id": True
        },
        {
            "operation": "windows_ntfs_mft",
            "description": "Windows NTFS MFT (Master File Table)",
            "params": {},
            "requires_client_id": True
        }
    ]

    observations = []
    start_time = time.time()
    client_id = None


    for idx, artifact in enumerate(VELOCIRAPTOR_SEQUENCE, 1):
        operation = artifact["operation"]
        description = artifact["description"]
        params = artifact["params"].copy()

        if artifact.get("requires_client_id") and client_id:
            params["client_id"] = client_id

        if params.get("client_id"):
            pass

        try:
            mcp_client = get_mcp_client()
            result = mcp_client.call_tool("velociraptor", operation, params, timeout=120)

            if job_id:
                from ..storage.job_storage import add_mcp_tool
                add_mcp_tool(job_id, "velociraptor", operation, task_id)

            if artifact.get("is_client_info"):
                if isinstance(result, dict):
                    result_data = result.get("result", {})
                    if isinstance(result_data, dict):
                        client_id = result_data.get("client_id")
                    elif isinstance(result_data, str):
                        import re
                        match = re.search(r'"?client_id"?\s*:\s*"?([^",\s}]+)"?', result_data)
                        if match:
                            client_id = match.group(1)

                if client_id:
                    pass
                else:
                    pass


            success = result.get("success", False) if isinstance(result, dict) else True
            result_data = result.get("result") if isinstance(result, dict) else result

            log_mcp_execution(
                mcp_name="velociraptor",
                tool_name=operation,
                request=params,
                response=result_data,
                success=success,
                job_id=job_id
            )

            result_str = str(result)
            if len(result_str) > 5000:
                result_str = result_str[:5000] + "\n\n...(truncated)"

            observations.append({
                "iteration": idx,
                "thought": f"Collecting {description}",
                "action": {
                    "tool": "velociraptor",
                    "operation": operation,
                    "params": params
                },
                "observation": result_str
            })


        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"

            log_mcp_execution(
                mcp_name="velociraptor",
                tool_name=operation,
                request=params,
                response=str(e),
                success=False,
                job_id=job_id
            )

            observations.append({
                "iteration": idx,
                "thought": f"Collecting {description}",
                "action": {
                    "tool": "velociraptor",
                    "operation": operation,
                    "params": params
                },
                "observation": error_msg
            })

    execution_time = time.time() - start_time


    llm = LLMClient()

    data_summary = f"**User Request:** {user_prompt}\n\n"
    data_summary += f"**Collected Artifacts ({len(observations)}):**\n\n"

    for obs in observations:
        action = obs['action']
        action_name = f"{action['tool']}.{action['operation']}"
        result_preview = obs['observation'][:1500]

        data_summary += f"### {obs['iteration']}. {action_name}\n"
        data_summary += f"Result: {result_preview}\n\n"

    try:
        analysis_prompt = format_prompt(
            "velociraptor_analysis.txt",
            data_summary=data_summary
        )
    except FileNotFoundError:
        import sys
        sys.stderr.write("[WARNING] Prompt file not found, using inline fallback\n")
        analysis_prompt = f"""You are a senior DFIR analyst specializing in Windows forensics.

Analyze the collected Velociraptor artifacts and provide a comprehensive forensic report.

{data_summary}

**REQUIRED OUTPUT FORMAT** (Minimum 400 words):

# Windows Forensic Analysis Report

## Executive Summary
[2-3 sentences summarizing key findings]

## Artifacts Analyzed
- Process List (PSList)
- Master File Table (MFT)
- UserAssist Registry
- Amcache
- Prefetch Files

## Detailed Findings

### Process Analysis
[Running/historical processes, suspicious processes, parent-child relationships]

### File Timeline (MFT)
[File creation/modification events, suspicious file activities, deleted files]

### Program Execution History
**UserAssist:** [Programs executed by user, counts, timestamps]
**Amcache:** [Installed programs, execution history]
**Prefetch:** [Frequently executed programs, execution times]

### Indicators of Compromise (IOCs)
- **Suspicious Processes**: [PIDs, names, paths]
- **Malicious Files**: [paths, timestamps]
- **Persistence**: [registry keys, startup items]

## Timeline
[Chronological sequence of key events]

## Risk Assessment
- **Severity**: Critical/High/Medium/Low
- **Confidence**: High/Medium/Low
- **Justification**: [Why]

## Recommendations
1. **Immediate Actions**: [Steps]
2. **Further Investigation**: [Additional data]
3. **Remediation**: [Fixes]

---
Use ACTUAL data values from artifacts. Be specific with timestamps, file paths, process names."""

    try:
        response = llm.chat(
            [{"role": "user", "content": analysis_prompt}],
            timeout=180
        )
        analysis = response["choices"][0]["message"]["content"]

    except Exception as e:
        analysis = f"""# Velociraptor Artifact Collection Summary

{len(observations)} Windows forensic artifacts collected.

## Artifacts
{chr(10).join([f"- {obs['action']['operation']}" for obs in observations])}

Analysis generation failed: {str(e)}
Please review raw artifact data."""


    return {
        "observations": observations,
        "iterations": len(observations),
        "answer": analysis,
        "success": True
    }


def _execute_sleuthkit_sequence(target_path: str, file_paths: list = None, job_id: str = None, task_id: str = None) -> Dict[str, Any]:
    """SleuthKit 파일 추출 3단계 파이프라인

    ReAct Agent가 시행착오를 거치는 대신, 정해진 순서로 파일 추출 수행:
    1. disk_partition_info: 파티션 정보 조회 (fs_offset_sectors 획득)
    2. search_inode_by_path: 파일 경로로 inode 검색
    3. extract_files_by_inode: inode로 파일 추출

    Args:
        target_path: 추출할 파일 경로 (예: "C:/Users/winbg/AppData/Roaming/WindowsUpdate.py")
        file_paths: 디스크 이미지 경로 리스트
        job_id: 작업 ID
        task_id: Task ID (task별 mcp_tools 추적용)

    Returns:
        Dict: ReAct 결과 형식과 동일
            - observations: 각 단계 실행 결과
            - iterations: 실행 횟수 (3)
            - answer: 최종 결과
            - success: 성공 여부
    """
    from ..mcp_client.singleton import get_mcp_client
    from ..storage.evidence_logger import log_mcp_execution
    import json
    import re
    import time

    observations = []
    start_time = time.time()

    if not file_paths or len(file_paths) == 0:
        return {
            "observations": [],
            "iterations": 0,
            "answer": "Error: No disk image file provided",
            "success": False
        }

    image_path = file_paths[0]

    try:
        mcp_client = get_mcp_client()
        result = mcp_client.call_tool("sleuthkit", "disk_partition_info", {"image_path": image_path}, timeout=120)

        if job_id:
            from ..storage.job_storage import add_mcp_tool
            add_mcp_tool(job_id, "sleuthkit", "disk_partition_info", task_id)

        result_str = str(result)
        observations.append({
            "iteration": 1,
            "thought": "Get partition info to find fs_offset_sectors",
            "action": {
                "tool": "sleuthkit",
                "operation": "disk_partition_info",
                "params": {"image_path": image_path}
            },
            "observation": result_str,
            "success": True
        })

        log_mcp_execution("sleuthkit", "disk_partition_info", {"image_path": image_path}, result, True, job_id)

        fs_offset_sectors = None
        if isinstance(result, dict):
            stdout = result.get("stdout", "")
            partition_lines = stdout.split("\n")
            max_length = 0
            for line in partition_lines:
                match = re.search(r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(Basic data partition|Microsoft basic data)', line, re.IGNORECASE)
                if match:
                    start_sector = match.group(2)
                    length = int(match.group(4))
                    if length > max_length:
                        max_length = length
                        fs_offset_sectors = start_sector

        if not fs_offset_sectors:
            fs_offset_sectors = "239616"
            pass
        else:
            pass

    except Exception as e:
        error_msg = f"disk_partition_info failed: {str(e)}"
        observations.append({
            "iteration": 1,
            "thought": "Get partition info to find fs_offset_sectors",
            "action": {"tool": "sleuthkit", "operation": "disk_partition_info", "params": {"image_path": image_path}},
            "observation": error_msg,
            "success": False
        })
        return {
            "observations": observations,
            "iterations": 1,
            "answer": f"Failed at Step 1: {error_msg}",
            "success": False
        }

    filepath_unix = target_path.replace("\\", "/")
    if filepath_unix.startswith("C:/") or filepath_unix.startswith("c:/"):
        filepath_unix = filepath_unix[2:]
    elif filepath_unix.startswith("C:\\") or filepath_unix.startswith("c:\\"):
        filepath_unix = filepath_unix[2:]

    try:
        mcp_client = get_mcp_client()
        result = mcp_client.call_tool("sleuthkit", "search_inode_by_path", {
            "image_path": image_path,
            "fs_offset_sectors": fs_offset_sectors,
            "path": filepath_unix
        }, timeout=120)

        if job_id:
            from ..storage.job_storage import add_mcp_tool
            add_mcp_tool(job_id, "sleuthkit", "search_inode_by_path", task_id)

        result_str = str(result)
        observations.append({
            "iteration": 2,
            "thought": f"Search inode for file: {filepath_unix}",
            "action": {
                "tool": "sleuthkit",
                "operation": "search_inode_by_path",
                "params": {"image_path": image_path, "fs_offset_sectors": fs_offset_sectors, "filepath": filepath_unix}
            },
            "observation": result_str,
            "success": True
        })

        log_mcp_execution("sleuthkit", "search_inode_by_path", {"filepath": filepath_unix}, result, True, job_id)

        inode = None
        if isinstance(result, dict):
            result_data = result.get("result")
            if isinstance(result_data, str):
                try:
                    parsed = json.loads(result_data)
                    inodes_list = parsed.get("inodes", [])
                    if inodes_list and len(inodes_list) > 0:
                        inode = inodes_list[0]
                except:
                    pass
            elif isinstance(result_data, dict):
                inodes_list = result_data.get("inodes", [])
                if inodes_list and len(inodes_list) > 0:
                    inode = inodes_list[0]

        if not inode:
            result_str = str(result)
            match = re.search(r'"?inodes"?\s*:\s*\[\s*"?(\d+)"?\s*\]', result_str)
            if match:
                inode = match.group(1)

        if not inode:
            error_msg = f"Could not find inode for file: {target_path}"
            return {
                "observations": observations,
                "iterations": 2,
                "answer": error_msg,
                "success": False
            }


    except Exception as e:
        error_msg = f"search_inode_by_path failed: {str(e)}"
        observations.append({
            "iteration": 2,
            "thought": f"Search inode for file: {filepath_unix}",
            "action": {"tool": "sleuthkit", "operation": "search_inode_by_path", "params": {}},
            "observation": error_msg,
            "success": False
        })
        return {
            "observations": observations,
            "iterations": 2,
            "answer": f"Failed at Step 2: {error_msg}",
            "success": False
        }

    out_dir = "./data/output"

    try:
        mcp_client = get_mcp_client()
        result = mcp_client.call_tool("sleuthkit", "extract_files_by_inode", {
            "image_path": image_path,
            "fs_offset_sectors": fs_offset_sectors,
            "inodes": [inode],
            "out_dir": out_dir
        }, timeout=120)

        if job_id:
            from ..storage.job_storage import add_mcp_tool
            add_mcp_tool(job_id, "sleuthkit", "extract_files_by_inode", task_id)

        result_str = str(result)
        observations.append({
            "iteration": 3,
            "thought": f"Extract file with inode: {inode}",
            "action": {
                "tool": "sleuthkit",
                "operation": "extract_files_by_inode",
                "params": {"image_path": image_path, "fs_offset_sectors": fs_offset_sectors, "inodes": [inode], "out_dir": out_dir}
            },
            "observation": result_str,
            "success": True
        })

        log_mcp_execution("sleuthkit", "extract_files_by_inode", {"inodes": [inode]}, result, True, job_id)

        success = False
        if isinstance(result, dict):
            ok = result.get("ok", False)
            results = result.get("results", [])
            if ok and results:
                for r in results:
                    if r.get("ok", False):
                        success = True
                        break

        if success:
            answer = f"Successfully extracted {target_path} (inode: {inode}) to {out_dir}"
        else:
            answer = f"Extraction attempted for {target_path} (inode: {inode}), please check {out_dir}"

    except Exception as e:
        error_msg = f"extract_files_by_inode failed: {str(e)}"
        observations.append({
            "iteration": 3,
            "thought": f"Extract file with inode: {inode}",
            "action": {"tool": "sleuthkit", "operation": "extract_files_by_inode", "params": {}},
            "observation": error_msg,
            "success": False
        })
        return {
            "observations": observations,
            "iterations": 3,
            "answer": f"Failed at Step 3: {error_msg}",
            "success": False
        }

    execution_time = time.time() - start_time

    from ..llm_client.client import LLMClient
    llm = LLMClient()

    extraction_summary = f"**File Extraction Process:**\n\n"
    for obs in observations:
        action = obs['action']
        action_name = f"{action['tool']}.{action['operation']}"
        result_preview = obs['observation'][:500]
        extraction_summary += f"### Step {obs['iteration']}: {action_name}\n"
        extraction_summary += f"Result: {result_preview}\n\n"

    status = "Success" if success else "Partial/Failed"

    priority_score = 3
    suspicious_paths = ['appdata', 'temp', 'startup', 'programdata', 'windows\\system32']
    suspicious_extensions = ['.exe', '.dll', '.sys', '.bat', '.ps1', '.vbs', '.scr']

    target_lower = target_path.lower()
    if any(path in target_lower for path in suspicious_paths):
        priority_score += 1
    if any(ext in target_lower for ext in suspicious_extensions):
        priority_score += 1
    priority_score = min(priority_score, 5)

    try:
        analysis_prompt = format_prompt(
            "sleuthkit_extraction_analysis.txt",
            extraction_summary=extraction_summary,
            target_path=target_path,
            inode=inode,
            status=status,
            out_dir=out_dir,
            priority_score=priority_score
        )
    except FileNotFoundError:
        import sys
        sys.stderr.write("[WARNING] Prompt file not found, using inline fallback\n")
        analysis_prompt = f"""You are a senior DFIR analyst. Analyze this file extraction:

{extraction_summary}

Target: {target_path}
Inode: {inode}
Status: {status}
Output: {out_dir}

Provide forensic analysis of this extracted file, including risk assessment and recommended next steps."""

    try:
        response = llm.chat(
            [{"role": "user", "content": analysis_prompt}],
            timeout=180
        )
        analysis = response["choices"][0]["message"]["content"]

    except Exception as e:
        analysis = f"""# SleuthKit File Extraction Summary

## Extraction Result
- **File**: {target_path}
- **Inode**: {inode}
- **Status**: {status}
- **Output**: {out_dir}

## Steps Performed
{chr(10).join([f"{i+1}. {obs['action']['operation']}" for i, obs in enumerate(observations)])}

Analysis generation failed: {str(e)}
Please review the extracted file manually at {out_dir}"""


    return {
        "observations": observations,
        "iterations": 3,
        "answer": analysis,
        "success": success
    }


def _execute_dissect_sequence(
    user_prompt: str,
    file_paths: list = None,
    job_id: str = None,
    task_id: str = None
) -> Dict[str, Any]:
    """Dissect 아티팩트를 정해진 순서대로 수집 (run_single_artifact_plugin 사용)

    run_all_artifact_plugins의 응답이 너무 커서 에이전트가 받을 수 없으므로,
    개별 아티팩트를 하나씩 실행하여 수집합니다.

    Args:
        user_prompt: 사용자 요청
        file_paths: 디스크 이미지 경로 리스트
        job_id: 작업 ID
        task_id: Task ID (task별 mcp_tools 추적용)

    Returns:
        Dict: ReAct 결과 형식과 동일
            - observations: 각 도구 실행 결과
            - iterations: 실행 횟수
            - answer: 최종 분석 결과
    """
    from ..mcp_client.lazy_loader import get_mcp_client_for_server
    from ..storage.evidence_logger import log_mcp_execution
    from ..llm_client.client import LLMClient
    import time

    DISSECT_ARTIFACT_SEQUENCE = [
        {"plugin_name": "os.windows.prefetch", "description": "Prefetch (프로그램 실행 기록)"},
        {"plugin_name": "os.windows.jumplist", "description": "Jumplist (최근 파일 기록)"},
        {"plugin_name": "browser.history", "description": "Browser History (Chrome, Firefox, Edge 등)"},
        {"plugin_name": "os.windows.regf.regf", "description": "Registry (전체 레지스트리)"},
        {"plugin_name": "os.windows.regf.nethist", "description": "Network History (네트워크 연결 기록)"},
        {"plugin_name": "os.windows.regf.mru.mstsc", "description": "Remote Desktop MRU"},
        {"plugin_name": "os.windows.regf.mru.opensave", "description": "OpenSave MRU"},
        {"plugin_name": "os.windows.amcache", "description": "Amcache"},
        {"tool_name": "extract_powershell_activity", "description": "PowerShell Activity (스크립트 실행 기록)"}
    ]

    observations = []
    start_time = time.time()

    if not file_paths or len(file_paths) == 0:
        return {
            "observations": [],
            "iterations": 0,
            "answer": "Error: No disk image file provided for Dissect analysis",
            "success": False
        }

    image_path = file_paths[0]

    debug_write(f"\n│ [Dissect Sequence] Collecting {len(DISSECT_ARTIFACT_SEQUENCE)} artifacts from {image_path}...\n")

    try:
        dissect_client = get_mcp_client_for_server("dissect")
        if not dissect_client:
            return {
                "observations": [],
                "iterations": 0,
                "answer": "Error: Dissect MCP server not available",
                "success": False
            }
    except Exception as e:
        return {
            "observations": [],
            "iterations": 0,
            "answer": f"Error: Failed to connect to Dissect MCP server: {str(e)}",
            "success": False
        }

    for idx, artifact in enumerate(DISSECT_ARTIFACT_SEQUENCE, 1):
        description = artifact["description"]

        # tool_name이 있으면 직접 MCP tool 호출, 아니면 plugin 방식
        if "tool_name" in artifact:
            tool_name = artifact["tool_name"]
            operation_name = tool_name
            artifact_label = tool_name
            debug_write(f"│ Artifact {idx}/{len(DISSECT_ARTIFACT_SEQUENCE)}: {tool_name} - {description}\n")

            params = {
                "image_path": image_path
            }
        else:
            plugin_name = artifact["plugin_name"]
            operation_name = "run_single_plugin"
            artifact_label = plugin_name
            debug_write(f"│ Artifact {idx}/{len(DISSECT_ARTIFACT_SEQUENCE)}: {plugin_name} - {description}\n")

            params = {
                "image_path": image_path,
                "plugin": plugin_name,
                "max_rows": 1000
            }

        try:
            result = dissect_client.call_tool("dissect", operation_name, params, timeout=300)

            if job_id:
                from ..storage.job_storage import add_mcp_tool
                add_mcp_tool(job_id, "dissect", operation_name, task_id)

            success = result.get("success", False) if isinstance(result, dict) else True
            result_data = result.get("result") if isinstance(result, dict) else result

            log_mcp_execution(
                mcp_name="dissect",
                tool_name=operation_name,
                request=params,
                response=result_data,
                success=success,
                job_id=job_id
            )

            result_str = str(result)
            if len(result_str) > 5000:
                result_str = result_str[:5000] + "\n\n...(truncated)"

            observations.append({
                "iteration": idx,
                "thought": f"Collecting {description}",
                "action": {
                    "tool": "dissect",
                    "operation": operation_name,
                    "params": params
                },
                "observation": result_str,
                "success": success
            })

            debug_write(f"│   [OK] {artifact_label}: {len(result_str)} bytes\n")

        except Exception as e:
            error_msg = f"Execution failed: {str(e)}"
            debug_write(f"│   [X] {artifact_label}: {error_msg}\n")

            log_mcp_execution(
                mcp_name="dissect",
                tool_name=operation_name,
                request=params,
                response=str(e),
                success=False,
                job_id=job_id
            )

            observations.append({
                "iteration": idx,
                "thought": f"Collecting {description}",
                "action": {
                    "tool": "dissect",
                    "operation": operation_name,
                    "params": params
                },
                "observation": error_msg,
                "success": False
            })

    execution_time = time.time() - start_time
    debug_write(f"\n│ [OK] Dissect collection: {len(observations)} artifacts, {execution_time:.2f}s\n")
    debug_write(f"│ Analyzing collected artifacts with LLM...\n")

    llm = LLMClient()

    data_summary = f"**User Request:** {user_prompt}\n\n"
    data_summary += f"**Collected Artifacts ({len(observations)}):**\n\n"

    for obs in observations:
        action = obs['action']
        plugin = action['params'].get('plugin_name', 'unknown')
        result_preview = obs['observation'][:2000]
        success_marker = "[OK]" if obs.get('success', True) else "[FAILED]"

        data_summary += f"### {obs['iteration']}. {plugin} {success_marker}\n"
        data_summary += f"Result: {result_preview}\n\n"

    try:
        analysis_prompt = format_prompt(
            "dissect_analysis.txt",
            data_summary=data_summary
        )
    except FileNotFoundError:
        analysis_prompt = f"""You are a senior DFIR analyst specializing in Windows forensics.

Analyze the collected Dissect artifacts and provide a comprehensive forensic report.

{data_summary}

**REQUIRED OUTPUT FORMAT** (Minimum 500 words):

# Dissect Forensic Analysis Report

## Executive Summary
[2-3 sentences summarizing key findings]

## Artifacts Analyzed
- Browser History
- Prefetch Files
- Amcache
- Registry (Shellbags, Shimcache, UserAssist, BAM, MRU)
- Scheduled Tasks
- Event Logs

## Detailed Findings

### Browser Activity
[URLs visited, download history, timestamps]

### Program Execution Evidence
**Prefetch:** [Executed programs, timestamps, run counts]
**Amcache:** [Installed applications, execution history]
**UserAssist:** [User-executed programs, counts]
**Shimcache:** [Application compatibility entries]
**BAM:** [Background activity records]

### File Access History
**Shellbags:** [Folder navigation history]
**Jumplist:** [Recent files and folders]
**MRU (RecentDocs, OpenSave, MSTSC):** [Recent document access]

### System Events
**Event Logs:** [Security events, logon/logoff, service changes]
**Scheduled Tasks:** [Persistence mechanisms, scheduled jobs]

### Indicators of Compromise (IOCs)
- **Suspicious Programs**: [paths, timestamps]
- **Malicious Files**: [hashes, paths]
- **Persistence Mechanisms**: [registry keys, scheduled tasks]
- **Network Indicators**: [URLs, domains, IPs]

## Timeline
[Chronological sequence of key events]

## Risk Assessment
- **Severity**: Critical/High/Medium/Low
- **Confidence**: High/Medium/Low
- **Justification**: [Why]

## Recommendations
1. **Immediate Actions**: [Steps]
2. **Further Investigation**: [Additional analysis needed]
3. **Remediation**: [Fixes]

---
Use ACTUAL data values from artifacts. Be specific with timestamps, file paths, URLs, process names."""

    try:
        response = llm.chat(
            [{"role": "user", "content": analysis_prompt}],
            timeout=180
        )
        analysis = response["choices"][0]["message"]["content"]
        debug_write(f"│ [OK] Dissect analysis completed!\n")

    except Exception as e:
        debug_write(f"│ [X] Analysis failed: {e}\n")
        analysis = f"""# Dissect Artifact Collection Summary

{len(observations)} Windows forensic artifacts collected from disk image.

## Artifacts
{chr(10).join([f"- {obs['action']['params'].get('plugin_name', 'unknown')}" for obs in observations])}

Analysis generation failed: {str(e)}
Please review raw artifact data."""

    return {
        "observations": observations,
        "iterations": len(observations),
        "answer": analysis,
        "success": True
    }


def _execute_consolehost_history_sequence(
    user_prompt: str,
    file_paths: list = None,
    job_id: str = None,
    task_id: str = None
) -> Dict[str, Any]:
    """ConsoleHost_history를 사용하여 PowerShell 명령어 히스토리 수집

    E01 디스크 이미지에서 모든 사용자의 ConsoleHost_history.txt를 추출하고 분석합니다.

    Args:
        user_prompt: 사용자 요청
        file_paths: 디스크 이미지 경로 리스트
        job_id: 작업 ID
        task_id: Task ID (task별 mcp_tools 추적용)

    Returns:
        Dict: ReAct 결과 형식과 동일
            - observations: 실행 결과
            - iterations: 실행 횟수
            - answer: 최종 분석 결과
    """
    from ..mcp_client.lazy_loader import get_mcp_client_for_server
    from ..storage.evidence_logger import log_mcp_execution
    from ..llm_client.client import LLMClient
    import time

    observations = []
    start_time = time.time()

    if not file_paths or len(file_paths) == 0:
        return {
            "observations": [],
            "iterations": 0,
            "answer": "Error: No disk image file provided for ConsoleHost_history analysis",
            "success": False
        }

    image_path = file_paths[0]

    debug_write(f"\n│ [ConsoleHost_history Sequence] Extracting PowerShell history from {image_path}...\n")

    try:
        consolehost_client = get_mcp_client_for_server("consolehost-history")
        if not consolehost_client:
            return {
                "observations": [],
                "iterations": 0,
                "answer": "Error: ConsoleHost_history MCP server not available",
                "success": False
            }
    except Exception as e:
        return {
            "observations": [],
            "iterations": 0,
            "answer": f"Error: Failed to connect to ConsoleHost_history MCP server: {str(e)}",
            "success": False
        }

    params = {"image_path": image_path}

    try:
        result = consolehost_client.call_tool("consolehost-history", "extract_consolehost_history", params, timeout=300)

        if job_id:
            from ..storage.job_storage import add_mcp_tool
            add_mcp_tool(job_id, "consolehost-history", "extract_consolehost_history", task_id)

        success = result.get("success", False) if isinstance(result, dict) else True
        result_data = result.get("result") if isinstance(result, dict) else result

        log_mcp_execution(
            mcp_name="consolehost-history",
            tool_name="extract_consolehost_history",
            request=params,
            response=result_data,
            success=success,
            job_id=job_id
        )

        result_str = str(result)
        if len(result_str) > 5000:
            result_str = result_str[:5000] + "\n\n...(truncated)"

        observations.append({
            "iteration": 1,
            "thought": "Extracting PowerShell command history from disk image",
            "action": {
                "tool": "consolehost-history",
                "operation": "extract_consolehost_history",
                "params": params
            },
            "observation": result_str,
            "success": success
        })

        debug_write(f"│   [OK] ConsoleHost_history extracted: {len(result_str)} bytes\n")

    except Exception as e:
        error_msg = f"extract_consolehost_history failed: {str(e)}"
        debug_write(f"│   [X] {error_msg}\n")

        log_mcp_execution(
            mcp_name="consolehost-history",
            tool_name="extract_consolehost_history",
            request=params,
            response=str(e),
            success=False,
            job_id=job_id
        )

        observations.append({
            "iteration": 1,
            "thought": "Extracting PowerShell command history from disk image",
            "action": {
                "tool": "consolehost-history",
                "operation": "extract_consolehost_history",
                "params": params
            },
            "observation": error_msg,
            "success": False
        })

        return {
            "observations": observations,
            "iterations": 1,
            "answer": f"Failed to extract ConsoleHost_history: {error_msg}",
            "success": False
        }

    execution_time = time.time() - start_time
    debug_write(f"\n│ [OK] ConsoleHost_history extraction: {execution_time:.2f}s\n")
    debug_write(f"│ Analyzing PowerShell commands with LLM...\n")

    llm = LLMClient()

    data_summary = f"**User Request:** {user_prompt}\n\n"
    data_summary += f"**PowerShell Command History:**\n\n"

    for obs in observations:
        result_preview = obs['observation'][:3000]
        success_marker = "[OK]" if obs.get('success', True) else "[FAILED]"
        data_summary += f"### ConsoleHost_history {success_marker}\n"
        data_summary += f"Result: {result_preview}\n\n"

    analysis_prompt = f"""You are a senior DFIR analyst specializing in PowerShell forensics.

Analyze the extracted ConsoleHost_history (PowerShell command history) and provide a comprehensive forensic report.

{data_summary}

**REQUIRED OUTPUT FORMAT** (Minimum 300 words):

# PowerShell Forensic Analysis Report

## Executive Summary
[2-3 sentences summarizing key findings from PowerShell history]

## Users Analyzed
[List of users whose PowerShell history was found]

## Suspicious Command Analysis

### High-Risk Commands
[Commands indicating potential malicious activity]
- Encoded commands (Base64)
- Download operations (Invoke-WebRequest, curl, wget)
- Credential harvesting
- Lateral movement (Enter-PSSession, Invoke-Command)
- Persistence mechanisms
- Execution policy bypasses

### Command Timeline
[Chronological sequence of significant commands]

### Indicators of Compromise (IOCs)
- **Suspicious URLs/IPs**: [URLs, domains, IPs from download commands]
- **Suspicious Files**: [File paths referenced in commands]
- **Encoded Payloads**: [Base64 or obfuscated content]

## Risk Assessment
- **Severity**: Critical/High/Medium/Low
- **Confidence**: High/Medium/Low
- **Justification**: [Why]

## Recommendations
1. **Immediate Actions**: [Steps]
2. **Further Investigation**: [Additional analysis needed]
3. **Remediation**: [Fixes]

---
Use ACTUAL command data from the extracted history. Be specific with command text, timestamps, and user accounts."""

    try:
        response = llm.chat(
            [{"role": "user", "content": analysis_prompt}],
            timeout=180
        )
        analysis = response["choices"][0]["message"]["content"]
        debug_write(f"│ [OK] ConsoleHost_history analysis completed!\n")

    except Exception as e:
        debug_write(f"│ [X] Analysis failed: {e}\n")
        analysis = f"""# ConsoleHost_history Collection Summary

PowerShell command history extracted from disk image.

## Extraction Result
{observations[0]['observation'][:2000] if observations else 'No data'}

Analysis generation failed: {str(e)}
Please review raw command data."""

    return {
        "observations": observations,
        "iterations": len(observations),
        "answer": analysis,
        "success": True
    }


def node_task_complete(state: Dict[str, Any]) -> Dict[str, Any]:
    """Task 완료 처리

    ReAct 컨텍스트의 결과를 current_task에 통합하고 TaskQueue 업데이트

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - completed_tasks: 완료된 Task 추가
            - task_queue_state: 업데이트
    """
    import time
    from ..schemas.task import HighLevelTask, TaskStatus

    current_task_dict = state.get("current_task")
    react_context = state.get("react_context", {})

    if not current_task_dict:
        return state

    if react_context.get("use_velociraptor_sequence"):
        job_id = state.get("job_id")
        task_id = current_task_dict.get("task_id")
        task_prompt = react_context.get("task_prompt", "")
        file_paths = react_context.get("file_paths", [])

        react_result = _execute_velociraptor_sequence(task_prompt, file_paths, job_id, task_id)

        observations = react_result.get("observations", [])
        execution_results = []

        for obs in observations:
            action = obs.get("action", {})
            execution_results.append({
                "success": True,
                "action": {
                    "tool": action.get("tool", ""),
                    "operation": action.get("operation", ""),
                    "params": action.get("params", {}),
                    "reason": obs.get("thought", "")
                },
                "result": obs.get("observation", ""),
                "execution_time_seconds": 0
            })

        current_task_dict["execution_results"] = execution_results
        current_task_dict["react_answer"] = react_result.get("answer", "")
        current_task_dict["react_iterations"] = react_result.get("iterations", 0)
        current_task_dict["react_success"] = react_result.get("success", False)


    elif react_context.get("use_sleuthkit_sequence"):
        job_id = state.get("job_id")
        task_id = current_task_dict.get("task_id")
        target_path = react_context.get("target_path", "")
        file_paths = react_context.get("file_paths", [])

        react_result = _execute_sleuthkit_sequence(target_path, file_paths, job_id, task_id)

        observations = react_result.get("observations", [])
        execution_results = []

        for obs in observations:
            action = obs.get("action", {})
            execution_results.append({
                "success": obs.get("success", True),
                "action": {
                    "tool": action.get("tool", ""),
                    "operation": action.get("operation", ""),
                    "params": action.get("params", {}),
                    "reason": obs.get("thought", "")
                },
                "result": obs.get("observation", ""),
                "execution_time_seconds": 0
            })

        current_task_dict["execution_results"] = execution_results
        current_task_dict["react_answer"] = react_result.get("answer", "")
        current_task_dict["react_iterations"] = react_result.get("iterations", 0)
        current_task_dict["react_success"] = react_result.get("success", False)


    elif react_context.get("use_dissect_sequence"):
        job_id = state.get("job_id")
        task_id = current_task_dict.get("task_id")
        user_prompt = react_context.get("user_prompt", "")
        file_paths = react_context.get("file_paths", [])

        react_result = _execute_dissect_sequence(user_prompt, file_paths, job_id, task_id)

        observations = react_result.get("observations", [])
        execution_results = []

        for obs in observations:
            action = obs.get("action", {})
            execution_results.append({
                "success": obs.get("success", True),
                "action": {
                    "tool": action.get("tool", ""),
                    "operation": action.get("operation", ""),
                    "params": action.get("params", {}),
                    "reason": obs.get("thought", "")
                },
                "result": obs.get("observation", ""),
                "execution_time_seconds": 0
            })

        current_task_dict["execution_results"] = execution_results
        current_task_dict["react_answer"] = react_result.get("answer", "")
        current_task_dict["react_iterations"] = react_result.get("iterations", 0)
        current_task_dict["react_success"] = react_result.get("success", False)

        import sys
        sys.__stdout__.write(
            f"│ [Task Complete] {task_id} (Dissect): {len(execution_results)} artifacts collected, "
            f"success={react_result.get('success', False)}\n"
        )
        sys.__stdout__.flush()

    elif react_context.get("use_consolehost_sequence"):
        job_id = state.get("job_id")
        task_id = current_task_dict.get("task_id")
        user_prompt = react_context.get("user_prompt", "")
        file_paths = react_context.get("file_paths", [])

        react_result = _execute_consolehost_history_sequence(user_prompt, file_paths, job_id, task_id)

        observations = react_result.get("observations", [])
        execution_results = []

        for obs in observations:
            action = obs.get("action", {})
            execution_results.append({
                "success": obs.get("success", True),
                "action": {
                    "tool": action.get("tool", ""),
                    "operation": action.get("operation", ""),
                    "params": action.get("params", {}),
                    "reason": obs.get("thought", "")
                },
                "result": obs.get("observation", ""),
                "execution_time_seconds": 0
            })

        current_task_dict["execution_results"] = execution_results
        current_task_dict["react_answer"] = react_result.get("answer", "")
        current_task_dict["react_iterations"] = react_result.get("iterations", 0)
        current_task_dict["react_success"] = react_result.get("success", False)

        import sys
        sys.__stdout__.write(
            f"│ [Task Complete] {task_id} (ConsoleHost_history): PowerShell history extracted, "
            f"success={react_result.get('success', False)}\n"
        )
        sys.__stdout__.flush()

    else:
        observations = react_context.get("observations", [])
        answer = react_context.get("answer", "No answer provided")
        iteration = react_context.get("iteration", 0)


        execution_results = []
        for obs in observations:
            action = obs.get("action", {})
            execution_results.append({
                "success": obs.get("success", True),
                "action": {
                    "tool": action.get("tool", ""),
                    "operation": action.get("operation", ""),
                    "params": action.get("params", {}),
                    "reason": obs.get("thought", "")
                },
                "result": obs.get("observation", ""),
                "execution_time_seconds": obs.get("execution_time", 0)
            })

        current_task_dict["execution_results"] = execution_results
        current_task_dict["react_answer"] = answer
        current_task_dict["react_iterations"] = iteration
        current_task_dict["react_success"] = len(execution_results) > 0


    timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
    task_id = current_task_dict.get("task_id")

    if task_id in timing.get("tasks", {}):
        task_timing = timing["tasks"][task_id]
        start_time = task_timing.get("start_time", 0)

        if start_time > 0:
            task_timing["total"] = time.time() - start_time

        task_timing.pop("start_time", None)
        task_timing.pop("exec_start", None)

    current_task_dict["status"] = "done"

    completed_tasks = state.get("completed_tasks", [])
    completed_tasks.append(current_task_dict)

    task_queue_state = state.get("task_queue_state", {})
    all_tasks_dict = task_queue_state.get("all_tasks", {})
    all_tasks_dict[task_id] = current_task_dict

    completed_ids = set(task_queue_state.get("completed_ids", []))
    completed_ids.add(task_id)

    job_id = state.get("job_id")
    if job_id:
        from ..storage.job_storage import update_task_status
        update_task_status(job_id, task_id, "done")

    ioc_analysis_results = state.get("ioc_analysis_results", [])
    is_first_execution = state.get("is_first_execution", False)

    if is_first_execution:
        tool_hint = current_task_dict.get("metadata", {}).get("tool_hint", "")
        if tool_hint != "virustotal":
            task_result_str = current_task_dict.get("react_answer", "")
            mcp_name = tool_hint or "unknown"

            try:
                ioc_analysis = _analyze_task_result_for_iocs(
                    task_result=task_result_str,
                    mcp_name=mcp_name,
                    task_description=current_task_dict.get("description", "")
                )

                ioc_analysis["source_task_id"] = task_id
                ioc_analysis["source_mcp"] = mcp_name
                ioc_analysis_results.append(ioc_analysis)

                if ioc_analysis.get("should_query_virustotal"):
                    suspicious_iocs = ioc_analysis.get("suspicious_iocs", [])

                    if suspicious_iocs:
                        existing_vt_task = None
                        for t_id, t_dict in all_tasks_dict.items():
                            if t_dict.get("metadata", {}).get("tool_hint") == "virustotal":
                                if t_dict.get("status") == "pending":
                                    existing_vt_task = t_dict
                                    break

                        if existing_vt_task:
                            existing_iocs = existing_vt_task.get("metadata", {}).get("iocs", {})
                            for ioc in suspicious_iocs:
                                ioc_type = ioc.get("type", "")
                                ioc_value = ioc.get("value", "")
                                if ioc_type in ["sha256", "md5", "sha1"]:
                                    if "hashes" not in existing_iocs:
                                        existing_iocs["hashes"] = []
                                    if ioc_value not in existing_iocs["hashes"]:
                                        existing_iocs["hashes"].append(ioc_value)
                                elif ioc_type == "ip":
                                    if "ips" not in existing_iocs:
                                        existing_iocs["ips"] = []
                                    if ioc_value not in existing_iocs["ips"]:
                                        existing_iocs["ips"].append(ioc_value)
                                elif ioc_type == "domain":
                                    if "domains" not in existing_iocs:
                                        existing_iocs["domains"] = []
                                    if ioc_value not in existing_iocs["domains"]:
                                        existing_iocs["domains"].append(ioc_value)
                            existing_vt_task["metadata"]["iocs"] = existing_iocs
                        else:
                            max_task_num = 0
                            for t_id in all_tasks_dict.keys():
                                try:
                                    num = int(t_id.split("_")[1])
                                    max_task_num = max(max_task_num, num)
                                except:
                                    pass

                            vt_task = _create_virustotal_task(
                                suspicious_iocs,
                                ioc_analysis.get("reason", "AI 판단에 의한 IoC 조회")
                            )
                            vt_task["task_id"] = f"task_{max_task_num + 1:03d}"
                            vt_task["status"] = "pending"
                            all_tasks_dict[vt_task["task_id"]] = vt_task

                            import sys
                            sys.stderr.write(f"\n[AI IoC 분석] VirusTotal 조회 필요: {ioc_analysis.get('reason')}\n")
                            sys.stderr.write(f"[AI IoC 분석] 의심 IoC {len(suspicious_iocs)}개 발견 → Task {vt_task['task_id']} 생성\n")
                            sys.stderr.flush()

            except Exception as e:
                import sys
                sys.stderr.write(f"\n[AI IoC 분석] 오류 발생: {str(e)}\n")
                sys.stderr.flush()


    return {
        **state,
        "completed_tasks": completed_tasks,
        "task_queue_state": {
            "all_tasks": all_tasks_dict,
            "completed_ids": list(completed_ids)
        },
        "current_task": None,
        "react_context": {},
        "timing": timing,
        "ioc_analysis_results": ioc_analysis_results
    }


def node_finish_two_stage(state: Dict[str, Any]) -> Dict[str, Any]:
    """모든 Task 완료 (Two-Stage 모드용)

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - completed: True
    """
    return {
        **state,
        "completed": True
    }


def should_get_next_task(state: Dict[str, Any]) -> str:
    """다음 Task가 있는지 확인

    Args:
        state: 현재 상태

    Returns:
        str: "execute" (다음 Task 있음) 또는 "finish" (없음)
    """
    current_task = state.get("current_task")

    if current_task is None:
        return "finish"
    else:
        return "execute"

