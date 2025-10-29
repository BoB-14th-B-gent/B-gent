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
            print(f"검증 경고: {reason}")
            print(f"계속 진행합니다...")
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

    candidates = query_mcp_for_task(task.description, task.metadata, top_k=30)

    print(f"  RAG 검색 결과: {len(candidates)}개 도구")
    for idx, cand in enumerate(candidates[:5], 1):
        meta = cand.get("meta", {})
        if meta.get("is_mcp"):
            print(f"    {idx}. {meta.get('server')}.{meta.get('tool_name')}")

    description_lower = task.description.lower()
    # Velociraptor 강제 사용 조건: task_type이 artifact_collection이거나, 명시적으로 Velociraptor 언급
    # "수집"이라는 단어만으로는 판단하지 않음 (Elasticsearch 로그 수집과 혼동 방지)
    is_velociraptor_task = (
        task.task_type.value == "artifact_collection" or
        "velociraptor" in description_lower or
        any(kw in description_lower for kw in ["아티팩트", "artifact", "브라우저 히스토리", "레지스트리 키", "prefetch", "shellbag"])
    )

    if is_velociraptor_task:
        print("  Velociraptor 아티팩트 수집 작업: 규칙 기반 계획 사용")
        return _generate_default_plan_for_task(task, dependency_results)

    if not candidates:
        print("RAG에서 도구를 찾지 못했습니다. 기본 계획을 생성합니다.")
        return _generate_default_plan_for_task(task, dependency_results)

    # Ghidra 작업: LLM이 먼저 시도 (강제 폴백 제거)
    # tool_hint == "ghidra"일 때도 LLM이 사용자 요청의 복잡도를 판단하여 계획 생성
    # 실패 시에만 규칙 기반 폴백 사용

    try:
        plan = _generate_plan_with_llm_for_task(task, candidates, dependency_results)
        if plan:
            return plan
        print("LLM이 빈 계획을 반환했습니다.")
    except TimeoutError as e:
        print(f"LLM 계획 생성 중 타임아웃: {e}")
        print(f"     Fallback: 규칙 기반 계획 사용")
    except Exception as e:
        print(f"LLM 계획 생성 중 오류: {e}")
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
- 주의: Task 설명이 "수집 **및** 분석"처럼 **여러 작업을 포함**하면 모두 계획에 포함해야 함
- 예시:
  - "인덱스 목록 조회만" Task → list_indices만 실행
  - "로그 수집 및 분석" Task → list_indices + search_documents 실행

핵심 규칙:
1. **operation은 반드시 "사용 가능한 도구" 목록에 있는 tool_name과 정확히 일치해야 함**
   - ❌ 절대 금지: 임의로 도구 이름을 생성하거나 추측하지 마세요
   - ❌ 절대 금지: "search", "get", "index" 같은 짧은 이름 사용 (반드시 전체 이름 사용)
   - ❌ 절대 금지: decompile_function_by_address, disassemble_function 같은 존재하지 않는 도구 사용
   - ✅ 올바른 방법: 아래 "사용 가능한 도구" JSON에서 tool_name을 그대로 복사
   - 예시: ❌ "search" → ✅ "search_documents"
   - 예시: ❌ "index" → ✅ "index_document"
   - 예시: ❌ "get" → ✅ "get_document"
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
  3단계: extract_files_by_inode (inode 파일 추출)

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
  *3. Task별 예시 (매우 중요 - 반드시 이 패턴을 따르세요):*

  예시 1 - Task: "Elasticsearch 인덱스 목록 조회만" (메타데이터만)
  올바른 계획: [{"tool": "elastic", "operation": "list_indices", "params": {}, "reason": "인덱스 목록 조회"}]

  예시 2 - Task: "Elasticsearch에서 최근 10개 데이터 분석" (이전 Task에서 인덱스 목록 이미 조회함)
  올바른 계획: [{"tool": "elastic", "operation": "search_documents", "params": {"index": "PLACEHOLDER_INDEX", "body": {"query": {"match_all": {}}, "size": 10}}, "reason": "최근 데이터 조회"}]

  **예시 3 - Task: "Elasticsearch에서 로그 수집 및 분석" (수집 + 분석을 하나의 Task에서 수행)**
  **올바른 계획 (2단계 모두 포함):**
  ```json
  {
    "plan": [
      {
        "tool": "elastic",
        "operation": "list_indices",
        "params": {},
        "reason": "인덱스 목록 조회"
      },
      {
        "tool": "elastic",
        "operation": "search_documents",
        "params": {
          "index": "PLACEHOLDER_INDEX",
          "body": {
            "query": {"match_all": {}},
            "size": 100
          }
        },
        "reason": "로그 데이터 분석"
      }
    ]
  }
  ```
  **잘못된 계획: list_indices만 실행 (분석을 빠뜨림)**

  *중요 규칙*:
  - Task 설명에 "수집 및 분석", "조회 및 분석", "검색 및 분석" 같이 **"및 분석"**이 포함되면
    → list_indices + search_documents 2단계 모두 실행
  - Task 설명이 "인덱스 목록 조회"만 언급하면
    → list_indices만 실행

  중요: search_documents의 파라미터는 반드시 "index"와 "body" 2개
  중요: index 값은 정확히 "PLACEHOLDER_INDEX" (영문)만 허용
  중요: body에 "sort" 필드를 절대 포함하지 마세요

- *Ghidra 바이너리 리버스 엔지니어링: 사용자 요청에 따라 적절한 분석 수행*

  **사용 가능한 Ghidra 도구 (이 목록에 없는 도구는 절대 사용 금지)**:
  - list_functions: 함수 목록 추출 (params: offset, limit)
  - list_imports: Import 함수 목록 (params: offset, limit)
  - list_exports: Export 함수 목록 (params: offset, limit)
  - list_segments: 메모리 세그먼트 목록 (params: offset, limit)
  - list_strings: 문자열 추출 (params: offset, limit)
  - decompile_function: 함수 디컴파일 (params: name - 함수 이름 필수)
  - get_current_address: 현재 주소 확인 (params: 없음)
  - get_current_function: 현재 함수 확인 (params: 없음)

  **절대 사용 금지**: decompile_function_by_address, disassemble_function, get_function_at 등 위 목록에 없는 도구

  *분석 복잡도 판단 규칙*:
  1. **간단한 분석 요청** ("분석해줘", "파일 분석", "바이너리 분석"):
     → 핵심 정보만 추출 (list_functions, list_imports, decompile_function 1-2개)
     → 사용자가 추가 정보를 원하면 나중에 요청할 것

  2. **구체적인 단일 작업** ("main 함수 디컴파일", "문자열 추출", "함수 목록"):
     → 해당 도구만 호출

  3. **복잡한 분석 요청** ("특정 문자열 참조하는 함수 찾기", "호출 체인 분석"):
     → 필요한 도구들을 조합 (list_strings + list_functions + decompile_function 여러 개)

  *간단한 분석 예시* (추상적 요청: "분석해줘", "파일 분석"):
  ```json
  {
    "plan": [
      {
        "tool": "ghidra",
        "operation": "list_functions",
        "params": {"offset": 0, "limit": 20},
        "reason": "주요 함수 목록 확인 (첫 20개)"
      },
      {
        "tool": "ghidra",
        "operation": "list_imports",
        "params": {"offset": 0, "limit": 20},
        "reason": "Import 함수 확인"
      },
      {
        "tool": "ghidra",
        "operation": "decompile_function",
        "params": {"name": "entry"},
        "reason": "entry 함수 디컴파일"
      }
    ]
  }
  ```

  *복잡한 분석 예시* (구체적 요청: "Correct! 문자열 참조하는 함수 찾기"):
  ```json
  {
    "plan": [
      {
        "tool": "ghidra",
        "operation": "list_strings",
        "params": {"offset": 0, "limit": 100},
        "reason": "바이너리 문자열 추출 (Correct! 찾기)"
      },
      {
        "tool": "ghidra",
        "operation": "list_functions",
        "params": {},
        "reason": "전체 함수 목록"
      },
      {
        "tool": "ghidra",
        "operation": "decompile_function",
        "params": {"name": "entry"},
        "reason": "entry 함수 디컴파일"
      },
      {
        "tool": "ghidra",
        "operation": "decompile_function",
        "params": {"name": "FUN_140001000"},
        "reason": "문자열 참조 가능성 있는 함수"
      }
    ]
  }
  ```

  *전체 분석 예시* (명시적 요청: "바이너리 전체 분석", "모든 정보 추출"):
  ```json
  {
    "plan": [
      {
        "tool": "ghidra",
        "operation": "list_functions",
        "params": {},
        "reason": "전체 함수 목록 가져오기"
      },
      {
        "tool": "ghidra",
        "operation": "list_imports",
        "params": {"offset": 0, "limit": 50},
        "reason": "Import 함수 목록 확인"
      },
      {
        "tool": "ghidra",
        "operation": "list_exports",
        "params": {"offset": 0, "limit": 50},
        "reason": "Export 함수 목록 확인"
      },
      {
        "tool": "ghidra",
        "operation": "decompile_function",
        "params": {"name": "entry"},
        "reason": "entry 함수 디컴파일"
      },
      {
        "tool": "ghidra",
        "operation": "list_segments",
        "params": {"offset": 0, "limit": 20},
        "reason": "메모리 세그먼트 구조 확인"
      },
      {
        "tool": "ghidra",
        "operation": "list_strings",
        "params": {"offset": 0, "limit": 100},
        "reason": "바이너리 문자열 추출"
      }
    ]
  }
  ```

  *중요 규칙*:
  * **기본값**: 추상적인 요청("분석해줘")은 간단한 분석 (list_functions limit=20, list_imports, decompile_function 1개)
  * **명시적 요청**: "전체 분석", "모든 함수", "자세히" 등의 키워드가 있을 때만 전체 분석 수행
  * **단일 작업**: "main 디컴파일", "문자열 추출", "함수 목록" → 해당 도구만 호출
  * decompile_function의 params는 {"name": "함수명"} 형식
  * list 계열 도구는 offset, limit 파라미터 지원 - **과도한 출력 방지를 위해 limit 사용 권장**
  * operation은 반드시 RAG 검색 결과의 tool_name과 정확히 일치

- *Phase 2 (decompile) Task 전용 규칙*:
  Task 설명에 "주요 함수 디컴파일"이 포함되어 있고, 이전 Task에서 함수 목록(list_functions)을 수집했다면:

  **절대 금지**: entry와 main만 디컴파일하는 것
  **올바른 방법**: 이전 Task 결과에서 함수 목록을 확인하고, entry + 낮은 주소의 FUN_ 함수들(최소 3-5개) 디컴파일

  *잘못된 예시 (절대 금지)*:
  ```json
  {
    "plan": [
      {"tool": "ghidra", "operation": "decompile_function", "params": {"name": "entry"}},
      {"tool": "ghidra", "operation": "decompile_function", "params": {"name": "main"}}  ❌ main이 없으면 실패!
    ]
  }
  ```

  *올바른 예시 (반드시 이렇게)*:
  이전 Task에서 발견된 함수 목록:
  - FUN_140001000, FUN_140001290, FUN_140001350, FUN_140001638, entry

  ```json
  {
    "plan": [
      {"tool": "ghidra", "operation": "decompile_function", "params": {"name": "entry"}, "reason": "entry 함수 디컴파일"},
      {"tool": "ghidra", "operation": "decompile_function", "params": {"name": "FUN_140001000"}, "reason": "핵심 로직 함수 (낮은 주소)"},
      {"tool": "ghidra", "operation": "decompile_function", "params": {"name": "FUN_140001290"}, "reason": "핵심 로직 함수"},
      {"tool": "ghidra", "operation": "decompile_function", "params": {"name": "FUN_140001350"}, "reason": "핵심 로직 함수"},
      {"tool": "ghidra", "operation": "decompile_function", "params": {"name": "FUN_140001638"}, "reason": "entry가 호출하는 함수"}
    ]
  }
  ```

  *핵심 원칙*:
  - main이 없으면 FUN_으로 시작하는 함수들 선택 (절대 main만 고집하지 말 것)
  - 낮은 주소 (0x140001000 ~ 0x140001700) 함수가 핵심 로직일 가능성 높음
  - entry 주소(보통 0x1400017b4)에 가까운 함수는 entry가 호출할 가능성 높음
  - 최소 3-5개 함수 디컴파일 (entry + FUN_ 함수들)
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

        print(f"\n[DEBUG] LLM 원본 응답 (처음 500자):")
        print(content[:500])
        print()

        data = json.loads(content)
        plan_data = data.get("plan", [])

        print(f"[DEBUG] LLM이 생성한 계획 ({len(plan_data)}개 단계):")
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
                print(f"경고: 단계 {idx}에서 알 수 없는 서버 '{tool}' 사용. 사용 가능한 서버: {list(valid_tools.keys())}")
                print(f"     이 단계를 건너뜁니다.")
                continue

            if operation not in valid_tools[tool]:
                corrected = False
                # 자동 수정 규칙
                auto_corrections = {
                    "get_indices": "list_indices",
                    "search": "search_documents",
                    "index": "index_document",
                    "get": "get_document",
                    "delete": "delete_document",
                }

                if operation in auto_corrections and auto_corrections[operation] in valid_tools[tool]:
                    corrected_op = auto_corrections[operation]
                    print(f"경고: 단계 {idx}에서 '{operation}' -> '{corrected_op}' 자동 수정")
                    operation = corrected_op
                    corrected = True
                elif operation == "list_indices" and "list_indices" in valid_tools[tool]:
                    print(f"  단계 {idx}: '{operation}'는 유효한 도구입니다.")
                    corrected = True

                if not corrected:
                    print(f"오류: 단계 {idx}에서 '{tool}' 서버에 존재하지 않는 도구 '{operation}' 사용.")
                    print(f"     사용 가능한 도구: {sorted(valid_tools[tool])}")

                    if operation == "get_index" and tool == "sleuthkit":
                        print(f"     오류: SleuthKit에는 'get_index'가 없습니다 (Elasticsearch 도구와 혼동)")

                    print(f"     이 단계를 건너뜁니다.")
                    continue

            if tool == "elastic":

                if operation == "list_indices":

                    if params:
                        print(f"경고: 단계 {idx}에서 list_indices에 파라미터가 있습니다: {params}")
                        print(f"     자동 수정: 빈 객체로 변경")
                        params = {}

                if operation == "search_documents":
                    index = params.get("index", "")

                    if index and index != "PLACEHOLDER_INDEX" and "*" not in index:
                        if any(char in index for char in ["<", ">", "인덱스", "이름", "레이블"]):
                            print(f"경고: 단계 {idx}에서 잘못된 index placeholder: '{index}'")
                            print(f"     자동 수정: '{index}' -> 'PLACEHOLDER_INDEX'")
                            params["index"] = "PLACEHOLDER_INDEX"

            if tool == "sleuthkit":
                if operation in ["search_inode_by_path", "extract_files_by_inode"]:
                    fs_offset = params.get("fs_offset_sectors")

                    if fs_offset is None or fs_offset == "" or fs_offset == "0" or fs_offset == 0:
                        print(f"경고: 단계 {idx}에서 fs_offset_sectors가 잘못되었습니다: {repr(fs_offset)}")
                        print(f"     자동 수정: {repr(fs_offset)} -> 'PLACEHOLDER_OFFSET'")
                        params["fs_offset_sectors"] = "PLACEHOLDER_OFFSET"

                if operation == "search_inode_by_path":
                    path = params.get("path", "")

                    if "\\" in path:
                        original_path = path
                        path = path.replace("\\", "/")
                        print(f"경고: 단계 {idx}에서 백슬래시 경로 감지")
                        print(f"     자동 수정: {original_path} -> {path}")

                    if path.startswith("/C/") or path.startswith("/D/") or path.startswith("/E/"):
                        corrected_path = "/" + path[3:]
                        print(f"경고: 단계 {idx}에서 잘못된 경로 변환: {path}")
                        print(f"     자동 수정: {path} -> {corrected_path}")
                        path = corrected_path

                    import re
                    drive_match = re.match(r'^([A-Z]):/(.+)$', path)
                    if drive_match:
                        corrected_path = "/" + drive_match.group(2)
                        print(f"경고: 단계 {idx}에서 드라이브 문자 포함: {path}")
                        print(f"     자동 수정: {path} -> {corrected_path}")
                        path = corrected_path

                    params["path"] = path

                if operation == "extract_files_by_inode":
                    inodes = params.get("inodes")

                    if inodes is None or inodes == "":
                        print(f"경고: 단계 {idx}에서 inodes가 None/빈 값입니다.")
                        print(f"     자동 수정: {repr(inodes)} -> 'PLACEHOLDER_INODES'")
                        params["inodes"] = "PLACEHOLDER_INODES"
                    elif isinstance(inodes, list):
                        print(f"경고: 단계 {idx}에서 inodes가 배열입니다. PLACEHOLDER_INODES를 사용해야 합니다.")
                        print(f"     자동 수정: {inodes} -> 'PLACEHOLDER_INODES'")
                        params["inodes"] = "PLACEHOLDER_INODES"
                    elif isinstance(inodes, str) and inodes.startswith("[") and inodes.endswith("]"):
                        print(f"경고: 단계 {idx}에서 inodes가 JSON 문자열입니다. PLACEHOLDER_INODES를 사용해야 합니다.")
                        print(f"     자동 수정: '{inodes}' -> 'PLACEHOLDER_INODES'")
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
                print(f"\n심각한 오류: SleuthKit 파일 추출 워크플로우가 불완전합니다")
                print(f"     필수 3단계: {required}")
                print(f"     현재 단계: {sleuthkit_ops}")
                print(f"     누락된 단계: {missing}")
                print(f"\n     폴백: 규칙 기반 계획 사용")

                return []
        print(f"LLM이 {len(actions)}단계 계획을 생성했습니다.")

        return actions

    except json.JSONDecodeError as e:
        print(f"LLM 응답 파싱 실패: {e}")
        print(f"     응답 내용: {content[:200]}...")
        return []

    except TimeoutError as e:
        print(f"LLM 호출 타임아웃: {e}")
        raise

    except Exception as e:
        print(f"LLM 계획 생성 중 오류: {e}")
        raise

def _extract_function_names_from_results(dependency_results: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """dependency_results에서 함수 목록 추출

    Args:
        dependency_results: 이전 Task 실행 결과

    Returns:
        List[str]: 함수 이름 리스트
    """
    function_names = []

    if not dependency_results:
        return function_names

    for task_id, results in dependency_results.items():
        for result in results:
            if result.get("operation") == "list_functions" and result.get("success"):
                result_text = str(result.get("result", ""))

                import re
                matches = re.findall(r'^(\S+)\s+at\s+[0-9a-fA-F]+', result_text, re.MULTILINE)
                function_names.extend(matches)

                if function_names:
                    print(f"  {len(function_names)}개 함수 발견")
                    return function_names

    return function_names


def _extract_function_names_with_offsets(dependency_results: Dict[str, List[Dict[str, Any]]]) -> List[tuple]:
    """dependency_results에서 함수 목록과 오프셋 추출

    Args:
        dependency_results: 이전 Task 실행 결과

    Returns:
        List[tuple]: [(함수명, 오프셋), ...] 형식
    """
    import re
    function_list = []

    if not dependency_results:
        return function_list

    for task_id, results in dependency_results.items():
        for result in results:
            action = result.get("action", {})
            if action.get("operation") == "list_functions" and result.get("success"):
                result_text = str(result.get("result", ""))
                matches = re.findall(r'^(\S+)\s+at\s+([0-9a-fA-F]+)', result_text, re.MULTILINE)

                for func_name, addr_str in matches:
                    try:
                        offset = int(addr_str, 16)
                        function_list.append((func_name, offset))
                    except ValueError:
                        continue

                if function_list:
                    return function_list

    return function_list


def _extract_called_functions_from_decompiled(dependency_results: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """이미 디컴파일된 함수에서 호출하는 함수 추출

    Args:
        dependency_results: 이전 Task 실행 결과

    Returns:
        List[str]: 호출된 함수 목록
    """
    import re
    called_funcs = set()

    if not dependency_results:
        return []

    try:
        for task_id, results in dependency_results.items():
            for result in results:
                action = result.get("action", {})

                if action.get("operation") == "decompile_function" and result.get("success"):
                    result_text = str(result.get("result", ""))

                    matches = re.findall(r'\b(FUN_[0-9a-fA-F]{8})\s*\(', result_text)
                    called_funcs.update(matches)

        return list(called_funcs)
    except Exception:
        return []


def _select_important_functions_dynamic(
    available_functions: List[tuple],
    dependency_results: Dict[str, List[Dict[str, Any]]]
) -> List[str]:
    """오프셋 기반 동적 함수 선택

    Args:
        available_functions: [(함수명, 오프셋), ...] 리스트
        dependency_results: 이전 Task 실행 결과

    Returns:
        List[str]: 디컴파일할 함수 이름 리스트 (최대 12개)
    """
    if not available_functions:
        return ["entry", "main"]

    priority_names = ["entry", "main", "_main", "wmain", "WinMain", "wWinMain", "DllMain"]

    selected = []
    available_dict = {name: offset for name, offset in available_functions}

    for func_name in priority_names:
        if func_name in available_dict:
            selected.append(func_name)

    called_functions = _extract_called_functions_from_decompiled(dependency_results)
    for func_name in called_functions[:3]:
        if func_name not in selected and func_name in available_dict:
            selected.append(func_name)

    important_funcs = []
    for func_name, offset in available_functions:
        if func_name not in selected:
            # 32비트
            if 0x00402000 <= offset < 0x00403000:
                important_funcs.append((offset, func_name))
            # 64비트
            elif 0x140002000 <= offset < 0x140003000:
                important_funcs.append((offset, func_name))

    important_funcs.sort()
    for offset, func_name in important_funcs[:2]:
        if func_name not in selected and len(selected) < 12:
            selected.append(func_name)

    entry_offset = available_dict.get("entry")
    if entry_offset:
        near_entry = []
        for func_name, offset in available_functions:
            if func_name != "entry" and func_name not in selected:
                distance = abs(offset - entry_offset)
                if distance < 0x2000:
                    near_entry.append((distance, func_name))

        near_entry.sort()
        for distance, func_name in near_entry[:5]:
            if func_name not in selected and len(selected) < 12:
                selected.append(func_name)

    low_addr_funcs = []
    for func_name, offset in available_functions:
        if func_name.startswith("FUN_") and func_name not in selected:
            if 0x00401000 <= offset < 0x00402000 or 0x140001000 <= offset < 0x140002000:
                low_addr_funcs.append((offset, func_name))

    low_addr_funcs.sort()
    for offset, func_name in low_addr_funcs[:2]:
        if len(selected) < 12:
            selected.append(func_name)

    if not selected:
        return ["entry", "main"]

    return selected[:12]


def _select_important_functions(available_functions: List[str]) -> List[str]:
    """중요한 함수 선택 (entry, main, WinMain 등)

    Args:
        available_functions: 사용 가능한 함수 목록

    Returns:
        List[str]: 디컴파일할 함수 목록 (최대 5개)
    """
    import re

    priority_names = [
        "entry",
        "main",
        "_main",
        "wmain",
        "WinMain",
        "wWinMain",
        "DllMain",
        "_DllMain@12",
    ]

    selected = []
    available_set = set(available_functions)

    for func_name in priority_names:
        if func_name in available_set:
            selected.append(func_name)

    entry_addr = None
    for func in available_functions:
        if func == "entry":
            continue
        if "entry" in func.lower():
            match = re.match(r'FUN_([0-9a-fA-F]+)', func)
            if match:
                entry_addr = int(match.group(1), 16)
                break

    if entry_addr is None:
        all_addrs = []
        for func in available_functions:
            match = re.match(r'FUN_([0-9a-fA-F]+)', func)
            if match:
                all_addrs.append(int(match.group(1), 16))

        if all_addrs:
            min_addr = min(all_addrs)
            entry_addr = min_addr + 0x800
        else:
            entry_addr = 0x140001800

    candidate_functions = []
    for func in available_functions:
        match = re.match(r'FUN_([0-9a-fA-F]+)', func)
        if match:
            addr = int(match.group(1), 16)
            if addr < entry_addr and (entry_addr - addr) < 0x2000:
                candidate_functions.append((addr, func))

    candidate_functions.sort()
    for addr, func in candidate_functions[:3]:
        if func not in selected:
            selected.append(func)

    if "main" not in selected and "_main" not in selected:
        close_to_entry = []
        for func in available_functions:
            match = re.match(r'FUN_([0-9a-fA-F]+)', func)
            if match:
                addr = int(match.group(1), 16)
                if entry_addr - 0x200 <= addr < entry_addr:
                    close_to_entry.append((abs(entry_addr - addr), func))

        close_to_entry.sort()
        for dist, func in close_to_entry[:2]:
            if func not in selected:
                selected.append(func)
                print(f"  entry 근처 함수 발견: {func} (entry가 호출할 가능성 높음)")

    return selected[:5] if selected else []


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
    print("기본 계획을 사용합니다.")
    description_lower = task.description.lower()
    tool_hint = task.metadata.get("tool_hint", "")

    if tool_hint == "ghidra" or any(kw in description_lower for kw in ["ghidra", "바이너리", "리버스", "디컴파일", "함수", "문자열", "실행 파일", "executable", "binary", "reverse"]):
        analysis_phase = task.metadata.get("analysis_phase", "full")

        if analysis_phase == "metadata":
            print("  Ghidra Phase 1: 메타데이터 수집")
            return [
                Action(tool="ghidra", operation="list_functions", params={}, reason="전체 함수 목록 추출"),
                Action(tool="ghidra", operation="list_imports", params={"offset": 0, "limit": 50}, reason="Import 함수 목록"),
                Action(tool="ghidra", operation="list_exports", params={"offset": 0, "limit": 50}, reason="Export 함수 목록"),
                Action(tool="ghidra", operation="list_segments", params={"offset": 0, "limit": 20}, reason="메모리 세그먼트 구조"),
                Action(tool="ghidra", operation="list_strings", params={"offset": 0, "limit": 100}, reason="바이너리 문자열 추출", timeout_seconds=120),
            ]

        elif analysis_phase == "decompile":
            has_previous_decompile = False
            if dependency_results:
                for task_id, results in dependency_results.items():
                    for result in results:
                        action = result.get("action", {})
                        if action.get("operation") == "decompile_function" and result.get("success"):
                            has_previous_decompile = True
                            break
                    if has_previous_decompile:
                        break

            if has_previous_decompile:
                print("  Ghidra Phase 3: Call Chain 함수 디컴파일 (Task 2 결과 활용)")

                called_functions = _extract_called_functions_from_decompiled(dependency_results)

                if called_functions:
                    print(f"  Task 2 entry 함수가 호출하는 함수 발견: {', '.join(called_functions[:12])}")
                    target_functions = called_functions[:12]
                else:
                    print("  Call chain을 찾을 수 없습니다. 오프셋 기반 선택으로 폴백")
                    available_functions_with_offsets = _extract_function_names_with_offsets(dependency_results)
                    if available_functions_with_offsets:
                        target_functions = _select_important_functions_dynamic(
                            available_functions_with_offsets,
                            dependency_results
                        )
                    else:
                        target_functions = ["main"]
            else:
                print("  Ghidra Phase 2: 주요 함수 디컴파일")

                available_functions_with_offsets = _extract_function_names_with_offsets(dependency_results)
                print(f"  [DEBUG] 추출된 함수 (오프셋 포함): {len(available_functions_with_offsets)}개")
                if available_functions_with_offsets:
                    print(f"  [DEBUG] 샘플: {available_functions_with_offsets[:3]}")

                if available_functions_with_offsets:
                    target_functions = _select_important_functions_dynamic(
                        available_functions_with_offsets,
                        dependency_results
                    )
                    print(f"  [DEBUG] 동적 선택된 함수: {target_functions}")
                else:
                    available_functions = _extract_function_names_from_results(dependency_results)
                    print(f"  [DEBUG] 추출된 함수 (이름만): {len(available_functions)}개")
                    if available_functions:
                        print(f"  [DEBUG] 샘플: {available_functions[:5]}")
                    target_functions = _select_important_functions(available_functions)
                    print(f"  [DEBUG] 정적 선택된 함수: {target_functions}")

                if not target_functions:
                    print("  [경고] 함수 목록을 찾을 수 없습니다. 기본 함수명 사용")
                    target_functions = ["entry", "main"]

            print(f"  디컴파일 대상 함수 ({len(target_functions)}개): {', '.join(target_functions)}")
            print(f"  Tip: 함수를 찾을 수 없어도 계속 진행됩니다 (다른 함수 디컴파일 시도)")

            actions = []
            for idx, func_name in enumerate(target_functions, 1):
                # 빈 함수 이름 검증
                if not func_name or not isinstance(func_name, str) or func_name.strip() == "":
                    print(f"  [경고] 빈 함수 이름 발견 (인덱스 {idx}), 건너뜁니다.")
                    continue

                actions.append(
                    Action(tool="ghidra", operation="decompile_function",
                           params={"name": func_name},
                           reason=f"[{idx}/{len(target_functions)}] {func_name} 함수 디컴파일",
                           retry_count=0)
                )

            if not actions:
                print(f"  [경고] 유효한 함수가 없습니다. entry를 기본으로 추가합니다.")
                actions.append(
                    Action(tool="ghidra", operation="decompile_function",
                           params={"name": "entry"},
                           reason="기본 entry 함수 디컴파일",
                           retry_count=0)
                )

            return actions

        else:
            print("  Ghidra 전체 분석 모드 (레거시)")
            return [
                Action(tool="ghidra", operation="list_functions", params={}, reason="전체 함수 목록"),
                Action(tool="ghidra", operation="list_imports", params={"offset": 0, "limit": 50}, reason="Import 함수 목록"),
                Action(tool="ghidra", operation="list_exports", params={"offset": 0, "limit": 50}, reason="Export 함수 목록"),
                Action(tool="ghidra", operation="decompile_function", params={"name": "entry"}, reason="entry 함수 디컴파일"),
                Action(tool="ghidra", operation="list_segments", params={"offset": 0, "limit": 20}, reason="메모리 세그먼트 구조"),
                Action(tool="ghidra", operation="list_strings", params={"offset": 0, "limit": 100}, reason="바이너리 문자열 추출", timeout_seconds=120),
            ]

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
            print(f"  Windows 파일 경로를 찾을 수 없습니다.")
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

