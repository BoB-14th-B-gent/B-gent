# Elastic MCP – Available Tools

본 문서는 MCP 툴의 **정확한 요청/응답 포맷**을 제공한다.  
쿼리 본문은 모두 **Elasticsearch DSL(JSON)** 이다.  
MCP 호출 시에는 반드시 `tool` + `arguments` 래핑을 사용한다.  

---

## list_indices
- **설명**: 인덱스 목록 조회 (연결/인벤토리 확인 용)

### 요청
```json
{
  "tool": "list_indices",
  "arguments": {
    "index_pattern": "*"
  }
}
```

### 응답 (예시)
```json
[
  ".internal.alerts-security.alerts-default-000001",
  "ds-logs-windows.sysmon_operational-*",
  "ds-logs-system.security-*",
  "filebeat-*"
]
```

- **비고**: 보안 알람 인덱스 접두어는 보통 `.internal.alerts-security.`

---

## search
- **설명**: Elasticsearch DSL 쿼리 실행

### 요청
```json
{
  "tool": "search",
  "arguments": {
    "index": ".internal.alerts-security.alerts-default-000001",
    "query_body": {
      "size": 1,
      "query": { "match_all": {} },
      "_source": true
    }
  }
}
```

### 응답 (예시)
```json
{
  "took": <number>,              // 쿼리 실행 시간(ms)
  "timed_out": <boolean>,        // 타임아웃 여부
  "_shards": {                   // 샤드 실행 결과
    "total": <number>,
    "successful": <number>,
    "skipped": <number>,
    "failed": <number>
  },
  "hits": {                      // 검색 결과
    "total": {                   // 매칭된 문서 수
      "value": <number>,
      "relation": "eq" | "gte"
    },
    "max_score": <number|null>,  // 점수 기반 정렬 시 최대 점수
    "hits": [                    // 반환된 문서 목록
      {
        "_index": "<string>",    // 문서 인덱스
        "_id": "<string>",       // 문서 ID
        "_score": <number|null>, // 검색 점수
        "_source": {             // 실제 문서 데이터 (인덱스 스키마에 따라 달라짐)
          ...
        }
      }
    ]
  },
  "aggregations": {              // (선택) 집계 결과
    ... user-defined aggregations ...
  }
}
```



# Velociraptor MCP – Available Tools (Windows Plugins Only)
 **Velociraptor 기반 MCP 서버**에서 제공하는 Windows 포렌식 수집용 툴 사용법을 정리합니다.  

---

## About this MCP
- **Purpose**: Velociraptor의 Windows 아티팩트(플러그인)를 수집합니다.
- **Scope (이번 문서)**: 아래 9개 Windows 플러그인만 다룹니다.
- **Output contract (고정 스키마)** – 모든 호출은 아래 JSON 스키마로 결과를 래핑합니다.
  ```json
  {
    "mcp": "velociraptor",
    "plugin": "<windows plugin name>",
    "success": true,
    "request": { /* MCP arguments you sent */ },
    "response": "<stringified tool response (JSON/CSV/TSV/LOG)>"
  }
  ```
  - `mcp`: 항상 `"velociraptor"`
  - `plugin`: 실행한 플러그인 이름(아래 목록 중 하나)
  - `success`: 실행 성공 여부(Boolean)
  - `request`: MCP에 보낸 arguments 그대로(감사/재현용)
  - `response`: Velociraptor 결과를 문자열로 래핑(원본 JSON/CSV/텍스트 등)

---

## Available Windows Plugins
아래 플러그인만 본 문서에서 지원합니다.

```
windows_scheduled_tasks
windows_recentdocs
windows_shellbags
windows_execution_amcache
windows_execution_activitiesCache
windows_execution_userassist
windows_execution_shimcache
windows_execution_prefetch
client_info
```

### Request (공통)
```json
{
  "tool": "velociraptor.run",
  "arguments": {
    "plugin": "<one of supported windows plugins>",
    "args": { /* plugin-specific arguments (optional) */ },
    "output_format": "jsonl",   // or "json", "csv", "tsv"
    "timeout_sec": 300          // optional, default 300
  }
}
```

### Response (공통; 고정 스키마)
```json
{
  "mcp": "velociraptor",
  "plugin": "<plugin>",
  "success": true,
  "request": {
    "plugin": "<plugin>",
    "args": { /* echoed */ },
    "output_format": "jsonl",
    "timeout_sec": 300
  },
  "response": "<stringified tool output>"
}
```

> **Note**  
> - `args` 는 플러그인별 옵션(경로, 사용자, 시간범위 등)을 의미합니다. 비우면 기본값으로 실행합니다.  
> - `output_format` 은 Velociraptor 결과 포맷 선택입니다. 후처리/파이프라인 사정에 맞게 고르세요.  
> - `response` 는 원본 출력을 **문자열**로 감싼 값입니다(예: JSONL 여러 줄, CSV 등).

---

## Plugin-by-Plugin Quick Reference

### 1) `windows_scheduled_tasks`
- **What**: Windows 작업 스케줄러(Task Scheduler) 항목 수집
- **Use cases**: 지속성(Persistence) 진단, 의심 작업 확인

**Normalized Return (schema)**
```json
{
  "mcp": "velociraptor",
  "plugin": "windows_scheduled_tasks",
  "success": true,
  "request": { "plugin": "windows_scheduled_tasks", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of scheduled tasks>"
}
```

---

### 2) `windows_recentdocs`
- **What**: 최근 문서(Recent Documents) 목록
- **Use cases**: 사용자 활동, 최근 접근 파일 추적

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "windows_recentdocs", "success": true,
  "request": { "plugin": "windows_recentdocs", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of recent documents>" }
```

---

### 3) `windows_shellbags`
- **What**: ShellBags(폴더 보기 설정) 아티팩트
- **Use cases**: 폴더 접근 흔적, 경로 히스토리

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "windows_shellbags", "success": true,
  "request": { "plugin": "windows_shellbags", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of shellbags>" }
```

---

### 4) `windows_execution_amcache`
- **What**: Amcache 실행 흔적
- **Use cases**: 실행된 바이너리, 해시/경로/설치 정보 추적

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "windows_execution_amcache", "success": true,
  "request": { "plugin": "windows_execution_amcache", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of amcache execution artifacts>" }
```

---

### 5) `windows_execution_activitiesCache`
- **What**: Windows ActivitiesCache(Timeline) 분석
- **Use cases**: 사용자 타임라인/활동 내역

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "windows_execution_activitiesCache", "success": true,
  "request": { "plugin": "windows_execution_activitiesCache", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of ActivitiesCache>" }
```

---

### 6) `windows_execution_userassist`
- **What**: UserAssist 키(실행 흔적)
- **Use cases**: 실행 빈도/최근 실행 프로그램

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "windows_execution_userassist", "success": true,
  "request": { "plugin": "windows_execution_userassist", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of UserAssist entries>" }
```

---

### 7) `windows_execution_shimcache`
- **What**: ShimCache(AppCompatCache) 실행 흔적
- **Use cases**: 실행 파일 추적, 타임라인 보강

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "windows_execution_shimcache", "success": true,
  "request": { "plugin": "windows_execution_shimcache", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of ShimCache entries>" }
```

---

### 8) `windows_execution_prefetch`
- **What**: Windows Prefetch 실행 흔적
- **Use cases**: 프로그램 최초 실행/빈도/경로

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "windows_execution_prefetch", "success": true,
  "request": { "plugin": "windows_execution_prefetch", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of Prefetch analysis>" }
```

---

### 9) `client_info`
- **What**: 대상 호스트의 기본 정보 수집
- **Use cases**: 스코핑, 환경 식별(호스트명/OS/네트워크 등)

**Normalized Return**
```json
{ "mcp": "velociraptor", "plugin": "client_info", "success": true,
  "request": { "plugin": "client_info", "args": {}, "output_format": "jsonl" },
  "response": "<JSONL lines of client info>" }
```
