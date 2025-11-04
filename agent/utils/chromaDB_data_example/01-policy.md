# Policy - Ordered Flow (Indices → Alert/Generic Branch → Absolute Time → Pivots) [DSL-only]

본 정책은 ES|QL 미사용, Elasticsearch DSL(JSON) 전용이며, 항상 같은 순서로 실행된다.
LLM은 "무엇을 볼지"만 결정하고, 문법 형식은 이 문서를 따른다.

---

## 0) 공통 하드 규칙

- 항상 시간 필터 포함. 상대시간(now-24h)은 가능하면 절대시간으로 변환한다.
- ECS 우선 필드: @timestamp, host.name, user.name, event.code, process.name, process.command_line, source.ip, destination.ip, dns.question.name, file.hash.sha256, url.original, http.response.status_code
- 정확 일치/집계에는 .keyword 서브필드 사용 (예: host.name.keyword)
- 조건 결합:
  - 공통 제약(시간/인덱스/host/user/ip) → bool.filter
  - 의심 패턴(여러 조건 OR) → bool.should + "minimum_should_match": 1
  - 정상/허용 제외 → bool.must_not
- event.code 등 keyword 타입은 문자열 값 사용(예: "4625")
- 쿼리 전에 필드 존재 검증: 필요 시 {"exists":{"field":"<field>"}}를 bool.filter에 추가
- 출력은 유효한 JSON만. 플레이스홀더({{...}}) 금지

---

## 1) 고정 실행 순서 - 가장 먼저 실행할 것

### Step 1: 인덱스 나열 (필수 1단계)

MCP: list_indices

요청:
```json
{ "index_pattern": "*" }
```

응답 예시:
```json
[
  ".internal.alerts-security.alerts-default-000001",
  "ds-logs-windows.sysmon_operational-*",
  "logs-*",
  "filebeat-*"
]
```

분기:
- 응답에 ^\.internal\.alerts-security\. 존재 → Step 2: Alerts Branch
- 없으면 → Step 3: Generic Branch

---

## 2) Alerts Branch (알람 인덱스 존재)

### 2.1 Top10 알림 (최신순)

MCP: search

요청:
```json
{
  "index": ".internal.alerts-security.alerts-default-000001",
  "query_body": {
    "size": 10,
    "sort": [{ "@timestamp": { "order": "desc" } }],
    "query": { "match_all": {} },
    "_source": [
      "@timestamp",
      "kibana.alert.rule.name",
      "kibana.alert.severity",
      "kibana.alert.reason",
      "host.name",
      "user.name",
      "process.entity_id",
      "process.name"
    ]
  }
}
```

### 2.2 알림 기반 절대시간 산출

Top10 결과의 @timestamp들을 수집하여 min_ts, max_ts 계산.

절대시간 계산 규칙:
- 기본 윈도우: start = min_ts - 30m, end = max_ts + 30m
- 단일 알림만 존재 시: start = ts - 1h, end = ts + 1h
- 호스트/사용자별 피벗 시에도 같은 윈도우를 1차 적용(필요 시 추가 축소/확대)

### 2.3 요약 집계(Top-N)로 우선순위 결정

MCP: search

요청(절대시간 사용):
```json
{
  "index": ".internal.alerts-security.alerts-default-000001",
  "query_body": {
    "size": 0,
    "query": { 
      "range": { 
        "@timestamp": { 
          "gte": "<ABS_START>", 
          "lte": "<ABS_END>" 
        } 
      } 
    },
    "aggs": {
      "by_rule": { 
        "terms": { 
          "field": "kibana.alert.rule.name.keyword", 
          "size": 10 
        } 
      },
      "by_host": { 
        "terms": { 
          "field": "host.name.keyword", 
          "size": 10 
        } 
      },
      "by_user": { 
        "terms": { 
          "field": "user.name.keyword", 
          "size": 10 
        } 
      }
    }
  }
}
```

### 2.4 원로그 피벗(Host/User/Process 기준)

인덱스 후보: logs-*, ds-logs-*, filebeat-* (환경에 맞춰 선택)

요청(절대시간 사용, 예: host 피벗 + 의심 패턴 OR):
```json
{
  "index": "logs-*",
  "query_body": {
    "size": 100,
    "sort": [{ "@timestamp": { "order": "desc" } }],
    "query": {
      "bool": {
        "filter": [
          { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
          { "terms": { "host.name.keyword": ["<HOST1>","<HOST2>"] } }
        ],
        "should": [
          { "terms": { "event.code": ["4624","4625"] } },
          { "regexp": { "process.command_line": "(?i)(invoke-webrequest|wget|curl|certutil)\\b" } },
          { "regexp": { "message": "(?i)http(s)?://.+" } }
        ],
        "must_not": [
          { "match_phrase": { "message": "healthcheck" } }
        ],
        "minimum_should_match": 1
      }
    }
  }
}
```

### 2.5 반복/정밀화

결과 과다:
- 상위 host/user 한정
- 절대시간 축소
- 정규식 구체화

결과 부족:
- message 포함
- 절대시간 확대(+45m, +2h)
- 패턴 완화

Stop 조건:
- 유의미한 히트 ≥ 30
- 반복 ≥ 5
- 평균 took ≥ 3000ms

---

## 3) Generic Branch (알람 없거나 접근 불가)

### 3.1 시계 앵커링("최신"이 실제 현재와 다를 수 있음)

SIEM이 최신 데이터를 즉시 수집하지 않을 수 있으므로, 데이터 자체의 최신 타임스탬프를 기준으로 삼는다.

후보 인덱스(예: logs-*, ds-logs-*, filebeat-*)에서 1건 샘플을 내려받아 최신 @timestamp 수집:

MCP: search

요청:
```json
{
  "index": "logs-*",
  "query_body": {
    "size": 1,
    "sort": [{ "@timestamp": { "order": "desc" } }],
    "query": { "match_all": {} },
    "_source": ["@timestamp"]
  }
}
```

여러 인덱스 중 가장 최근 @timestamp를 T_anchor로 정의.

절대창 설정:
- 초기 절대창: ABS_START = T_anchor - 24h, ABS_END = T_anchor
- 검색 결과는 size=N (예: 500, 1000)으로 최대 개수 제한
- 데이터가 드문 경우(히트 적음) -48h까지 확장 고려

### 3.2 스키마 확인

MCP: get_mappings로 실제 필드 구조 확보

요청:
```json
{ "index": "logs-*" }
```

조회에 실패하거나 부족하면 샘플 1건에서 필드 직접 추출:
```json
{
  "index": "logs-*",
  "query_body": {
    "size": 1,
    "sort": [{ "@timestamp": { "order": "desc" } }],
    "query": { "match_all": {} }
  }
}
```

### 3.3 분포/스파이크 분석

분포 집계로 "먼저 볼 데이터셋/호스트/사용자"를 선정(절대시간 권장).

요청:
```json
{
  "index": "logs-*",
  "query_body": {
    "size": 0,
    "query": { 
      "range": { 
        "@timestamp": { 
          "gte": "<ABS_START>", 
          "lte": "<ABS_END>" 
        } 
      } 
    },
    "aggs": {
      "by_dataset": { 
        "terms": { 
          "field": "event.dataset.keyword", 
          "size": 200 
        } 
      },
      "by_host": { 
        "terms": { 
          "field": "host.name.keyword", 
          "size": 100 
        } 
      },
      "by_day": { 
        "date_histogram": { 
          "field": "@timestamp", 
          "calendar_interval": "1d" 
        } 
      }
    }
  }
}
```

### 3.4 헌팅(OR 패턴 + 정상 제외)

유의미 이벤트가 잡히면 해당 이벤트의 시간대로 절대시간 재설정 후 2차 검색.

요청 예시:
```json
{
  "index": "logs-*",
  "query_body": {
    "size": 100,
    "sort": [{ "@timestamp": { "order": "desc" } }],
    "query": {
      "bool": {
        "filter": [
          { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
        ],
        "should": [
          { "regexp": { "process.command_line": "(?i)(invoke-webrequest|iwr|wget|curl|certutil|bitsadmin)\\b" } },
          { "regexp": { "process.command_line": "(?i)(-enc|encodedcommand)\\b" } },
          { "regexp": { "message": "(?i)http(s)?://.+" } }
        ],
        "must_not": [
          { "match_phrase": { "message": "healthcheck" } },
          { "match_phrase": { "message": "updates.safe" } }
        ],
        "minimum_should_match": 1
      }
    }
  }
}
```

### 3.5 절대시간 재설정 프로세스

1차 헌팅 결과에서 히트된 이벤트들의 @timestamp 수집:
- min_hit_ts, max_hit_ts 계산
- 새로운 절대창: ABS_START = min_hit_ts - 30m, ABS_END = max_hit_ts + 30m
- 이 절대창으로 2차 정밀 검색 수행

---

## 4) 인덱스/필드명 추출 (MCP 표준 절차)

0. 항상 실제 필드명으로 템플릿 치환할 것.
1. get_mappings(index)로 필드/타입 확보
2. 실패/빈약하면 search(index, size=1, sort:@timestamp desc)로 샘플 1건 확인 후, 실제 필드명으로 템플릿 치환
3. ECS 우선: @timestamp, host.name, source.ip, destination.ip, user.name, process.name, dns.question.name, file.hash.sha256, url.original, http.response.status_code
4. .keyword가 있으면 정확 일치/집계에 우선 사용
5. 쿼리 전 exists(field)로 존재 검증 → 동적 분기

---
## 5) 성능 최적화 원칙

- 시간 범위 최소화: 필요한 만큼만 검색
- 필드 필터 우선: exists, term, terms를 filter에 배치
- 정규식 최소화: 가능하면 wildcard나 prefix 사용
- 집계 크기 제한: size를 적절히 설정 (기본 10-100)
- _source 필터링: 필요한 필드만 반환

---

## 6) 헌팅 우선순위 (Generic Branch 전용)

Alert가 없을 때 다음 순서로 헌팅 실행:

1. 비표준 포트 통신 (높은 임팩트, 쉬운 탐지)
2. Downloads 폴더 실행파일 (높은 임팩트, 쉬운 탐지)
3. 이중 확장자 파일 (높은 임팩트, 쉬운 탐지)
4. PowerShell 의심 명령어 (높은 임팩트, 중간 탐지)
5. Office → Shell 프로세스 (높은 임팩트, 중간 탐지)

상세 쿼리는 hunting_workflow.md 참조할 것.

---
