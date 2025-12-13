# Elastic MCP Strategy

## Purpose
SIEM log search - Query Elasticsearch indices for security logs, Windows events, network logs.

## Important Notice
**READ-ONLY MODE** - Only search/query operations are allowed. No write/delete operations.

## CRITICAL: Required Execution Order

### STEP 1: ALWAYS call `list_indices` FIRST
- **MANDATORY** - You MUST call `list_indices` as your FIRST action before any search
- This is non-negotiable - never skip this step
- No parameters required: `{}`
- Returns available index names (e.g., winlogbeat-*, filebeat-*, sysmon-*)


### STEP 1.1: Filter indices - exclude internal/system indices
- After `list_indices`, you MUST exclude dot-prefixed indices by default
- Indices starting with `.` are NOT valid primary investigation targets unless explicitly required
- Exclude patterns include (but are not limited to):
  - `.internal.*`
  - `.ds-.fleet-*`
  - `.kibana*`

- Prefer non-dot indices with `docs.count > 0`

### STEP 1.2: Validate candidate indices via sampling (MANDATORY)
- Before any conditional search, you MUST run a small sampling query to confirm:
  - The index contains investigable data
  - Real field names and value formats
- Sampling rule:
  - Use `search_documents` with `match_all`
  - Use small `size` (1-5)
- Skipping sampling is FORBIDDEN


### STEP 2: Perform MULTIPLE `search_documents` calls
- **DO NOT** finish after just 1-2 searches
- **ITERATE** multiple times to achieve the analysis goal
- Each search should refine or expand your investigation
- Continue searching until you have comprehensive evidence

## Analysis Strategy: Iterative Deep Dive

For malicious behavior detection or incident analysis:

1. **Initial Discovery** (1-2 searches)
   - Broad search to identify data scope
   - Find relevant time ranges and hosts

2. **Deep Investigation** (3-5+ searches)
   - Process execution analysis (Sysmon event_id:1, Windows 4688)
   - Network connections (event_id:3, firewall logs)
   - File operations (event_id:11, 15, 23)
   - Registry modifications (event_id:12, 13, 14)
   - User authentication (4624, 4625, 4648)

3. **Correlation & Validation** (2-3+ searches)
   - Cross-reference findings across different log sources
   - Timeline reconstruction
   - Identify attack chain

**Minimum recommended searches: 5-10 for thorough analysis**

## Available Tools

### 1. list_indices (ALWAYS FIRST)
- No required params
- Returns list of index names

### 2. search_documents (REPEAT MULTIPLE TIMES)
- Required params: `index`, `body`
- `body` contains: `query` (Elasticsearch DSL), `size`, `from`, `sort`

### 3. search_by_time_range
- Required params: `index`, `start_time`, `end_time`
- Optional: `query` (additional filter)

### 4. aggregate_logs
- Required params: `index`, `agg_field`
- Returns counts/statistics grouped by field

## Common Mistakes to Avoid
- **NEVER** skip list_indices - always call it first
- **NEVER** finish with only 1-2 searches - iterate until goal is achieved
- **NEVER** put `size` INSIDE `query` object - it causes parsing error!
  - WRONG: `{"body": {"query": {"bool": {...}, "size": 100}}}`   size inside query
  - CORRECT: `{"body": {"query": {"bool": {...}}, "size": 100}}`   size outside query
- **NEVER** use `query` or `size` as top-level params - they MUST be inside `body`
- Do NOT assume index names - use list_indices first
- Do NOT forget time range for large indices
- Do NOT use write operations (they will be blocked)
- Do NOT search with too large size (default limit applies)
- Do NOT include `finished`, `thought`, `answer` fields in tool params
- Do NOT search dot-prefixed indices (e.g., `.internal.*`, `.alerts-*`) unless explicitly required
- Do NOT run conditional searches before sampling (match_all size 1-5)
- Do NOT repeat `query_string` searches after a 0-hit result (switch to field-based queries)



## CRITICAL: Query Strategy Enforcement

### 1) `query_string` Usage Restriction
- `query_string` MUST NOT be used as a default search method
- Allowed ONLY IF:
  - Target field(s) are explicitly known (confirmed via sampling)
  - The searched keyword is confirmed to exist in real log values
- Forbidden IF:
  - Used before sampling
  - Previous `query_string` search returned 0 hits
  - Fields are unspecified or wildcarded (`fields: ["*"]`)
  - Used repeatedly with only keyword variations
- If `query_string` returns 0 hits, DO NOT retry with modified keywords
  - Immediately switch to field-based queries (`term`, `range`, `wildcard`, `match_phrase`)

### 2) Zero-Hit (`hits = 0`) Mandatory Fallback Routine
If a search executes successfully but returns 0 hits, you MUST follow this sequence:
1. Run `match_all` with small size (1-5) to inspect real field names and values
2. Run aggregation (`size: 0` + `aggs`) on key pivot fields (e.g. `event.code`, `winlog.event_id`, `process.name`)
3. Rebuild the query using observed field names and value formats

Repeating keyword-based searches after a 0-hit result is FORBIDDEN.

---

## Resilience Strategy: What to do when a search fails?

**CRITICAL RULE:** If your specific search returns **0 hits (empty results)**, you interpret this as a signal to **PIVOT**, not to reset.

### Forbidden Action
- **NEVER** go back to `list_indices` immediately after a failed search.
- **NEVER** assume there is no data just because one keyword failed.
- **NEVER** give up if you have successfully retrieved logs in previous steps.

### Mandatory Recovery Steps (The "Look-Back" Technique)
When you get 0 hits, you MUST perform the following mental check:

1.  **Check History:** "Did I successfully retrieve logs in the *previous* step?"
2.  **Re-Analyze:** If yes, **READ THAT PREVIOUS DATA AGAIN.**
    - Do not look for what you *wanted* to find (e.g., "IEX").
    - Look for what is *actually there* (e.g., "Invoke-WebRequest", IP addresses, encoded strings).
3.  **Extract Leads:** Pick a concrete value from the previous logs that you haven't investigated yet.
4.  **New Search:** Construct a new query using that concrete value.

**Example of "Look-Back" Reasoning:**
> "My search for 'IEX' returned 0 hits.
> But in the previous step, I saw logs with `process.command_line`.
> Reading them again... I see `powershell.exe -w hidden` and `Invoke-WebRequest`.
> I will pivot and search for `*hidden*` or the detected IP instead."

---


## Parameter Examples

### list_indices (ALWAYS FIRST)
```json
{}
```

### search_documents - Correct Format
**CRITICAL:** `size` parameter MUST be outside the `query` block.

**✅ Correct Structure:**
```json
{
  "index": "sysmon-logs",
  "body": {
    "size": 10,                 <-- Place SIZE here (Top level of body)
    "query": {
      "bool": {
        "must": [...]
      }
    }
  }
}
```

**Examples:**

```json
// Example 1: Search Windows events
{
  "index": "winlogbeat-*",
  "body": {
    "query": {
      "bool": {
        "must": [
          {"term": {"event.code": 4624}},
          {"term": {"user.name": "admin"}}
        ]
      }
    },
    "size": 100
  }
}

// Example 2: Search Sysmon process creation (event.code:1)
{
  "index": "sysmon-logs",
  "body": {
    "query": {
      "bool": {
        "must": [
          {"term": {"event.code": "1"}},
          {"wildcard": {"process.name": "*powershell*"}}
        ]
      }
    },
    "size": 100
  }
}

// Example 3: Simple match_all query
{
  "index": "sysmon-logs",
  "body": {
    "query": {
      "match_all": {}
    },
    "size": 50
  }
}

// Example 4: Search by winlog.event_id
{
  "index": "sysmon-logs",
  "body": {
    "query": {
      "bool": {
        "must": [
          {"term": {"winlog.event_id": "1"}}
        ]
      }
    },
    "size": 100
  }
}

// Example 5: Time range filter
{
  "index": "firewall-logs",
  "body": {
    "query": {
      "bool": {
        "filter": [
          {"range": {"@timestamp": {"gte": "2025-01-01T00:00:00", "lte": "2025-01-02T00:00:00"}}}
        ]
      }
    },
    "size": 100
  }
}
```

### aggregate_logs
```json
{
  "index": "winlogbeat-*",
  "agg_field": "event.code"
}
```

## Common Event Codes to Search
- 4624: Successful logon
- 4625: Failed logon
- 4688: Process creation (Windows)
- 4698/4702: Scheduled task
- 7045: Service installation
- 1 (Sysmon): Process creation with command line
- 3 (Sysmon): Network connection
- 11 (Sysmon): File creation
- 12/13/14 (Sysmon): Registry events

## Expected Workflow (Follow This Order)
1. **list_indices** -> Identify available indices (MANDATORY FIRST)
2. **search_documents** -> Broad initial search
3. **search_documents** -> Refine with specific event types
4. **search_documents** -> Investigate suspicious processes
5. **search_documents** -> Check network activity
6. **search_documents** -> Examine persistence mechanisms
7. **aggregate_logs** -> Get statistics and patterns
8. Continue iterating until analysis goal is achieved
