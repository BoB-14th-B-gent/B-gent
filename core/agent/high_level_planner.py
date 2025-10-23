"""High-Level Planner 모듈

LLM을 사용하여 사용자 프롬프트를 분석하고 상위 계획 생성
"""
from __future__ import annotations
from typing import List, Dict, Any
import json
import os
from .schemas.task import HighLevelTask, TaskType
from .llm_client import LLMClient


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

    system_prompt = """당신은 DFIR(Digital Forensics and Incident Response) 분석 전문가입니다.
사용자의 요청과 파일 목록을 분석하여 *High-level 작업 계획*을 생성하세요.

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
        "tool_hint": "elastic | sleuthkit | velociraptor",
        "priority": "high | medium | low"
      }
    }
  ]
}
```

*Task 생성 규칙*:
1. *Task 설명에 구체적인 정보 포함 (매우 중요):*
   - *사용자 요청에 파일 경로/이름이 명시되어 있으면, Task 설명에도 반드시 포함*
   - 예: "C:\\Users\\hacker\\file.exe 파일을 추출해줘" → "SleuthKit으로 C:\\Users\\hacker\\file.exe 추출"
   - *잘못된 예*: "의심 파일(exe, dll) 추출" (너무 추상적)
   - *올바른 예*: "SleuthKit으로 C:\\Users\\hacker\\Downloads\\Report_2025.pdf.exe 추출"

2. *적절한 Task 크기 유지*:
   - *너무 세분화하지 마세요* 하나의 도구로 처리 가능한 작업은 하나의 Task로 통합
   - 예: "브라우저 히스토리, 레지스트리, 이벤트 로그 수집" → 1개 Task (Velociraptor 아티팩트 수집)
   - 예외: 서로 다른 도구가 필요하거나, 명확히 순차 의존성이 있는 경우에만 분리

3. *분석 대상별* Task 분리:
   - 디스크 이미지에서 파일 추출 → task_type: "file_extract", tool_hint: "sleuthkit"
   - PE 파일 분석 → task_type: "file_analysis"
   - 로그 수집/검색/분석 → task_type: "log_collection", tool_hint: "elastic"
   - 아티팩트 수집 → task_type: "artifact_collection", tool_hint: "velociraptor"

4. *도구별* tool_hint 필수 지정:
   - Elasticsearch 작업 (인덱스 목록, 데이터 조회/검색/분석) → tool_hint: "elastic" *필수*
   - SleuthKit 작업 (디스크 이미지, 파일 추출) → tool_hint: "sleuthkit" *필수*
   - Velociraptor 작업 (아티팩트 수집, 시스템 정보) → tool_hint: "velociraptor" *필수*
   - tool_hint를 반드시 지정하세요 없으면 도구 검색이 실패할 수 있습니다.

5. *의존성 설정*:
   - 이전 Task의 결과가 *반드시* 필요한 경우에만 dependencies에 추가
   - 예: 파일 추출(task_001) → PE 분석(task_002) → 로그 검색(task_003)
   - 독립적인 Task는 dependencies: []

*MCP 도구 제약사항*:
- 디스크 이미지: .e01, .dd, .raw, .img만 지원 (SleuthKit 사용)
- PE 파일: .exe, .dll, .sys만 지원
- 로그 파일: 전처리기가 처리하므로 무시

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
      "metadata": {"tool_hint": "sleuthkit", "priority": "high"}
    }
  ]
}
```

*예시 1-2* (Task 분리 - 서로 다른 도구 사용):
입력: "디스크 이미지에서 악성 파일 추출 후 로그 검색"
출력:
```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "description": "SleuthKit으로 디스크 이미지에서 의심 파일 추출",
      "task_type": "file_extract",
      "target_files": ["data/Image.E01"],
      "dependencies": [],
      "metadata": {"tool_hint": "sleuthkit", "priority": "high"}
    },
    {
      "task_id": "task_002",
      "description": "Elasticsearch에서 추출된 파일 관련 로그 검색",
      "task_type": "log_collection",
      "target_files": [],
      "dependencies": ["task_001"],
      "metadata": {"tool_hint": "elastic", "priority": "medium"}
    }
  ]
}
```

*예시 2* (Task 통합 - 같은 도구 사용):
입력: "디스크 이미지에서 브라우저 히스토리, 레지스트리, 이벤트 로그를 포함해서 기본적인 포렌식 아티팩트를 수집해줘"
출력:
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
        llm_start = time.time()
        print(f" LLM 호출 중 (High-level Planning)...")

        response = llm.chat(messages, response_format_json=True, timeout=60)

        llm_elapsed = time.time() - llm_start
        print(f" LLM 응답 완료 ({llm_elapsed:.2f}초)")
        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)

        tasks_data = data.get("tasks", [])

        if not tasks_data:
            print("⚠️  LLM이 빈 계획을 생성했습니다. 기본 계획을 사용합니다.")
            return _generate_default_high_level_plan(user_prompt, disk_images, pe_files)

        tasks = []
        for task_data in tasks_data:
            task_type_str = task_data.get("task_type", "custom")
            try:
                task_type = TaskType(task_type_str)
            except ValueError:
                print(f"⚠️  알 수 없는 task_type: {task_type_str}, CUSTOM으로 설정")
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

        print(f"✓ High-level 계획 생성 완료: {len(tasks)}개 Task")
        for idx, task in enumerate(tasks, 1):
            deps_info = f" (의존: {', '.join(task.dependencies)})" if task.dependencies else ""
            print(f"  {idx}. [{task.task_type.value}] {task.description}{deps_info}")

        return tasks

    except json.JSONDecodeError as e:
        print(f"⚠️  LLM 응답 파싱 실패: {e}")
        return _generate_default_high_level_plan(user_prompt, disk_images, pe_files)

    except Exception as e:
        print(f"⚠️  High-level 계획 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return _generate_default_high_level_plan(user_prompt, disk_images, pe_files)


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
    print("⚠️  기본 High-level 계획을 사용합니다.")

    tasks = []
    prompt_lower = user_prompt.lower()

    if disk_images or any(kw in prompt_lower for kw in ["디스크", "이미지", "추출", "파일", "disk", "image", "extract"]):
        tasks.append(HighLevelTask(
            task_id="task_001",
            description="디스크 이미지 분석 및 파일 추출",
            task_type=TaskType.FILE_EXTRACT,
            target_files=disk_images,
            dependencies=[],
            metadata={"tool_hint": "sleuthkit", "priority": "high"}
        ))

    if any(kw in prompt_lower for kw in ["로그", "log", "이벤트", "event", "검색", "search", "elastic"]):
        dependencies = ["task_001"] if tasks else []
        task_id = f"task_{len(tasks)+1:03d}"

        tasks.append(HighLevelTask(
            task_id=task_id,
            description="Elasticsearch 로그 검색 및 분석",
            task_type=TaskType.LOG_COLLECTION,
            target_files=[],
            dependencies=dependencies,
            metadata={"tool_hint": "elastic", "priority": "medium"}
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

    print(f"✓ 기본 계획 생성 완료: {len(tasks)}개 Task")
    return tasks
