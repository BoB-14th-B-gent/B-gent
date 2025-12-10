"""High-Level Planner 모듈

LLM을 사용하여 사용자 프롬프트를 분석하고 상위 계획 생성
- generate_high_level_plan: Stage 시작 시 Task 계획 생성
- recommend_next_mcps: Stage 완료 시 다음 MCP 추천
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
import json
import os
import sys
from ..schemas.task import HighLevelTask, TaskType
from ..llm_client.client import LLMClient
from ..utils.prompt_loader import load_prompt, format_prompt


def _get_available_mcp_tools() -> List[Dict[str, Any]]:
    """MCP 클라이언트에서 동적으로 사용 가능한 도구 목록 가져오기

    Returns:
        List[Dict]: 도구 목록 (server, tool_name, description)
    """
    from ..config import get_config
    from ..mcp_client.lazy_loader import get_mcp_clients_for_servers

    cfg = get_config()

    if not cfg.mcp.enabled:
        return []

    enabled_servers = [srv.name for srv in cfg.mcp.servers if srv.enabled]

    if not enabled_servers:
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
            })

        return tools

    except Exception as e:
        sys.stderr.write(f"[WARNING] MCP 도구 로드 실패: {e}\n")
        return []


def _format_mcp_tools_for_prompt(tools: List[Dict[str, Any]]) -> str:
    """MCP 도구 목록을 프롬프트용 문자열로 변환

    Args:
        tools: MCP 도구 목록

    Returns:
        str: 서버별로 그룹화된 도구 설명 문자열
    """
    if not tools:
        return "No MCP tools available."

    servers = {}
    for tool in tools:
        server = tool.get("server", "unknown")
        if server not in servers:
            servers[server] = []
        servers[server].append(tool)

    parts = []
    for server, server_tools in sorted(servers.items()):
        parts.append(f"\n**{server}** (MCP Server):")
        for tool in server_tools[:5]:
            name = tool.get("tool_name", "")
            desc = tool.get("description", "No description")
            if len(desc) > 150:
                desc = desc[:150] + "..."
            parts.append(f"  - {name}: {desc}")
        if len(server_tools) > 5:
            parts.append(f"  - ... and {len(server_tools) - 5} more tools")

    return "\n".join(parts)




def recommend_next_mcps(
    stage_results: List[Dict[str, Any]],
    ioc_analysis_results: List[Dict[str, Any]],
    available_mcps: List[str]
) -> Dict[str, Any]:
    """AI가 현재 Stage 분석 결과를 보고 다음 MCP 추천

    Args:
        stage_results: 현재 Stage에서 완료된 Task 결과 리스트
        ioc_analysis_results: IoC 분석 결과 리스트
        available_mcps: 사용 가능한 MCP 목록

    Returns:
        Dict[str, Any]: MCP 추천 결과
    """
    llm = LLMClient()

    analysis_summary = _create_analysis_summary(stage_results, ioc_analysis_results)
    mcp_descriptions_str = _format_mcp_descriptions(available_mcps)

    try:
        prompt = format_prompt(
            "mcp_recommendation_system.txt",
            analysis_summary=analysis_summary,
            mcp_descriptions=mcp_descriptions_str
        )
    except FileNotFoundError:
        import sys
        sys.stderr.write("[WARNING] mcp_recommendation_system.txt not found, using inline fallback\n")
        prompt = f"""You are a DFIR expert. Review the analysis results and recommend next MCP tools.

## Analysis Results
{analysis_summary}

## Available MCP Tools
{mcp_descriptions_str}

Respond in JSON format with recommended_mcps array and reasoning."""

    try:
        response = llm.chat(
            [{"role": "user", "content": prompt}],
            response_format_json=True,
            timeout=60
        )

        content = response["choices"][0]["message"]["content"]
        result = json.loads(content)

        return {
            "recommended_mcps": result.get("recommended_mcps", []),
            "reasoning": result.get("reasoning", "분석 완료")
        }

    except json.JSONDecodeError as e:
        return {
            "recommended_mcps": [],
            "reasoning": f"JSON 파싱 실패: {str(e)}"
        }

    except Exception as e:
        return {
            "recommended_mcps": [],
            "reasoning": f"MCP 추천 실패: {str(e)}"
        }


def _create_analysis_summary(
    stage_results: List[Dict[str, Any]],
    ioc_analysis_results: List[Dict[str, Any]]
) -> str:
    """분석 결과 요약 문자열 생성"""
    parts = []

    parts.append("### 완료된 Task")
    for task in stage_results:
        task_id = task.get("task_id", "unknown")
        description = task.get("description", "")
        tool_hint = task.get("metadata", {}).get("tool_hint", "unknown")
        react_answer = task.get("react_answer", "")

        parts.append(f"\n**{task_id}** ({tool_hint}): {description}")

        if react_answer:
            answer_preview = react_answer[:500]
            if len(react_answer) > 500:
                answer_preview += "..."
            parts.append(f"결과: {answer_preview}")

    if ioc_analysis_results:
        parts.append("\n### IoC 분석 결과")

        all_suspicious = []
        all_benign = []

        for analysis in ioc_analysis_results:
            all_suspicious.extend(analysis.get("suspicious_iocs", []))
            all_benign.extend(analysis.get("benign_iocs_excluded", []))

        if all_suspicious:
            parts.append("\n**의심 IoC:**")
            for ioc in all_suspicious[:10]:
                ioc_type = ioc.get("type", "unknown")
                ioc_value = ioc.get("value", "")
                ioc_context = ioc.get("context", "")
                confidence = ioc.get("confidence", "")
                parts.append(f"- [{ioc_type}] {ioc_value}")
                if ioc_context:
                    parts.append(f"  → {ioc_context} (신뢰도: {confidence})")

        if all_benign:
            parts.append(f"\n**정상 판정된 IoC:** {len(all_benign)}개")

    return "\n".join(parts)


def _format_mcp_descriptions(available_mcps: List[str]) -> str:
    """사용 가능한 MCP 설명 문자열 생성 (동적으로 MCP 서버에서 가져옴)"""
    tools = _get_available_mcp_tools()

    if not tools:
        return "No MCP tools available."

    # available_mcps에 해당하는 도구만 필터링
    filtered_tools = [t for t in tools if t.get("server") in available_mcps]

    if not filtered_tools:
        # 필터링 결과가 없으면 모든 도구 사용
        filtered_tools = tools

    # 서버별로 그룹화
    servers = {}
    for tool in filtered_tools:
        server = tool.get("server", "unknown")
        if server not in servers:
            servers[server] = []
        servers[server].append(tool)

    parts = []
    for server, server_tools in sorted(servers.items()):
        parts.append(f"\n**{server}** (MCP Server):")
        for tool in server_tools[:5]:
            name = tool.get("tool_name", "")
            desc = tool.get("description", "No description")
            if len(desc) > 100:
                desc = desc[:100] + "..."
            parts.append(f"  - {name}: {desc}")
        if len(server_tools) > 5:
            parts.append(f"  - ... and {len(server_tools) - 5} more tools")

    return "\n".join(parts)


def _format_previous_context(previous_context: Dict[str, Any]) -> str:
    """이전 Stage AI 분석 결과를 프롬프트용 문자열로 변환

    Args:
        previous_context: 이전 Stage 컨텍스트 (conversation_contexts 문서)

    Returns:
        str: 프롬프트에 포함할 AI 분석 결과 문자열
    """
    if not previous_context:
        return ""

    parts = ["\n**[이전 Stage AI 분석 결과]**"]

    stage_results = previous_context.get("stage_results", {})
    if not stage_results:
        return ""

    all_suspicious_iocs = []
    all_vt_results = {}
    latest_recommendations = None

    for stage_id in sorted(stage_results.keys(), key=int):
        stage_data = stage_results[stage_id]

        ioc_analysis = stage_data.get("ioc_analysis", {})
        suspicious_iocs = ioc_analysis.get("suspicious_iocs", [])
        all_suspicious_iocs.extend(suspicious_iocs)

        vt_results = ioc_analysis.get("virustotal_results", {})
        if vt_results:
            all_vt_results.update(vt_results)

        recommendations = stage_data.get("ai_recommendations", {})
        if recommendations:
            latest_recommendations = recommendations

    if all_suspicious_iocs:
        parts.append("\n1. 발견된 의심 IoC:")
        for ioc in all_suspicious_iocs[:10]:
            ioc_type = ioc.get("type", "unknown")
            ioc_value = ioc.get("value", "")
            ioc_context = ioc.get("context", "")
            confidence = ioc.get("confidence", "")
            parts.append(f"   - [{ioc_type}] {ioc_value}")
            if ioc_context:
                parts.append(f"     → {ioc_context} (신뢰도: {confidence})")

    if all_vt_results:
        parts.append("\n2. VirusTotal 조회 결과:")
        raw_result = all_vt_results.get("raw_result", "")
        if raw_result:
            summary = raw_result[:500] + "..." if len(raw_result) > 500 else raw_result
            parts.append(f"   {summary}")

    if latest_recommendations:
        parts.append("\n3. AI 추천 다음 단계:")
        recommended_mcps = latest_recommendations.get("recommended_mcps", [])
        for rec in recommended_mcps[:5]:
            if isinstance(rec, dict):
                mcp = rec.get("mcp", "")
                reason = rec.get("reason", "")
                priority = rec.get("priority", "")
                suggested_params = rec.get("suggested_params", {})
                parts.append(f"   - **{mcp}** (우선순위: {priority}): {reason}")
                if suggested_params:
                    params_str = ", ".join([f"{k}={v}" for k, v in suggested_params.items()])
                    parts.append(f"     파라미터: {params_str}")

        reasoning = latest_recommendations.get("reasoning", "")
        if reasoning:
            parts.append(f"\n   종합 판단: {reasoning}")

    if len(parts) <= 1:
        return ""

    parts.append("\n**위 AI 분석 결과를 참고하여 Task를 생성하세요.**")
    parts.append("**이전 Stage에서 발견된 구체적인 파일 경로, 해시값을 Task 설명에 포함하세요.**")

    return "\n".join(parts)


def _classify_file_type(file_path: str) -> str:
    """파일 확장자로 타입 분류

    Args:
        file_path: 파일 경로

    Returns:
        str: 파일 타입 (disk_image, pe_file, unknown)
    """
    if not file_path:
        return "unknown"

    _, ext = os.path.splitext(file_path.lower())

    disk_extensions = [".e01", ".dd", ".raw", ".img", ".aff", ".vmdk"]
    if ext in disk_extensions:
        return "disk_image"

    pe_extensions = [".exe", ".dll", ".sys", ".scr"]
    if ext in pe_extensions:
        return "pe_file"

    return "unknown"


def _filter_analyzable_files(file_paths: List[str]) -> Dict[str, List[str]]:
    """분석 가능한 파일만 필터링 및 분류

    Args:
        file_paths: 파일 경로 리스트

    Returns:
        Dict[str, List[str]]: 타입별로 분류된 파일
            {
                "disk_images": [...],
                "pe_files": [...],
                "unknown": [...]
            }
    """
    categorized = {
        "disk_images": [],
        "pe_files": [],
        "unknown": []
    }

    for file_path in file_paths:
        file_type = _classify_file_type(file_path)

        if file_type == "disk_image":
            categorized["disk_images"].append(file_path)
        elif file_type == "pe_file":
            categorized["pe_files"].append(file_path)
        else:
            categorized["unknown"].append(file_path)

    return categorized


def generate_high_level_plan(
    user_prompt: str,
    file_paths: List[str] = None,
    file_meta: Dict[str, Any] = None,
    is_first_execution: bool = True,
    previous_context: Dict[str, Any] = None
) -> List[HighLevelTask]:
    """High-level 계획 생성 (Phase 1)

    LLM을 사용하여 사용자 프롬프트를 분석하고 추상적인 작업 단계 생성
    파일 목록을 확인하여 디스크 이미지, PE 파일만 분석 대상으로 선정

    Args:
        user_prompt: 사용자 요청
        file_paths: 파일 경로 리스트 (선택)
        file_meta: 파일 메타데이터 (선택)
        is_first_execution: 해당 conversation에서 첫 번째 실행 여부 (기본값: True)
            - True: Velociraptor + Elasticsearch를 함께 사용
            - False: LLM이 적절한 MCP를 판단하여 사용
        previous_context: 이전 Stage의 AI 분석 결과 (선택)
            - stage_results: Stage별 분석 결과 (ioc_analysis, ai_recommendations 등)

    Returns:
        List[HighLevelTask]: High-level Task 리스트

    로직:
        1. 파일 목록 분석 (디스크 이미지, PE 파일 필터링)
        2. LLM에게 사용자 의도 분석 요청
        3. 분석 대상별/도구별 Task 생성
        4. Task 간 의존성 설정
        5. Task 리스트 반환

    Example:
        입력:
            user_prompt = "디스크 이미지에서 악성 파일 추출 후 PE 분석하고 로그 검색"
            file_paths = ["data/Image.E01"]

        출력:
            [
                HighLevelTask(
                    task_id="task_001",
                    description="디스크 이미지에서 의심 파일 추출",
                    task_type=TaskType.FILE_EXTRACT,
                    target_files=["data/Image.E01"],
                    dependencies=[]
                ),
                HighLevelTask(
                    task_id="task_002",
                    description="추출된 PE 파일 분석",
                    task_type=TaskType.FILE_ANALYSIS,
                    dependencies=["task_001"]
                ),
                HighLevelTask(
                    task_id="task_003",
                    description="Elasticsearch에서 관련 로그 검색",
                    task_type=TaskType.LOG_COLLECTION,
                    dependencies=["task_002"]
                )
            ]
    """
    file_paths = file_paths or []
    file_meta = file_meta or {}

    categorized_files = _filter_analyzable_files(file_paths)
    disk_images = categorized_files["disk_images"]
    pe_files = categorized_files["pe_files"]

    llm = LLMClient()

    try:
        system_prompt = load_prompt("high_level_planning_system.txt")
    except FileNotFoundError:
        import sys
        sys.stderr.write("[WARNING] high_level_planning_system.txt not found, trying fallback\n")
        try:
            system_prompt = load_prompt("high_level_planning_fallback.txt")
        except FileNotFoundError:
            sys.stderr.write("[WARNING] Fallback prompt not found, using minimal inline fallback\n")
            system_prompt = """You are a DFIR analysis expert. Create a high-level work plan.

**IMPORTANT**: Select tools based on the available MCP tool descriptions provided in the user message.
The tool_hint must be selected from the available server list.

Output format (JSON):
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "Task description (be specific)",
      "task_type": "log_collection | file_extract | artifact_collection | file_analysis | custom",
      "target_files": ["file path"],
      "dependencies": [],
      "metadata": {
        "tool_hint": "server_name_from_available_tools",
        "priority": "high | medium | low"
      }
    }
  ]
}
```

Rules:
1. Include specific file paths, names, or hashes from user request in task description
2. tool_hint must be selected from the available server list provided in user message
3. Set dependencies only when previous task result is strictly required
"""

    file_info = ""
    if disk_images:
        disk_list = '\n'.join(f'    - "{f}"' for f in disk_images if f is not None)
        file_info += f"\n- 디스크 이미지 ({len(disk_images)}개, use EXACT paths below):\n{disk_list}"
    if pe_files:
        pe_list = '\n'.join(f'    - "{f}"' for f in pe_files if f is not None)
        file_info += f"\n- PE 파일 ({len(pe_files)}개, use EXACT paths below):\n{pe_list}"
    if categorized_files["unknown"]:
        unknown_list = '\n'.join(f'    - "{f}"' for f in categorized_files['unknown'][:3] if f is not None)
        file_info += f"\n- 기타 파일 ({len(categorized_files['unknown'])}개, 무시됨):\n{unknown_list}"

    additional_context = ""
    if not is_first_execution:
        ai_context_str = ""
        if previous_context:
            ai_context_str = _format_previous_context(previous_context)

        available_resources_str = ""
        if disk_images:
            disk_resources = chr(10).join(f'- "{img}"' for img in disk_images)
            available_resources_str = f"""
**사용 가능한 디스크 이미지 (use EXACT paths without trailing commas):**
{disk_resources}

→ 파일 추출(SleuthKit) 시 위 디스크 이미지를 target_files에 지정하세요."""

        additional_context = f"""
**참고: 이전 Stage AI 분석 결과**
{ai_context_str}
{available_resources_str}
"""

    available_tools = _get_available_mcp_tools()
    tools_description = _format_mcp_tools_for_prompt(available_tools)

    available_servers = list(set(t.get("server", "") for t in available_tools if t.get("server")))

    user_message = f"""사용자 요청: {user_prompt}

파일 목록:{file_info if file_info else " (없음)"}

**사용 가능한 MCP 도구:**
{tools_description}

**사용 가능한 서버 목록 (tool_hint에 사용):** {', '.join(available_servers) if available_servers else 'None'}
{additional_context}
위 정보와 사용 가능한 MCP 도구를 바탕으로 High-level 작업 계획을 생성하세요.
각 task의 tool_hint는 반드시 사용 가능한 서버 목록에서 선택하세요."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        response = llm.chat(messages, response_format_json=True, timeout=30, max_tokens=2048)

        content = response["choices"][0]["message"]["content"]

        data = json.loads(content)

        tasks_data = data.get("tasks", [])

        if not tasks_data:
            return _generate_default_high_level_plan(user_prompt, disk_images, pe_files)

        tasks = []
        for task_data in tasks_data:
            task_type_str = task_data.get("task_type", "custom")
            try:
                task_type = TaskType(task_type_str)
            except ValueError:
                task_type = TaskType.CUSTOM

            task = HighLevelTask(
                task_id=task_data.get("task_id", f"task_{len(tasks)+1:03d}"),
                description=task_data.get("description", ""),
                task_type=task_type,
                target_files=task_data.get("target_files", []),
                dependencies=task_data.get("dependencies", []),
                metadata=task_data.get("metadata", {})
            )
            tasks.append(task)

        tasks = _validate_and_fix_ghidra_tasks(tasks, user_prompt, file_paths)

        return tasks

    except json.JSONDecodeError:
        tasks = _generate_default_high_level_plan(user_prompt, disk_images, pe_files)
        return tasks

    except TimeoutError:
        tasks = _generate_default_high_level_plan(user_prompt, disk_images, pe_files)
        return tasks

    except Exception:
        tasks = _generate_default_high_level_plan(user_prompt, disk_images, pe_files)
        return tasks


def _validate_and_fix_ghidra_tasks(tasks: List[HighLevelTask], user_prompt: str, file_paths: List[str] = None) -> List[HighLevelTask]:
    """Ghidra Task 검증 및 자동 수정

    LLM이 Ghidra 분석을 1개 Task로 통합한 경우 자동으로 2개로 분리

    Args:
        tasks: LLM이 생성한 Task 리스트
        user_prompt: 사용자 요청
        file_paths: 분석 대상 파일 경로 리스트

    Returns:
        List[HighLevelTask]: 검증 및 수정된 Task 리스트
    """
    import sys

    prompt_lower = user_prompt.lower()
    virustotal_keywords = ["virustotal", "바이러스토탈", "vt", "sha256", "sha1", "md5", "해시", "hash"]
    if any(kw in prompt_lower for kw in virustotal_keywords):
        return tasks

    ghidra_keywords = ["ghidra", "바이너리", "리버스", "디컴파일", "reverse", "binary", "decompile"]
    is_ghidra_request = any(kw in prompt_lower for kw in ghidra_keywords)

    ghidra_tasks = [t for t in tasks if t.metadata.get("tool_hint") == "ghidra"]

    if is_ghidra_request and not ghidra_tasks:
        # print("\n[!]  Ghidra 요청이지만 LLM이 잘못된 도구를 선택했습니다!")
        # print(f"   LLM 선택: {[t.metadata.get('tool_hint') for t in tasks]}")
        # print(f"   자동 수정: Ghidra 2단계 구조로 교체")

        task_001 = HighLevelTask(
            task_id="task_001",
            description="Ghidra로 바이너리 메타데이터 수집 (함수 목록, Import/Export, 세그먼트, 문자열)",
            task_type=TaskType.FILE_ANALYSIS,
            target_files=file_paths if file_paths else [],
            dependencies=[],
            metadata={"tool_hint": "ghidra", "priority": "high", "analysis_phase": "metadata"}
        )

        task_002 = HighLevelTask(
            task_id="task_002",
            description="Ghidra로 주요 함수 디컴파일 (entry, main, 핵심 로직)",
            task_type=TaskType.FILE_ANALYSIS,
            target_files=file_paths if file_paths else [],
            dependencies=["task_001"],
            metadata={"tool_hint": "ghidra", "priority": "high", "analysis_phase": "decompile"}
        )

        # print(f"\n[OK] Ghidra Task 자동 생성 완료:")
        # print(f"  1. {task_001.task_id}: {task_001.description}")
        # print(f"  2. {task_002.task_id}: {task_002.description} (의존: {task_002.dependencies})")

        return [task_001, task_002]

    if len(ghidra_tasks) >= 2:
        has_metadata = any(t.metadata.get("analysis_phase") == "metadata" for t in ghidra_tasks)
        has_decompile = any(t.metadata.get("analysis_phase") == "decompile" for t in ghidra_tasks)

        if has_metadata and has_decompile:
            # print("Ghidra Task 검증 통과 (2단계 구조 확인)")
            return tasks

    if len(ghidra_tasks) > 0:
        # print("\nGhidra Task 구조 오류 감지!")
        # print(f"   현재: {len(ghidra_tasks)}개 Ghidra Task")
        # print(f"   자동 수정: 2단계 구조로 분리")

        non_ghidra_tasks = [t for t in tasks if t.metadata.get("tool_hint") != "ghidra"]
        task_001 = HighLevelTask(
            task_id="task_001",
            description="Ghidra로 바이너리 메타데이터 수집 (함수 목록, Import/Export, 세그먼트, 문자열)",
            task_type=TaskType.FILE_ANALYSIS,
            target_files=file_paths if file_paths else [],
            dependencies=[],
            metadata={"tool_hint": "ghidra", "priority": "high", "analysis_phase": "metadata"}
        )

        task_002 = HighLevelTask(
            task_id="task_002",
            description="Ghidra로 주요 함수 디컴파일 (entry, main, 핵심 로직)",
            task_type=TaskType.FILE_ANALYSIS,
            target_files=file_paths if file_paths else [],
            dependencies=["task_001"],
            metadata={"tool_hint": "ghidra", "priority": "high", "analysis_phase": "decompile"}
        )

        if non_ghidra_tasks:
            max_id = max([int(t.task_id.split("_")[1]) for t in non_ghidra_tasks])
            task_001.task_id = f"task_{max_id + 1:03d}"
            task_002.task_id = f"task_{max_id + 2:03d}"
            task_002.dependencies = [task_001.task_id]

            result = non_ghidra_tasks + [task_001, task_002]
        else:
            result = [task_001, task_002]

        # print(f"\n[OK] Ghidra Task 자동 수정 완료:")
        # print(f"  1. {task_001.task_id}: {task_001.description}")
        # print(f"  2. {task_002.task_id}: {task_002.description} (의존: {task_002.dependencies})")

        return result

    return tasks


def _generate_default_high_level_plan(
    user_prompt: str,
    disk_images: List[str],
    pe_files: List[str]
) -> List[HighLevelTask]:
    """기본 High-level 계획 생성 (폴백)

    LLM 실패 시 규칙 기반으로 Task 생성

    Args:
        user_prompt: 사용자 요청
        disk_images: 디스크 이미지 파일 리스트
        pe_files: PE 파일 리스트

    Returns:
        List[HighLevelTask]: 기본 Task 리스트
    """
    import sys
    # sys.stderr.write("\n[!] 기본 High-level 계획을 사용합니다 (LLM 폴백)\n")
    # sys.stderr.flush()

    tasks = []
    prompt_lower = user_prompt.lower()

    virustotal_keywords = ["virustotal", "바이러스토탈", "vt", "sha256", "sha1", "md5", "해시", "hash"]
    if any(kw in prompt_lower for kw in virustotal_keywords):
        import re
        hash_pattern = r'\b[a-fA-F0-9]{32,64}\b'
        hash_matches = re.findall(hash_pattern, user_prompt)
        file_hash = hash_matches[0] if hash_matches else ""

        return [
            HighLevelTask(
                task_id="task_001",
                description=f"VirusTotal로 파일 해시 조사{' (해시: ' + file_hash + ')' if file_hash else ''}",
                task_type=TaskType.FILE_ANALYSIS,
                target_files=[],
                dependencies=[],
                metadata={"tool_hint": "virustotal", "priority": "high", "file_hash": file_hash}
            )
        ]

    ghidra_keywords = ["ghidra", "바이너리", "리버스", "디컴파일", "reverse", "binary", "decompile"]
    if any(kw in prompt_lower for kw in ghidra_keywords):
        # sys.stderr.write("[!] Ghidra 키워드 감지 → Ghidra 2-Task 구조 생성 (기본)\n")
        # sys.stderr.flush()
        return [
            HighLevelTask(
                task_id="task_001",
                description="Ghidra로 바이너리 메타데이터 수집 (함수 목록, Import/Export, 세그먼트, 문자열)",
                task_type=TaskType.FILE_ANALYSIS,
                target_files=pe_files if pe_files else [],
                dependencies=[],
                metadata={"tool_hint": "ghidra", "priority": "high", "analysis_phase": "metadata"}
            ),
            HighLevelTask(
                task_id="task_002",
                description="Ghidra로 주요 함수 디컴파일 (entry, main, 핵심 로직)",
                task_type=TaskType.FILE_ANALYSIS,
                target_files=pe_files if pe_files else [],
                dependencies=["task_001"],
                metadata={"tool_hint": "ghidra", "priority": "high", "analysis_phase": "decompile"}
            )
        ]

    if disk_images or any(kw in prompt_lower for kw in ["디스크", "이미지", "disk", "image"]):
        if any(kw in prompt_lower for kw in ["추출", "extract", "찾기", "find", "파일", "file"]):
            import re

            win_path_pattern = r'[A-Za-z]:\\[^"\s]+'
            unix_path_pattern = r'/[^\s"]+'
            filename_pattern = r'\b[\w\-]+\.[a-zA-Z0-9]{2,5}\b'

            target_path = None

            win_matches = re.findall(win_path_pattern, user_prompt)
            if win_matches:
                target_path = win_matches[0]
            elif re.search(unix_path_pattern, user_prompt):
                unix_matches = re.findall(unix_path_pattern, user_prompt)
                target_path = unix_matches[0] if unix_matches else None
            elif re.search(filename_pattern, user_prompt):
                filename_matches = re.findall(filename_pattern, user_prompt)
                target_path = filename_matches[0] if filename_matches else None

            if target_path:
                description = f"SleuthKit으로 디스크 이미지에서 파일 추출: {target_path}"
            else:
                description = f"SleuthKit으로 디스크 이미지에서 파일 추출 (프롬프트: {user_prompt[:100]})"

            tasks.append(HighLevelTask(
                task_id="task_001",
                description=description,
                task_type=TaskType.FILE_EXTRACT,
                target_files=disk_images,
                dependencies=[],
                metadata={
                    "tool_hint": "sleuthkit",
                    "priority": "high",
                    "target_path": target_path,
                    "user_prompt": user_prompt
                }
            ))
        else:
            tasks.append(HighLevelTask(
                task_id="task_001",
                description="Velociraptor로 디스크 이미지 아티팩트 수집 및 분석",
                task_type=TaskType.ARTIFACT_COLLECTION,
                target_files=disk_images,
                dependencies=[],
                metadata={"tool_hint": "velociraptor", "priority": "high"}
            ))

    if any(kw in prompt_lower for kw in ["로그", "log", "이벤트", "event", "검색", "search", "elastic", "siem"]):
        dependencies = []
        task_id = f"task_{len(tasks)+1:03d}"

        tasks.append(HighLevelTask(
            task_id=task_id,
            description="Elasticsearch 로그 검색 및 분석",
            task_type=TaskType.LOG_COLLECTION,
            target_files=[],
            dependencies=dependencies,
            metadata={"tool_hint": "elastic", "priority": "high"}
        ))

    if any(kw in prompt_lower for kw in ["아티팩트", "artifact", "수집", "collect", "velociraptor", "prefetch", "프로세스"]):
        dependencies = [tasks[-1].task_id] if tasks else []
        task_id = f"task_{len(tasks)+1:03d}"

        tasks.append(HighLevelTask(
            task_id=task_id,
            description="Velociraptor로 아티팩트 수집",
            task_type=TaskType.ARTIFACT_COLLECTION,
            target_files=[],
            dependencies=dependencies,
            metadata={"tool_hint": "velociraptor", "priority": "medium"}
        ))

    if not tasks:
        tasks.append(HighLevelTask(
            task_id="task_001",
            description="Elasticsearch 로그 검색",
            task_type=TaskType.LOG_COLLECTION,
            target_files=[],
            dependencies=[],
            metadata={"tool_hint": "elastic", "priority": "medium"}
        ))

    # print(f"  기본 계획 생성 완료: {len(tasks)}개 Task")
    return tasks
