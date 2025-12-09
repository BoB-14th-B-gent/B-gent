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
from ..llm_client.client import LLMClient


# =============================================================================
# IoC 분석 관련 (Task 완료 시 AI 기반 IoC 분석)
# =============================================================================

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

    prompt = f"""당신은 DFIR(Digital Forensics and Incident Response) 전문가입니다.
아래 MCP 실행 결과를 분석하여 VirusTotal로 조회할 가치가 있는 **의심스러운 IoC**를 판단하세요.

## 분석 대상
- MCP: {mcp_name}
- Task: {task_description}
- 실행 결과:
```
{truncated_result}
```

## 판단 기준

### VirusTotal 조회가 필요한 경우 (should_query_virustotal: true)
- 의심스러운 경로의 파일 해시 (AppData, Temp, Startup, Downloads, ProgramData 등)
- 알려지지 않은 외부 IP 통신 (C2 서버 의심)
- 의심스러운 도메인 (DGA 패턴, 최근 등록 도메인 등)
- 비정상적인 프로세스의 해시
- 난독화된 스크립트 파일
- 비정상적인 시간대 실행 파일

### VirusTotal 조회가 불필요한 경우 (should_query_virustotal: false)
- Windows 시스템 파일 (notepad.exe, cmd.exe, explorer.exe 등)의 정상 해시
- 내부 IP (192.168.x.x, 10.x.x.x, 172.16-31.x.x, 127.x.x.x)
- 알려진 정상 도메인 (microsoft.com, google.com, windows.com 등)
- 컨텍스트상 정상으로 판단되는 항목
- 정상 경로의 정상 프로그램 (C:\\Windows\\System32, C:\\Program Files 등)

## 응답 형식 (JSON)
```json
{{
    "should_query_virustotal": true,
    "reason": "판단 이유 (1-2문장)",
    "suspicious_iocs": [
        {{
            "type": "sha256",
            "value": "실제 해시값",
            "context": "왜 의심스러운지 설명",
            "confidence": "high"
        }}
    ],
    "benign_iocs_excluded": [
        {{
            "type": "ip",
            "value": "192.168.1.1",
            "reason": "내부 네트워크 IP"
        }}
    ]
}}
```

**중요**:
- 단순히 해시/IP가 있다고 조회하지 마세요. **컨텍스트**를 보고 판단하세요.
- confidence가 high/medium인 IoC만 suspicious_iocs에 포함하세요.
- 확실히 정상인 항목은 benign_iocs_excluded에 포함하세요.
- IoC가 발견되지 않으면 should_query_virustotal: false로 설정하세요.
- suspicious_iocs 배열은 최대 10개까지만 포함하세요 (우선순위 순)."""

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


# =============================================================================
# LangGraph 워크플로우 정의
# =============================================================================

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

    # print("\n[Phase 1] Planning")

    user_prompt = state["user_prompt"]
    file_paths = state.get("file_paths", [])
    file_meta = state.get("file_meta", {})
    is_first_execution = state.get("is_first_execution", True)  # 첫 실행 여부
    previous_context = state.get("previous_context")  # 이전 Stage AI 분석 결과

    start_time = time.time()

    try:
        # print(f"│ Requesting LLM analysis...")
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

        # print(f"[OK] Generated {len(high_level_tasks)} tasks")

        # print(f"\n[Phase 2] Execution\n")

        timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
        timing["high_level_planning"] = high_level_planning_time

        job_id = state.get("job_id")
        current_stage_id = state.get("stage_id", 1)  # state에서 stage_id 가져오기
        if job_id:
            plan_list = [
                {
                    "task_id": t.task_id,
                    "description": t.description,
                    "mcp_server": "",
                    "mcp_tools": [],
                    "status": "pending"
                }
                for t in high_level_tasks
            ]
            save_agent_state(
                agent_id=job_id,
                stage_id=current_stage_id,  # 동적으로 stage_id 사용
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
        # print(f"\n[[X]] {error_msg}\n")
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

    # print(f"\nTask {len(completed_tasks) + 1}: {task.description}")

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

                    dependency_context += f"\n### {dep_id}: {dep_desc}\n"
                    dependency_context += f"- Tool: {dep_tool_hint}\n"
                    dependency_context += f"- Status: {success_count}/{len(dep_results)} successful\n"

                    # 추출된 파일 경로 파싱 (sleuthkit 결과에서)
                    if dep_tool_hint == "sleuthkit" and react_answer:
                        dependency_context += f"\n**Extracted Files (use these paths for analysis):**\n"
                        # react_answer에서 파일 경로 추출 시도
                        import re
                        # 일반적인 추출 경로 패턴 (예: /tmp/extracted/..., ./output/...)
                        extracted_paths = re.findall(r'(?:extracted|output|saved)[^\n]*?([/\\.][^\s\n"\']+\.[a-zA-Z0-9]+)', react_answer, re.IGNORECASE)
                        if extracted_paths:
                            for path in extracted_paths[:5]:  # 최대 5개
                                dependency_context += f"  - {path}\n"
                        else:
                            # 경로를 찾지 못한 경우 react_answer 일부 포함
                            answer_preview = react_answer[:500] if len(react_answer) > 500 else react_answer
                            dependency_context += f"```\n{answer_preview}\n```\n"

                    # velociraptor 아티팩트 결과에서 의심 파일 경로 추출
                    elif dep_tool_hint == "velociraptor" and react_answer:
                        dependency_context += f"\n**Artifact Analysis Results:**\n"
                        # 의심 파일 경로 패턴
                        import re
                        suspicious_paths = re.findall(r'[A-Za-z]:\\[^\s\n"\'<>|*?]+\.[a-zA-Z0-9]{2,5}', react_answer)
                        if suspicious_paths:
                            unique_paths = list(set(suspicious_paths))[:10]  # 최대 10개
                            dependency_context += f"**Suspicious file paths found (extract these using SleuthKit):**\n"
                            for path in unique_paths:
                                dependency_context += f"  - {path}\n"
                        # react_answer 요약 포함
                        answer_preview = react_answer[:800] if len(react_answer) > 800 else react_answer
                        dependency_context += f"\n**Summary:**\n```\n{answer_preview}\n```\n"

                    # 기타 도구 결과
                    elif react_answer:
                        answer_preview = react_answer[:500] if len(react_answer) > 500 else react_answer
                        dependency_context += f"\n**Result:**\n```\n{answer_preview}\n```\n"

                    break

    # depends_on_output 처리: 선행 Task에서 추출된 파일 경로를 target_files에 추가
    depends_on_output = task.metadata.get("depends_on_output", "")
    extracted_file_paths = []

    if depends_on_output and task.dependencies:
        for dep_id in task.dependencies:
            for completed in completed_tasks:
                if completed.get("task_id") == dep_id:
                    react_answer = completed.get("react_answer", "")
                    dep_tool_hint = completed.get("metadata", {}).get("tool_hint", "")

                    if depends_on_output == "extracted_file_path" and dep_tool_hint == "sleuthkit":
                        # SleuthKit 결과에서 추출된 파일 경로 파싱
                        import re
                        # 다양한 추출 경로 패턴
                        patterns = [
                            r'(?:extracted|output|saved|written)[^\n]*?([/\\][^\s\n"\'<>|*?]+\.[a-zA-Z0-9]+)',
                            r'(?:File saved to|Extracted to|Output:)\s*["\']?([^\s\n"\']+)["\']?',
                            r'(/tmp/[^\s\n"\']+)',
                            r'(\./output/[^\s\n"\']+)',
                        ]
                        for pattern in patterns:
                            paths = re.findall(pattern, react_answer, re.IGNORECASE)
                            if paths:
                                extracted_file_paths.extend(paths)
                                break

                    elif depends_on_output == "suspicious_file_paths" and dep_tool_hint == "velociraptor":
                        # Velociraptor 결과에서 의심 파일 경로 파싱
                        import re
                        suspicious_paths = re.findall(r'[A-Za-z]:\\[^\s\n"\'<>|*?]+\.[a-zA-Z0-9]{2,5}', react_answer)
                        if suspicious_paths:
                            extracted_file_paths.extend(list(set(suspicious_paths))[:10])

                    break

    # target_files 업데이트 (추출된 파일 경로 추가)
    if extracted_file_paths:
        task.target_files = list(set(task.target_files + extracted_file_paths))
        # current_task_dict도 업데이트
        current_task_dict["target_files"] = task.target_files
        dependency_context += f"\n**Files to analyze (from previous task):**\n"
        for path in extracted_file_paths[:5]:
            dependency_context += f"  - {path}\n"

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

    available_tools = get_available_tools_for_task(task.description, file_meta)

    import os
    if os.getenv("MCP_DEBUG") == "1":
        if available_tools:
            tool_names = [f"{t['server']}.{t['tool_name']}" for t in available_tools[:3]]
            # print(f"│ Available tools: {len(available_tools)} (first 3: {', '.join(tool_names)})")

    tool_hint = task.metadata.get("tool_hint", "")

    if tool_hint == "velociraptor":
        # print(f"│ Using predefined Velociraptor artifact sequence (skipping ReAct loop)")
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
            # print(f"│ Using predefined SleuthKit extraction pipeline (skipping ReAct loop)")
            # print(f"│ Target file: {target_path}")
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
        "use_velociraptor_sequence": False,
        "tool_hint": tool_hint  # MCP 전략 프롬프트 미리 로딩용
    }

    # print(f"│ ReAct Loop initialized (max {react_context['max_iterations']} iterations)")
    # print(f"│ Available tools: {len(available_tools)}")

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
    tool_hint = react_context.get("tool_hint", "")  # MCP 전략 힌트

    # print(f"\n│ Iteration {iteration}/{max_iterations}")
    # print(f"│ [THINK] Analyzing situation...")

    start_time = time.time()

    thought_result = generate_react_thought(
        task_description=task_prompt,
        observations=observations,
        available_tools=available_tools,
        file_paths=file_paths,
        max_iterations=max_iterations,
        user_prompt=state.get("user_prompt"),
        tool_hint=tool_hint  # 전략 프롬프트 미리 로딩용
    )

    think_time = time.time() - start_time

    finished = thought_result.get("finished", False)
    thought = thought_result.get("thought", "")
    action = thought_result.get("action")
    answer = thought_result.get("answer")

    # print(f"│ [THINK] {thought[:100]}..." if len(thought) > 100 else f"│ [THINK] {thought}")
    # print(f"│ Think time: {think_time:.2f}s")

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

    if not action_dict:
        # print(f"│ [EXECUTE] No action to execute")
        react_context["finished"] = True
        react_context["answer"] = "No valid action provided - cannot execute"
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
        # print(f"│ [EXECUTE] Invalid tool name: '{tool_name}' - forcing completion")
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
    # print(f"│ [EXECUTE] {action_name}")

    start_time = time.time()

    result = execute_action(action, job_id=job_id, task_id=task_id)

    exec_time = time.time() - start_time

    react_context["current_execution_result"] = result.to_dict()
    react_context["current_execution_time"] = exec_time

    success_marker = "[OK]" if result.success else "[X]"
    # print(f"│ [{success_marker}] Execution time: {exec_time:.2f}s")

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
    action_dict = react_context.get("current_action", {})
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

    obs_preview = observation[:200] if len(observation) > 200 else observation
    # print(f"│ [OBSERVE] {obs_preview}...")

    # DEBUG: observation 내용 확인 (성공/실패 모두 출력)
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
        "react_context": react_context
    }


def should_continue_react(state: Dict[str, Any]) -> str:
    """ReAct 루프 계속 여부 판단

    Args:
        state: 현재 상태

    Returns:
        str: "act" (계속 실행) 또는 "finish" (완료)
    """
    react_context = state.get("react_context", {})

    if react_context.get("use_velociraptor_sequence") or react_context.get("use_sleuthkit_sequence"):
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
            "operation": "windows_execution_amcache",
            "description": "Windows Execution - Amcache",
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

    # print(f"\n│ Collecting {len(VELOCIRAPTOR_SEQUENCE)} Velociraptor artifacts in predefined order...")

    for idx, artifact in enumerate(VELOCIRAPTOR_SEQUENCE, 1):
        operation = artifact["operation"]
        description = artifact["description"]
        params = artifact["params"].copy()

        if artifact.get("requires_client_id") and client_id:
            params["client_id"] = client_id

        # print(f"│ Artifact {idx}/{len(VELOCIRAPTOR_SEQUENCE)}: {operation}")
        # print(f"│   → {description}")
        if params.get("client_id"):
            # print(f"│   → Using Client ID: {client_id}")
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
                    # print(f"│   [OK] Extracted Client ID: {client_id}")
                    pass
                else:
                    # print(f"│   [!]  Warning: Could not extract Client ID")
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

            # print(f"│   [OK] Success ({len(result_str)} bytes)")

        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            # print(f"│   [X] Failed: {str(e)}")

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
    # print(f"\n│ [OK] Velociraptor collection: {len(observations)} artifacts, {execution_time:.2f}s")

    # print(f"│ ")
    # print(f"│ Analyzing collected artifacts with LLM (this may take 1-2 minutes)...")
    # print(f"│ ")

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
        # print(f"│ Requesting LLM analysis...")
        response = llm.chat(
            [{"role": "user", "content": analysis_prompt}],
            timeout=180
        )
        analysis = response["choices"][0]["message"]["content"]
        # print(f"│ ")
        # print(f"│ [OK] Analysis completed!")
        # print(f"│ ")

    except Exception as e:
        # print(f"│ ")
        # print(f"│ [[X]] Analysis failed: {e}")
        # print(f"│ ")
        analysis = f"""# Velociraptor Artifact Collection Summary

{len(observations)} Windows forensic artifacts collected.

## Artifacts
{chr(10).join([f"- {obs['action']['operation']}" for obs in observations])}

Analysis generation failed: {str(e)}
Please review raw artifact data."""

    # print(f"│ Returning analysis results to workflow...")

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
    # print(f"\n│ Extracting file using SleuthKit 3-step pipeline...")
    # print(f"│ Image: {image_path}")
    # print(f"│ Target: {target_path}")

    # print(f"\n│ Step 1/3: Get disk partition info")
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
            # print(f"│   [!] Could not parse fs_offset_sectors, using default: {fs_offset_sectors}")
            pass
        else:
            # print(f"│   [OK] Found fs_offset_sectors: {fs_offset_sectors}")
            pass

    except Exception as e:
        error_msg = f"disk_partition_info failed: {str(e)}"
        # print(f"│   [[X]] {error_msg}")
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

    # print(f"\n│ Step 2/3: Search inode by path")
    filepath_unix = target_path.replace("\\", "/")
    if filepath_unix.startswith("C:/") or filepath_unix.startswith("c:/"):
        filepath_unix = filepath_unix[2:]
    elif filepath_unix.startswith("C:\\") or filepath_unix.startswith("c:\\"):
        filepath_unix = filepath_unix[2:]
    # print(f"│   → Searching: {filepath_unix}")

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
            # print(f"│   [X] {error_msg}")
            return {
                "observations": observations,
                "iterations": 2,
                "answer": error_msg,
                "success": False
            }

        # print(f"│   [OK] Found inode: {inode}")

    except Exception as e:
        error_msg = f"search_inode_by_path failed: {str(e)}"
        # print(f"│   [[X]] {error_msg}")
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

    # print(f"\n│ Step 3/3: Extract file by inode")
    out_dir = "./data/output"
    # print(f"│   → Output directory: {out_dir}")

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
            # print(f"│   [OK] File extracted successfully")
            answer = f"Successfully extracted {target_path} (inode: {inode}) to {out_dir}"
        else:
            # print(f"│   [!] Extraction may have failed - check result")
            answer = f"Extraction attempted for {target_path} (inode: {inode}), please check {out_dir}"

    except Exception as e:
        error_msg = f"extract_files_by_inode failed: {str(e)}"
        # print(f"│   [[X]] {error_msg}")
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
    # print(f"\n│ [OK] SleuthKit extraction pipeline: 3 steps, {execution_time:.2f}s")

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
        # print(f"│ Requesting LLM analysis...")
        response = llm.chat(
            [{"role": "user", "content": analysis_prompt}],
            timeout=180
        )
        analysis = response["choices"][0]["message"]["content"]
        # print(f"│ ")
        # print(f"│ [OK] Analysis completed!")
        # print(f"│ ")

    except Exception as e:
        # print(f"│ ")
        # print(f"│ [[X]] Analysis failed: {e}")
        # print(f"│ ")
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

    # print(f"│ Returning analysis results to workflow...")

    return {
        "observations": observations,
        "iterations": 3,
        "answer": analysis,
        "success": success
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
        # import sys
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

        # # Velociraptor sequence 완료 로깅
        # sys.__stdout__.write(
        #     f"[Task Complete] {task_id} (Velociraptor): {len(execution_results)} artifacts collected, "
        #     f"success={react_result.get('success', False)}\n"
        # )
        # sys.__stdout__.flush()

    elif react_context.get("use_sleuthkit_sequence"):
        # import sys
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

        # # SleuthKit sequence 완료 로깅
        # sys.__stdout__.write(
        #     f"[Task Complete] {task_id} (SleuthKit): {len(execution_results)} steps, "
        #     f"target={target_path}, success={react_result.get('success', False)}\n"
        # )
        # sys.__stdout__.flush()

    else:
        observations = react_context.get("observations", [])
        answer = react_context.get("answer", "No answer provided")
        iteration = react_context.get("iteration", 0)
        # task_id_for_log = current_task_dict.get("task_id", "unknown")
        # task_desc_for_log = current_task_dict.get("description", "")[:50]

        # # ReAct 즉시 종료 감지 및 로깅
        # import sys
        # if not observations or len(observations) == 0:
        #     sys.__stdout__.write(
        #         f"\n[ReAct Early Termination] Task {task_id_for_log} completed with NO tool executions\n"
        #         f"  Description: {task_desc_for_log}...\n"
        #         f"  Iterations: {iteration}\n"
        #         f"  Answer: {answer[:300] if answer else 'None'}...\n\n"
        #     )
        #     sys.__stdout__.flush()
        # else:
        #     # observations가 있지만 iteration이 1인 경우 (빠른 종료)
        #     if iteration <= 1:
        #         sys.__stdout__.write(
        #             f"\n[ReAct Quick Finish] Task {task_id_for_log} finished after {iteration} iteration(s)\n"
        #             f"  Description: {task_desc_for_log}...\n"
        #             f"  Tool executions: {len(observations)}\n"
        #         )
        #         sys.__stdout__.flush()

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

        # # 최종 로깅: execution_results 개수
        # sys.__stdout__.write(
        #     f"[Task Complete] {task_id_for_log}: {len(execution_results)} execution_results, "
        #     f"iterations={iteration}, success={len(execution_results) > 0}\n"
        # )
        # sys.__stdout__.flush()

    timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
    task_id = current_task_dict.get("task_id")

    if task_id in timing.get("tasks", {}):
        task_timing = timing["tasks"][task_id]
        start_time = task_timing.get("start_time", 0)

        if start_time > 0:
            task_timing["total"] = time.time() - start_time

        task_timing.pop("start_time", None)
        task_timing.pop("exec_start", None)

    # Task 상태를 'done'으로 업데이트 (의존성 해결에 필수)
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

    # Stage 1(첫 실행)에서 AI 기반 IoC 분석
    ioc_analysis_results = state.get("ioc_analysis_results", [])
    is_first_execution = state.get("is_first_execution", False)

    if is_first_execution:
        # VirusTotal Task가 아닌 경우에만 IoC 분석 수행
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

                # 분석 결과 저장 (Stage 2+에서 활용)
                ioc_analysis["source_task_id"] = task_id
                ioc_analysis["source_mcp"] = mcp_name
                ioc_analysis_results.append(ioc_analysis)

                # AI가 VirusTotal 조회 필요하다고 판단한 경우
                if ioc_analysis.get("should_query_virustotal"):
                    suspicious_iocs = ioc_analysis.get("suspicious_iocs", [])

                    if suspicious_iocs:
                        # 이미 VirusTotal Task가 큐에 있는지 확인
                        existing_vt_task = None
                        for t_id, t_dict in all_tasks_dict.items():
                            if t_dict.get("metadata", {}).get("tool_hint") == "virustotal":
                                if t_dict.get("status") == "pending":
                                    existing_vt_task = t_dict
                                    break

                        if existing_vt_task:
                            # 기존 VirusTotal Task에 IoC 추가
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
                            # 새로운 VirusTotal Task 생성
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

    # print(f"│ [OK] Task completed: {len(current_task_dict['execution_results'])} actions, {current_task_dict['react_iterations']} iterations")

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

