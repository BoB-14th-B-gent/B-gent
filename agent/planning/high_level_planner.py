"""High-Level Planner 모듈

LLM을 사용하여 사용자 프롬프트를 분석하고 상위 계획 생성
"""
from __future__ import annotations
from typing import List, Dict, Any
import json
import os
from ..schemas.task import HighLevelTask, TaskType
from ..llm_client.client import LLMClient
from ..utils.prompt_loader import load_prompt


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
    file_meta: Dict[str, Any] = None
) -> List[HighLevelTask]:
    """High-level 계획 생성 (Phase 1)

    LLM을 사용하여 사용자 프롬프트를 분석하고 추상적인 작업 단계 생성
    파일 목록을 확인하여 디스크 이미지, PE 파일만 분석 대상으로 선정

    Args:
        user_prompt: 사용자 요청
        file_paths: 파일 경로 리스트 (선택)
        file_meta: 파일 메타데이터 (선택)

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

    # 프롬프트 파일에서 로드
    try:
        system_prompt = load_prompt("high_level_planning_system.txt")
    except FileNotFoundError:
        import sys
        sys.stderr.write("[WARNING] Prompt file not found, using inline fallback\n")
        system_prompt = """당신은 DFIR(Digital Forensics and Incident Response) 분석 전문가입니다.
사용자의 요청과 파일 목록을 분석하여 *High-level 작업 계획*을 생성하세요.

*중요: 도구 선택 우선순위*:
1. 사용자가 "Ghidra"를 명시하거나, 바이너리/실행 파일 분석, 디컴파일, 리버스 엔지니어링, 함수 분석을 요청하면 → 무조건 tool_hint: "ghidra"
2. 사용자가 "Elasticsearch", "인덱스", "로그" 등을 명시하면 → tool_hint: "elastic"
3. **사용자가 "디스크 이미지 분석", "아티팩트 분석", "포렌식 분석"을 요청하면 → tool_hint: "velociraptor"** (기본값)
4. **사용자가 명시적으로 "파일 추출", "특정 파일 찾기", "파일 복사"를 요청할 때만 → tool_hint: "sleuthkit"**

**주의: "disk image"만으로는 SleuthKit을 선택하지 마세요!**
- "analyze disk image" → velociraptor (아티팩트 분석)
- "extract file from disk image" → sleuthkit (파일 추출)
- "analyze artifacts" → velociraptor (아티팩트 분석)

*출력 형식* (반드시 JSON):
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "작업 설명 (구체적으로)",
      "task_type": "log_collection | file_extract | artifact_collection | file_analysis | custom",
      "target_files": ["파일 경로1", "파일 경로2"],
      "dependencies": ["task_000"],
      "metadata": {
        "tool_hint": "elastic | sleuthkit | velociraptor | ghidra",
        "priority": "high | medium | low",
        "target_path": "추출할 파일 경로 (file_extract 태스크인 경우 필수)"
      }
    }
  ]
}
```

*Task 생성 규칙*:
1. *Task 설명에 구체적인 정보 포함 (매우 중요):*
   - *사용자 요청에 파일 경로/이름이 명시되어 있으면, Task 설명에도 반드시 포함*
   - 예: "C:\\Users\\hacker\\file.exe 파일을 추출해줘" → "SleuthKit으로 C:\\Users\\hacker\\file.exe 추출"
   - *잘못된 예*: "의심 파일(exe, dll) 추출" (너��� 추상적)
   - *올바른 예*: "SleuthKit으로 C:\\Users\\hacker\\Downloads\\Report_2025.pdf.exe 추출"

2. *적절한 Task 크기 유지*:
   - *너무 세분화하지 마세요* 하나의 도구로 처리 가능한 작업은 하나의 Task로 통합
   - 예: "브라우저 히스토리, 레지스트리, 이벤트 로그 수집" → 1개 Task (Velociraptor 아티팩트 수집)
   - 예외: 서로 다른 도구가 필요하거나, 명확히 순차 의존성이 있는 경우에만 분리

3. *분석 대상별* Task 분리:
   - **디스크 이미지 아티팩트 분석** → task_type: "artifact_collection", tool_hint: "velociraptor" (기본값)
   - **디스크 이미지에서 특정 파일 추출** → task_type: "file_extract", tool_hint: "sleuthkit" (명시적 요청 시에만)
   - PE 파일 분석 → task_type: "file_analysis", tool_hint: "ghidra"
   - 로그 수집/검색/분석 → task_type: "log_collection", tool_hint: "elastic"

4. *도구별* tool_hint 필수 지정:
   - **Velociraptor** (아티팩트 수집, 디스크 이미지 분석, 레지스트리/프리페치/브라우저 히스토리 등) → tool_hint: "velociraptor" *기본값*
   - **SleuthKit** (특정 파일 추출만) → tool_hint: "sleuthkit" *명시적 요청 시에만*
   - Elasticsearch (로그 수집/검색/분석) → tool_hint: "elastic"
   - Ghidra (바이너리 리버스 엔지니어링, 디컴파일) → tool_hint: "ghidra"
   - tool_hint를 반드시 지정하세요. 없으면 도구 검색이 실패할 수 있습니다.

5. *의존성 설정*:
   - 이전 Task의 결과가 *반드시* 필요한 경우에만 dependencies에 추가
   - 예: 파일 추출(task_001) → PE 분석(task_002) → 로그 검색(task_003)
   - 독립적인 Task는 dependencies: []

*MCP 도구 제약사항*:
- 디스크 이미지: .e01, .dd, .raw, .img만 지원 (SleuthKit 사용)
- PE 파일: .exe, .dll, .sys만 지원
- 로그 파일: 전처리기가 처리하므로 무시
- **Elasticsearch (elastic): READ-ONLY MODE** - create, delete, update, insert, modify 등 쓰기 작업 금지. 오직 search, query, get, list, count 등 읽기 작업만 허용

*예시 1* (구체적인 파일 경로 포함):
입력: "디스크 이미지에서 C:\\Users\\hacker\\Downloads\\Report_2025.pdf.exe 파일을 추출해줘"
출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "SleuthKit으로 C:\\Users\\hacker\\Downloads\\Report_2025.pdf.exe 추출",
      "task_type": "file_extract",
      "target_files": ["data/Image.E01"],
      "dependencies": [],
      "metadata": {
        "tool_hint": "sleuthkit",
        "priority": "high",
        "target_path": "C:\\Users\\hacker\\Downloads\\Report_2025.pdf.exe"
      }
    }
  ]
}
```

*예시 1-2* (디스크 이미지 아티팩트 분석 - Velociraptor 기본값):
입력: "디스크 이미지에서 악성 행위 분석"
입력: "디스크 이미지 아티팩트 분석"
입력: "analyze disk image"
출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "Velociraptor로 디스크 이미지 아티팩트 수집 (레지스트리, 프리페치, 브라우저 히스토리 등)",
      "task_type": "artifact_collection",
      "target_files": ["data/Image.E01"],
      "dependencies": [],
      "metadata": {"tool_hint": "velociraptor", "priority": "high"}
    }
  ]
}
```

*예시 1-3* (명시적 파일 추출 요청 - SleuthKit):
입력: "디스크 이미지에서 C:\\Users\\hacker\\suspicious.exe 파일을 추출해줘"
출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "SleuthKit으로 디스크 이미지에서 C:\\Users\\hacker\\suspicious.exe 파일 추출",
      "task_type": "file_extract",
      "target_files": ["data/Image.E01"],
      "dependencies": [],
      "metadata": {
        "tool_hint": "sleuthkit",
        "priority": "high",
        "target_path": "C:\\Users\\hacker\\suspicious.exe"
      }
    }
  ]
}
```

*예시 2* (Task 통합 - 같은 도구 사용):
입력: "디스크 이미지에서 브라우저 히스토리, 레지스트리, 이벤트 로그를 포함해서 기본적인 포렌식 아티팩트를 수집해줘"
���력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "Velociraptor로 브라우저 히스토리, 레지스트리, 이벤트 로그 등 기본 포렌식 아티팩트 수집",
      "task_type": "artifact_collection",
      "target_files": ["data/Image.E01"],
      "dependencies": [],
      "metadata": {"tool_hint": "velociraptor", "priority": "high"}
    }
  ]
}
```

*예시 3*:
입력: "elasticsearch에서 인덱스 목록을 조회해준 후에, 최근 데이터 10개에 대해 분석해줘"
출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "Elasticsearch 인덱스 목록 조회",
      "task_type": "log_collection",
      "target_files": [],
      "dependencies": [],
      "metadata": {"tool_hint": "elastic", "priority": "high"}
    },
    {
      "task_id": "task_002",
      "description": "Elasticsearch에서 최근 10개 데이터 분석",
      "task_type": "log_collection",
      "target_files": [],
      "dependencies": ["task_001"],
      "metadata": {"tool_hint": "elastic", "priority": "high"}
    }
  ]
}
```

*예시 4* (바이너리 리버스 엔지니어링):
입력: "Ghidra로 suspicious.exe의 main 함수를 디컴파일해줘"
출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "Ghidra로 suspicious.exe의 main 함수 디컴파일",
      "task_type": "file_analysis",
      "target_files": ["suspicious.exe"],
      "dependencies": [],
      "metadata": {"tool_hint": "ghidra", "priority": "high"}
    }
  ]
}
```

*예시 5* (Ghidra 바이너리 분석 - **최소 2단계, 복잡한 경우 3단계 이상**):

**간단한 분석 요청 (2-Task)**:
입력: "Ghidra로 바이너리를 분석해줘"
입력: "실행 파일 디컴파일"

출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "Ghidra로 바이너리 메타데이터 수집 (함수 목록, Import/Export, 세그먼트, 문자열)",
      "task_type": "file_analysis",
      "target_files": [],
      "dependencies": [],
      "metadata": {"tool_hint": "ghidra", "priority": "high", "analysis_phase": "metadata"}
    },
    {
      "task_id": "task_002",
      "description": "Ghidra로 주요 함수 디컴파일 (entry, main, 핵심 로직)",
      "task_type": "file_analysis",
      "target_files": [],
      "dependencies": ["task_001"],
      "metadata": {"tool_hint": "ghidra", "priority": "high", "analysis_phase": "decompile"}
    }
  ]
}
```

**복잡한 분석 요청 (3-Task 이상)**:
입력: "Ghidra로 사용자에게 숫자를 받아 정해진 방법으로 입력값을 검증하여 correct 또는 wrong을 출력하는 프로그램을 분석하고 있어"
입력: "바이너리에서 'Correct!' 문자열을 참조하는 함수를 찾고, entry부터 해당 함수까지의 호출 체인을 분석해줘"

출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "Ghidra로 바이너리 메타데이터 수집 (함수 목록, Import/Export, 세그먼트, 문자열)",
      "task_type": "file_analysis",
      "target_files": [],
      "dependencies": [],
      "metadata": {"tool_hint": "ghidra", "priority": "high", "analysis_phase": "metadata"}
    },
    {
      "task_id": "task_002",
      "description": "Ghidra로 entry 함수 디컴파일하여 호출하는 함수 확인",
      "task_type": "file_analysis",
      "target_files": [],
      "dependencies": ["task_001"],
      "metadata": {"tool_hint": "ghidra", "priority": "high", "analysis_phase": "decompile"}
    },
    {
      "task_id": "task_003",
      "description": "Ghidra로 entry가 호출하는 주요 함수들 디컴파일 (call chain 추적)",
      "task_type": "file_analysis",
      "target_files": [],
      "dependencies": ["task_002"],
      "metadata": {"tool_hint": "ghidra", "priority": "high", "analysis_phase": "decompile"}
    }
  ]
}
```

*Ghidra Task 생성 규칙*:
1. **첫 번째 Task는 항상 "metadata" 수집**: 함수 목록, 문자열, Import/Export 등
2. **분석 복잡도에 따라 Task 개수 결정**:
   - *간단*: "바이너리 분석", "파일 디컴파일" → 2개 Task (metadata + decompile)
   - *복잡*: "특정 문자열 찾기", "호출 체인 분석", "검증 로직 찾기" → 3개 이상 Task
3. **복잡한 경우 Task 분리 예시**:
   - Task 1: 메타데이터 수집 (전체 함수 목록, 문자열 목록)
   - Task 2: entry 함수 디컴파일 (어떤 함수를 호출하는지 파악)
   - Task 3: entry가 호출하는 함수들 디컴파일 (실제 로직 분석)
   - Task 4 (선택): 특정 조건 검증 (필요시)
4. **analysis_phase**:
   - 첫 번째 Task: "metadata"
   - 나머지 Task: "decompile"
5. **dependencies**: 각 Task는 이전 Task의 결과를 활용하므로 순차적 의존성 설정
"""

    file_info = ""
    if disk_images:
        file_info += f"\n- 디스크 이미지 ({len(disk_images)}개): {', '.join(disk_images)}"
    if pe_files:
        file_info += f"\n- PE 파일 ({len(pe_files)}개): {', '.join(pe_files)}"
    if categorized_files["unknown"]:
        file_info += f"\n- 기타 파일 ({len(categorized_files['unknown'])}개, 무시됨): {', '.join(categorized_files['unknown'][:3])}"

    user_message = f"""사용자 요청: {user_prompt}

파일 목록:{file_info if file_info else " (없음)"}

위 정보를 바탕으로 High-level 작업 계획을 생성하세요."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        import time
        import sys
        llm_start = time.time()
        sys.stderr.write(f"[Plan] LLM 호출 중 (High-level Planning)...\n")
        sys.stderr.flush()

        # 순환 참조 방지: 타임아웃을 10초로 제한
        response = llm.chat(messages, response_format_json=True, timeout=10)

        llm_elapsed = time.time() - llm_start
        sys.stderr.write(f"[Plan] LLM 응답 완료 ({llm_elapsed:.2f}초)\n")
        sys.stderr.flush()

        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)

        tasks_data = data.get("tasks", [])

        if not tasks_data:
            sys.stderr.write("[Plan] LLM이 빈 계획을 생성 → 폴백 사용\n")
            sys.stderr.flush()
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

    except json.JSONDecodeError as e:
        sys.stderr.write(f"[Plan] LLM 응답 파싱 실패: {e} → 폴백 사용\n")
        sys.stderr.flush()
        return _generate_default_high_level_plan(user_prompt, disk_images, pe_files)

    except TimeoutError as e:
        sys.stderr.write(f"[Plan] LLM 타임아웃 (순환 참조 가능성) → 폴백 사용\n")
        sys.stderr.flush()
        return _generate_default_high_level_plan(user_prompt, disk_images, pe_files)

    except Exception as e:
        error_str = str(e).lower()
        if "timeout" in error_str or "recursion" in error_str or "connection" in error_str:
            sys.stderr.write(f"[Plan] LLM 연결 실패 (순환 참조/타임아웃): {e} → 폴백 사용\n")
        else:
            sys.stderr.write(f"[Plan] High-level 계획 생성 실패: {e} → 폴백 사용\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc()
        return _generate_default_high_level_plan(user_prompt, disk_images, pe_files)


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
    ghidra_keywords = ["ghidra", "바이너리", "리버스", "디컴파일", "reverse", "binary", "decompile"]
    prompt_lower = user_prompt.lower()
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

        # print(f"\n✓ Ghidra Task 자동 생성 완료:")
        # print(f"  1. {task_001.task_id}: {task_001.description}")
        # print(f"  2. {task_002.task_id}: {task_002.description} (의존: {task_002.dependencies})")

        return [task_001, task_002]

    # Ghidra task가 이미 존재하는 경우, 2개 이상이고 analysis_phase가 올바르면 통과
    if len(ghidra_tasks) >= 2:
        has_metadata = any(t.metadata.get("analysis_phase") == "metadata" for t in ghidra_tasks)
        has_decompile = any(t.metadata.get("analysis_phase") == "decompile" for t in ghidra_tasks)

        if has_metadata and has_decompile:
            # print("Ghidra Task 검증 통과 (2단계 구조 확인)")
            return tasks

    # Ghidra task가 1개만 있거나, analysis_phase가 불완전한 경우에만 수정
    # (Ghidra task가 없는 경우 자동 생성하지 않음)
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

        # print(f"\n✓ Ghidra Task 자동 수정 완료:")
        # print(f"  1. {task_001.task_id}: {task_001.description}")
        # print(f"  2. {task_002.task_id}: {task_002.description} (의존: {task_002.dependencies})")

        return result

    # Ghidra task가 없으면 그대로 반환 (자동 생성 금지)
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
