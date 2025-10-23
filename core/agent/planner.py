"""작업 계획 생성기 모듈

RAG로 적절한 MCP 도구를 검색하고 LLM으로 실행 계획 생성
"""
from __future__ import annotations
from typing import List, Dict, Any, Tuple
import json
from .schemas.actions import Action
from .rag import query_mcp_candidates
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
**DFIR 관련 작업 (허용)**:
- 로그 분석 (Elasticsearch, SIEM, 인덱스, 레이블)
- 디스크 포렌식 (파일 추출, 이미지 분석)
- 아티팩트 수집 (Velociraptor, Windows 포렌식)
- 보안 이벤트 탐지
- 시스템 정보 수집 (프로세스, 네트워크 등)
- 악성코드 분석 관련
- 침해 사고 조사 관련
- 메타데이터 조회 (인덱스 목록, 레이블 목록, 스키마, 필드 등)
**용어 참고**:
- "레이블", "라벨" = Elasticsearch의 "인덱스"를 의미할 수 있음
- "분석 가능한 데이터", "수집된 데이터" = DFIR 데이터를 의미
**DFIR 무관 작업 (거부)**:
- 일상 대화, 인사, 감정 표현
- DFIR와 무관한 일반 질문
- 개인적인 요청
- 코딩/개발 요청 (DFIR 도구 개발 제외)
**출력 형식** (반드시 JSON):
```json
{
  "is_valid": true or false,
  "reason": "거부 이유 (is_valid=false인 경우) 또는 빈 문자열"
}
```
**예시**:
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
        # LLM 실패 시 경고만 하고 계속 진행 (디버깅용)
        error_reason = f"입력 검증 시스템 오류: {str(e)}"
        print(f"⚠️  검증 실패: {error_reason}")
        print(f"⚠️  검증을 건너뛰고 계속 진행합니다...")
        return True, ""

def generate_plan(user_prompt: str, file_paths: List[str] = None, file_meta: Dict[str, Any] = None) -> List[Action]:
    """사용자 프롬프트를 기반으로 실행 계획 생성
    RAG로 관련 MCP 도구를 검색하고, LLM을 사용하여 실행 계획 생성
    LLM 실패 시 규칙 기반 폴백 사용
    Args:
        user_prompt: 사용자 요청
        file_paths: 파일 경로 배열 (선택, 디스크 이미지 등)
        file_meta: 파일 메타데이터 (선택)
    Returns:
        List[Action]: 실행 계획 (액션 리스트)
    Raises:
        ValueError: DFIR 무관 요청인 경우
    """
    file_meta = file_meta or {}
    file_paths = file_paths or []

    is_valid, reject_reason = _validate_dfir_request(user_prompt)
    if not is_valid:
        raise ValueError(f"❌ DFIR 분석과 무관한 요청입니다: {reject_reason}")

    candidates = query_mcp_candidates(user_prompt, file_meta, top_k=5)

    if not candidates:
        print("⚠️  RAG에서 도구를 찾지 못했습니다. 기본 계획을 생성합니다.")
        return _generate_default_plan(user_prompt, file_paths)

    try:
        plan = _generate_plan_with_llm(user_prompt, file_paths, candidates)
        if plan:
            return plan
    except Exception as e:
        print(f"⚠️  LLM 계획 생성 실패: {e}")

    return _generate_default_plan(user_prompt, file_paths)

def _generate_plan_with_llm(user_prompt: str, file_paths: List[str], candidates: List[Dict[str, Any]]) -> List[Action]:
    """LLM으로 실행 계획 생성"""
    prompt_lower = user_prompt.lower()
    disk_image_path = None
    if any(kw in prompt_lower for kw in ["추출", "파일", "디스크", "이미지", "extract", "file"]):
        disk_image_path = _find_disk_image_from_paths(file_paths)

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

            max_chars = 2000
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
핵심 규칙:
1. operation은 제공된 도구 목록의 tool_name과 정확히 일치해야 함
2. params는 input_schema의 required 필드를 모두 포함
3. 사용자 요청을 완전히 충족하는 단계 생성 (중간에 멈추지 말 것!)
4. 여러 단계가 필요한 경우 모두 계획에 포함
특수 규칙:
- Velociraptor: 2단계 필수 (client_info → collect_artifact, client_id="PLACEHOLDER_CLIENT_ID")
- SleuthKit 파일 추출: 3단계 필수 (disk_partition_info → search_inode_by_path → extract_files_by_inode)
  * fs_offset_sectors="PLACEHOLDER_OFFSET", inodes="PLACEHOLDER_INODES" 사용
  * Windows 경로 추출: 정확한 파일 경로만 추출! (예: C:\\Users\\hacker\\file.exe)
  * "파일을 추출해줘" 같은 요청 텍스트는 경로에 포함하지 말 것!
  * Windows 경로 → Unix 스타일 변환 (C:\\Users\\hacker\\file.exe → /Users/hacker/file.exe)
- Elasticsearch 워크플로우:
  **1. 메타데이터 조회 (인덱스/레이블 목록):**
  - list_indices(): 파라미터 없음! 반드시 빈 객체 {} 사용
  - 예시: {"tool": "elastic", "operation": "list_indices", "params": {}, "reason": "인덱스 목록 조회"}
  **2. 데이터 조회/분석:**
  - search_documents(index, body): 특정 인덱스에서 문서 검색
  - index="PLACEHOLDER_INDEX": 이전 단계 결과에서 자동 선택됨
  - body: 검색 쿼리 (필수! query_body가 아님)
  - 예시: {"tool": "elastic", "operation": "search_documents", "params": {"index": "PLACEHOLDER_INDEX", "body": {"query": {"match_all": {}}, "size": 10}}, "reason": "선택된 인덱스 데이터 분석"}
  - ⚠️ 주의: 파라미터 이름은 정확히 "body"를 사용! "query_body"나 다른 이름 사용 금지!
  **3. 전체 워크플로우 예시:**
  사용자 요청: "elasticsearch에서 분석 가능한 레이블의 목록을 알려준 후에, 한 레이블을 선택하여 가장 최근에 생성된 데이터 10개에 대해 분석해줘"
  올바른 계획:
  [
    {"tool": "elastic", "operation": "list_indices", "params": {}, "reason": "분석 가능한 인덱스(레이블) 목록 조회"},
    {"tool": "elastic", "operation": "search_documents", "params": {"index": "PLACEHOLDER_INDEX", "body": {"query": {"match_all": {}}, "size": 10}}, "reason": "선택된 레이블에서 최근 데이터 10개 분석"}
  ]
  ⚠️ 중요: search_documents의 파라미터는 반드시 "index"와 "body" 2개! "query_body" 같은 잘못된 이름 사용 금지!
  ⚠️ 중요: 사용자가 "목록 조회 후 분석"을 요청하면 반드시 2단계 모두 생성! 목록 조회만 하고 멈추지 말 것!
"""

    file_info = ""
    if disk_image_path and disk_image_path != "/unknown":
        file_info = f"\n디스크 이미지: {disk_image_path}"
    elif file_paths:
        file_info = f"\n파일: {', '.join(file_paths)}"

    knowledge_info = ""
    if knowledge_docs:
        knowledge_info = "\n\n참고 문서:\n"
        for doc in knowledge_docs:
            knowledge_info += f"- {doc['title']}: {doc['content']}\n"

    user_message = f"""요청: {user_prompt}{file_info}
도구:
{json.dumps(tools_info, ensure_ascii=False)}{knowledge_info}"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        response = llm.chat(messages, response_format_json=True, timeout=90)
        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)
        plan_data = data.get("plan", [])
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
                print(f"⚠️  경고: 단계 {idx}에서 '{tool}' 서버에 존재하지 않는 도구 '{operation}' 사용.")
                print(f"     사용 가능한 도구: {sorted(valid_tools[tool])}")

                if operation == "get_indices" and "list_indices" in valid_tools[tool]:
                    print(f"     → 자동 수정: 'get_indices' → 'list_indices'")
                    operation = "list_indices"

                elif operation == "get_index" and tool == "sleuthkit":
                    print(f"     → 오류: SleuthKit에는 'get_index'가 없습니다 (Elasticsearch 도구와 혼동)")
                    print(f"     → 이 단계를 건너뜁니다.")
                    continue

            if tool == "elastic":

                if operation == "list_indices":

                    if params:
                        print(f"⚠️  경고: 단계 {idx}에서 list_indices에 파라미터가 있습니다: {params}")
                        print(f"     → 자동 수정: 빈 객체로 변경")
                        params = {}

            if tool == "sleuthkit" and operation == "extract_files_by_inode":
                inodes = params.get("inodes")

                if isinstance(inodes, list):
                    print(f"⚠️  경고: 단계 {idx}에서 inodes가 배열입니다. PLACEHOLDER_INODES를 사용해야 합니다.")
                    print(f"     → 자동 수정: {inodes} → 'PLACEHOLDER_INODES'")
                    params["inodes"] = "PLACEHOLDER_INODES"

                elif isinstance(inodes, str) and inodes.startswith("[") and inodes.endswith("]"):
                    print(f"⚠️  경고: 단계 {idx}에서 inodes가 JSON 문자열입니다. PLACEHOLDER_INODES를 사용해야 합니다.")
                    print(f"     → 자동 수정: '{inodes}' → 'PLACEHOLDER_INODES'")
                    params["inodes"] = "PLACEHOLDER_INODES"
                fs_offset = params.get("fs_offset_sectors")

                if fs_offset == "0" or fs_offset == 0:
                    print(f"⚠️  경고: 단계 {idx}에서 fs_offset_sectors가 '0'입니다. PLACEHOLDER_OFFSET을 사용해야 합니다.")
                    print(f"     → 자동 수정: {fs_offset} → 'PLACEHOLDER_OFFSET'")
                    params["fs_offset_sectors"] = "PLACEHOLDER_OFFSET"
            actions.append(Action(
                tool=tool,
                operation=operation,
                params=params,
                reason=item.get("reason", ""),
                timeout_seconds=item.get("timeout_seconds", 60)
            ))
        sleuthkit_ops = [a.operation for a in actions if a.tool == "sleuthkit"]

        if "extract_files_by_inode" in sleuthkit_ops:
            required = ["disk_partition_info", "search_inode_by_path", "extract_files_by_inode"]
            missing = [op for op in required if op not in sleuthkit_ops]

            if missing:
                print(f"\n⚠️  심각한 오류: SleuthKit 파일 추출 워크플로우가 불완전합니다!")
                print(f"     필수 3단계: {required}")
                print(f"     현재 단계: {sleuthkit_ops}")
                print(f"     누락된 단계: {missing}")
                print(f"\n     → 폴백: 규칙 기반 계획 사용")

                return []
        print(f"✓ LLM이 {len(actions)}단계 계획을 생성했습니다.")

        return actions

    except json.JSONDecodeError as e:
        print(f"⚠️  LLM 응답 파싱 실패: {e}")

        return []

    except Exception as e:
        print(f"⚠️  LLM 계획 생성 중 오류: {e}")

        return []

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
                    print(f"  ℹ️  디스크 이미지 선택 (입력 파일): {abs_path}")

                    return abs_path

                else:
                    print(f"  ⚠️  파일이 존재하지 않음: {path}")
    search_dirs = [
        "./data",
        "./data/images",
        "./data/disk_images",
        "."
    ]

    for search_dir in search_dirs:

        if not os.path.exists(search_dir):
            continue

        for ext in disk_extensions:
            pattern = os.path.join(search_dir, "**", f"*{ext}")
            matches = glob.glob(pattern, recursive=True)

            if matches:
                disk_image = os.path.abspath(matches[0])
                print(f"  ℹ️  디스크 이미지 자동 검색 완료: {disk_image}")

                return disk_image
    print(f"  ⚠️  디스크 이미지 파일을 찾을 수 없습니다.")

    if file_paths:
        print(f"     제공된 파일: {file_paths}")
    print(f"     검색 위치: {', '.join(search_dirs)}")
    print(f"     지원 형식: .e01, .dd, .raw, .img")

    return "/unknown"

def _generate_default_plan(user_prompt: str, file_paths: List[str]) -> List[Action]:
    """기본 계획 생성 (폴백)"""
    print("⚠️  기본 계획을 사용합니다.")
    prompt_lower = user_prompt.lower()

    if any(kw in prompt_lower for kw in ["인덱스 목록", "index list", "indices", "레이블 목록", "레이블의 목록", "분석 가능한", "매핑", "mapping", "스키마", "schema", "필드 목록"]):

        return [
            Action(
                tool="elastic",
                operation="list_indices",
                params={},
                reason="Elasticsearch 인덱스 목록 조회"
            )
        ]

    if any(kw in prompt_lower for kw in ["로그", "siem", "이벤트", "탐지", "쿼리", "검색"]):

        return [
            Action(
                tool="elastic",
                operation="search_documents",
                params={
                    "index": "*",
                    "body": {
                        "query": {
                            "query_string": {
                                "query": user_prompt
                            }
                        },
                        "size": 100
                    }
                },
                reason="SIEM 로그 검색"
            )
        ]

    if file_paths or any(kw in prompt_lower for kw in ["추출", "파일", "디스크", "이미지"]):
        import re
        target_path = None
        quoted_match = re.search(r'"([A-Z]:[^"]+)"', user_prompt)

        if quoted_match:
            target_path = quoted_match.group(1)

        else:
            unquoted_match = re.search(r'(C:\\(?:[^\\:\*\?"<>\|\s]+\\)*[^\\:\*\?"<>\|\s]+\.[a-zA-Z0-9]+)', user_prompt)

            if unquoted_match:
                target_path = unquoted_match.group(1)

        if not target_path:
            print(f"  ⚠️  Windows 파일 경로를 찾을 수 없습니다.")
            print(f"     프롬프트: {user_prompt}")
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
                                    "query": user_prompt
                                }
                            },
                            "size": 100
                        }
                    },
                    reason="파일 경로를 찾을 수 없어 로그 검색으로 대체"
                )
            ]
        unix_path = target_path.replace('C:', '').replace('\\', '/')
        disk_image_path = _find_disk_image_from_paths(file_paths)

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

    if any(kw in prompt_lower for kw in ["아티팩트", "수집", "velociraptor", "artifact", "프리패치", "prefetch", "프로세스", "pslist", "netstat", "네트워크"]):
        hostname = "Virtual Host"
        import re
        host_match = re.search(r'([A-Za-z0-9\-\_\s\.]+)(?:에서|에)', user_prompt)

        if host_match:
            potential_host = host_match.group(1).strip()

            if potential_host and not any(kw in potential_host.lower() for kw in ["윈도우", "아티팩트", "수집", "프리패치", "프로세스"]):
                hostname = potential_host
        operation = "collect_artifact"
        artifact_name = "Windows.KapeFiles.Targets"
        parameters = "_BasicCollection='Y'"
        reason = "Windows 아티팩트 수집 (KAPE 타깃)"

        if any(kw in prompt_lower for kw in ["프리패치", "prefetch"]):
            operation = "windows_execution_prefetch"
            reason = "Windows Prefetch 수집"

            return [
                Action(
                    tool="velociraptor",
                    operation="client_info",
                    params={"hostname": hostname},
                    reason=f"{hostname}의 client_id 조회"
                ),
                Action(
                    tool="velociraptor",
                    operation=operation,
                    params={
                        "client_id": "PLACEHOLDER_CLIENT_ID",
                        "Fields": "Binary,CreationTime,LastRunTimes,RunCount,Hash"
                    },
                    reason=reason
                )
            ]

        elif any(kw in prompt_lower for kw in ["프로세스", "pslist", "process"]):
            operation = "windows_pslist"
            reason = "Windows 프로세스 리스트 수집"

            return [
                Action(
                    tool="velociraptor",
                    operation="client_info",
                    params={"hostname": hostname},
                    reason=f"{hostname}의 client_id 조회"
                ),
                Action(
                    tool="velociraptor",
                    operation=operation,
                    params={
                        "client_id": "PLACEHOLDER_CLIENT_ID",
                        "ProcessRegex": ".",
                        "PidRegex": ".",
                        "ExePathRegex": ".",
                        "CommandLineRegex": ".",
                        "UsernameRegex": ".",
                        "Fields": "Pid,Ppid,TokenIsElevated,Name,Exe,CommandLine,Username"
                    },
                    reason=reason
                )
            ]

        elif any(kw in prompt_lower for kw in ["네트워크", "netstat", "network", "연결"]):
            operation = "windows_netstat_enriched"
            reason = "Windows 네트워크 연결 수집"

            return [
                Action(
                    tool="velociraptor",
                    operation="client_info",
                    params={"hostname": hostname},
                    reason=f"{hostname}의 client_id 조회"
                ),
                Action(
                    tool="velociraptor",
                    operation=operation,
                    params={
                        "client_id": "PLACEHOLDER_CLIENT_ID",
                        "IPRegex": ".",
                        "PortRegex": ".",
                        "ProcessNameRegex": ".",
                        "ProcessPathRegex": ".",
                        "CommandLineRegex": ".",
                        "UsernameRegex": ".",
                        "Fields": "Pid,Ppid,Name,Path,CommandLine,Username,Type,Status,Laddr,Lport,Raddr,Rport"
                    },
                    reason=reason
                )
            ]

        return [
            Action(
                tool="velociraptor",
                operation="client_info",
                params={"hostname": hostname},
                reason=f"{hostname}의 client_id 조회"
            ),
            Action(
                tool="velociraptor",
                operation="collect_artifact",
                params={
                    "client_id": "PLACEHOLDER_CLIENT_ID",
                    "artifact": artifact_name,
                    "parameters": parameters
                },
                reason=reason
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
                            "query": user_prompt
                        }
                    },
                    "size": 100
                }
            },
            reason="기본 로그 검색"
        )
    ]

