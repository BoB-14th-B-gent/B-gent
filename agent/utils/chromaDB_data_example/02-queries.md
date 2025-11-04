# DSL Query Templates - Pure Templates (RAG Reference)

목적: LLM이 바로 응용/수정 가능한 순수 DSL 템플릿을 제공한다. 하지만 이 모든 쿼리는 예시이다. 
모든 필드 값과 인덱스명은 예시를 그대로 사용하지 말고, 조회된 명칭으로 치환하여 사용한다.
주의: ES|QL 금지. 필요 시 policy.md의 절차로 절대시간을 산출해 치환한다.

---

## B. Alerts-first 시나리오

### B-1) 보안 알람 Top10 (최신순)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
}
```

### B-2) 알림 기반 절대시간 집계(Top-N)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
}
```

### B-3) 원로그 피벗 (host 기반, 절대시간)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
}
```

---

## C. 기본 필터/정렬/집계

### C-1) 특정 키워드 포함 (message)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 50,
      "query": { 
        "match_phrase": { 
          "message": "<keyword>" 
        } 
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### C-2) 정확 매칭 (복수 조건)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "term": { "event.action.keyword": "<event_action>" } },
            { "term": { "user.name.keyword": "<username>" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### C-3) IN / NOT IN
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "terms": { "host.name.keyword": ["<HOST1>","<HOST2>","<HOST3>"] } }
          ],
          "must_not": [
            { "terms": { "user.name.keyword": ["<svc_a>","<svc_b>"] } }
          ]
        }
      }
    }
  }
}
```

### C-4) 시간 범위 필터 (절대시간)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "range": { 
          "@timestamp": { 
            "gte": "<ABS_START>", 
            "lte": "<ABS_END>" 
          } 
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### C-5) 시간 범위 필터 (상대시간 - 1차 탐색용)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "range": { 
          "@timestamp": { 
            "gte": "now-24h", 
            "lte": "now" 
          } 
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### C-6) 필드별 발생 건수 (집계)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "aggs": {
        "by_field": { 
          "terms": { 
            "field": "<FIELD>.keyword", 
            "size": 20 
          } 
        }
      }
    }
  }
}
```

### C-7) 드문 값 상위 N (희귀값)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "aggs": {
        "rare_values": { 
          "terms": { 
            "field": "<FIELD>.keyword", 
            "size": 20, 
            "order": { "_count": "asc" } 
          } 
        }
      }
    }
  }
}
```

### C-8) 필요한 필드만 가져오기
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "_source": ["@timestamp","host.name","user.name","message"],
      "size": 50,
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### C-9) 중복 제거 유사 (collapse)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": { "match_all": {} },
      "collapse": { 
        "field": "<FIELD>.keyword" 
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### C-10) 시간대별 히스토그램
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
        "by_hour": {
          "date_histogram": {
            "field": "@timestamp",
            "calendar_interval": "1h"
          }
        }
      }
    }
  }
}
```

---

## D. 복합 조건 (bool 쿼리)

### D-1) AND 조건 (filter)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "host.name.keyword": "<HOST>" } },
            { "term": { "event.code": "4625" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### D-2) OR 조건 (should + minimum_should_match)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            { "term": { "event.code": "4624" } },
            { "term": { "event.code": "4625" } },
            { "term": { "event.code": "4720" } }
          ],
          "minimum_should_match": 1
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### D-3) NOT 조건 (must_not)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "must_not": [
            { "match_phrase": { "message": "healthcheck" } },
            { "term": { "user.name.keyword": "SYSTEM" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### D-4) AND + OR + NOT 복합
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "host.name.keyword": "<HOST>" } }
          ],
          "should": [
            { "wildcard": { "process.name": "*powershell*" } },
            { "wildcard": { "process.name": "*cmd*" } }
          ],
          "must_not": [
            { "match_phrase": { "process.command_line": "Windows Update" } }
          ],
          "minimum_should_match": 1
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

---

## E. 텍스트 검색 패턴

### E-1) Wildcard (부분 일치)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "wildcard": { 
          "file.path": "*\\\\Downloads\\\\*.exe" 
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### E-2) Regexp (정규식)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "regexp": { 
          "process.command_line": "(?i).*(invoke-webrequest|wget|curl).*" 
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### E-3) Match (전문 검색)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "match": { 
          "message": "error failed" 
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### E-4) Match Phrase (구문 검색)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "match_phrase": { 
          "message": "connection refused" 
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### E-5) Prefix (접두사 검색)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "prefix": { 
          "process.name.keyword": "power" 
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

---

## F. 집계 패턴

### F-1) Terms 집계 (Top-N)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
        "top_hosts": {
          "terms": { 
            "field": "host.name.keyword", 
            "size": 20 
          }
        }
      }
    }
  }
}
```

### F-2) 중첩 집계 (Sub-aggregation)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
        "by_host": {
          "terms": { 
            "field": "host.name.keyword", 
            "size": 50 
          },
          "aggs": {
            "by_user": {
              "terms": { 
                "field": "user.name.keyword", 
                "size": 10 
              }
            }
          }
        }
      }
    }
  }
}
```

### F-3) Cardinality (고유값 개수)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
        "unique_hosts": {
          "cardinality": { 
            "field": "host.name.keyword" 
          }
        },
        "unique_users": {
          "cardinality": { 
            "field": "user.name.keyword" 
          }
        }
      }
    }
  }
}
```

### F-4) Stats 집계 (통계)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
        "response_time_stats": {
          "stats": { 
            "field": "http.response.time" 
          }
        }
      }
    }
  }
}
```

### F-5) Filter 집계 (조건별 집계)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
        "failed_logins": {
          "filter": { 
            "term": { 
              "event.code": "4625" 
            } 
          }
        },
        "success_logins": {
          "filter": { 
            "term": { 
              "event.code": "4624" 
            } 
          }
        }
      }
    }
  }
}
```

### F-6) Date Histogram (시계열)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
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
        "events_over_time": {
          "date_histogram": {
            "field": "@timestamp",
            "calendar_interval": "1h"
          },
          "aggs": {
            "top_hosts": {
              "terms": { 
                "field": "host.name.keyword", 
                "size": 5 
              }
            }
          }
        }
      }
    }
  }
}
```

---

## G. 네트워크 분석 템플릿

### G-1) 특정 포트 통신
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "destination.port": 8000 } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### G-2) 비표준 포트 (정상 포트 제외)
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "exists": { "field": "destination.port" } }
          ],
          "must_not": [
            { "terms": { "destination.port": [80, 443, 53, 22, 3389, 445, 135, 139, 389, 636, 88, 464] } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### G-3) 특정 IP 통신
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            { "term": { "source.ip.keyword": "<IP>" } },
            { "term": { "destination.ip.keyword": "<IP>" } }
          ],
          "minimum_should_match": 1
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

---

## H. 프로세스 분석 템플릿

### H-1) 특정 프로세스 실행
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "wildcard": { "process.name": "*powershell*" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### H-2) 부모-자식 프로세스 관계
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "process.parent.name.keyword": "winword.exe" } },
            { "term": { "process.name.keyword": "powershell.exe" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### H-3) 명령줄 인자 검색
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "exists": { "field": "process.command_line" } }
          ],
          "should": [
            { "regexp": { "process.command_line": "(?i).*(invoke-webrequest).*" } },
            { "regexp": { "process.command_line": "(?i).*(-enc|-encodedcommand).*" } }
          ],
          "minimum_should_match": 1
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

---

## I. 파일 분석 템플릿

### I-1) 파일 생성/수정
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "exists": { "field": "file.path" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### I-2) 특정 폴더 파일 활동
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "wildcard": { "file.path": "*\\\\Downloads\\\\*" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

### I-3) 파일 해시 검색
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "file.hash.md5.keyword": "<HASH>" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```

---

## J. DNS 분석 템플릿

### J-1) 특정 도메인 질의
**MCP 호출:**
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "wildcard": { "dns.question.name": "*malicious.com*" } }
          ]
        }
      },
      "sort": [{ "@timestamp": { "order": "desc" } }]
    }
  }
}
```
