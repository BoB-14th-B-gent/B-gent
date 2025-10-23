"""Low-Level Planner 모듈 (Phase 2)

High-level Task를 RAG 검색 → LLM 계획 생성 → 규칙 기반 폴백으로 변환
개별 Task에 대해 MCP 도구 기반 Low-level Action 생성
"""
from __future__ import annotations
from typing import List, Dict, Any, Tuple
import json
from .schemas.actions import Action
from .schemas.task import HighLevelTask
from .rag import query_mcp_for_task
from .llm_client import LLMClient

def _validate_dfir_request(user_prompt: str) -> Tuple[bool, str]:
    """사용자 요청이 DFIR 분석과 관련있는지 검증

    Args:
        user_prompt: 사용자 요청

    Returns:
        Tuple[bool, str]: (유효한지 여부, 거부 이유 또는 빈 문자열)
    """
    llm = LLMClient()
    validation_prompt = """당신은 DFIR(Digital Forensics and Incident Response) 분석 요청을 검증하는 AI입니다.
사용자 요청이 다음 중 하나에 해당하는지 판단하세요:
*DFIR 관련 작업 (허용)*:
- 로그 분석 (Elasticsearch, SIEM, 인덱스, 레이블)
- 디스크 포렌식 (파일 추출, 이미지 분석)
- 아티팩트 수집 (Velociraptor, Windows 포렌식)
- 보안 이벤트 탐지
- 시스템 정보 수집 (프로세스, 네트워크 등)
- 악성코드 분석 관련
- 침해 사고 조사 관련
- 메타데이터 조회 (인덱스 목록, 레이블 목록, 스키마, 필드 등)
*용어 참고*:
- "레이블", "라벨" = Elasticsearch의 "인덱스"를 의미할 수 있음
- "분석 가능한 데이터", "수집된 데이터" = DFIR 데이터를 의미
*DFIR 무관 작업 (거부)*:
- 일상 대화, 인사, 감정 표현
- DFIR와 무관한 일반 질문
- 개인적인 요청
- 코딩/개발 요청 (DFIR 도구 개발 제외)
*출력 형식* (반드시 JSON):
```json
{
  "is_valid": true or false,
  "reason": "거부 이유 (is_valid=false인 경우) 또는 빈 문자열"
}
```
*예시*:
입력: "배고파"
출력: {"is_valid": false, "reason": "DFIR 분석과 무관한 개인적 감정 표현입니다."}
입력: "인덱스 목록 조회"
출력: {"is_valid": true, "reason": ""}
입력: "레이블 목록을 알려줘"
출력: {"is_valid": true, "reason": ""}
입력: "분석 가능한 데이터 목록"
출력: {"is_valid": true, "reason": ""}
입력: "Virtual Host에서 프로세스 리스트 수집"
출력: {"is_valid": true, "reason": ""}
입력: "날씨 어때?"
출력: {"is_valid": false, "reason": "DFIR 분석과 무관한 일반 질문입니다."}
"""

    messages = [
        {"role": "system", "content": validation_prompt},
        {"role": "user", "content": f"다음 요청을 검증하세요: {user_prompt}"}
    ]

    try:
        response = llm.chat(messages, response_format_json=True, timeout=10)
        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)

        is_valid = data.get("is_valid", False)
        reason = data.get("reason", "")

        if not is_valid:
            print(f"⚠️  검증 경고: {reason}")
            print(f"⚠️  계속 진행합니다...")
            return True, ""  

        return is_valid, reason

    except Exception as e:
        return True, ""  

def generate_low_level_plan(
    task: HighLevelTask,
    dependency_results: Dict[str, List[Dict[str, Any]]] = None
) -> List[Action]:
    """High-level Task를 Low-level Action으로 변환 (Phase 2)

    Task 설명을 임베딩하여 RAG 검색 → LLM 계획 생성 → 폴백
    의존하는 Task의 결과를 활용 가능

    Args:
        task: High-level Task 객체
        dependency_results: 의존하는 Task들의 실행 결과
            {task_id: [result1, result2, ...]}

    Returns:
        List[Action]: Low-level Action 리스트

    로직:
        1. Task 설명을 임베딩하여 RAG 검색 (query_mcp_for_task)
        2. LLM으로 Low-level Action 생성 (_generate_plan_with_llm)
        3. 실패 시 규칙 기반 폴백 (_generate_default_plan)

    Example:
        >>> task = HighLevelTask(
        ...     description="디스크 이미지에서 의심 파일 추출",
        ...     task_type=TaskType.FILE_EXTRACT,
        ...     target_files=["data/Image.E01"],
        ...     metadata={"tool_hint": "sleuthkit"}
        ... )
        >>> actions = generate_low_level_plan(task)
        >>> # 결과: [
        >>> #   Action(tool="sleuthkit", operation="disk_partition_info", ...),
        >>> #   Action(tool="sleuthkit", operation="search_inode_by_path", ...),
        >>> #   Action(tool="sleuthkit", operation="extract_files_by_inode", ...)
        >>> # ]
    """
    dependency_results = dependency_results or {}

    print(f"\n[Low-level Planning] Task: {task.description}")

    candidates = query_mcp_for_task(task.description, task.metadata, top_k=10)

    # RAG 검색 결과 확인 (디버깅용)
    print(f"  RAG 검색 결과: {len(candidates)}개 도구")
    for idx, cand in enumerate(candidates[:5], 1):
        meta = cand.get("meta", {})
        if meta.get("is_mcp"):
            print(f"    {idx}. {meta.get('server')}.{meta.get('tool_name')}")

    description_lower = task.description.lower()
    if any(kw in description_lower for kw in ["아티팩트", "수집", "velociraptor", "artifact", "브라우저 히스토리", "레지스트리", "이벤트 로그"]):
        print("  ⚠️  Velociraptor 아티팩트 수집 작업: 규칙 기반 계획 사용")
        return _generate_default_plan_for_task(task, dependency_results)

    if not candidates:
        print("⚠️  RAG에서 도구를 찾지 못했습니다. 기본 계획을 생성합니다.")
        return _generate_default_plan_for_task(task, dependency_results)

    try:
        plan = _generate_plan_with_llm_for_task(task, candidates, dependency_results)
        if plan:
            return plan
        print("⚠️  LLM이 빈 계획을 반환했습니다.")
    except TimeoutError as e:
        print(f"⚠️  LLM 계획 생성 중 타임아웃: {e}")
        print(f"     → Fallback: 규칙 기반 계획 사용")
    except Exception as e:
        print(f"⚠️  LLM 계획 생성 중 오류: {e}")
        import traceback
        traceback.print_exc()

    return _generate_default_plan_for_task(task, dependency_results)

def _generate_plan_with_llm_for_task(
    task: HighLevelTask,
    candidates: List[Dict[str, Any]],
    dependency_results: Dict[str, List[Dict[str, Any]]]
) -> List[Action]:
    """LLM으로 Task 기반 Low-level Action 생성

    Args:
        task: High-level Task
        candidates: RAG 검색 결과 (MCP 도구 후보)
        dependency_results: 의존 Task 실행 결과

    Returns:
        List[Action]: Low-level Action 리스트
    """
    disk_image_path = None
    if task.task_type.value == "file_extract" and task.target_files:
        disk_image_path = _find_disk_image_from_paths(task.target_files)

    llm = LLMClient()

    tools_info = []
    knowledge_docs = []

    for cand in candidates:
        meta = cand.get("meta", {})
        doc_id = cand.get("id", "")

        is_mcp = meta.get("is_mcp", False)

        if is_mcp:
            schema = {}
            schema_str = meta.get("input_schema", "{}")
            try:
                schema = json.loads(schema_str) if isinstance(schema_str, str) else schema_str
            except:
                schema = {}

            tools_info.append({
                "server": meta.get("server", "unknown"),
                "tool_name": meta.get("tool_name", "unknown"),
                "description": meta.get("description", ""),
                "input_schema": schema
            })
        else:
            doc_type = meta.get("type", "document")
            doc_title = meta.get("title", "N/A")
            doc_content = cand.get("document", "")

            max_chars = 5000  
            if len(doc_content) > max_chars:
                doc_content = doc_content[:max_chars] + "\n... (생략)"

            knowledge_docs.append({
                "id": doc_id,
                "type": doc_type,
                "title": doc_title,
                "tags": meta.get("tags", ""),
                "content": doc_content
            })
    
    system_prompt = """DFIR 분석 작업 계획을 JSON으로 생성하세요.
출력 형식:
{"plan": [{"tool": "서버이름", "operation": "도구이름", "params": {...}, "reason": "이유"}]}

*중요: 현재 Task의 범위만 계획하세요*
- 주어진 Task 설명에 명시된 작업*만* 수행
- 다른 Task의 작업을 포함하지 말 것
- 예: "인덱스 목록 조회" Task → list_indices만 실행 (search는 다른 Task에서)

핵심 규칙:
1. operation은 제공된 도구 목록의 tool_name과 정확히 일치해야 함
2. params는 input_schema의 required 필드를 모두 포함
3. *현재 Task 설명에 명시된 작업만* 수행 (다른 작업 추가 금지)
4. 한 Task 내에서 여러 단계가 필요한 경우만 모두 계획에 포함
특수 규칙:
- *Velociraptor 아티팩트 수집: 반드시 2단계 구조 (client_info → 개별 아티팩트 도구)*
  1단계: client_info (호스트의 client_id 조회)
  2단계: 구체적인 아티팩트 도구 호출 (windows_recentdocs, windows_execution_amcache 등)

  *사용 가능한 아티팩트 도구 (디스크 이미지 분석용 - 핵심 5개):*
  - windows_recentdocs: 최근 문서 이력
  - windows_evidence_of_download: 다운로드 증거
  - windows_execution_bam: BAM 실행 증거
  - windows_execution_amcache: Amcache 실행 증거
  - windows_execution_shimcache: ShimCache 실행 증거

  *완전한 예시 (디스크 이미지에서 기본 아티팩트 수집):*
  ```json
  {
    "plan": [
      {
        "tool": "velociraptor",
        "operation": "client_info",
        "params": {"hostname": "Virtual Host"},
        "reason": "클라이언트 ID 조회"
      },
      {
        "tool": "velociraptor",
        "operation": "windows_recentdocs",
        "params": {
          "client_id": "PLACEHOLDER_CLIENT_ID",
          "Fields": "Username,LastWriteTime,Value,Key,MruEntries,HiveName"
        },
        "reason": "최근 문서 이력 수집"
      },
      {
        "tool": "velociraptor",
        "operation": "windows_evidence_of_download",
        "params": {
          "client_id": "PLACEHOLDER_CLIENT_ID",
          "Fields": "DownloadedFilePath,_ZoneIdentifierContent,FileHash,HostUrl,ReferrerUrl"
        },
        "reason": "다운로드 증거 수집"
      },
      {
        "tool": "velociraptor",
        "operation": "windows_execution_amcache",
        "params": {
          "client_id": "PLACEHOLDER_CLIENT_ID",
          "Fields": "FullPath,SHA1,ProgramID,FileDescription,FileVersion,Publisher,CompileTime,LastModified,LastRunTime"
        },
        "reason": "Amcache 실행 증거 수집"
      },
      {
        "tool": "velociraptor",
        "operation": "windows_execution_shimcache",
        "params": {
          "client_id": "PLACEHOLDER_CLIENT_ID",
          "Fields": "Position,ModificationTime,Path,ExecutionFlag,ControlSet"
        },
        "reason": "ShimCache 실행 증거 수집"
      }
    ]
  }
  ```

  *중요 규칙:*
  * client_id는 반드시 문자열 "PLACEHOLDER_CLIENT_ID" 사용
  * 절대 금지: collect_artifact, collect_forensic_triage 같은 통합 도구 사용 금지
  * 반드시 개별 아티팩트 도구만 사용: windows_recentdocs, windows_evidence_of_download 등
  * "브라우저/레지스트리/이벤트 로그" 요청 시 → 위 5개 아티팩트를 각각 별도 단계로 모두 호출
  * Fields는 해당 아티팩트의 주요 필드만 포함 (위 예시 참고)
  * operation은 반드시 RAG 검색 결과의 tool_name과 정확히 일치해야 함 (임의 생성 절대 금지)

- *SleuthKit 파일 추출: 반드시 3단계 모두 포함 (하나라도 빠지면 실패)*
  1단계: disk_partition_info (파티션 오프셋 확인)
  2단계: search_inode_by_path (파일 경로 → inode 변환)
  3단계: extract_files_by_inode (inode �� 파일 추출)

  *완전한 예시 (C:\\Users\\hacker\\file.exe 추출):*
  ```json
  {
    "plan": [
      {
        "tool": "sleuthkit",
        "operation": "disk_partition_info",
        "params": {"image_path": "/path/to/disk.E01"},
        "reason": "파티션 오프셋 확인"
      },
      {
        "tool": "sleuthkit",
        "operation": "search_inode_by_path",
        "params": {
          "image_path": "/path/to/disk.E01",
          "fs_offset_sectors": "PLACEHOLDER_OFFSET",
          "path": "/Users/hacker/file.exe",
          "imgtype": "ewf",
          "fstype": "ntfs"
        },
        "reason": "파일 경로를 inode로 변환"
      },
      {
        "tool": "sleuthkit",
        "operation": "extract_files_by_inode",
        "params": {
          "image_path": "/path/to/disk.E01",
          "fs_offset_sectors": "PLACEHOLDER_OFFSET",
          "inodes": "PLACEHOLDER_INODES",
          "out_dir": "./data/extracted_files",
          "imgtype": "ewf",
          "fstype": "ntfs"
        },
        "reason": "inode로 파일 추출"
      }
    ]
  }
  ```

  *중요 규칙:*
  * fs_offset_sectors는 반드시 문자열 "PLACEHOLDER_OFFSET" (null/None/0 절대 금지)
  * inodes는 반드시 문자열 "PLACEHOLDER_INODES" (배열/null 절대 금지)
  * *Windows 경로 변환 규칙 (매우 중요):*
    - C:\\Users\\hacker\\file.exe → /Users/hacker/file.exe
    - D:\\Data\\file.txt → /Data/file.txt
    - *잘못된 예*: /C/Users/... (절대 금지 C: 드라이브 제거 필수)
    - *올바른 예*: /Users/... (C: 제거 후 / 추가)
  * 3단계 중 하나라도 빠지면 파일 추출 불가능
- Elasticsearch 워크플로우:
  *1. 메타데이터 조회 (인덱스/레이블 목록):*
  - list_indices(): 파라미터 없음 반드시 빈 객체 {} 사용
  - 예시: {"tool": "elastic", "operation": "list_indices", "params": {}, "reason": "인덱스 목록 조회"}
  *2. 데이터 조회/분석:*
  - search_documents(index, body): 특정 인덱스에서 문서 검색
  - index: 반드시 "PLACEHOLDER_INDEX" 문자열 사용 (이전 단계 결과에서 자동 선택됨)
  - body: 검색 쿼리 (필수 query_body가 아님)
  - 정렬(sort) 사용 금지: 인덱스마다 필드가 다르므로 "sort" 필드를 사용하지 마세요
  - 올바른 예시: {"tool": "elastic", "operation": "search_documents", "params": {"index": "PLACEHOLDER_INDEX", "body": {"query": {"match_all": {}}, "size": 10}}, "reason": "선택된 인덱스 데이터 분석"}
  - 잘못된 예시: {"body": {"query": {...}, "sort": [{"@timestamp": "desc"}]}} ← sort 사용 금지
  - 주의: 파라미터 이름은 정확히 "body"를 사용 "query_body"나 다른 이름 사용 금지
  - 주의: index 값은 반드시 영문 "PLACEHOLDER_INDEX" 한글이나 다른 표현 절대 금지
  *3. Task별 예시:*

  예시 1 - Task: "Elasticsearch 인덱스 목록 조회"
  올바른 계획: [{"tool": "elastic", "operation": "list_indices", "params": {}, "reason": "인덱스 목록 조회"}]
  잘못된 계획: list_indices + search_documents (search는 다른 Task)

  예시 2 - Task: "Elasticsearch에서 최근 10개 데이터 분석" (이전 Task에서 인덱스 목록 조회 완료)
  올바른 계획: [{"tool": "elastic", "operation": "search_documents", "params": {"index": "PLACEHOLDER_INDEX", "body": {"query": {"match_all": {}}, "size": 10}}, "reason": "최근 데이터 10개 조회"}]

  중요: search_documents의 파라미터는 반드시 "index"와 "body" 2개
  중요: index 값은 정확히 "PLACEHOLDER_INDEX" (영문)만 허용
  중요: body에 "sort" 필드를 절대 포함하지 마세요
"""

    file_info = ""
    if disk_image_path and disk_image_path != "/unknown":
        file_info = f"\n디스크 이미지: {disk_image_path}"
    elif task.target_files:
        file_info = f"\n파일: {', '.join(task.target_files)}"

    dependency_info = ""
    if dependency_results:
        dependency_info = "\n\n이전 Task 결과:\n"
        for task_id, results in dependency_results.items():
            dependency_info += f"- {task_id}: {len(results)}개 결과\n"
            if results:
                dependency_info += f"  첫 번째 결과: {str(results[0])[:200]}...\n"

    knowledge_info = ""
    if knowledge_docs:
        knowledge_info = "\n\n참고 문서:\n"
        for doc in knowledge_docs:
            knowledge_info += f"- {doc['title']}: {doc['content']}\n"

    user_message = f"""Task: {task.description}
Task 타입: {task.task_type.value}
도구 힌트: {task.metadata.get('tool_hint', '없음')}{file_info}{dependency_info}

사용 가능한 도구:
{json.dumps(tools_info, ensure_ascii=False)}{knowledge_info}"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        print(f"  LLM 호출 중...")
        response = llm.chat(messages, response_format_json=True, timeout=None)
        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)
        plan_data = data.get("plan", [])

        # LLM 응답 확인 (디버깅용)
        print(f"\n[DEBUG] LLM이 생성한 계획:")
        print(json.dumps(plan_data, ensure_ascii=False, indent=2))
        print()
        valid_tools = {}

        for tool_info in tools_info:
            server = tool_info["server"]
            tool_name = tool_info["tool_name"]

            if server not in valid_tools:
                valid_tools[server] = set()
            valid_tools[server].add(tool_name)
        actions = []

        for idx, item in enumerate(plan_data, 1):
            tool = item.get("tool", "")
            operation = item.get("operation", "")
            params = item.get("params", {})

            if tool not in valid_tools:
                print(f"⚠️  경고: 단계 {idx}에서 알 수 없는 서버 '{tool}' 사용. 사용 가능한 서버: {list(valid_tools.keys())}")

            elif operation not in valid_tools[tool]:
                corrected = False
                if operation == "get_indices" and "list_indices" in valid_tools[tool]:
                    print(f"⚠️  경고: 단계 {idx}에서 '{operation}' → 'list_indices' 자동 수정")
                    operation = "list_indices"
                    corrected = True
                elif operation == "list_indices" and "list_indices" in valid_tools[tool]:
                    print(f"  단계 {idx}: '{operation}'는 유효한 도구입니다.")
                    corrected = True

                if not corrected:
                    print(f"❌ 오류: 단계 {idx}에서 '{tool}' 서버에 존재하지 않는 도구 '{operation}' 사용.")
                    print(f"     사용 가능한 도구: {sorted(valid_tools[tool])}")

                    if operation == "get_index" and tool == "sleuthkit":
                        print(f"     → 오류: SleuthKit에는 'get_index'가 없습니다 (Elasticsearch 도구와 혼동)")

                    print(f"     → 이 단계를 건너뜁니다.")
                    continue

            if tool == "elastic":

                if operation == "list_indices":

                    if params:
                        print(f"⚠️  경고: 단계 {idx}에서 list_indices에 파라미터가 있습니다: {params}")
                        print(f"     → 자동 수정: 빈 객체로 변경")
                        params = {}

                if operation == "search_documents":
                    index = params.get("index", "")

                    if index and index != "PLACEHOLDER_INDEX" and "*" not in index:
                        if any(char in index for char in ["<", ">", "인덱스", "이름", "레이블"]):
                            print(f"⚠️  경고: 단계 {idx}에서 잘못된 index placeholder: '{index}'")
                            print(f"     → 자동 수정: '{index}' → 'PLACEHOLDER_INDEX'")
                            params["index"] = "PLACEHOLDER_INDEX"

            if tool == "sleuthkit":
                if operation in ["search_inode_by_path", "extract_files_by_inode"]:
                    fs_offset = params.get("fs_offset_sectors")

                    if fs_offset is None or fs_offset == "" or fs_offset == "0" or fs_offset == 0:
                        print(f"⚠️  경고: 단계 {idx}에서 fs_offset_sectors가 잘못되었습니다: {repr(fs_offset)}")
                        print(f"     → 자동 수정: {repr(fs_offset)} → 'PLACEHOLDER_OFFSET'")
                        params["fs_offset_sectors"] = "PLACEHOLDER_OFFSET"

                if operation == "search_inode_by_path":
                    path = params.get("path", "")

                    if "\\" in path:
                        original_path = path
                        path = path.replace("\\", "/")
                        print(f"⚠️  경고: 단계 {idx}에서 백슬래시 경로 감지")
                        print(f"     → 자동 수정: {original_path} → {path}")

                    if path.startswith("/C/") or path.startswith("/D/") or path.startswith("/E/"):
                        corrected_path = "/" + path[3:]
                        print(f"⚠️  경고: 단계 {idx}에서 잘못된 경로 변환: {path}")
                        print(f"     → 자동 수정: {path} → {corrected_path}")
                        path = corrected_path

                    import re
                    drive_match = re.match(r'^([A-Z]):/(.+)$', path)
                    if drive_match:
                        corrected_path = "/" + drive_match.group(2)
                        print(f"⚠️  경고: 단계 {idx}에서 드라이브 문자 포함: {path}")
                        print(f"     → 자동 수정: {path} → {corrected_path}")
                        path = corrected_path

                    params["path"] = path

                if operation == "extract_files_by_inode":
                    inodes = params.get("inodes")

                    if inodes is None or inodes == "":
                        print(f"⚠️  경고: 단계 {idx}에서 inodes가 None/빈 값입니다.")
                        print(f"     → 자동 수정: {repr(inodes)} → 'PLACEHOLDER_INODES'")
                        params["inodes"] = "PLACEHOLDER_INODES"
                    elif isinstance(inodes, list):
                        print(f"⚠️  경고: 단계 {idx}에서 inodes가 배열입니다. PLACEHOLDER_INODES를 사용해야 합니다.")
                        print(f"     → 자동 수정: {inodes} → 'PLACEHOLDER_INODES'")
                        params["inodes"] = "PLACEHOLDER_INODES"
                    elif isinstance(inodes, str) and inodes.startswith("[") and inodes.endswith("]"):
                        print(f"⚠️  경고: 단계 {idx}에서 inodes가 JSON 문자열입니다. PLACEHOLDER_INODES를 사용해야 합니다.")
                        print(f"     → 자동 수정: '{inodes}' → 'PLACEHOLDER_INODES'")
                        params["inodes"] = "PLACEHOLDER_INODES"
            default_timeout = 180 if tool == "velociraptor" else 60
            actions.append(Action(
                tool=tool,
                operation=operation,
                params=params,
                reason=item.get("reason", ""),
                timeout_seconds=item.get("timeout_seconds", default_timeout)
            ))
        sleuthkit_ops = [a.operation for a in actions if a.tool == "sleuthkit"]

        if "extract_files_by_inode" in sleuthkit_ops:
            required = ["disk_partition_info", "search_inode_by_path", "extract_files_by_inode"]
            missing = [op for op in required if op not in sleuthkit_ops]

            if missing:
                print(f"\n⚠️  심각한 오류: SleuthKit 파일 추출 워크플로우가 불완전합니다")
                print(f"     필수 3단계: {required}")
                print(f"     현재 단계: {sleuthkit_ops}")
                print(f"     누락된 단계: {missing}")
                print(f"\n     → 폴백: 규칙 기반 계획 사용")

                return []
        print(f"✓ LLM이 {len(actions)}단계 계획을 생성했습니다.")

        return actions

    except json.JSONDecodeError as e:
        print(f"⚠️  LLM 응답 파싱 실패: {e}")
        print(f"     응답 내용: {content[:200]}...")
        return []

    except TimeoutError as e:
        print(f"⚠️  LLM 호출 타임아웃: {e}")
        raise

    except Exception as e:
        print(f"⚠️  LLM 계획 생성 중 오류: {e}")
        raise

def _find_disk_image_from_paths(file_paths: List[str] = None) -> str:
    """파일 경로 배열 또는 data 디렉터리에서 디스크 이미지 파일 자동 검색

    지원 형식: .e01, .E01, .dd, .DD, .raw, .RAW, .img, .IMG

    Args:
        file_paths: 파일 경로 배열 (선택)

    Returns:
        str: 디스크 이미지 파일 경로 (찾지 못하면 "/unknown")
    """
    import os
    import glob
    disk_extensions = [".e01", ".E01", ".dd", ".DD", ".raw", ".RAW", ".img", ".IMG"]

    if file_paths:

        for path in file_paths:

            if not path:
                continue
            _, ext = os.path.splitext(path)

            if ext in disk_extensions:

                if os.path.exists(path):
                    abs_path = os.path.abspath(path)
                    print(f"     디스크 이미지 선택 (입력 파일): {abs_path}")

                    return abs_path

                else:
                    print(f"     파일이 존재하지 않음: {path}")
    search_dirs = [
        "./data",
    ]

    for search_dir in search_dirs:

        if not os.path.exists(search_dir):
            continue

        for ext in disk_extensions:
            pattern = os.path.join(search_dir, "*", f"*{ext}")
            matches = glob.glob(pattern, recursive=True)

            if matches:
                disk_image = os.path.abspath(matches[0])
                print(f"     디스크 이미지 자동 검색 완료: {disk_image}")

                return disk_image
    print(f"     디스크 이미지 파일을 찾을 수 없습니다.")

    if file_paths:
        print(f"     제공된 파일: {file_paths}")
    print(f"     검색 위치: {', '.join(search_dirs)}")
    print(f"     지원 형식: .e01, .dd, .raw, .img")

    return "/unknown"

def _generate_default_plan_for_task(
    task: HighLevelTask,
    dependency_results: Dict[str, List[Dict[str, Any]]]
) -> List[Action]:
    """Task 기반 기본 계획 생성 (폴백)

    Args:
        task: High-level Task
        dependency_results: 의존 Task 실행 결과

    Returns:
        List[Action]: 기본 Low-level Action 리스트
    """
    print("⚠️  기본 계획을 사용합니다.")
    description_lower = task.description.lower()
    tool_hint = task.metadata.get("tool_hint", "")

    if any(kw in description_lower for kw in ["아티팩트", "수집", "velociraptor", "artifact", "프리패치", "prefetch", "프로세스", "pslist", "netstat", "네트워크", "브라우저 히스토리", "레지스트리", "이벤트 로그", "kape"]):
        hostname = "Virtual Host"
        import re
        host_match = re.search(r'([A-Za-z0-9\-\_\s\.]+)(?:에서|에)', task.description)

        if host_match:
            potential_host = host_match.group(1).strip()

            if potential_host and not any(kw in potential_host.lower() for kw in ["윈도우", "아티팩트", "수집", "프리패치", "프로세스"]):
                hostname = potential_host

        artifact_operations = [
            ("windows_scheduled_tasks", "OSPath,Mtime,Command,ExpandedCommand,Arguments,ComHandler,UserId,StartBoundary,Authenticode", "Scheduled Tasks 수집"),
            ("windows_services", "UserAccount,Created,ServiceDll,FailureCommand,FailureActions,AbsoluteExePath,HashServiceExe,CertinfoServiceExe,HashServiceDll,CertinfoServiceDll", "Windows Services 수집"),
            ("windows_recentdocs", "Username,LastWriteTime,Value,Key,MruEntries,HiveName", "RecentDocs 수집"),
            ("windows_shellbags", "ModTime,Name,_OSPath,Hive,KeyPath,Description,Path,_RawData,_Parsed", "ShellBags 수집"),
            ("windows_mounted_mass_storage_usb", "KeyLastWriteTimestamp, KeyName, FriendlyName, HardwareID", "USB 연결 이력 수집"),
            ("windows_evidence_of_download", "DownloadedFilePath,_ZoneIdentifierContent,FileHash,HostUrl,ReferrerUrl", "다운로드 증거 수집"),
            ("windows_mountpoints2", "ModifiedTime, MountPoint, Hive, Key", "MountPoints2 수집"),
            ("windows_execution_bam", "*", "BAM 실행 증거 수집"),
            ("windows_execution_amcache", "FullPath,SHA1,ProgramID,FileDescription,FileVersion,Publisher,CompileTime,LastModified,LastRunTime", "Amcache 실행 증거 수집"),
            ("windows_execution_activitiesCache", "*", "ActivitiesCache 수집"),
            ("windows_execution_userassist", "Name,User,LastExecution,NumberOfExecutions", "UserAssist 실행 증거 수집"),
            ("windows_execution_shimcache", "Position,ModificationTime,Path,ExecutionFlag,ControlSet", "ShimCache 실행 증거 수집"),
        ]

        actions = [
            Action(
                tool="velociraptor",
                operation="client_info",
                params={"hostname": hostname},
                reason=f"{hostname}의 client_id 조회"
            )
        ]

        for operation, fields, reason in artifact_operations:
            actions.append(
                Action(
                    tool="velociraptor",
                    operation=operation,
                    params={
                        "client_id": "PLACEHOLDER_CLIENT_ID",
                        "Fields": fields
                    },
                    reason=reason,
                    timeout_seconds=180
                )
            )

        return actions

    if tool_hint == "elastic" or any(kw in description_lower for kw in ["인덱스 목록", "index list", "indices", "레이블 목록", "레이블의 목록", "분석 가능한", "매핑", "mapping", "스키마", "schema", "필드 목록"]):

        return [
            Action(
                tool="elastic",
                operation="list_indices",
                params={},
                reason="Elasticsearch 인덱스 목록 조회"
            )
        ]

    if any(kw in description_lower for kw in ["로그", "siem", "탐지", "쿼리"]):

        return [
            Action(
                tool="elastic",
                operation="search_documents",
                params={
                    "index": "*",
                    "body": {
                        "query": {
                            "query_string": {
                                "query": task.description
                            }
                        },
                        "size": 100
                    }
                },
                reason="SIEM 로그 검색"
            )
        ]

    if task.target_files or any(kw in description_lower for kw in ["추출", "파일", "디스크", "이미지"]):
        import re
        target_path = None
        quoted_match = re.search(r'"([A-Z]:[^"]+)"', task.description)

        if quoted_match:
            target_path = quoted_match.group(1)

        else:
            unquoted_match = re.search(r'(C:\\(?:[^\\:\*\?"<>\|\s]+\\)*[^\\:\*\?"<>\|\s]+\.[a-zA-Z0-9]+)', task.description)

            if unquoted_match:
                target_path = unquoted_match.group(1)

        if not target_path:
            print(f"  ⚠️  Windows 파일 경로를 찾을 수 없습니다.")
            print(f"     Task 설명: {task.description}")
            print(f"     예시: C:\\Users\\hacker\\Downloads\\file.exe")

            return [
                Action(
                    tool="elastic",
                    operation="search_documents",
                    params={
                        "index": "*",
                        "body": {
                            "query": {
                                "query_string": {
                                    "query": task.description
                                }
                            },
                            "size": 100
                        }
                    },
                    reason="파일 경로를 찾을 수 없어 로그 검색으로 대체"
                )
            ]
        unix_path = target_path.replace('C:', '').replace('\\', '/')
        disk_image_path = _find_disk_image_from_paths(task.target_files)

        return [
            Action(
                tool="sleuthkit",
                operation="disk_partition_info",
                params={
                    "image_path": disk_image_path
                },
                reason="디스크 파티션 정보 확인 및 오프셋 추출"
            ),
            Action(
                tool="sleuthkit",
                operation="search_inode_by_path",
                params={
                    "image_path": disk_image_path,
                    "fs_offset_sectors": "PLACEHOLDER_OFFSET",
                    "path": unix_path,
                    "imgtype": "ewf",
                    "fstype": "ntfs"
                },
                reason=f"파일 경로를 inode로 변환: {unix_path} (원본: {target_path})"
            ),
            Action(
                tool="sleuthkit",
                operation="extract_files_by_inode",
                params={
                    "image_path": disk_image_path,
                    "fs_offset_sectors": "PLACEHOLDER_OFFSET",
                    "inodes": "PLACEHOLDER_INODES",
                    "out_dir": "./data/extracted_files",
                    "imgtype": "ewf",
                    "fstype": "ntfs"
                },
                reason="inode로 파일 추출"
            )
        ]

    return [
        Action(
            tool="elastic",
            operation="search_documents",
            params={
                "index": "*",
                "body": {
                    "query": {
                        "query_string": {
                            "query": task.description
                        }
                    },
                    "size": 100
                }
            },
            reason="기본 로그 검색"
        )
    ]

