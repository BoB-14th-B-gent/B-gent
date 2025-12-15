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


def _load_server_descriptions_from_file() -> Dict[str, str]:
    """mcp_server_descriptions.json 파일에서 서버 설명 로드

    Returns:
        Dict[str, str]: 서버 이름 -> 서버 설명
    """
    import json
    descriptions_path = os.path.join(os.path.dirname(__file__), "..", "mcp_server_descriptions.json")

    try:
        with open(descriptions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            servers = data.get("servers", {})
            return {name: info.get("description", "") for name, info in servers.items()}
    except FileNotFoundError:
        sys.stderr.write(f"[WARNING] mcp_server_descriptions.json not found: {descriptions_path}\n")
        return {}
    except Exception as e:
        sys.stderr.write(f"[WARNING] Failed to load server descriptions: {e}\n")
        return {}


def _get_mcp_server_descriptions() -> Dict[str, str]:
    """MCP 서버별 설명 반환 (설명 파일 + 도구 목록)

    Returns:
        Dict[str, str]: 서버 이름 -> 서버 기능 설명
    """
    from ..config import get_config
    from ..mcp_client.lazy_loader import get_mcp_clients_for_servers

    cfg = get_config()

    if not cfg.mcp.enabled:
        return {}

    enabled_servers = [srv.name for srv in cfg.mcp.servers if srv.enabled]

    if not enabled_servers:
        return {}

    file_descriptions = _load_server_descriptions_from_file()

    try:
        client = get_mcp_clients_for_servers(enabled_servers)
        all_tools = client.get_all_tools()

        servers = {}
        for tool in all_tools:
            server = tool.get("server", "unknown")
            if server not in servers:
                servers[server] = []
            servers[server].append(tool)

        server_descriptions = {}
        for server, tools in servers.items():
            tool_names = [t.get("name", "") for t in tools]
            purpose = file_descriptions.get(server, f"MCP server with {len(tools)} tools")
            tool_list = ', '.join(tool_names[:8])
            if len(tool_names) > 8:
                tool_list += f" ... (+{len(tool_names) - 8} more)"
            server_descriptions[server] = f"{purpose}\n    Tools: {tool_list}"

        return server_descriptions

    except Exception as e:
        sys.stderr.write(f"[WARNING] MCP 서버 설명 로드 실패: {e}\n")
        return {}


def _get_e01_capable_servers() -> List[str]:
    """mcp_server_descriptions.json에서 E01 지원 서버 목록 로드

    Returns:
        List[str]: E01 이미지를 직접 처리할 수 있는 서버 목록
    """
    descriptions_path = os.path.join(os.path.dirname(__file__), "..", "mcp_server_descriptions.json")
    try:
        with open(descriptions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("e01_capable_servers", [])
    except Exception:
        return []


def _format_mcp_servers_for_prompt(server_descriptions: Dict[str, str]) -> str:
    """MCP 서버 목록을 프롬프트용 문자열로 변환 (서버 레벨만)

    E01 지원 서버와 SQLite/파일 전용 서버를 구분하여 표시

    Args:
        server_descriptions: 서버 이름 -> 서버 설명

    Returns:
        str: 서버별 설명 문자열
    """
    if not server_descriptions:
        return "No MCP servers available."

    e01_capable = _get_e01_capable_servers()

    e01_servers = []
    other_servers = []

    for server in sorted(server_descriptions.keys()):
        if server in e01_capable:
            e01_servers.append(server)
        else:
            other_servers.append(server)

    parts = []

    parts.append("\n**[E01 DISK IMAGE CAPABLE - Use for E01/dd/raw disk images]**")
    for server in e01_servers:
        description = server_descriptions[server]
        parts.append(f"\n**{server}** (MCP Server - E01 supported):")
        parts.append(f"  {description}")

    if other_servers:
        parts.append("\n\n**[OTHER SERVERS - For pre-extracted files, logs, etc.]**")
        for server in other_servers:
            description = server_descriptions[server]
            parts.append(f"\n**{server}** (MCP Server):")
            parts.append(f"  {description}")

    return "\n".join(parts)


def _format_mcp_tools_for_prompt(tools: List[Dict[str, Any]]) -> str:
    """MCP 도구 목록을 프롬프트용 문자열로 변환 (Legacy - 사용하지 않음)

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

    filtered_tools = [t for t in tools if t.get("server") in available_mcps]

    if not filtered_tools:
        filtered_tools = tools

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


def _generate_forced_dissect_elastic_tasks(
    user_prompt: str,
    disk_images: List[str]
) -> List[HighLevelTask]:
    """Stage 1에서 전체 Evidence 수집 Task 생성

    ANALYZE_ON_STAGE1 설정이 활성화된 경우,
    LLM 계획 생성을 건너뛰고 모든 Evidence 수집을 강제로 실행합니다.

    실행 순서:
    1. Dissect: prefetch, jumplist, Browser history, registry, network_history, mru.*
    2. Velociraptor: Amcache, UserAssist, ShimCache, Shellbags, BAM, download Folder, scheduled tasks, mru.recentdocs
    3. ConsoleHost_history: PowerShell command history
    4. Elasticsearch: SIEM Log 검색

    Args:
        user_prompt: 사용자 요청
        disk_images: 디스크 이미지 파일 경로 리스트

    Returns:
        List[HighLevelTask]: 전체 Evidence 수집 Task 리스트
    """
    tasks = []

    if disk_images:
        tasks.append(HighLevelTask(
            task_id="task_001",
            description="Dissect를 사용하여 디스크 이미지에서 Windows 아티팩트 수집 (Prefetch, Jumplist, Browser History, Registry, Network History, MRU)",
            task_type=TaskType.ARTIFACT_COLLECTION,
            target_files=disk_images,
            dependencies=[],
            metadata={
                "priority": "high",
                "tool_hint": "dissect",
                "use_dissect_sequence": True  # Dissect sequence 사용 플래그
            }
        ))

    tasks.append(HighLevelTask(
        task_id="task_002",
        description="Velociraptor를 사용하여 Live Endpoint에서 Windows 아티팩트 수집 (Amcache, UserAssist, ShimCache, Shellbags, BAM, Downloads, Scheduled Tasks, RecentDocs)",
        task_type=TaskType.ARTIFACT_COLLECTION,
        target_files=[],
        dependencies=[],
        metadata={
            "priority": "high",
            "tool_hint": "velociraptor"
        }
    ))

    tasks.append(HighLevelTask(
        task_id="task_003",
        description=f"Elasticsearch에서 SIEM 로그 검색: {user_prompt[:100]}",
        task_type=TaskType.LOG_COLLECTION,
        target_files=[],
        dependencies=[],
        metadata={
            "priority": "high",
            "tool_hint": "elastic"
        }
    ))

    return tasks


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
    from ..config import get_config

    file_paths = file_paths or []
    file_meta = file_meta or {}

    categorized_files = _filter_analyzable_files(file_paths)
    disk_images = categorized_files["disk_images"]
    pe_files = categorized_files["pe_files"]

    cfg = get_config()
    sys.stderr.write(f"[DEBUG] is_first_execution={is_first_execution}, analyze_on_stage1={cfg.stage.analyze_on_stage1}\n")
    sys.stderr.write(f"[DEBUG] disk_images={disk_images}\n")
    sys.stderr.flush()
    if is_first_execution and cfg.stage.analyze_on_stage1:
        sys.stderr.write("[High-Level Planner] ANALYZE_ON_STAGE1 enabled - Force Dissect + Elastic mode\n")
        sys.stderr.flush()
        tasks = _generate_forced_dissect_elastic_tasks(user_prompt, disk_images)
        sys.stderr.write(f"[DEBUG] Generated {len(tasks)} tasks\n")
        sys.stderr.flush()
        return tasks

    llm = LLMClient()

    try:
        system_prompt = load_prompt("high_level_planning_system.txt")
    except FileNotFoundError:
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

    server_descriptions = _get_mcp_server_descriptions()
    servers_description = _format_mcp_servers_for_prompt(server_descriptions)

    available_servers = list(server_descriptions.keys())

    user_message = f"""사용자 요청: {user_prompt}

파일 목록:{file_info if file_info else " (없음)"}

**사용 가능한 MCP 서버:**
{servers_description}

**사용 가능한 서버 목록 (tool_hint에 사용):** {', '.join(available_servers) if available_servers else 'None'}
{additional_context}
위 정보와 사용 가능한 MCP 서버를 바탕으로 High-level 작업 계획을 생성하세요.
각 task의 tool_hint는 반드시 사용 가능한 서버 목록에서 선택하세요.
**중요**: mcp_call 필드의 operation은 서버의 도구 이름입니다. ReAct 단계에서 해당 서버의 전체 도구 목록을 조회하여 적절한 도구를 선택합니다."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        response = llm.chat(messages, response_format_json=True, timeout=60, max_tokens=2048)

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
                metadata=task_data.get("metadata", {}),
                mcp_call=task_data.get("mcp_call")
            )
            tasks.append(task)

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


def _generate_default_high_level_plan(
    user_prompt: str,
    disk_images: List[str],
    pe_files: List[str]
) -> List[HighLevelTask]:
    """기본 High-level 계획 생성 (폴백)

    LLM 실패 시 파일 타입 기반으로 Task 생성

    Args:
        user_prompt: 사용자 요청
        disk_images: 디스크 이미지 파일 리스트
        pe_files: PE 파일 리스트

    Returns:
        List[HighLevelTask]: 기본 Task 리스트
    """
    tasks = []

    if disk_images:
        tool_hint = "dissect"  # 기본값
        prompt_lower = user_prompt.lower()
        if any(kw in prompt_lower for kw in ["browser", "history", "chrome", "firefox", "edge", "브라우저", "히스토리"]):
            tool_hint = "dissect"  # E01 브라우저 분석은 dissect
        elif any(kw in prompt_lower for kw in ["powershell", "consolehost", "파워셸"]):
            tool_hint = "consolehost-history"
        elif any(kw in prompt_lower for kw in ["lnk", "shortcut", "바로가기"]):
            tool_hint = "lnk-parser"

        tasks.append(HighLevelTask(
            task_id="task_001",
            description=f"디스크 이미지 분석: {user_prompt[:100]}",
            task_type=TaskType.ARTIFACT_COLLECTION,
            target_files=disk_images,
            dependencies=[],
            metadata={"priority": "high", "tool_hint": tool_hint}
        ))

    if pe_files:
        task_id = f"task_{len(tasks)+1:03d}"
        tasks.append(HighLevelTask(
            task_id=task_id,
            description=f"PE 파일 분석: {user_prompt[:100]}",
            task_type=TaskType.FILE_ANALYSIS,
            target_files=pe_files,
            dependencies=[],
            metadata={"priority": "high"}
        ))

    if not tasks:
        tasks.append(HighLevelTask(
            task_id="task_001",
            description=f"분석 수행: {user_prompt[:100]}",
            task_type=TaskType.CUSTOM,
            target_files=[],
            dependencies=[],
            metadata={"priority": "medium"}
        ))

    return tasks
