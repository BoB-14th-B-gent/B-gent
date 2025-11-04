# Threat Hunting Workflow - Alert 없을 때 체계적 분석 순서 [DSL-only]

목적: Alert가 없거나 시작점이 불명확할 때, 통계 이상 탐지 기반으로 위협을 찾는 단계별 워크플로우.
원칙: ES|QL 금지, 모든 쿼리는 Elasticsearch DSL(JSON)만 사용.

주의: 본 문서는 Alert가 없을 때를 중심으로 작성되었으나, Alert Branch에서도 필요 시 참조 가능.
- Alert 후속 조사 시: 해당 Phase의 쿼리 활용
- 연관 분석 시: "Pivot 분석" 참조
- 공격 체인 재구성 시: "고급 패턴: 시퀀스 탐지" 참조

---

## 0) 핵심 전략

1. 베이스라인 구축 → 정상 패턴 파악
2. 통계적 이상 탐지 → 드문 것, 갑작스러운 변화
3. 고위험 신호 우선 → 빠르게 찾을 수 있는 것부터
4. MITRE ATT&CK 기반 → 공격 단계별 체계적 헌팅

---

## 1) Phase 0: 시계 앵커링 (T_anchor 설정)

SIEM이 최신 데이터를 즉시 수집하지 않을 수 있으므로, 데이터 자체의 최신 타임스탬프를 기준으로 삼는다.

### 1-1) 최신 타임스탬프 추출

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 1,
      "sort": [{ "@timestamp": { "order": "desc" } }],
      "query": { "match_all": {} },
      "_source": ["@timestamp"]
    }
  }
}
```

여러 인덱스가 있다면 각각 확인하여 가장 최근 @timestamp를 T_anchor로 정의.

### 1-2) 초기 절대창 설정

- ABS_START = T_anchor - 24h
- ABS_END = T_anchor

데이터가 드문 경우 (히트 < 10) -48h까지 확장 고려.

모든 후속 쿼리는 이 절대시간을 사용한다.

---

## 2) Phase 1: 베이스라인 구축 (정상 패턴 파악)

### 2-1) 호스트별 이벤트 빈도 분석

목적: 비정상적으로 활동이 많거나 적은 호스트 식별

MCP 호출:
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
            "size": 100,
            "order": { "_count": "desc" }
          }
        }
      }
    }
  }
}
```

분석 포인트:
- 상위 10% 호스트 = 의심 (과도한 활동)
- 하위 10% 호스트 = 의심 (비정상 정적)
- 평소와 다른 호스트 = 최우선 조사

### 2-2) 시간대별 이벤트 분포

목적: 업무 외 시간(야간, 주말) 활동 탐지

MCP 호출:
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

분석 포인트:
- 새벽 2-5시 활동 스파이크 = 의심
- 주말 활동 = 의심
- 평소와 다른 시간대 패턴 = 조사

### 2-3) 사용자별 활동 패턴

목적: 비정상 사용자 행동 식별

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "exists": { "field": "user.name" } }
          ]
        }
      },
      "aggs": {
        "by_user": {
          "terms": { 
            "field": "user.name.keyword", 
            "size": 100 
          },
          "aggs": {
            "unique_hosts": {
              "cardinality": { "field": "host.name.keyword" }
            }
          }
        }
      }
    }
  }
}
```

분석 포인트:
- 한 사용자가 많은 호스트에 접근 = 횡적 이동 의심
- 서비스 계정이 아닌데 24시간 활동 = 의심

---

## 3) Phase 2: 고위험 신호 우선 탐지

포트 번호만으로는 악성/정상을 구분할 수 없음 (80/443도 C2에 사용됨)
따라서 3가지 독립적인 관점으로 동시 탐지

중요: 아래 3개 검사는 순차가 아닌 병렬 실행. 각각 다른 위협을 찾음

### 3-1) 관점 1: 비표준 포트

목적: 저수준 공격자, 자동화 도구 빠른 발견

검사 대상: 비표준 포트만 (80/443 등 제외)
한계: 고급 APT는 80/443 사용하므로 이것만으로는 부족

MCP 호출:
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
            { "exists": { "field": "destination.port" } }
          ],
          "must_not": [
            { "terms": { "destination.port": [80, 443, 53, 22, 3389, 445, 135, 139, 389, 636, 88, 464, 3268, 3269] } }
          ]
        }
      },
      "aggs": {
        "by_port": {
          "terms": { "field": "destination.port", "size": 20 },
          "aggs": {
            "top_processes": {
              "terms": { "field": "process.name.keyword", "size": 5 }
            }
          }
        }
      }
    }
  }
}
```

예상 발견: 4444, 5555, 8000, 8080, 8443, 9001, 1337 등

히트 발견 시: 절대시간 재설정하여 2차 정밀 검색

### 3-2) 관점 2: 비콘 패턴

목적: 주기적 C2 통신 탐지

검사 대상: 모든 포트 (80, 443 포함)
핵심: C2는 일정 주기로 체크인하므로 시간 패턴으로 탐지 가능

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "exists": { "field": "destination.ip" } },
            { "exists": { "field": "destination.port" } }
          ]
        }
      },
      "aggs": {
        "by_source": {
          "terms": { "field": "source.ip.keyword", "size": 100 },
          "aggs": {
            "by_destination": {
              "terms": { "field": "destination.ip.keyword", "size": 50 },
              "aggs": {
                "by_port": {
                  "terms": { "field": "destination.port", "size": 10 },
                  "aggs": {
                    "connections_per_minute": {
                      "date_histogram": {
                        "field": "@timestamp",
                        "fixed_interval": "1m"
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

분석 기준:
- 매 분마다 연결 = 의심 (포트 무관)
- 443 포트여도 매 분 연결되면 조사
- 같은 destination에 > 100회 = 즉시 조사

예상 발견: 
- 443 포트 C2 (Cobalt Strike, Metasploit)
- 80 포트 C2 (일부 프레임워크)

상세 조사 쿼리:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 100,
      "sort": [{ "@timestamp": { "order": "asc" } }],
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "source.ip.keyword": "<의심_IP>" } },
            { "term": { "destination.ip.keyword": "<의심_목적지>" } }
          ]
        }
      }
    }
  }
}
```

### 3-3) 관점 3: 프로세스 기반

목적: 비정상 프로세스의 네트워크 활동 탐지

검사 대상: 모든 포트 (80, 443 포함)
핵심: 브라우저의 443은 정상, PowerShell의 443은 의심

MCP 호출:
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
            { "exists": { "field": "destination.ip" } },
            { "exists": { "field": "process.name" } }
          ],
          "should": [
            {
              "bool": {
                "must": [
                  { "terms": { "destination.port": [80, 443] } }
                ],
                "must_not": [
                  { "terms": { "process.name.keyword": [
                    "chrome.exe", "firefox.exe", "msedge.exe", "iexplore.exe",
                    "teams.exe", "outlook.exe", "slack.exe",
                    "OneDrive.exe", "Dropbox.exe", "svchost.exe"
                  ] } }
                ]
              }
            },
            {
              "bool": {
                "must": [
                  { "exists": { "field": "destination.port" } },
                  { "wildcard": { "process.executable": "*\\\\Downloads\\\\*" } }
                ]
              }
            },
            {
              "bool": {
                "must": [
                  { "exists": { "field": "destination.port" } },
                  { "terms": { "process.name.keyword": ["powershell.exe", "cmd.exe", "rundll32.exe", "regsvr32.exe", "mshta.exe"] } }
                ]
              }
            }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

예상 발견:
- PowerShell이 443으로 통신 (다운로드 시도)
- Downloads 폴더 실행파일의 80/443 통신
- rundll32/regsvr32의 네트워크 활동

즉시 조사 대상:
- PowerShell/cmd.exe의 모든 외부 통신
- Downloads 폴더 실행파일의 모든 통신
- LOLBins의 네트워크 활동

---

## 3가지 관점의 실행 예시

```
시나리오: 동일한 24시간 로그 분석

관점 1 실행 (비표준 포트):
→ 8000 포트 통신 1건 발견
→ 프로세스: unknown.exe

관점 2 실행 (비콘 패턴):
→ 443 포트에서 매 분마다 연결 발견
→ 프로세스: svchost.exe (의심)

관점 3 실행 (프로세스 기반):
→ powershell.exe가 443으로 통신 발견
→ 명령어: Invoke-WebRequest

결과 종합:
- 3가지 독립적인 위협 발견
- 관점 1만 실행했다면 443 포트 위협 2건 놓침
- 모든 관점 실행으로 완전한 가시성 확보
```

---

## 4) Phase 3: 네트워크 이상 탐지

### 4-1) 대량 연결 시도

포트 스캔, C2 비콘 탐지

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "exists": { "field": "destination.ip" } }
          ]
        }
      },
      "aggs": {
        "by_source": {
          "terms": { "field": "source.ip.keyword", "size": 100 },
          "aggs": {
            "unique_destinations": {
              "cardinality": { "field": "destination.ip.keyword" }
            },
            "unique_ports": {
              "cardinality": { "field": "destination.port" }
            }
          }
        }
      }
    }
  }
}
```

분석 포인트:
- unique_destinations > 100 = 포트 스캔
- unique_ports > 50 = 스캔 활동
- 1분마다 같은 IP:Port 연결 = C2 비콘

### 4-2) DNS 터널링/DGA 탐지

비정상 DNS 패턴

MCP 호출:
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
            { "exists": { "field": "dns.question.name" } }
          ],
          "should": [
            { "regexp": { "dns.question.name": ".*\\.onion$" } },
            { "regexp": { "dns.question.name": "^[a-z0-9]{20,}\\." } },
            { "script": { "script": { "source": "doc['dns.question.name.keyword'].value.length() > 50" } } }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

### 4-3) 내부 IP 간 비정상 통신

횡적 이동 탐지

MCP 호출:
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
            { "exists": { "field": "source.ip" } },
            { "exists": { "field": "destination.ip" } }
          ],
          "should": [
            { "terms": { "destination.port": [445, 139, 135, 3389] } }
          ],
          "must_not": [
            { "terms": { "process.name.keyword": ["System", "svchost.exe"] } }
          ],
          "minimum_should_match": 1
        }
      },
      "aggs": {
        "by_source": {
          "terms": { "field": "source.ip.keyword", "size": 50 },
          "aggs": {
            "unique_targets": {
              "cardinality": { "field": "destination.ip.keyword" }
            }
          }
        }
      }
    }
  }
}
```

---

## 5) Phase 4: 파일 시스템 이상

### 5-1) 시스템 폴더 의심 파일

루트킷, 드로퍼 탐지

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            {
              "bool": {
                "must": [
                  { "wildcard": { "file.path": "*\\\\System32\\\\*" } }
                ],
                "must_not": [
                  { "wildcard": { "file.path": "*.dll" } },
                  { "wildcard": { "file.path": "*.sys" } },
                  { "wildcard": { "file.path": "*.exe" } }
                ]
              }
            },
            { "wildcard": { "file.path": "*\\\\Temp\\\\*.exe" } },
            { "wildcard": { "file.path": "*\\\\AppData\\\\Roaming\\\\*.exe" } }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

### 5-2) 파일 해시 빈도 분석

드문 파일 = 의심

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "exists": { "field": "file.hash.sha256" } }
          ]
        }
      },
      "aggs": {
        "rare_hashes": {
          "terms": { 
            "field": "file.hash.sha256.keyword", 
            "size": 100,
            "order": { "_count": "asc" }
          }
        }
      }
    }
  }
}
```

분석: count=1인 해시 → 상세 조사

---

## 6) Phase 5: 계정 및 권한 이상

### 6-1) Brute Force 시도

실패한 로그인 집중

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "event.code": "4625" } }
          ]
        }
      },
      "aggs": {
        "by_user": {
          "terms": { "field": "user.name.keyword", "size": 100 },
          "aggs": {
            "by_source_ip": {
              "terms": { "field": "source.ip.keyword", "size": 10 }
            }
          }
        }
      }
    }
  }
}
```

임계값: 10회 이상 실패 = 즉시 조사

### 6-2) 새 계정 생성

백도어 계정 탐지

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 50,
      "sort": [{ "@timestamp": { "order": "desc" } }],
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "event.code": "4720" } }
          ]
        }
      },
      "_source": ["@timestamp", "host.name", "user.name", "event.action"]
    }
  }
}
```

### 6-3) 권한 그룹 변경

권한 상승 탐지

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 50,
      "sort": [{ "@timestamp": { "order": "desc" } }],
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "terms": { "event.code": ["4728", "4732", "4756"] } }
          ]
        }
      }
    }
  }
}
```

---

## 7) Phase 6: MITRE ATT&CK 기반 심화 헌팅

### 7-1) Persistence (지속성)

레지스트리 Run 키 수정

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            { "wildcard": { "registry.path": "*\\\\Run\\\\*" } },
            { "wildcard": { "registry.path": "*\\\\RunOnce\\\\*" } },
            { "regexp": { "process.command_line": "(?i).*(schtasks.*create).*" } }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

### 7-2) Defense Evasion (탐지 회피)

보안 도구 비활성화

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            { "regexp": { "process.command_line": "(?i).*(Set-MpPreference|DisableRealtimeMonitoring).*" } },
            { "regexp": { "process.command_line": "(?i).*(wevtutil.*clear-log).*" } },
            { "regexp": { "process.command_line": "(?i).*(Stop-Service.*WinDefend).*" } }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

### 7-3) Credential Access (자격증명 탈취)

LSASS 덤프 시도

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            {
              "bool": {
                "must": [
                  { "wildcard": { "process.name.keyword": "*procdump*" } },
                  { "wildcard": { "process.command_line": "*lsass*" } }
                ]
              }
            },
            { "regexp": { "process.command_line": "(?i).*(sekurlsa|lsadump|mimikatz).*" } }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

### 7-4) Discovery (정찰)

시스템 정보 수집

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            { "regexp": { "process.command_line": "(?i).*(systeminfo|whoami|ipconfig|net user|net group).*" } },
            { "regexp": { "powershell.script_block.text": "(?i).*(Get-ComputerInfo|Get-NetIPAddress|Get-LocalUser).*" } }
          ],
          "must_not": [
            { "match_phrase": { "process.command_line": "healthcheck" } }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

---

## 8) Pivot 분석 (연쇄 추적)

### 8-1) IOC 확장 검색 - 파일 해시 기반

MCP 호출:
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
            { "term": { "file.hash.md5.keyword": "<FOUND_HASH>" } }
          ]
        }
      },
      "aggs": {
        "affected_hosts": {
          "terms": { "field": "host.name.keyword", "size": 100 }
        }
      }
    }
  }
}
```

### 8-2) IOC 확장 검색 - IP 기반

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            { "term": { "source.ip.keyword": "<SUSPICIOUS_IP>" } },
            { "term": { "destination.ip.keyword": "<SUSPICIOUS_IP>" } }
          ],
          "minimum_should_match": 1
        }
      },
      "aggs": {
        "by_host": {
          "terms": { "field": "host.name.keyword", "size": 50 }
        }
      }
    }
  }
}
```

### 8-3) 타임라인 상관분석 - 특정 호스트 전체 활동

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 500,
      "sort": [{ "@timestamp": { "order": "asc" } }],
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } },
            { "term": { "host.name.keyword": "<SUSPICIOUS_HOST>" } }
          ]
        }
      },
      "_source": ["@timestamp", "event.action", "process.name", "process.command_line", "user.name", "destination.ip", "file.path"]
    }
  }
}
```

---

## 10) 결과 판단 기준

### 즉시 조사 대상 (Critical)

- 비표준 포트 통신 + 의심 프로세스
- Downloads 폴더 실행파일 + 네트워크 연결
- PowerShell 인코딩 명령어
- Office → Shell 스폰
- LSASS 덤프 시도
- 443 포트 비콘 패턴

### 심층 조사 대상 (High)

- 대량 네트워크 연결 (>100 unique IPs)
- DNS 쿼리 이상 (긴 도메인, DGA 패턴)
- 업무 외 시간 대량 활동
- 새 계정 생성 + 권한 그룹 추가

### 모니터링 강화 (Medium)

- 드문 프로세스 실행 (빈도 분석 결과)
- 정찰 명령어 (systeminfo, whoami)
- 시스템 폴더 파일 생성

---

## 11) 헌팅 효율화 팁

### Tip 1: 쿼리 결과 시간대로 절대시간 재생성

1차 검색 결과의 @timestamp 수집
→ min_ts, max_ts 계산
→ start = min_ts - 10m, end = max_ts + 10m
→ 모든 후속 쿼리에 이 절대시간 적용

### Tip 2: 집계로 우선순위 결정

size:0 + aggs로 Top-N 추출
→ 상위 10개 호스트/사용자/프로세스만 상세 조사
→ 노이즈 제거

### Tip 3: 정상 패턴 제외 (must_not)

알려진 정상 프로세스, 도메인, IP를 미리 제외
→ Signal-to-Noise 비율 향상

### Tip 4: 점진적 필터링

1차: 넓은 범위 (24h, 모든 호스트)
2차: 집계로 상위 N개 추출
3차: 특정 호스트/사용자로 좁혀서 정밀 분석

### Tip 5: 자동화 쿼리북 구축

자주 사용하는 헌팅 쿼리를 카테고리별로 저장
→ RAG 시스템에 임베딩
→ 유사 상황 시 즉시 재사용

---

## 12) 쿼리 성능 최적화

### 최적화 원칙

1. 시간 범위 최소화: 필요한 만큼만 검색
2. 필드 필터 우선: exists, term, terms를 filter에 배치
3. 정규식 최소화: 가능하면 wildcard나 prefix 사용
4. 집계 크기 제한: size를 적절히 설정 (기본 10-100)
5. _source 필터링: 필요한 필드만 반환

### 느린 쿼리 개선 예시

Before (느림):
```json
{
  "query": {
    "regexp": { "message": ".*suspicious.*" }
  }
}
```

After (빠름):
```json
{
  "query": {
    "bool": {
      "filter": [
        { "exists": { "field": "process.name" } }
      ],
      "should": [
        { "match_phrase": { "message": "suspicious" } },
        { "wildcard": { "process.name": "*suspicious*" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

---

## 13) 통계적 임계값 가이드

### 네트워크

- 포트 스캔: unique_destinations > 100 / 1시간
- C2 비콘: 같은 destination에 > 10회 / 10분
- 데이터 유출: outbound connections > 1000 / 1시간

### 프로세스

- 드문 프로세스: 30일간 count < 5
- 의심 부모-자식: Office → Shell 조합 = 즉시 조사
- 시스템 폴더 실행: System32 외부 실행 = 조사

### 계정

- Brute Force: 실패 로그인 > 10회 / 1시간
- 횡적 이동: 1 사용자 → > 10 호스트 / 1시간
- 권한 상승: 새 관리자 계정 생성 = 즉시 조사

### DNS

- DGA: 도메인 길이 > 50자
- 터널링: 쿼리 빈도 > 100회 / 분
- 의심 TLD: .onion, .bit, 알 수 없는 TLD

---

## 14) False Positive 제거 패턴

### 공통 정상 제외 (must_not에 추가)

```json
{
  "must_not": [
    { "match_phrase": { "message": "healthcheck" } },
    { "match_phrase": { "message": "monitoring" } },
    { "match_phrase": { "process.name": "System" } },
    { "match_phrase": { "process.name": "svchost.exe" } },
    { "match_phrase": { "user.name": "SYSTEM" } },
    { "match_phrase": { "user.name": "NT AUTHORITY\\\\SYSTEM" } },
    { "wildcard": { "process.command_line": "*Windows\\\\Update*" } },
    { "wildcard": { "process.command_line": "*Microsoft\\\\EdgeUpdate*" } },
    { "terms": { "destination.ip.keyword": ["127.0.0.1", "::1"] } }
  ]
}
```

### 업데이트/정상 도메인 제외

```json
{
  "must_not": [
    { "wildcard": { "dns.question.name": "*.microsoft.com" } },
    { "wildcard": { "dns.question.name": "*.windows.com" } },
    { "wildcard": { "dns.question.name": "*.windowsupdate.com" } },
    { "wildcard": { "dns.question.name": "*.github.com" } },
    { "wildcard": { "dns.question.name": "*.cloudflare.com" } },
    { "wildcard": { "dns.question.name": "*.google.com" } }
  ]
}
```

---

## 15) 환경별 맞춤 설정

### 소규모 환경 (< 100 호스트)

- 절대시간 범위: T_anchor - 7d ~ T_anchor
- 집계 size: 50-100
- 임계값: 더 낮게 설정

### 중규모 환경 (100-1000 호스트)

- 절대시간 범위: T_anchor - 24h ~ T_anchor
- 집계 size: 100-500
- 임계값: 표준 사용

### 대규모 환경 (> 1000 호스트)

- 절대시간 범위: T_anchor - 1h ~ T_anchor (초기), 필요 시 확장
- 집계 size: 100-200
- 임계값: 더 높게 설정
- 샘플링 고려

---

## 16) 헌팅 결과 → 탐지 룰 전환

### 발견한 패턴을 자동 탐지로

Step 1: 헌팅으로 패턴 발견
```
"Downloads 폴더에서 .pdf.exe 실행" 패턴 발견
→ 3건 탐지, 모두 악성
```

Step 2: 탐지 룰로 전환
```json
{
  "name": "Suspicious Double Extension Execution",
  "query": {
    "bool": {
      "filter": [
        { "range": { "@timestamp": { "gte": "now-5m" } } }
      ],
      "should": [
        { "regexp": { "file.path": ".*\\.(pdf|doc|xls)\\.(exe|scr|com)$" } },
        { "regexp": { "process.executable": ".*\\.(pdf|doc|xls)\\.(exe|scr|com)$" } }
      ],
      "minimum_should_match": 1
    }
  },
  "severity": "high",
  "alert_action": "create_case"
}
```

Step 3: 지속적 개선
```
False Positive 발생 → must_not에 예외 추가
새로운 변종 발견 → should에 패턴 추가
```

---

## 17) 실전 시나리오별 워크플로우

### 시나리오 1: "시스템이 느려졌다"는 신고

Step 1: 해당 호스트 전체 활동 확인

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<T_anchor - 1h>", "lte": "<T_anchor>" } } },
            { "term": { "host.name.keyword": "<신고_호스트>" } }
          ]
        }
      },
      "aggs": {
        "by_process": {
          "terms": { "field": "process.name.keyword", "size": 20 }
        },
        "network_activity": {
          "filter": { "exists": { "field": "destination.ip" } },
          "aggs": {
            "unique_destinations": {
              "cardinality": { "field": "destination.ip.keyword" }
            }
          }
        }
      }
    }
  }
}
```

Step 2: 비정상 프로세스 확인
- 상위 프로세스 중 생소한 것 → 상세 조사
- 네트워크 활동 급증 → 연결 상세 확인

Step 3: 타임라인 재구성
- 느려지기 시작한 시점 파악
- 그 시점 전후 ±30분 모든 이벤트 조회
- 절대시간 재설정하여 정밀 분석

### 시나리오 2: "외부 보안업체가 우리 IP를 악성으로 신고"

Step 1: 해당 IP 사용 호스트 식별

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<T_anchor - 7d>", "lte": "<T_anchor>" } } },
            { "term": { "source.ip.keyword": "<신고된_IP>" } }
          ]
        }
      },
      "aggs": {
        "by_host": {
          "terms": { "field": "host.name.keyword", "size": 10 }
        }
      }
    }
  }
}
```

Step 2: 해당 호스트들의 아웃바운드 통신 분석

MCP 호출:
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
            { "terms": { "host.name.keyword": ["<HOST1>", "<HOST2>"] } },
            { "exists": { "field": "destination.ip" } }
          ],
          "must_not": [
            { "wildcard": { "destination.ip": "192.168.*" } },
            { "wildcard": { "destination.ip": "10.*" } }
          ]
        }
      }
    }
  }
}
```

Step 3: 의심 프로세스 찾기
- Quick Hunt 체크리스트 실행
- C2 통신 패턴 확인

### 시나리오 3: "랜섬웨어 감염 의심"

Step 1: 대량 파일 수정 탐지

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 0,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<T_anchor - 1h>", "lte": "<T_anchor>" } } },
            { "exists": { "field": "file.path" } }
          ]
        }
      },
      "aggs": {
        "by_host": {
          "terms": { "field": "host.name.keyword", "size": 50 },
          "aggs": {
            "file_changes": {
              "cardinality": { "field": "file.path.keyword" }
            }
          }
        }
      }
    }
  }
}
```

Step 2: 랜섬 노트 파일 검색

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<T_anchor - 24h>", "lte": "<T_anchor>" } } }
          ],
          "should": [
            { "wildcard": { "file.path": "*README*" } },
            { "wildcard": { "file.path": "*DECRYPT*" } },
            { "wildcard": { "file.path": "*RANSOM*" } },
            { "wildcard": { "file.path": "*.txt" } }
          ],
          "minimum_should_match": 1
        }
      }
    }
  }
}
```

Step 3: 초기 감염 벡터 역추적
- 첫 파일 수정 시점 확인
- 그 전 1시간 동안의 프로세스/네트워크 활동
- Downloads, 이메일 첨부파일 실행 확인

---

## 18) 고급 패턴: 시퀀스 탐지

### 공격 체인 탐지 (다단계 패턴)

패턴: 피싱 → 실행 → C2 연결

Step 1: 이메일/브라우저에서 다운로드

MCP 호출:
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
            { "terms": { "process.parent.name.keyword": ["outlook.exe", "chrome.exe", "msedge.exe"] } },
            { "wildcard": { "file.path": "*\\\\Downloads\\\\*" } }
          ]
        }
      },
      "_source": ["@timestamp", "host.name", "user.name", "file.path", "file.hash.md5"]
    }
  }
}
```

Step 2: 10분 내 실행 확인

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<DOWNLOAD_TIME>", "lte": "<DOWNLOAD_TIME+10m>" } } },
            { "term": { "host.name.keyword": "<SAME_HOST>" } },
            { "wildcard": { "process.executable": "*\\\\Downloads\\\\*" } }
          ]
        }
      }
    }
  }
}
```

Step 3: 실행 후 10분 내 네트워크 연결

MCP 호출:
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
            { "range": { "@timestamp": { "gte": "<EXEC_TIME>", "lte": "<EXEC_TIME+10m>" } } },
            { "term": { "host.name.keyword": "<SAME_HOST>" } },
            { "exists": { "field": "destination.ip" } }
          ],
          "must_not": [
            { "terms": { "destination.port": [80, 443, 53] } }
          ]
        }
      }
    }
  }
}
```

이 3단계가 모두 연결되면 → High Confidence 위협

---

## 19) 메모리 효율적인 대량 검색

### 대용량 환경에서의 Scroll API 활용

초기 검색:

MCP 호출:
```json
{
  "tool": "search",
  "arguments": {
    "index": "logs-*",
    "query_body": {
      "size": 1000,
      "query": {
        "bool": {
          "filter": [
            { "range": { "@timestamp": { "gte": "<ABS_START>", "lte": "<ABS_END>" } } }
          ],
          "should": [
            { "regexp": { "process.command_line": "(?i).*(invoke-webrequest).*" } }
          ],
          "minimum_should_match": 1
        }
      },
      "scroll": "5m"
    }
  }
}
```

후속 페이징: scroll_id 사용하여 계속 조회

---

## 20) 최종 체크리스트

### 헌팅 시작 전

- [ ] 인덱스 목록 확인 (list_indices)
- [ ] T_anchor 설정 (최신 @timestamp 추출)
- [ ] 필드 매핑 확인 (get_mappings)
- [ ] 절대시간 범위 결정 (T_anchor 기준)
- [ ] False Positive 제외 리스트 준비

### 헌팅 실행 중

- [ ] Top 10 의심 호스트 식별
- [ ] 각 호스트별 상세 조사
- [ ] 히트 발견 시 절대시간 재설정
- [ ] Pivot으로 연관 호스트 추가 조사
- [ ] 타임라인 재구성

### 헌팅 완료 후

- [ ] 발견 사항 문서화
- [ ] IOC 목록 작성
- [ ] 탐지 룰 생성/업데이트
- [ ] 대응 조치 권고
- [ ] 베이스라인 업데이트

---